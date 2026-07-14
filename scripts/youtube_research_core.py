from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


API_BASE = "https://www.googleapis.com/youtube/v3"
API_USER_AGENT = "Mist-of-Ages-Research-Core/1.0"
DEFAULT_CACHE_NAMESPACE = "youtube_data_api"
PLAN_SCHEMA_VERSION = 1
SHORT_THRESHOLD_SECONDS = 180
LONG_3_10_MAX_SECONDS = 599
LONG_10_30_MAX_SECONDS = 1799
DEFAULT_BASELINE_MIN_AGE_HOURS = 48
DEFAULT_BASELINE_RECENT_COUNT = 20
DEFAULT_PUBLISHED_DAYS = 365
QUALIFYING_VELOCITY_OUTLIER_THRESHOLD = 1.5
TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}


JsonFetcher = Callable[..., dict[str, Any]]
SleepFn = Callable[[float], None]


class YouTubeResearchError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error(code: str, message: str, status: int = 400) -> YouTubeResearchError:
    return YouTubeResearchError(code, message, status)


def stable_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def load_api_key(explicit: str | None, *, env: dict[str, str] | None = None, key_file: Path | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env_map = env if env is not None else os.environ
    env_key = (env_map.get("YOUTUBE_API_KEY") or "").strip()
    if env_key:
        return env_key
    path = key_file if key_file is not None else Path("youtube_api_key.txt")
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                return line
    raise _error(
        "YOUTUBE_API_KEY_MISSING",
        "YouTube API key not found. Use --api-key, YOUTUBE_API_KEY, or a local ignored youtube_api_key.txt file.",
    )


def parse_iso8601_duration(value: str) -> int:
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?",
        value or "",
    )
    if not match:
        return 0
    parts = {name: int(number or 0) for name, number in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(max(seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def classify_duration_band(duration_seconds: int) -> str:
    if duration_seconds < SHORT_THRESHOLD_SECONDS:
        return "SHORT"
    if duration_seconds <= LONG_3_10_MAX_SECONDS:
        return "LONG_3_10"
    if duration_seconds <= LONG_10_30_MAX_SECONDS:
        return "LONG_10_30"
    return "LONG_30_PLUS"


def parse_datetime(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise _error("INVALID_DATETIME", "Missing ISO-8601 datetime.")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error("INVALID_DATETIME", "Invalid ISO-8601 datetime value.") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_query(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def deterministic_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return cleaned or "value"


def median_or_none(values: list[float]) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def outlier_ratio(numerator: float | int, denominator: float | int | None) -> float | None:
    if denominator is None:
        return None
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def baseline_confidence_label(count: int) -> str:
    if count < 4:
        return "LOW"
    if count < 8:
        return "MEDIUM"
    return "HIGH"


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def video_age_hours(published_at: str, *, now: datetime) -> float:
    published_dt = parse_datetime(published_at)
    return max((now - published_dt).total_seconds() / 3600, 0.0)


def lifetime_views_per_day(views: int, published_at: str, *, now: datetime) -> float:
    age_hours = max(video_age_hours(published_at, now=now), 1 / 24)
    return views / max(age_hours / 24, 1 / 24)


def views_per_subscriber(views: int, subscribers: int | None) -> float | None:
    if subscribers is None or subscribers <= 0:
        return None
    return views / subscribers


def baseline_is_eligible(
    target_video_id: str,
    target_duration_band: str,
    baseline_video: dict[str, Any],
    *,
    baseline_min_age_hours: int,
    now: datetime,
) -> bool:
    if baseline_video.get("video_id") == target_video_id:
        return False
    if baseline_video.get("duration_band") != target_duration_band:
        return False
    age_hours = float(baseline_video.get("age_hours") or 0.0)
    if age_hours < baseline_min_age_hours:
        return False
    return True


def normalize_video_metrics(
    video_item: dict[str, Any],
    *,
    channel_stats: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or utc_now()
    snippet = video_item.get("snippet", {})
    content_details = video_item.get("contentDetails", {})
    statistics_data = video_item.get("statistics", {})
    published_at = snippet.get("publishedAt", "")
    duration_seconds = parse_iso8601_duration(content_details.get("duration", ""))
    duration_band = classify_duration_band(duration_seconds)
    views = safe_int(statistics_data.get("viewCount"))
    likes = safe_int(statistics_data.get("likeCount"))
    comments = safe_int(statistics_data.get("commentCount"))
    subscribers_hidden = bool((channel_stats or {}).get("hiddenSubscriberCount", False))
    subscribers = None if subscribers_hidden else safe_int((channel_stats or {}).get("subscriberCount"))
    age_hours = video_age_hours(published_at, now=current_time) if published_at else 0.0
    value = {
        "video_id": video_item.get("id", ""),
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "channel_id": snippet.get("channelId", ""),
        "published_at": published_at,
        "age_hours": round(age_hours, 2),
        "age_days": round(age_hours / 24, 2),
        "duration_seconds": duration_seconds,
        "duration": format_duration(duration_seconds),
        "duration_band": duration_band,
        "views": views,
        "lifetime_views_per_day": round(lifetime_views_per_day(views, published_at, now=current_time), 6) if published_at else 0.0,
        "subscribers": subscribers,
        "subscribers_hidden": subscribers_hidden,
        "views_per_subscriber": views_per_subscriber(views, subscribers),
        "likes": likes,
        "comments": comments,
        "url": f"https://www.youtube.com/watch?v={video_item.get('id', '')}",
    }
    return value


def build_request_fingerprint(resource: str, params: dict[str, Any], *, namespace: str = DEFAULT_CACHE_NAMESPACE) -> str:
    sanitized = {key: value for key, value in params.items() if key != "key"}
    payload = {"namespace": namespace, "resource": resource, "params": sanitized}
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def write_json_atomic(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    _write_bytes_atomic(path, stable_json_dumps(payload).encode("utf-8"))


def write_text_atomic(path: Path, text: str) -> None:
    _write_bytes_atomic(path, text.encode("utf-8"))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    import csv
    import io

    with io.StringIO(newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
        text = handle.getvalue()
    if not text.endswith("\n"):
        text += "\n"
    write_text_atomic(path, text)


def redact_api_key(value: str, api_key: str | None) -> str:
    text = str(value or "")
    if api_key:
        text = text.replace(api_key, "<redacted-api-key>")
    text = re.sub(r"([?&]key=)[^&\s]+", r"\1<redacted-api-key>", text)
    return text


def sanitize_error_message(value: str, api_key: str | None = None) -> str:
    text = redact_api_key(value, api_key)
    return " ".join(text.split())[:500]


def default_json_fetcher(*, resource: str, params: dict[str, Any], api_key: str, timeout: int = 30) -> dict[str, Any]:
    query = dict(params)
    query["key"] = api_key
    url = f"{API_BASE}/{resource}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": API_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


@dataclass
class RequestStats:
    request_count: int = 0
    cache_hit_count: int = 0


class YouTubeResearchClient:
    def __init__(
        self,
        api_key: str,
        *,
        cache_dir: Path | None = None,
        refresh: bool = False,
        retries: int = 3,
        sleeper: SleepFn | None = None,
        fetcher: JsonFetcher | None = None,
        timeout: int = 30,
    ):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.retries = max(retries, 1)
        self.sleeper = sleeper or time.sleep
        self.fetcher = fetcher or default_json_fetcher
        self.timeout = timeout
        self.stats = RequestStats()

    def _cache_path(self, fingerprint: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{fingerprint}.json"

    def get(self, resource: str, **params: Any) -> dict[str, Any]:
        fingerprint = build_request_fingerprint(resource, params)
        cache_path = self._cache_path(fingerprint)
        if cache_path is not None and cache_path.exists() and not self.refresh:
            self.stats.cache_hit_count += 1
            return json.loads(cache_path.read_text(encoding="utf-8"))

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                self.stats.request_count += 1
                payload = self.fetcher(
                    resource=resource,
                    params=dict(params),
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
                if cache_path is not None:
                    write_json_atomic(cache_path, payload)
                return payload
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body = str(exc)
                sanitized = sanitize_error_message(body or str(exc), self.api_key)
                if exc.code not in TRANSIENT_HTTP_STATUSES or attempt + 1 >= self.retries:
                    raise _error("YOUTUBE_API_REQUEST_FAILED", f"API request failed for {resource}: {sanitized}", exc.code) from exc
                last_error = exc
                self.sleeper(0.5 * (2 ** attempt))
            except urllib.error.URLError as exc:
                sanitized = sanitize_error_message(str(exc), self.api_key)
                if attempt + 1 >= self.retries:
                    raise _error("YOUTUBE_API_REQUEST_FAILED", f"API request failed for {resource}: {sanitized}", 502) from exc
                last_error = exc
                self.sleeper(0.5 * (2 ** attempt))
            except Exception as exc:
                sanitized = sanitize_error_message(str(exc), self.api_key)
                raise _error("YOUTUBE_API_REQUEST_FAILED", f"API request failed for {resource}: {sanitized}", 502) from exc
        if last_error is not None:
            raise _error("YOUTUBE_API_REQUEST_FAILED", sanitize_error_message(str(last_error), self.api_key), 502)
        raise _error("YOUTUBE_API_REQUEST_FAILED", f"API request failed for {resource}.", 502)


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def batch_videos(client: YouTubeResearchClient, video_ids: list[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    unique = list(dict.fromkeys(video_ids))
    for batch in chunked(unique, 50):
        payload = client.get("videos", part="snippet,contentDetails,statistics", id=",".join(batch), maxResults=len(batch))
        for item in payload.get("items", []):
            output[item["id"]] = item
    return output


def batch_channels(client: YouTubeResearchClient, channel_ids: list[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    unique = list(dict.fromkeys(channel_ids))
    for batch in chunked(unique, 50):
        payload = client.get("channels", part="snippet,contentDetails,statistics", id=",".join(batch), maxResults=len(batch))
        for item in payload.get("items", []):
            output[item["id"]] = item
    return output


def recent_upload_ids(client: YouTubeResearchClient, upload_playlist_id: str, count: int) -> list[str]:
    payload = client.get(
        "playlistItems",
        part="contentDetails,snippet",
        playlistId=upload_playlist_id,
        maxResults=min(max(count, 1), 50),
    )
    ids: list[str] = []
    for item in payload.get("items", []):
        video_id = item.get("contentDetails", {}).get("videoId") or item.get("snippet", {}).get("resourceId", {}).get("videoId")
        if video_id:
            ids.append(video_id)
    return ids[:count]


def parse_video_id(value: str) -> str:
    raw = (value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw
    parsed = urllib.parse.urlparse(raw)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    if "youtu.be" in host and path:
        return path.split("/")[0]
    if "youtube.com" in host or "youtube-nocookie.com" in host:
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("v"):
            return query["v"][0]
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            return parts[1]
    raise _error("INVALID_VIDEO_ID", "Could not determine a YouTube video ID from the provided value.")


def find_video_by_query(client: YouTubeResearchClient, query: str) -> tuple[str, list[dict[str, str]]]:
    payload = client.get("search", part="snippet", q=query, type="video", maxResults=5, order="relevance")
    items = payload.get("items", [])
    if not items:
        raise _error("VIDEO_QUERY_EMPTY", "No video results matched the query.")
    preview = []
    for item in items:
        preview.append(
            {
                "video_id": item.get("id", {}).get("videoId", ""),
                "title": item.get("snippet", {}).get("title", ""),
                "channel": item.get("snippet", {}).get("channelTitle", ""),
            }
        )
    video_id = items[0].get("id", {}).get("videoId", "")
    if not video_id:
        raise _error("VIDEO_QUERY_EMPTY", "No video results matched the query.")
    return video_id, preview


def validate_topic_scan_plan(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise _error("INVALID_PLAN", "Plan must be a JSON object.")
    if raw.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise _error("INVALID_PLAN", "Plan schema_version must be 1.")

    def _require_text(name: str) -> str:
        value = raw.get(name)
        if not isinstance(value, str) or not value.strip():
            raise _error("INVALID_PLAN", f"Plan field '{name}' must be a non-empty string.")
        return value.strip()

    cluster_id = _require_text("cluster_id")
    label = _require_text("label")
    published_days = safe_int(raw.get("published_days"))
    minimum_duration_seconds = safe_int(raw.get("minimum_duration_seconds"))
    maximum_duration_seconds = safe_int(raw.get("maximum_duration_seconds"))
    baseline_recent_count = safe_int(raw.get("baseline_recent_count") or DEFAULT_BASELINE_RECENT_COUNT)
    baseline_min_age_hours = safe_int(raw.get("baseline_min_age_hours") or DEFAULT_BASELINE_MIN_AGE_HOURS)
    if published_days <= 0:
        raise _error("INVALID_PLAN", "Plan field 'published_days' must be positive.")
    if minimum_duration_seconds <= 0 or maximum_duration_seconds <= 0:
        raise _error("INVALID_PLAN", "Plan duration limits must be positive.")
    if minimum_duration_seconds > maximum_duration_seconds:
        raise _error("INVALID_PLAN", "Plan minimum_duration_seconds must be less than or equal to maximum_duration_seconds.")
    if baseline_recent_count <= 0 or baseline_min_age_hours <= 0:
        raise _error("INVALID_PLAN", "Plan baseline settings must be positive.")

    groups = raw.get("groups")
    if not isinstance(groups, list) or not groups:
        raise _error("INVALID_PLAN", "Plan groups must be a non-empty array.")

    seen_group_ids: set[str] = set()
    seen_queries: set[str] = set()
    normalized_groups: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            raise _error("INVALID_PLAN", "Each plan group must be an object.")
        group_id = group.get("topic_group_id")
        if not isinstance(group_id, str) or not group_id.strip():
            raise _error("INVALID_PLAN", "Each plan group must include a non-empty topic_group_id.")
        group_id = group_id.strip()
        if group_id in seen_group_ids:
            raise _error("INVALID_PLAN", f"Duplicate topic_group_id '{group_id}'.")
        seen_group_ids.add(group_id)
        group_label = group.get("label")
        gateway_entity = group.get("gateway_entity")
        if not isinstance(group_label, str) or not group_label.strip():
            raise _error("INVALID_PLAN", f"Group '{group_id}' must include a non-empty label.")
        if not isinstance(gateway_entity, str) or not gateway_entity.strip():
            raise _error("INVALID_PLAN", f"Group '{group_id}' must include a non-empty gateway_entity.")
        queries = group.get("queries")
        if not isinstance(queries, list) or not queries:
            raise _error("INVALID_PLAN", f"Group '{group_id}' must include at least one query.")
        cleaned_queries: list[str] = []
        for query in queries:
            if not isinstance(query, str) or not query.strip():
                raise _error("INVALID_PLAN", f"Group '{group_id}' contains an empty query.")
            normalized_query = normalize_query(query)
            if normalized_query in seen_queries:
                raise _error("INVALID_PLAN", f"Duplicate normalized query '{normalized_query}'.")
            seen_queries.add(normalized_query)
            cleaned_queries.append(query.strip())
        normalized_groups.append(
            {
                "topic_group_id": group_id,
                "label": group_label.strip(),
                "gateway_entity": gateway_entity.strip(),
                "queries": cleaned_queries,
            }
        )
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "cluster_id": cluster_id,
        "label": label,
        "published_days": published_days,
        "minimum_duration_seconds": minimum_duration_seconds,
        "maximum_duration_seconds": maximum_duration_seconds,
        "baseline_recent_count": baseline_recent_count,
        "baseline_min_age_hours": baseline_min_age_hours,
        "groups": normalized_groups,
    }


def synthesize_plan_from_queries(
    queries: list[str],
    *,
    published_days: int,
    minimum_duration_seconds: int,
    maximum_duration_seconds: int,
    baseline_recent_count: int,
    baseline_min_age_hours: int,
) -> dict[str, Any]:
    cleaned = [query.strip() for query in queries if isinstance(query, str) and query.strip()]
    if not cleaned:
        raise _error("INVALID_QUERY", "At least one non-empty --query value is required.")
    normalized = {normalize_query(query) for query in cleaned}
    if len(normalized) != len(cleaned):
        raise _error("INVALID_QUERY", "Duplicate normalized queries are not allowed.")
    cluster_seed = cleaned[0]
    return validate_topic_scan_plan(
        {
            "schema_version": PLAN_SCHEMA_VERSION,
            "cluster_id": deterministic_slug(cluster_seed),
            "label": cluster_seed,
            "published_days": published_days,
            "minimum_duration_seconds": minimum_duration_seconds,
            "maximum_duration_seconds": maximum_duration_seconds,
            "baseline_recent_count": baseline_recent_count,
            "baseline_min_age_hours": baseline_min_age_hours,
            "groups": [
                {
                    "topic_group_id": "direct_query_group",
                    "label": "Direct Query Group",
                    "gateway_entity": cluster_seed,
                    "queries": cleaned,
                }
            ],
        }
    )


def quality_label_from_group(
    *,
    qualifying_outlier_channel_count: int,
    qualifying_outlier_video_count: int,
    confidence: str,
) -> str:
    if confidence == "LOW":
        return "WEAK"
    if qualifying_outlier_channel_count >= 3:
        return "STRONG"
    if qualifying_outlier_channel_count >= 2:
        return "SUPPORTED"
    if qualifying_outlier_video_count >= 1:
        return "DIRECTIONAL"
    return "WEAK"


def verdict_from_group(
    *,
    quality_label: str,
    confidence: str,
    qualifying_outlier_channel_count: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if confidence == "LOW":
        reasons.append("Low-confidence evidence cannot be shortlisted.")
        return "HOLD" if qualifying_outlier_channel_count else "REJECT", reasons
    if quality_label == "STRONG":
        reasons.append("Three or more independent qualifying channels support the topic.")
        return "SHORTLIST", reasons
    if quality_label == "SUPPORTED":
        reasons.append("At least two independent qualifying channels support the topic.")
        return "SHORTLIST", reasons
    if quality_label == "DIRECTIONAL":
        reasons.append("Only one independent qualifying channel supports the topic.")
        return "HOLD", reasons
    reasons.append("No qualifying outlier evidence passed the confidence gate.")
    return "REJECT", reasons


def cross_channel_status(unique_channels: int) -> str:
    if unique_channels <= 1:
        return "SINGLE_CHANNEL"
    if unique_channels == 2:
        return "TWO_CHANNELS"
    return "MULTI_CHANNEL"
