from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
import time
import urllib.parse
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from scripts import channel_oauth, channel_workspace


TokenProvider = Callable[..., str]
JsonFetcher = Callable[..., dict[str, Any]]
BinaryFetcher = Callable[..., bytes]

SCHEMA_VERSION = 1
SECRET_MARKERS = ("access_token", "refresh_token", "client_secret", "authorization", "bearer ")
REQUIRED_NORMALIZED_FILES = (
    "video_catalog.csv",
    "channel_daily.csv",
    "video_daily.csv",
    "traffic_source_daily.csv",
    "country_daily.csv",
    "country_summary.csv",
    "device_daily.csv",
    "subscriber_status_daily.csv",
    "reach_daily.csv",
    "retention.csv",
    "playlists_daily.csv",
)


class ChannelAnalyticsCollectorError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error(code: str, message: str, status: int = 400) -> ChannelAnalyticsCollectorError:
    return ChannelAnalyticsCollectorError(code, message, status)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _sanitize_text(value: str, *, root: Path | None = None) -> str:
    text = str(value or "")
    lowered = text.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        text = "Sanitized secret-sensitive error."
    if root is not None:
        try:
            text = text.replace(str(root.resolve()), "<repo-root>")
        except Exception:
            pass
    return text[:500]


def _sanitize_value(value: Any, *, root: Path | None = None) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if any(marker in key.lower() for marker in SECRET_MARKERS):
                continue
            clean[key] = _sanitize_value(item, root=root)
        return clean
    if isinstance(value, list):
        return [_sanitize_value(item, root=root) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value, root=root)
    return value


def _error_message(exc: Exception, *, root: Path) -> str:
    raw = getattr(exc, "message", None) or str(exc)
    return _sanitize_text(raw, root=root)


def _error_status(exc: Exception) -> int | None:
    status = getattr(exc, "status", None)
    return status if isinstance(status, int) else None


def _classify_group_error(exc: Exception, *, root: Path) -> tuple[str, str]:
    status = _error_status(exc)
    message = _error_message(exc, root=root)
    lowered = message.lower()
    if status == 401:
        return "UNAUTHORIZED", message
    if status == 403:
        if "permission" in lowered or "forbidden" in lowered or "authorized" in lowered:
            return "UNAUTHORIZED", message
        return "UNAVAILABLE", message
    if status == 404:
        return "UNSUPPORTED", message
    if "unsupported" in lowered or "unknown metric" in lowered or "unknown dimension" in lowered:
        return "UNSUPPORTED", message
    if "not available" in lowered or "unavailable" in lowered:
        return "UNAVAILABLE", message
    if "permission" in lowered or "authorized" in lowered:
        return "UNAUTHORIZED", message
    return "ERROR", message


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    _write_bytes_atomic(path, (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    with tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
        handle.seek(0)
        text = handle.read()
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _ensure_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _error("ANALYTICS_STATE_INVALID", f"Invalid JSON state file: {path.name}.", 500) from exc
    if not isinstance(value, dict):
        raise _error("ANALYTICS_STATE_INVALID", f"Invalid JSON state file: {path.name}.", 500)
    return value


def _analytics_paths(root: Path | str, channel_slug: str) -> dict[str, Path]:
    repo_root = Path(root).resolve()
    channel_paths = channel_workspace.canonical_channel_paths(repo_root, channel_slug)
    analytics_dir = channel_paths.channel_dir / "analytics"
    raw_reporting_dir = analytics_dir / "raw" / "reporting_api"
    normalized_dir = analytics_dir / "normalized"
    state_dir = analytics_dir / "state"
    return {
        "root": repo_root,
        "channel_dir": channel_paths.channel_dir,
        "analytics_dir": analytics_dir,
        "raw_reporting_dir": raw_reporting_dir,
        "normalized_dir": normalized_dir,
        "state_dir": state_dir,
        "collector_state": state_dir / "collector_state.json",
        "capability_snapshot": state_dir / "capability_snapshot.json",
    }


def _relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _normalized_table_specs() -> dict[str, dict[str, Any]]:
    return {
        "video_catalog.csv": {
            "columns": [
                "video_id",
                "title",
                "description",
                "published_at",
                "channel_id",
                "duration",
                "category_id",
                "tags",
                "live_broadcast_status",
                "caption_status",
                "privacy_status",
                "upload_status",
                "license",
                "embeddable",
                "made_for_kids",
                "public_stats_viewable",
                "view_count",
                "like_count",
                "comment_count",
            ],
            "key_columns": ["video_id"],
        },
        "channel_daily.csv": {
            "columns": ["day", "views", "estimated_minutes_watched", "average_view_duration", "average_view_percentage", "likes", "comments", "shares", "subscribers_gained", "subscribers_lost"],
            "key_columns": ["day"],
        },
        "video_daily.csv": {
            "columns": ["day", "video_id", "views", "estimated_minutes_watched", "average_view_duration", "average_view_percentage", "likes", "comments", "shares"],
            "key_columns": ["day", "video_id"],
        },
        "traffic_source_daily.csv": {
            "columns": ["day", "traffic_source", "views", "estimated_minutes_watched"],
            "key_columns": ["day", "traffic_source"],
        },
        "country_daily.csv": {
            "columns": ["day", "country", "views", "estimated_minutes_watched"],
            "key_columns": ["day", "country"],
        },
        "country_summary.csv": {
            "columns": ["country", "views", "estimated_minutes_watched"],
            "key_columns": ["country"],
        },
        "device_daily.csv": {
            "columns": ["day", "device_type", "operating_system", "views", "estimated_minutes_watched"],
            "key_columns": ["day", "device_type", "operating_system"],
        },
        "subscriber_status_daily.csv": {
            "columns": ["day", "subscriber_status", "views", "estimated_minutes_watched"],
            "key_columns": ["day", "subscriber_status"],
        },
        "reach_daily.csv": {
            "columns": ["day", "impressions", "impressions_ctr"],
            "key_columns": ["day"],
        },
        "retention.csv": {
            "columns": ["video_id", "elapsed_video_time_ratio", "audience_watch_ratio", "relative_retention_performance"],
            "key_columns": ["video_id", "elapsed_video_time_ratio"],
        },
        "playlists_daily.csv": {
            "columns": ["day", "playlist_id", "views", "estimated_minutes_watched"],
            "key_columns": ["day", "playlist_id"],
        },
        "playback_location_daily.csv": {
            "columns": ["day", "playback_location", "views", "estimated_minutes_watched"],
            "key_columns": ["day", "playback_location"],
        },
        "engagement_daily.csv": {
            "columns": ["day", "likes", "comments", "shares"],
            "key_columns": ["day"],
        },
        "cards_daily.csv": {
            "columns": ["day", "card_impressions", "card_teaser_impressions"],
            "key_columns": ["day"],
        },
        "end_screens_daily.csv": {
            "columns": ["day", "end_screen_element_impressions", "end_screen_element_clicks"],
            "key_columns": ["day"],
        },
        "monetary_daily.csv": {
            "columns": ["day", "estimated_revenue", "gross_revenue", "cpm"],
            "key_columns": ["day"],
        },
    }


TARGETED_QUERY_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "group_id": "channel_daily",
        "filename": "channel_daily.csv",
        "dimensions": "day",
        "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,subscribersLost",
        "mapping": {
            "day": "day",
            "views": "views",
            "estimatedMinutesWatched": "estimated_minutes_watched",
            "averageViewDuration": "average_view_duration",
            "averageViewPercentage": "average_view_percentage",
            "likes": "likes",
            "comments": "comments",
            "shares": "shares",
            "subscribersGained": "subscribers_gained",
            "subscribersLost": "subscribers_lost",
        },
    },
    {
        "group_id": "video_daily",
        "filename": "video_daily.csv",
        "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares",
        "mapping": {
            "day": "day",
            "video": "video_id",
            "views": "views",
            "estimatedMinutesWatched": "estimated_minutes_watched",
            "averageViewDuration": "average_view_duration",
            "averageViewPercentage": "average_view_percentage",
            "likes": "likes",
            "comments": "comments",
            "shares": "shares",
        },
    },
    {
        "group_id": "traffic_source_daily",
        "filename": "traffic_source_daily.csv",
        "dimensions": "day,insightTrafficSourceType",
        "metrics": "views,estimatedMinutesWatched",
        "mapping": {
            "day": "day",
            "insightTrafficSourceType": "traffic_source",
            "views": "views",
            "estimatedMinutesWatched": "estimated_minutes_watched",
        },
    },
    {
        "group_id": "country_summary",
        "filename": "country_summary.csv",
        "dimensions": "country",
        "metrics": "views,estimatedMinutesWatched",
        "mapping": {
            "country": "country",
            "views": "views",
            "estimatedMinutesWatched": "estimated_minutes_watched",
        },
    },
    {
        "group_id": "device_daily",
        "filename": "device_daily.csv",
        "dimensions": "day,deviceType,operatingSystem",
        "metrics": "views,estimatedMinutesWatched",
        "mapping": {
            "day": "day",
            "deviceType": "device_type",
            "operatingSystem": "operating_system",
            "views": "views",
            "estimatedMinutesWatched": "estimated_minutes_watched",
        },
    },
    {
        "group_id": "subscriber_status_daily",
        "filename": "subscriber_status_daily.csv",
        "dimensions": "day,subscribedStatus",
        "metrics": "views,estimatedMinutesWatched",
        "mapping": {
            "day": "day",
            "subscribedStatus": "subscriber_status",
            "views": "views",
            "estimatedMinutesWatched": "estimated_minutes_watched",
        },
    },
    {
        "group_id": "playback_location_daily",
        "filename": "playback_location_daily.csv",
        "dimensions": "day,insightPlaybackLocationType",
        "metrics": "views,estimatedMinutesWatched",
        "mapping": {
            "day": "day",
            "insightPlaybackLocationType": "playback_location",
            "views": "views",
            "estimatedMinutesWatched": "estimated_minutes_watched",
        },
    },
    {
        "group_id": "engagement",
        "filename": "engagement_daily.csv",
        "dimensions": "day",
        "metrics": "likes,comments,shares",
        "mapping": {
            "day": "day",
            "likes": "likes",
            "comments": "comments",
            "shares": "shares",
        },
    },
    {
        "group_id": "cards_daily",
        "filename": "cards_daily.csv",
        "dimensions": "day",
        "metrics": "cardImpressions,cardTeaserImpressions",
        "mapping": {
            "day": "day",
            "cardImpressions": "card_impressions",
            "cardTeaserImpressions": "card_teaser_impressions",
        },
    },
    {
        "group_id": "playlists_daily",
        "filename": "playlists_daily.csv",
        "metrics": "views,estimatedMinutesWatched",
        "mapping": {
            "day": "day",
            "views": "views",
            "estimatedMinutesWatched": "estimated_minutes_watched",
        },
    },
    {
        "group_id": "retention",
        "filename": "retention.csv",
        "metrics": "audienceWatchRatio,relativeRetentionPerformance",
        "mapping": {
            "elapsedVideoTimeRatio": "elapsed_video_time_ratio",
            "audienceWatchRatio": "audience_watch_ratio",
            "relativeRetentionPerformance": "relative_retention_performance",
        },
    },
    {
        "group_id": "monetary_daily",
        "filename": "monetary_daily.csv",
        "dimensions": "day",
        "metrics": "estimatedRevenue,grossRevenue,cpm",
        "mapping": {
            "day": "day",
            "estimatedRevenue": "estimated_revenue",
            "grossRevenue": "gross_revenue",
            "cpm": "cpm",
        },
    },
)


