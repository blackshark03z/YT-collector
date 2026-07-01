from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts import channel_oauth, channel_workspace


TokenProvider = Callable[..., str]
Fetcher = Callable[..., Any]

CSV_COLUMNS = [
    "video_id",
    "title",
    "published_at",
    "views",
    "estimated_minutes_watched",
    "average_view_duration_seconds",
    "average_view_percentage",
    "likes",
    "comments",
    "thumbnail_impressions",
    "thumbnail_ctr",
    "data_status",
]
SECRET_MARKERS = ("access_token", "refresh_token", "client_secret", "authorization")


class ChannelMetricsError(Exception):
    pass


class ChannelMetricsReconnectRequiredError(ChannelMetricsError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    _write_bytes_atomic(path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            if any(marker in key.lower() for marker in SECRET_MARKERS):
                continue
            clean[key] = _sanitize_value(item)
        return clean
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str) and any(marker in value.lower() for marker in SECRET_MARKERS):
        return ""
    return value


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    with tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", newline="") as temp:
        writer = csv.DictWriter(temp, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})
        temp.seek(0)
        return temp.read().encode("utf-8")


def _normalized_video_row(video: dict[str, Any], analytics_row: dict[str, Any], reach_row: dict[str, Any] | None, status: str) -> dict[str, Any]:
    snippet = video.get("snippet", {})
    statistics = video.get("statistics", {})
    return {
        "video_id": video.get("id", ""),
        "title": snippet.get("title", ""),
        "published_at": snippet.get("publishedAt", ""),
        "views": analytics_row.get("views", statistics.get("viewCount", "")),
        "estimated_minutes_watched": analytics_row.get("estimated_minutes_watched", ""),
        "average_view_duration_seconds": analytics_row.get("average_view_duration_seconds", ""),
        "average_view_percentage": analytics_row.get("average_view_percentage", ""),
        "likes": statistics.get("likeCount", ""),
        "comments": statistics.get("commentCount", ""),
        "thumbnail_impressions": "" if reach_row is None else reach_row.get("thumbnail_impressions", ""),
        "thumbnail_ctr": "" if reach_row is None else reach_row.get("thumbnail_ctr", ""),
        "data_status": status,
    }


def _normalize_analytics_rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    headers = [header.get("name", "") for header in payload.get("columnHeaders", [])]
    rows = {}
    for row in payload.get("rows", []) or []:
        mapped = dict(zip(headers, row))
        video_id = mapped.get("video")
        if video_id:
            rows[str(video_id)] = {
                "views": mapped.get("views", ""),
                "estimated_minutes_watched": mapped.get("estimatedMinutesWatched", ""),
                "average_view_duration_seconds": mapped.get("averageViewDuration", ""),
                "average_view_percentage": mapped.get("averageViewPercentage", ""),
            }
    return rows


def _normalize_reach_rows(payload: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], str, list[str], list[str], str | None]:
    if not payload:
        return {}, "PENDING", [], ["thumbnail_impressions", "thumbnail_ctr"], None
    status = str(payload.get("status", "PENDING")).upper()
    message = payload.get("message")
    available = [str(item) for item in payload.get("available_metrics", []) if item]
    pending = [str(item) for item in payload.get("pending_metrics", []) if item]
    by_video = {}
    for row in payload.get("rows", []) or []:
        video_id = row.get("video_id")
        if not video_id:
            continue
        by_video[str(video_id)] = {
            "thumbnail_impressions": row.get("thumbnail_impressions", ""),
            "thumbnail_ctr": row.get("thumbnail_ctr", ""),
        }
    return by_video, status, available, pending, message


def sync_channel_metrics(
    root: Path | str,
    channel_slug: str,
    *,
    analytics_fetcher: Fetcher,
    recent_videos_fetcher: Fetcher,
    reporting_fetcher: Fetcher,
    token_provider: TokenProvider,
    window_days: int = 90,
    recent_count: int = 12,
) -> dict[str, Any]:
    if window_days <= 0 or recent_count <= 0:
        raise ChannelMetricsError("window_days and recent_count must be positive integers.")
    channel = channel_workspace.load_channel(root, channel_slug)
    paths = channel_workspace.canonical_channel_paths(root, channel_slug)
    metrics_dir = paths.metrics_dir
    temp_dir = metrics_dir.parent / f".tmp-metrics-{channel_slug}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)

    try:
        access_token = token_provider(root, channel_slug)
    except channel_oauth.ReconnectRequiredError as exc:
        raise ChannelMetricsReconnectRequiredError(str(exc)) from exc
    except channel_oauth.TokenMissingError as exc:
        raise ChannelMetricsReconnectRequiredError(str(exc)) from exc

    try:
        recent_payload = recent_videos_fetcher(
            root=root,
            channel_slug=channel_slug,
            access_token=access_token,
            recent_count=recent_count,
            channel=channel,
        )
        analytics_payload = analytics_fetcher(
            root=root,
            channel_slug=channel_slug,
            access_token=access_token,
            window_days=window_days,
            recent_count=recent_count,
            channel=channel,
            recent_payload=recent_payload,
        )
    except Exception as exc:
        raise ChannelMetricsError(str(exc)) from exc

    reach_payload = None
    reach_status = "PENDING"
    reach_message = None
    reach_available = []
    reach_pending = ["thumbnail_impressions", "thumbnail_ctr"]
    try:
        reach_payload = reporting_fetcher(
            root=root,
            channel_slug=channel_slug,
            access_token=access_token,
            window_days=window_days,
            recent_count=recent_count,
            channel=channel,
            recent_payload=recent_payload,
        )
    except Exception as exc:
        reach_message = str(exc)

    analytics_rows = _normalize_analytics_rows(analytics_payload)
    reach_rows, reach_status, reach_available, reach_pending, normalized_message = _normalize_reach_rows(reach_payload)
    if normalized_message:
        reach_message = normalized_message

    recent_items = recent_payload.get("items", [])
    if not isinstance(recent_items, list) or not recent_items:
        raise ChannelMetricsError("recent_videos_fetcher returned no usable videos.")

    metrics_status = "COMPLETE" if reach_status == "COMPLETE" else "PENDING_REACH"
    normalized_rows = [
        _normalized_video_row(video, analytics_rows.get(str(video.get("id", "")), {}), reach_rows.get(str(video.get("id", ""))), metrics_status)
        for video in recent_items
    ]

    reporting_state = {
        "schema_version": 1,
        "channel_slug": channel_slug,
        "youtube_channel_id": channel["youtube_channel_id"],
        "status": "COMPLETE" if reach_status == "COMPLETE" else "PENDING",
        "report_type": None if not reach_payload else reach_payload.get("report_type"),
        "last_checked_at": utc_now_iso(),
        "message": (reach_message or ("Reach data synchronized." if reach_status == "COMPLETE" else "Reach data pending."))[:500],
        "available_metrics": reach_available,
        "pending_metrics": reach_pending,
    }

    temp_raw = temp_dir / "_raw"
    temp_raw.mkdir(parents=True, exist_ok=False)
    csv_bytes = _csv_bytes(normalized_rows)
    if not csv_bytes.endswith(b"\r\n") and not csv_bytes.endswith(b"\n"):
        csv_bytes += b"\n"
    _write_bytes_atomic(temp_dir / "channel_metrics.csv", csv_bytes)
    _write_json_atomic(temp_dir / "reporting_state.json", _sanitize_value(reporting_state))
    _write_json_atomic(temp_raw / "channel_analytics.json", _sanitize_value(analytics_payload))
    _write_json_atomic(temp_raw / "recent_channel_videos.json", _sanitize_value(recent_payload))
    if reach_payload:
        _write_json_atomic(temp_raw / "channel_reach.json", _sanitize_value(reach_payload))

    try:
        metrics_dir.mkdir(parents=True, exist_ok=True)
        _write_bytes_atomic(paths.channel_metrics_csv, (temp_dir / "channel_metrics.csv").read_bytes())
        _write_bytes_atomic(paths.reporting_state_json, (temp_dir / "reporting_state.json").read_bytes())
        paths.metrics_raw_dir.mkdir(parents=True, exist_ok=True)
        _write_bytes_atomic(paths.metrics_raw_dir / "channel_analytics.json", (temp_raw / "channel_analytics.json").read_bytes())
        _write_bytes_atomic(paths.metrics_raw_dir / "recent_channel_videos.json", (temp_raw / "recent_channel_videos.json").read_bytes())
        if (temp_raw / "channel_reach.json").exists():
            _write_bytes_atomic(paths.metrics_raw_dir / "channel_reach.json", (temp_raw / "channel_reach.json").read_bytes())
        channel_workspace.update_channel_metrics_metadata(
            root,
            channel_slug,
            youtube_channel_id=channel["youtube_channel_id"],
            last_metrics_sync_at=utc_now_iso(),
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "channel_slug": channel_slug,
        "youtube_channel_id": channel["youtube_channel_id"],
        "status": reporting_state["status"],
        "metrics_status": metrics_status,
        "rows_written": len(normalized_rows),
        "reporting_state": reporting_state,
    }