def _dedupe_rows(rows: list[dict[str, Any]], key_columns: list[str]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(str(row.get(column, "")) for column in key_columns)
        unique[key] = row
    return [unique[key] for key in sorted(unique)]


def _normalize_query_payload(payload: dict[str, Any], mapping: dict[str, str], columns: list[str]) -> list[dict[str, Any]]:
    headers = [header.get("name", "") for header in payload.get("columnHeaders", []) if isinstance(header, dict)]
    normalized: list[dict[str, Any]] = []
    for values in payload.get("rows", []) or []:
        source_row = dict(zip(headers, values))
        row = {column: "" for column in columns}
        for source_name, target_name in mapping.items():
            row[target_name] = source_row.get(source_name, "")
        normalized.append(row)
    return normalized


def _csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def _page_through_analytics_query(
    *,
    repo_root: Path,
    channel_slug: str,
    access_token: str,
    analytics_query_fetcher: JsonFetcher,
    params: dict[str, str],
) -> dict[str, Any]:
    headers: list[dict[str, Any]] = []
    rows: list[list[Any]] = []
    page_token = ""
    while True:
        page_params = dict(params)
        if page_token:
            page_params["startIndex"] = page_token
        payload = analytics_query_fetcher(
            root=repo_root,
            channel_slug=channel_slug,
            access_token=access_token,
            params=page_params,
        )
        if not headers:
            headers = [item for item in payload.get("columnHeaders", []) if isinstance(item, dict)]
        rows.extend(payload.get("rows", []) or [])
        next_token = payload.get("nextPageToken")
        if next_token:
            page_token = str(next_token)
            continue
        page_info = payload.get("pageInfo", {}) if isinstance(payload.get("pageInfo"), dict) else {}
        total_results = page_info.get("totalResults")
        start_index = int(page_params.get("startIndex", "1"))
        max_results = int(page_params.get("maxResults", "200"))
        if isinstance(total_results, int) and start_index + max_results <= total_results:
            page_token = str(start_index + max_results)
            continue
        break
    return {"columnHeaders": headers, "rows": rows}


def _video_catalog_row(video: dict[str, Any]) -> dict[str, Any]:
    snippet = video.get("snippet", {}) or {}
    content_details = video.get("contentDetails", {}) or {}
    statistics = video.get("statistics", {}) or {}
    status = video.get("status", {}) or {}
    tags = snippet.get("tags") or []
    return {
        "video_id": video.get("id", ""),
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "published_at": snippet.get("publishedAt", ""),
        "channel_id": snippet.get("channelId", ""),
        "duration": content_details.get("duration", ""),
        "category_id": snippet.get("categoryId", ""),
        "tags": "|".join(str(tag) for tag in tags),
        "live_broadcast_status": snippet.get("liveBroadcastContent", ""),
        "caption_status": content_details.get("caption", ""),
        "privacy_status": status.get("privacyStatus", ""),
        "upload_status": status.get("uploadStatus", ""),
        "license": status.get("license", ""),
        "embeddable": status.get("embeddable", ""),
        "made_for_kids": status.get("madeForKids", ""),
        "public_stats_viewable": status.get("publicStatsViewable", ""),
        "view_count": statistics.get("viewCount", ""),
        "like_count": statistics.get("likeCount", ""),
        "comment_count": statistics.get("commentCount", ""),
    }


def _fetch_all_video_catalog(
    *,
    root: Path,
    channel_slug: str,
    access_token: str,
    channel: dict[str, Any],
    data_api_fetcher: JsonFetcher,
) -> list[dict[str, Any]]:
    channel_payload = data_api_fetcher(
        root=root,
        channel_slug=channel_slug,
        access_token=access_token,
        path="channels",
        params={"part": "contentDetails", "id": channel["youtube_channel_id"]},
    )
    items = channel_payload.get("items", [])
    if not items:
        raise _error("ANALYTICS_CHANNEL_NOT_FOUND", "No uploads playlist found for the selected channel.", 404)
    uploads = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads:
        raise _error("ANALYTICS_CHANNEL_NOT_FOUND", "Selected channel has no uploads playlist.", 404)

    video_ids: list[str] = []
    page_token = ""
    while True:
        params = {"part": "contentDetails", "playlistId": uploads, "maxResults": "50"}
        if page_token:
            params["pageToken"] = page_token
        playlist_payload = data_api_fetcher(
            root=root,
            channel_slug=channel_slug,
            access_token=access_token,
            path="playlistItems",
            params=params,
        )
        for item in playlist_payload.get("items", []) or []:
            video_id = item.get("contentDetails", {}).get("videoId")
            if isinstance(video_id, str) and video_id:
                video_ids.append(video_id)
        page_token = str(playlist_payload.get("nextPageToken", "") or "")
        if not page_token:
            break

    seen: set[str] = set()
    ordered_ids: list[str] = []
    for video_id in video_ids:
        if video_id not in seen:
            seen.add(video_id)
            ordered_ids.append(video_id)

    videos: list[dict[str, Any]] = []
    for start in range(0, len(ordered_ids), 50):
        chunk = ordered_ids[start:start + 50]
        payload = data_api_fetcher(
            root=root,
            channel_slug=channel_slug,
            access_token=access_token,
            path="videos",
            params={"part": "snippet,contentDetails,statistics,status", "id": ",".join(chunk), "maxResults": str(len(chunk))},
        )
        videos.extend(item for item in payload.get("items", []) or [] if isinstance(item, dict))

    by_id = {item.get("id"): item for item in videos if isinstance(item.get("id"), str)}
    return [by_id[video_id] for video_id in ordered_ids if video_id in by_id]


def _initial_collector_state(channel_slug: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "channel_slug": channel_slug,
        "last_attempt_at": None,
        "last_completed_sync_at": None,
        "last_successful_sync_at": None,
        "collection_window": {},
        "source_results": {},
        "query_group_results": {},
        "report_jobs": {},
        "ingested_reports": {},
        "row_counts": {},
        "report_type_counts": {"AVAILABLE": 0, "PENDING": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "UNAVAILABLE": 0, "ERROR": 0},
        "generated_report_counts": {"READY": 0, "PENDING": 0, "UNAVAILABLE": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "ERROR": 0},
        "errors": [],
    }


def _load_collector_state(paths: dict[str, Path], channel_slug: str) -> dict[str, Any]:
    payload = _ensure_json_dict(paths["collector_state"])
    if not payload:
        return _initial_collector_state(channel_slug)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("channel_slug", channel_slug)
    payload.setdefault("last_attempt_at", None)
    payload.setdefault("last_completed_sync_at", None)
    payload.setdefault("last_successful_sync_at", None)
    payload.setdefault("collection_window", {})
    payload.setdefault("source_results", {})
    payload.setdefault("query_group_results", {})
    payload.setdefault("report_jobs", {})
    payload.setdefault("ingested_reports", {})
    payload.setdefault("row_counts", {})
    payload.setdefault("report_type_counts", {"AVAILABLE": 0, "PENDING": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "UNAVAILABLE": 0, "ERROR": 0})
    payload.setdefault("generated_report_counts", {"READY": 0, "PENDING": 0, "UNAVAILABLE": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "ERROR": 0})
    payload.setdefault("errors", [])
    return payload


def _read_capability_snapshot(paths: dict[str, Path], channel_slug: str) -> dict[str, Any]:
    payload = _ensure_json_dict(paths["capability_snapshot"])
    if not payload:
        return {
            "schema_version": SCHEMA_VERSION,
            "channel_slug": channel_slug,
            "discovered_at": None,
            "capabilities": [],
            "report_type_counts": {"AVAILABLE": 0, "PENDING": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "UNAVAILABLE": 0, "ERROR": 0},
            "generated_report_counts": {"READY": 0, "PENDING": 0, "UNAVAILABLE": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "ERROR": 0},
        }
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("channel_slug", channel_slug)
    payload.setdefault("discovered_at", None)
    payload.setdefault("capabilities", [])
    payload.setdefault("report_type_counts", _build_capability_counts(payload.get("capabilities", [])))
    payload.setdefault("generated_report_counts", _build_report_readiness_counts(payload.get("capabilities", [])))
    return payload


def _annotate_capability_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    capabilities = snapshot.get("capabilities", []) if isinstance(snapshot.get("capabilities"), list) else []
    snapshot["report_type_counts"] = _build_capability_counts(capabilities)
    snapshot["generated_report_counts"] = _build_report_readiness_counts(capabilities)
    return snapshot


def discover_channel_analytics_capabilities(
    root: Path | str,
    channel_slug: str,
    *,
    token_provider: TokenProvider,
    reporting_api_fetcher: JsonFetcher,
) -> dict[str, Any]:
    repo_root = Path(root).resolve()
    channel = channel_workspace.load_channel(repo_root, channel_slug)
    paths = _analytics_paths(repo_root, channel_slug)
    state = _load_collector_state(paths, channel_slug)
    now = utc_now_iso()
    state["last_attempt_at"] = now
    try:
        access_token = token_provider(repo_root, channel_slug)
    except channel_oauth.OAuthServiceError as exc:
        message = _error_message(exc, root=repo_root)
        state["source_results"]["capability_discovery"] = {"status": "UNAUTHORIZED", "checked_at": now, "message": message}
        state["errors"] = [message]
        _write_json_atomic(paths["collector_state"], _sanitize_value(state, root=repo_root))
        raise _error("OAUTH_RECONNECT_REQUIRED", message, 409) from exc

    try:
        payload = reporting_api_fetcher(
            root=repo_root,
            channel_slug=channel_slug,
            access_token=access_token,
            method="GET",
            path="reportTypes",
            params={"includeSystemManaged": "true"},
            payload=None,
        )
        capabilities = []
        for item in payload.get("reportTypes", []) or []:
            capabilities.append(
                {
                    "report_type_id": item.get("id", ""),
                    "display_name": item.get("name", ""),
                    "system_managed": bool(item.get("systemManaged")),
                    "status": "AVAILABLE",
                    "availability_status": "AVAILABLE",
                    "discovered_at": now,
                }
            )
        snapshot = _annotate_capability_snapshot({
            "schema_version": SCHEMA_VERSION,
            "channel_slug": channel_slug,
            "youtube_channel_id": channel["youtube_channel_id"],
            "discovered_at": now,
            "capabilities": capabilities,
        })
        state["source_results"]["capability_discovery"] = {
            "status": "SUCCESS",
            "checked_at": now,
            "discovered_count": len(capabilities),
        }
        state["errors"] = []
        _write_json_atomic(paths["capability_snapshot"], _sanitize_value(snapshot, root=repo_root))
        _write_json_atomic(paths["collector_state"], _sanitize_value(state, root=repo_root))
        return snapshot
    except Exception as exc:
        status, message = _classify_group_error(exc, root=repo_root)
        state["source_results"]["capability_discovery"] = {"status": status, "checked_at": now, "message": message}
        state["errors"] = [message]
        _write_json_atomic(paths["collector_state"], _sanitize_value(state, root=repo_root))
        raise _error("ANALYTICS_CAPABILITY_DISCOVERY_FAILED", message, 400 if status == "ERROR" else 409) from exc


def _ingested_identity(job_id: str, report_id: str) -> str:
    return f"{job_id}:{report_id}"


def _stored_reporting_filename(job_id: str, report_id: str, source_filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", source_filename or "report.csv").strip("_") or "report.csv"
    return f"{job_id}__{report_id}__{cleaned}"


def _download_reporting_reports(
    *,
    repo_root: Path,
    channel_slug: str,
    access_token: str,
    paths: dict[str, Path],
    state: dict[str, Any],
    capabilities: list[dict[str, Any]],
    reporting_api_fetcher: JsonFetcher,
    report_download_fetcher: BinaryFetcher,
    now: str,
) -> dict[str, Any]:
    source_result = {
        "status": "SUCCESS",
        "checked_at": now,
        "discovered_report_types": len(capabilities),
        "jobs_total": 0,
        "reports_downloaded": 0,
        "reports_skipped": 0,
        "reports_ready": 0,
        "reports_pending": 0,
        "reports_error": 0,
        "message": "",
    }
    report_jobs: dict[str, Any] = {}
    ingested_reports = dict(state.get("ingested_reports", {}))
    pending_writes: list[tuple[Path, bytes]] = []

    try:
        jobs_payload = reporting_api_fetcher(
            root=repo_root,
            channel_slug=channel_slug,
            access_token=access_token,
            method="GET",
            path="jobs",
            params={"includeSystemManaged": "true"},
            payload=None,
        )
        jobs = [item for item in jobs_payload.get("jobs", []) or [] if isinstance(item, dict)]
    except Exception as exc:
        status, message = _classify_group_error(exc, root=repo_root)
        state["source_results"]["reporting_api"] = {"status": status, "checked_at": now, "message": message}
        return state["source_results"]["reporting_api"]

    jobs_by_report_type: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        report_type_id = str(job.get("reportTypeId", "") or "")
        jobs_by_report_type.setdefault(report_type_id, []).append(job)

    for capability in capabilities:
        report_type_id = capability.get("report_type_id", "")
        system_managed = bool(capability.get("system_managed"))
        jobs_for_type = list(jobs_by_report_type.get(report_type_id, []))
        readiness_status = "PENDING"
        readiness_message = ""
        generated_report_count = 0
        if not jobs_for_type:
            readiness_status = "PENDING" if system_managed else "UNAVAILABLE"
            readiness_message = "System-managed report type discovered with no visible job yet." if system_managed else "No existing Reporting API job is visible for this report type."

        report_jobs[report_type_id] = []
        for job in jobs_for_type:
            job_id = str(job.get("id", "") or "")
            job_status = "PENDING"
            job_message = ""
            job_generated_report_count = 0
            if not job_id:
                report_jobs[report_type_id].append(
                    {
                        "job_id": job_id,
                        "report_type_id": report_type_id,
                        "name": job.get("name", ""),
                        "system_managed": bool(job.get("systemManaged")),
                        "create_time": job.get("createTime"),
                        "expire_time": job.get("expireTime"),
                        "status": job_status,
                    }
                )
                continue
            try:
                reports_payload = reporting_api_fetcher(
                    root=repo_root,
                    channel_slug=channel_slug,
                    access_token=access_token,
                    method="GET",
                    path=f"jobs/{job_id}/reports",
                    params=None,
                    payload=None,
                )
                reports = [item for item in reports_payload.get("reports", []) or [] if isinstance(item, dict)]
            except Exception as exc:
                job_status, job_message = _classify_group_error(exc, root=repo_root)
                readiness_status = _merge_generated_report_status(readiness_status, job_status)
                if not readiness_message:
                    readiness_message = job_message
                report_jobs[report_type_id].append(
                    {
                        "job_id": job_id,
                        "report_type_id": report_type_id,
                        "name": job.get("name", ""),
                        "system_managed": bool(job.get("systemManaged")),
                        "create_time": job.get("createTime"),
                        "expire_time": job.get("expireTime"),
                        "status": job_status,
                        "message": job_message,
                    }
                )
                continue
            if not reports:
                job_status = "PENDING"
                job_message = "No generated reports are available yet."
            for report in reports:
                report_id = str(report.get("id", "") or "")
                if not report_id:
                    continue
                job_generated_report_count += 1
                generated_report_count += 1
                identity = _ingested_identity(job_id, report_id)
                download_url = str(report.get("downloadUrl", "") or "")
                source_filename = str(report.get("jobReportTypeId", "") or report.get("createTime", "") or "report.csv")
                stored_filename = _stored_reporting_filename(job_id, report_id, source_filename)
                stored_path = paths["raw_reporting_dir"] / stored_filename
                if identity in ingested_reports and stored_path.exists():
                    source_result["reports_skipped"] += 1
                    continue
                if not download_url:
                    continue
                try:
                    raw_bytes = report_download_fetcher(
                        root=repo_root,
                        channel_slug=channel_slug,
                        access_token=access_token,
                        url=download_url,
                    )
                except Exception as exc:
                    job_status, job_message = _classify_group_error(exc, root=repo_root)
                    continue
                pending_writes.append((stored_path, raw_bytes))
                ingested_reports[identity] = {
                    "report_id": report_id,
                    "job_id": job_id,
                    "report_type_id": report_type_id,
                    "downloaded_at": now,
                    "sha256": _sha256_bytes(raw_bytes),
                    "source_filename": source_filename,
                    "stored_filename": stored_filename,
                    "relative_path": _relative_to_root(repo_root, stored_path),
                    "start_time": report.get("startTime"),
                    "end_time": report.get("endTime"),
                }
                source_result["reports_downloaded"] += 1

            if job_generated_report_count > 0 and job_status in {"READY", "PENDING"}:
                job_status = "READY"
                job_message = ""
            report_jobs[report_type_id].append(
                {
                    "job_id": job_id,
                    "report_type_id": report_type_id,
                    "name": job.get("name", ""),
                    "system_managed": bool(job.get("systemManaged")),
                    "create_time": job.get("createTime"),
                    "expire_time": job.get("expireTime"),
                    "status": job_status,
                    "generated_report_count": job_generated_report_count,
                    **({"message": job_message} if job_message else {}),
                }
            )
            readiness_status = _merge_generated_report_status(readiness_status, job_status)
            if job_message and readiness_status != "READY" and not readiness_message:
                readiness_message = job_message

        if generated_report_count > 0 and readiness_status in {"READY", "PENDING"}:
            readiness_status = "READY"
            readiness_message = ""
        capability["availability_status"] = "AVAILABLE"
        capability["job_count"] = len(jobs_for_type)
        capability["generated_report_count"] = generated_report_count
        capability["generated_report_status"] = readiness_status
        if readiness_message:
            capability["generated_report_message"] = readiness_message
        if readiness_status == "READY":
            source_result["reports_ready"] += 1
        elif readiness_status == "PENDING":
            source_result["reports_pending"] += 1
        elif readiness_status == "ERROR":
            source_result["reports_error"] += 1

    for stored_path, raw_bytes in pending_writes:
        if stored_path.exists():
            continue
        _write_bytes_atomic(stored_path, raw_bytes)

    source_result["jobs_total"] = sum(len(items) for items in report_jobs.values())
    if source_result["reports_error"]:
        successful_reporting = source_result["reports_ready"] or source_result["reports_pending"] or source_result["reports_downloaded"] or source_result["reports_skipped"]
        source_result["status"] = "PARTIAL" if successful_reporting else "ERROR"
    state["report_jobs"] = report_jobs
    state["ingested_reports"] = ingested_reports
    state["source_results"]["reporting_api"] = source_result
    return source_result


def _window_bounds(window_days: int) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=window_days)
    return start.isoformat(), end.isoformat()


def _query_params_for_group(group: dict[str, Any], *, start_date: str, end_date: str) -> dict[str, str]:
    return {
        "ids": "channel==MINE",
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": group["dimensions"],
        "metrics": group["metrics"],
        "maxResults": "200",
    }


def _filter_pagination_params(base_params: dict[str, str], page_start: int) -> dict[str, str]:
    params = dict(base_params)
    params["startIndex"] = str(page_start)
    return params


def _run_basic_group(
    *,
    repo_root: Path,
    channel_slug: str,
    access_token: str,
    analytics_query_fetcher: JsonFetcher,
    group: dict[str, Any],
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    filename = group["filename"]
    columns = _normalized_table_specs()[filename]["columns"]
    params = _query_params_for_group(group, start_date=start_date, end_date=end_date)
    payload = _page_through_analytics_query(
        repo_root=repo_root,
        channel_slug=channel_slug,
        access_token=access_token,
        analytics_query_fetcher=analytics_query_fetcher,
        params=params,
    )
    rows = _normalize_query_payload(payload, group["mapping"], columns)
    deduped = _dedupe_rows(rows, _normalized_table_specs()[filename]["key_columns"])
    return (
        {
            "status": "SUCCESS" if deduped else "EMPTY",
            "row_count": len(deduped),
            "filename": filename,
            "params": _sanitize_value(params, root=repo_root),
        },
        deduped,
    )


def _run_video_daily_group(
    *,
    repo_root: Path,
    channel_slug: str,
    access_token: str,
    analytics_query_fetcher: JsonFetcher,
    start_date: str,
    end_date: str,
    video_ids: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    group = next(item for item in TARGETED_QUERY_GROUPS if item["group_id"] == "video_daily")
    filename = group["filename"]
    columns = _normalized_table_specs()[filename]["columns"]
    if not video_ids:
        return ({"status": "EMPTY", "row_count": 0, "filename": filename, "params": {}}, [])
    all_rows: list[dict[str, Any]] = []
    executed_filters: list[str] = []
    for start in range(0, len(video_ids), 500):
        chunk = video_ids[start:start + 500]
        params = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": "day,video",
            "metrics": group["metrics"],
            "filters": "video==" + ",".join(chunk),
            "maxResults": "200",
        }
        payload = _page_through_analytics_query(
            repo_root=repo_root,
            channel_slug=channel_slug,
            access_token=access_token,
            analytics_query_fetcher=analytics_query_fetcher,
            params=params,
        )
        executed_filters.append(params["filters"])
        all_rows.extend(_normalize_query_payload(payload, group["mapping"], columns))
    deduped = _dedupe_rows(all_rows, _normalized_table_specs()[filename]["key_columns"])
    return (
        {
            "status": "SUCCESS" if deduped else "EMPTY",
            "row_count": len(deduped),
            "filename": filename,
            "params": {"filters": executed_filters, "dimensions": "day,video"},
        },
        deduped,
    )


def _run_subscriber_status_group(
    *,
    repo_root: Path,
    channel_slug: str,
    access_token: str,
    analytics_query_fetcher: JsonFetcher,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    group = next(item for item in TARGETED_QUERY_GROUPS if item["group_id"] == "subscriber_status_daily")
    try:
        return _run_basic_group(
            repo_root=repo_root,
            channel_slug=channel_slug,
            access_token=access_token,
            analytics_query_fetcher=analytics_query_fetcher,
            group=group,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        status = _error_status(exc)
        message = _error_message(exc, root=repo_root).lower()
        should_retry = status is not None and status >= 500 or "internal" in message or "backend error" in message
        if not should_retry:
            raise
        time.sleep(0.05)
        return _run_basic_group(
            repo_root=repo_root,
            channel_slug=channel_slug,
            access_token=access_token,
            analytics_query_fetcher=analytics_query_fetcher,
            group=group,
            start_date=start_date,
            end_date=end_date,
        )


def _discover_channel_playlist_ids(
    *,
    repo_root: Path,
    channel_slug: str,
    access_token: str,
    channel: dict[str, Any],
    data_api_fetcher: JsonFetcher,
) -> list[str]:
    page_token = ""
    playlist_ids: list[str] = []
    while True:
        params = {
            "part": "id",
            "channelId": channel["youtube_channel_id"],
            "maxResults": "50",
        }
        if page_token:
            params["pageToken"] = page_token
        payload = data_api_fetcher(
            root=repo_root,
            channel_slug=channel_slug,
            access_token=access_token,
            path="playlists",
            params=params,
        )
        for item in payload.get("items", []) or []:
            playlist_id = item.get("id")
            if isinstance(playlist_id, str) and playlist_id:
                playlist_ids.append(playlist_id)
        page_token = str(payload.get("nextPageToken", "") or "")
        if not page_token:
            break
    return sorted(set(playlist_ids))


def _run_playlists_group(
    *,
    repo_root: Path,
    channel_slug: str,
    access_token: str,
    analytics_query_fetcher: JsonFetcher,
    data_api_fetcher: JsonFetcher,
    channel: dict[str, Any],
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    group = next(item for item in TARGETED_QUERY_GROUPS if item["group_id"] == "playlists_daily")
    filename = group["filename"]
    columns = _normalized_table_specs()[filename]["columns"]
    playlist_ids = _discover_channel_playlist_ids(
        repo_root=repo_root,
        channel_slug=channel_slug,
        access_token=access_token,
        channel=channel,
        data_api_fetcher=data_api_fetcher,
    )
    if not playlist_ids:
        return (
            {"status": "EMPTY", "row_count": 0, "filename": filename, "params": {"playlist_ids": []}},
            [],
        )
    rows: list[dict[str, Any]] = []
    for playlist_id in playlist_ids:
        params = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": "day",
            "metrics": group["metrics"],
            "filters": f"playlist=={playlist_id}",
            "maxResults": "200",
        }
        payload = _page_through_analytics_query(
            repo_root=repo_root,
            channel_slug=channel_slug,
            access_token=access_token,
            analytics_query_fetcher=analytics_query_fetcher,
            params=params,
        )
        for row in _normalize_query_payload(payload, group["mapping"], columns):
            row["playlist_id"] = playlist_id
            rows.append(row)
    deduped = _dedupe_rows(rows, _normalized_table_specs()[filename]["key_columns"])
    return (
        {"status": "SUCCESS" if deduped else "EMPTY", "row_count": len(deduped), "filename": filename, "params": {"playlist_ids": playlist_ids}},
        deduped,
    )


def _run_retention_group(
    *,
    repo_root: Path,
    channel_slug: str,
    access_token: str,
    analytics_query_fetcher: JsonFetcher,
    start_date: str,
    end_date: str,
    video_ids: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    group = next(item for item in TARGETED_QUERY_GROUPS if item["group_id"] == "retention")
    filename = group["filename"]
    columns = _normalized_table_specs()[filename]["columns"]
    all_rows: list[dict[str, Any]] = []
    failures: list[str] = []
    success_count = 0
    for video_id in video_ids:
        params = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": "elapsedVideoTimeRatio",
            "filters": f"video=={video_id}",
            "metrics": group["metrics"],
            "maxResults": "200",
        }
        try:
            payload = _page_through_analytics_query(
                repo_root=repo_root,
                channel_slug=channel_slug,
                access_token=access_token,
                analytics_query_fetcher=analytics_query_fetcher,
                params=params,
            )
            rows = _normalize_query_payload(payload, group["mapping"], columns)
            for row in rows:
                row["video_id"] = video_id
                all_rows.append(row)
            if rows:
                success_count += 1
        except Exception as exc:
            failures.append(f"{video_id}: {_error_message(exc, root=repo_root)}")
    deduped = _dedupe_rows(all_rows, _normalized_table_specs()[filename]["key_columns"])
    if deduped:
        status = "SUCCESS"
    elif failures:
        status = "ERROR"
    else:
        status = "EMPTY"
    result = {
        "status": status,
        "row_count": len(deduped),
        "filename": filename,
        "params": {"video_count": len(video_ids), "successful_videos": success_count, "failed_videos": len(failures)},
    }
    if failures:
        result["message"] = " | ".join(failures[:10])
    return result, deduped


def _bulk_pending_result(
    *,
    group_id: str,
    filename: str,
    message: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return (
        {
            "status": "UNAVAILABLE",
            "row_count": 0,
            "filename": filename,
            "message": message,
        },
        [],
    )


def _matching_report_jobs(report_jobs: dict[str, Any], pattern: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for report_type_id, jobs in report_jobs.items():
        if pattern not in report_type_id:
            continue
        matches.extend(jobs if isinstance(jobs, list) else [])
    return matches


def _merge_generated_report_status(current: str, candidate: str) -> str:
    priority = {
        "READY": 5,
        "ERROR": 4,
        "UNAUTHORIZED": 3,
        "UNSUPPORTED": 2,
        "UNAVAILABLE": 1,
        "PENDING": 0,
    }
    current_value = priority.get(str(current or "PENDING").upper(), 0)
    candidate_value = priority.get(str(candidate or "PENDING").upper(), 0)
    return str(current if current_value >= candidate_value else candidate).upper()


def _run_query_groups(
    *,
    repo_root: Path,
    channel_slug: str,
    access_token: str,
    analytics_query_fetcher: JsonFetcher,
    data_api_fetcher: JsonFetcher,
    channel: dict[str, Any],
    window_days: int,
    canonical_video_ids: list[str],
    report_jobs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    start_date, end_date = _window_bounds(window_days)
    results: dict[str, Any] = {}
    table_rows: dict[str, list[dict[str, Any]]] = {}

    basic_group_ids = {"channel_daily", "traffic_source_daily", "device_daily", "playback_location_daily", "engagement", "monetary_daily"}
    for group in TARGETED_QUERY_GROUPS:
        group_id = group["group_id"]
        try:
            if group_id in basic_group_ids:
                result, rows = _run_basic_group(
                    repo_root=repo_root,
                    channel_slug=channel_slug,
                    access_token=access_token,
                    analytics_query_fetcher=analytics_query_fetcher,
                    group=group,
                    start_date=start_date,
                    end_date=end_date,
                )
            elif group_id == "video_daily":
                result, rows = _run_video_daily_group(
                    repo_root=repo_root,
                    channel_slug=channel_slug,
                    access_token=access_token,
                    analytics_query_fetcher=analytics_query_fetcher,
                    start_date=start_date,
                    end_date=end_date,
                    video_ids=canonical_video_ids,
                )
            elif group_id == "country_summary":
                result, rows = _run_basic_group(
                    repo_root=repo_root,
                    channel_slug=channel_slug,
                    access_token=access_token,
                    analytics_query_fetcher=analytics_query_fetcher,
                    group=group,
                    start_date=start_date,
                    end_date=end_date,
                )
                bulk_result, bulk_rows = _bulk_pending_result(
                    group_id="country_daily_bulk",
                    filename="country_daily.csv",
                    message="Country daily remains pending until Reporting API bulk reports are generated.",
                )
                results["country_daily_bulk"] = bulk_result
                table_rows["country_daily.csv"] = bulk_rows
            elif group_id == "subscriber_status_daily":
                result, rows = _run_subscriber_status_group(
                    repo_root=repo_root,
                    channel_slug=channel_slug,
                    access_token=access_token,
                    analytics_query_fetcher=analytics_query_fetcher,
                    start_date=start_date,
                    end_date=end_date,
                )
            elif group_id == "cards_daily":
                try:
                    result, rows = _run_basic_group(
                        repo_root=repo_root,
                        channel_slug=channel_slug,
                        access_token=access_token,
                        analytics_query_fetcher=analytics_query_fetcher,
                        group=group,
                        start_date=start_date,
                        end_date=end_date,
                    )
                except Exception as exc:
                    status, message = _classify_group_error(exc, root=repo_root)
                    result = {"status": "UNSUPPORTED" if status == "ERROR" else status, "row_count": 0, "filename": group["filename"], "message": message}
                    rows = []
                end_jobs = _matching_report_jobs(report_jobs, "end_screen")
                end_message = "End-screen bulk reports have not been generated yet." if end_jobs else "End-screen bulk reports are not currently available."
                end_result, end_rows = _bulk_pending_result(group_id="end_screens_daily", filename="end_screens_daily.csv", message=end_message)
                results["end_screens_daily"] = end_result
                table_rows["end_screens_daily.csv"] = end_rows
            elif group_id == "playlists_daily":
                result, rows = _run_playlists_group(
                    repo_root=repo_root,
                    channel_slug=channel_slug,
                    access_token=access_token,
                    analytics_query_fetcher=analytics_query_fetcher,
                    data_api_fetcher=data_api_fetcher,
                    channel=channel,
                    start_date=start_date,
                    end_date=end_date,
                )
            elif group_id == "retention":
                result, rows = _run_retention_group(
                    repo_root=repo_root,
                    channel_slug=channel_slug,
                    access_token=access_token,
                    analytics_query_fetcher=analytics_query_fetcher,
                    start_date=start_date,
                    end_date=end_date,
                    video_ids=canonical_video_ids,
                )
            else:
                continue
            results[group_id] = result
            table_rows[result["filename"]] = rows
        except Exception as exc:
            status, message = _classify_group_error(exc, root=repo_root)
            results[group_id] = {
                "status": status,
                "row_count": 0,
                "filename": group["filename"],
                "message": message,
            }
            table_rows.setdefault(group["filename"], [])

    reach_jobs = _matching_report_jobs(report_jobs, "reach")
    reach_message = "Reach bulk reports have not been generated yet." if reach_jobs else "Reach bulk report jobs are not currently available."
    reach_result, reach_rows = _bulk_pending_result(group_id="reach_daily", filename="reach_daily.csv", message=reach_message)
    results["reach_daily"] = reach_result
    table_rows["reach_daily.csv"] = reach_rows
    return results, table_rows


def _write_normalized_outputs(
    *,
    paths: dict[str, Path],
    video_catalog_rows: list[dict[str, Any]],
    query_table_rows: dict[str, list[dict[str, Any]]],
    query_group_results: dict[str, Any],
    video_catalog_status: str,
) -> dict[str, int]:
    table_specs = _normalized_table_specs()
    row_counts: dict[str, int] = {}
    all_tables = {"video_catalog.csv": video_catalog_rows}
    all_tables.update(query_table_rows)
    refreshable_statuses = {"SUCCESS", "EMPTY"}
    for filename, spec in table_specs.items():
        output_path = paths["normalized_dir"] / filename
        if filename == "video_catalog.csv":
            should_refresh = video_catalog_status in refreshable_statuses
        else:
            matching_statuses = [str(result.get("status", "")) for result in query_group_results.values() if result.get("filename") == filename]
            should_refresh = bool(matching_statuses) and all(status in refreshable_statuses for status in matching_statuses)
        if should_refresh:
            rows = _dedupe_rows(all_tables.get(filename, []), spec["key_columns"])
            _write_bytes_atomic(output_path, _csv_bytes(rows, spec["columns"]))
            row_counts[filename] = len(rows)
            continue
        if output_path.exists():
            row_counts[filename] = _csv_row_count(output_path)
            continue
        _write_bytes_atomic(output_path, _csv_bytes([], spec["columns"]))
        row_counts[filename] = 0
    return row_counts


def _build_capability_counts(capabilities: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"AVAILABLE": 0, "PENDING": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "UNAVAILABLE": 0, "ERROR": 0}
    for item in capabilities:
        status = str(item.get("availability_status", "AVAILABLE") or "AVAILABLE").upper()
        counts[status] = counts.get(status, 0) + 1
    return counts


def _build_report_readiness_counts(capabilities: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"READY": 0, "PENDING": 0, "UNAVAILABLE": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "ERROR": 0}
    for item in capabilities:
        status = str(item.get("generated_report_status", "PENDING") or "PENDING").upper()
        counts[status] = counts.get(status, 0) + 1
    return counts


def sync_channel_analytics(
    root: Path | str,
    channel_slug: str,
    *,
    token_provider: TokenProvider,
    data_api_fetcher: JsonFetcher,
    analytics_query_fetcher: JsonFetcher,
    reporting_api_fetcher: JsonFetcher,
    report_download_fetcher: BinaryFetcher,
    window_days: int = 365,
) -> dict[str, Any]:
    if window_days <= 0:
        raise _error("INVALID_ANALYTICS_WINDOW", "window_days must be a positive integer.", 400)
    repo_root = Path(root).resolve()
    channel = channel_workspace.load_channel(repo_root, channel_slug)
    paths = _analytics_paths(repo_root, channel_slug)
    state = _load_collector_state(paths, channel_slug)
    now = utc_now_iso()
    state["last_attempt_at"] = now
    state["errors"] = []
    start_date, end_date = _window_bounds(window_days)
    state["collection_window"] = {"start_date": start_date, "end_date": end_date}

    try:
        access_token = token_provider(repo_root, channel_slug)
    except channel_oauth.OAuthServiceError as exc:
        message = _error_message(exc, root=repo_root)
        state["source_results"]["token"] = {"status": "UNAUTHORIZED", "checked_at": now, "message": message}
        state["errors"] = [message]
        _write_json_atomic(paths["collector_state"], _sanitize_value(state, root=repo_root))
        raise _error("OAUTH_RECONNECT_REQUIRED", message, 409) from exc

    try:
        capability_snapshot = discover_channel_analytics_capabilities(
            repo_root,
            channel_slug,
            token_provider=lambda *_args, **_kwargs: access_token,
            reporting_api_fetcher=reporting_api_fetcher,
        )
    except ChannelAnalyticsCollectorError:
        capability_snapshot = _read_capability_snapshot(paths, channel_slug)
        state = _load_collector_state(paths, channel_slug)

    try:
        catalog_videos = _fetch_all_video_catalog(
            root=repo_root,
            channel_slug=channel_slug,
            access_token=access_token,
            channel=channel,
            data_api_fetcher=data_api_fetcher,
        )
        video_catalog_rows = _dedupe_rows(
            [_video_catalog_row(video) for video in catalog_videos],
            _normalized_table_specs()["video_catalog.csv"]["key_columns"],
        )
        state["source_results"]["data_api_catalog"] = {
            "status": "SUCCESS" if video_catalog_rows else "EMPTY",
            "checked_at": now,
            "video_count": len(video_catalog_rows),
        }
    except Exception as exc:
        status, message = _classify_group_error(exc, root=repo_root)
        state["source_results"]["data_api_catalog"] = {"status": status, "checked_at": now, "video_count": 0, "message": message}
        video_catalog_rows = []
        state["errors"].append(message)

    capabilities = capability_snapshot.get("capabilities", []) if isinstance(capability_snapshot, dict) else []
    _download_reporting_reports(
        repo_root=repo_root,
        channel_slug=channel_slug,
        access_token=access_token,
        paths=paths,
        state=state,
        capabilities=capabilities,
        reporting_api_fetcher=reporting_api_fetcher,
        report_download_fetcher=report_download_fetcher,
        now=now,
    )
    if capabilities:
        capability_snapshot["capabilities"] = capabilities
        capability_snapshot["discovered_at"] = capability_snapshot.get("discovered_at") or now
        _annotate_capability_snapshot(capability_snapshot)
        _write_json_atomic(paths["capability_snapshot"], _sanitize_value(capability_snapshot, root=repo_root))

    query_group_results, query_table_rows = _run_query_groups(
        repo_root=repo_root,
        channel_slug=channel_slug,
        access_token=access_token,
        analytics_query_fetcher=analytics_query_fetcher,
        data_api_fetcher=data_api_fetcher,
        channel=channel,
        window_days=window_days,
        canonical_video_ids=[row["video_id"] for row in video_catalog_rows if row.get("video_id")],
        report_jobs=state.get("report_jobs", {}),
    )
    state["query_group_results"] = query_group_results
    video_catalog_status = str(state["source_results"].get("data_api_catalog", {}).get("status", "ERROR"))
    row_counts = _write_normalized_outputs(
        paths=paths,
        video_catalog_rows=video_catalog_rows,
        query_table_rows=query_table_rows,
        query_group_results=query_group_results,
        video_catalog_status=video_catalog_status,
    )
    state["row_counts"] = row_counts

    success_like = {"SUCCESS", "EMPTY", "UNAVAILABLE", "UNAUTHORIZED", "UNSUPPORTED"}
    source_statuses = [str(item.get("status", "")) for item in state["source_results"].values()]
    query_statuses = [str(item.get("status", "")) for item in query_group_results.values()]
    query_success_count = sum(1 for item in query_group_results.values() if item.get("status") == "SUCCESS")
    query_error_count = sum(1 for item in query_group_results.values() if item.get("status") == "ERROR")
    if query_error_count == 0:
        analytics_queries_status = "SUCCESS"
    elif query_success_count > 0:
        analytics_queries_status = "PARTIAL"
    else:
        analytics_queries_status = "ERROR"
    overall_success = analytics_queries_status == "SUCCESS" and all(status in success_like | {"PARTIAL"} for status in source_statuses)
    state["last_completed_sync_at"] = now
    if overall_success:
        state["last_successful_sync_at"] = now
    state["source_results"]["analytics_queries"] = {
        "status": analytics_queries_status,
        "checked_at": now,
        "groups_total": len(query_group_results),
        "success_count": query_success_count,
        "empty_count": sum(1 for item in query_group_results.values() if item["status"] == "EMPTY"),
        "unavailable_count": sum(1 for item in query_group_results.values() if item["status"] == "UNAVAILABLE"),
        "unauthorized_count": sum(1 for item in query_group_results.values() if item["status"] == "UNAUTHORIZED"),
        "unsupported_count": sum(1 for item in query_group_results.values() if item["status"] == "UNSUPPORTED"),
        "error_count": query_error_count,
    }
    state["report_type_counts"] = _build_capability_counts(capabilities)
    state["generated_report_counts"] = _build_report_readiness_counts(capabilities)
    _write_json_atomic(paths["collector_state"], _sanitize_value(state, root=repo_root))
    return load_channel_analytics_status(repo_root, channel_slug)


def load_channel_analytics_status(root: Path | str, channel_slug: str) -> dict[str, Any]:
    repo_root = Path(root).resolve()
    channel_workspace.load_channel(repo_root, channel_slug)
    paths = _analytics_paths(repo_root, channel_slug)
    state = _load_collector_state(paths, channel_slug)
    capability_snapshot = _read_capability_snapshot(paths, channel_slug)

    table_specs = _normalized_table_specs()
    normalized_tables = []
    for filename in sorted(table_specs):
        path = paths["normalized_dir"] / filename
        normalized_tables.append(
            {
                "filename": filename,
                "exists": path.exists(),
                "row_count": int(state.get("row_counts", {}).get(filename, 0)),
                "relative_path": _relative_to_root(repo_root, path) if path.exists() else None,
            }
        )

    source_results = state.get("source_results", {})
    query_group_results = state.get("query_group_results", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "channel_slug": channel_slug,
        "last_attempt_at": state.get("last_attempt_at"),
        "last_completed_sync_at": state.get("last_completed_sync_at"),
        "last_successful_sync_at": state.get("last_successful_sync_at"),
        "collection_window": state.get("collection_window", {}),
        "source_results": source_results,
        "query_group_results": query_group_results,
        "capability_counts": _build_capability_counts(capability_snapshot.get("capabilities", [])),
        "report_readiness_counts": _build_report_readiness_counts(capability_snapshot.get("capabilities", [])),
        "query_group_counts": {
            "SUCCESS": sum(1 for item in query_group_results.values() if item.get("status") == "SUCCESS"),
            "PARTIAL": sum(1 for item in query_group_results.values() if item.get("status") == "PARTIAL"),
            "EMPTY": sum(1 for item in query_group_results.values() if item.get("status") == "EMPTY"),
            "UNAVAILABLE": sum(1 for item in query_group_results.values() if item.get("status") == "UNAVAILABLE"),
            "UNAUTHORIZED": sum(1 for item in query_group_results.values() if item.get("status") == "UNAUTHORIZED"),
            "UNSUPPORTED": sum(1 for item in query_group_results.values() if item.get("status") == "UNSUPPORTED"),
            "ERROR": sum(1 for item in query_group_results.values() if item.get("status") == "ERROR"),
        },
        "normalized_tables": normalized_tables,
        "row_counts": state.get("row_counts", {}),
        "report_jobs": state.get("report_jobs", {}),
        "ingested_report_count": len(state.get("ingested_reports", {})),
        "capability_snapshot_exists": paths["capability_snapshot"].exists(),
        "collector_state_exists": paths["collector_state"].exists(),
        "export_url": f"/api/v2/channels/{channel_slug}/analytics/export",
        "unavailable_metrics": build_unavailable_metrics_payload(repo_root, channel_slug),
    }


def build_unavailable_metrics_payload(root: Path | str, channel_slug: str) -> dict[str, Any]:
    repo_root = Path(root).resolve()
    paths = _analytics_paths(repo_root, channel_slug)
    state = _load_collector_state(paths, channel_slug)
    capability_snapshot = _read_capability_snapshot(paths, channel_slug)
    return {
        "schema_version": SCHEMA_VERSION,
        "channel_slug": channel_slug,
        "generated_at": utc_now_iso(),
        "capabilities": [
            {
                "report_type_id": item.get("report_type_id"),
                "availability_status": item.get("availability_status"),
                "generated_report_status": item.get("generated_report_status"),
                "message": item.get("generated_report_message") or item.get("message", ""),
            }
            for item in capability_snapshot.get("capabilities", [])
            if item.get("generated_report_status") not in {None, "", "READY"}
        ],
        "query_groups": [
            {
                "group_id": group_id,
                "status": result.get("status"),
                "message": result.get("message", ""),
            }
            for group_id, result in sorted(state.get("query_group_results", {}).items())
            if result.get("status") in {"UNAVAILABLE", "UNAUTHORIZED", "UNSUPPORTED", "ERROR"}
        ],
    }


def build_channel_analytics_export(root: Path | str, channel_slug: str) -> dict[str, Any]:
    repo_root = Path(root).resolve()
    channel_workspace.load_channel(repo_root, channel_slug)
    paths = _analytics_paths(repo_root, channel_slug)
    status = load_channel_analytics_status(repo_root, channel_slug)
    capability_snapshot = _read_capability_snapshot(paths, channel_slug)
    collector_state = _load_collector_state(paths, channel_slug)
    unavailable_metrics = build_unavailable_metrics_payload(repo_root, channel_slug)

    files: list[tuple[str, bytes]] = []
    files.append(("capabilities.json", (json.dumps(_sanitize_value(capability_snapshot, root=repo_root), indent=2, ensure_ascii=False) + "\n").encode("utf-8")))
    files.append(("collector_status.json", (json.dumps(_sanitize_value(collector_state, root=repo_root), indent=2, ensure_ascii=False) + "\n").encode("utf-8")))
    files.append(("unavailable_metrics.json", (json.dumps(_sanitize_value(unavailable_metrics, root=repo_root), indent=2, ensure_ascii=False) + "\n").encode("utf-8")))

    for table in status["normalized_tables"]:
        if not table["exists"]:
            continue
        path = paths["normalized_dir"] / table["filename"]
        files.append((table["filename"], path.read_bytes()))

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "channel_slug": channel_slug,
        "generated_at": utc_now_iso(),
        "collection_time_range": status.get("collection_window", {}),
        "source_statuses": _sanitize_value(status.get("source_results", {}), root=repo_root),
        "included_filenames": [],
        "row_counts": {},
        "file_hashes": {},
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, payload in files:
            info = zipfile.ZipInfo(filename)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
            manifest["included_filenames"].append(filename)
            manifest["file_hashes"][filename] = _sha256_bytes(payload)
            if filename.endswith(".csv"):
                manifest["row_counts"][filename] = int(status.get("row_counts", {}).get(filename, 0))
        manifest_payload = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        info = zipfile.ZipInfo("manifest.json")
        info.date_time = (1980, 1, 1, 0, 0, 0)
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, manifest_payload)

    return {
        "filename": f"{channel_slug}_analytics_export.zip",
        "content_type": "application/zip",
        "body_bytes": buffer.getvalue(),
        "status": status,
    }
