from __future__ import annotations

import csv
import datetime as dt
import html
import json
import mimetypes
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts import channel_analytics_collector, channel_metrics, channel_oauth, channel_oauth_browser, channel_output_parser, channel_production_export, channel_projects, channel_prompt_bundle, channel_workflow, channel_workflow_write, channel_workspace


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "projects"
CHANNEL_DIR = ROOT / "channel" / "mist_of_ages"
CONFIG_DIR = ROOT / ".local"

API_KEY_FILE = ROOT / "youtube_api_key.txt"
OAUTH_CLIENT_FILE = ROOT / "youtube_oauth_client.json"
OAUTH_TOKEN_FILE = ROOT / "youtube_oauth_token.json"
CHANNEL_CONFIG_FILE = CONFIG_DIR / "mist_of_ages_channel.json"
MASTER_LEARNINGS_FILE = CHANNEL_DIR / "channel_learnings_master.md"

DATA_API = "https://www.googleapis.com/youtube/v3"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"
REPORTING_API = "https://youtubereporting.googleapis.com/v1"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


class AppError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class V2Error(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    PROJECTS_DIR.mkdir(exist_ok=True)
    CHANNEL_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(exist_ok=True)
    if not MASTER_LEARNINGS_FILE.exists():
        MASTER_LEARNINGS_FILE.write_text(
            "# Approved Channel Learnings\n\nNo approved learnings yet.\n",
            encoding="utf-8",
        )


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def first_valid_api_key() -> str | None:
    if not API_KEY_FILE.exists():
        return None
    raw = API_KEY_FILE.read_text(encoding="utf-8-sig")
    for line in raw.splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value
    return None


def mask_secret(value: str | None) -> str:
    if not value:
        return "MISSING"
    if len(value) <= 8:
        return "FOUND"
    return f"FOUND (...{value[-4:]})"


def parse_video_id(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise AppError("Competitor YouTube URL is required.")

    parsed = urllib.parse.urlparse(value)
    host = parsed.netloc.lower().replace("www.", "")
    path_parts = [part for part in parsed.path.split("/") if part]

    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/watch" and query.get("v"):
            return clean_video_id(query["v"][0])
        if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed", "live"}:
            return clean_video_id(path_parts[1])
    if host == "youtu.be" and path_parts:
        return clean_video_id(path_parts[0])

    raise AppError("Could not find a valid YouTube video ID in that URL.")


def clean_video_id(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    raise AppError("The YouTube video ID is not valid.")


def safe_slug(text: str, fallback: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = fallback
    return text[:70].strip("-") or fallback


def _extract_http_error_message(detail: str, fallback: str) -> str:
    fallback_message = detail or fallback
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        return fallback_message

    if isinstance(payload, dict):
        nested_error = payload.get("error")
        if isinstance(nested_error, dict):
            nested_message = nested_error.get("message")
            if isinstance(nested_message, str) and nested_message.strip():
                return nested_message.strip()
        error_description = payload.get("error_description")
        if isinstance(error_description, str) and error_description.strip():
            return error_description.strip()
        if isinstance(nested_error, str) and nested_error.strip():
            return nested_error.strip()
        top_level_message = payload.get("message")
        if isinstance(top_level_message, str) and top_level_message.strip():
            return top_level_message.strip()
        return fallback_message

    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return fallback_message


def request_json(url: str, headers: dict | None = None, data: bytes | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = res.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = _extract_http_error_message(detail, str(exc))
        raise AppError(message, exc.code) from exc
    except urllib.error.URLError as exc:
        raise AppError(f"Network error: {exc.reason}") from exc


def default_transport(*, method: str, url: str, headers: dict | None = None, data: bytes | None = None) -> dict:
    return request_json(url, headers=headers, data=data)


def data_api(path: str, params: dict) -> dict:
    key = first_valid_api_key()
    if not key:
        raise AppError("youtube_api_key.txt is missing or empty.")
    merged = dict(params)
    merged["key"] = key
    url = f"{DATA_API}/{path}?{urllib.parse.urlencode(merged)}"
    return request_json(url)


def choose_thumbnail(thumbnails: dict) -> tuple[str, str]:
    for name in ("maxres", "standard", "high", "medium", "default"):
        item = thumbnails.get(name)
        if item and item.get("url"):
            return name, item["url"]
    return "", ""


def fetch_competitor_video(video_id: str) -> dict:
    payload = data_api(
        "videos",
        {
            "part": "snippet,contentDetails,statistics",
            "id": video_id,
            "maxResults": "1",
        },
    )
    items = payload.get("items", [])
    if not items:
        raise AppError("No video found for that URL.", 404)
    return items[0]


def fetch_competitor_thumbnail(url: str) -> tuple[bytes | None, str | None]:
    if not url:
        return None, None
    req = urllib.request.Request(url, headers={"User-Agent": "MistOfAgesCollector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            content = res.read()
            ctype = res.headers.get("Content-Type", "")
    except Exception:
        return None, None
    ext = mimetypes.guess_extension(ctype.split(";")[0].strip()) or Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    return content, ext


def download_thumbnail(url: str, assets_dir: Path) -> str:
    if not url:
        return ""
    assets_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "MistOfAgesCollector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            content = res.read()
            ctype = res.headers.get("Content-Type", "")
    except Exception:
        return ""
    ext = mimetypes.guess_extension(ctype.split(";")[0].strip()) or Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    target = assets_dir / f"competitor_thumbnail{ext}"
    target.write_bytes(content)
    return str(target.relative_to(ROOT)).replace("\\", "/")


def token_payload() -> dict:
    token = read_json(OAUTH_TOKEN_FILE)
    if not token:
        raise AppError("Mist of Ages channel is not connected yet.")
    expires_at = token.get("expires_at", 0)
    if token.get("access_token") and expires_at > time.time() + 60:
        return token
    if not token.get("refresh_token"):
        raise AppError("OAuth token expired and has no refresh token. Connect again.")
    client_id, client_secret = oauth_client_details()
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": token["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    refreshed = request_json("https://oauth2.googleapis.com/token", data=body)
    token.update(refreshed)
    token["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
    write_json(OAUTH_TOKEN_FILE, token)
    return token


def oauth_headers() -> dict:
    token = token_payload()
    return {"Authorization": f"Bearer {token['access_token']}"}


def oauth_client_details() -> tuple[str, str]:
    if not OAUTH_CLIENT_FILE.exists():
        raise AppError("youtube_oauth_client.json is missing.")
    data = read_json(OAUTH_CLIENT_FILE)
    info = data.get("installed") or data.get("web") or {}
    client_id = info.get("client_id")
    client_secret = info.get("client_secret")
    if not client_id or not client_secret:
        raise AppError("OAuth client JSON is not a valid Google Desktop client.")
    return client_id, client_secret


def find_free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def build_oauth_url(callback_port: int, state: str) -> str:
    client_id, _ = oauth_client_details()
    params = {
        "client_id": client_id,
        "redirect_uri": f"http://127.0.0.1:{callback_port}/oauth/callback",
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def exchange_oauth_code(code: str, redirect_uri: str) -> dict:
    client_id, client_secret = oauth_client_details()
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    token = request_json("https://oauth2.googleapis.com/token", data=body)
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
    write_json(OAUTH_TOKEN_FILE, token)
    return token


def youtube_oauth_get(path: str, params: dict) -> dict:
    url = f"{DATA_API}/{path}?{urllib.parse.urlencode(params)}"
    return request_json(url, headers=oauth_headers())


def analytics_query(params: dict) -> dict:
    url = f"{ANALYTICS_API}?{urllib.parse.urlencode(params)}"
    return request_json(url, headers=oauth_headers())


def reporting_get(path: str, params: dict | None = None) -> dict:
    suffix = f"?{urllib.parse.urlencode(params or {})}" if params else ""
    return request_json(f"{REPORTING_API}/{path}{suffix}", headers=oauth_headers())


def connected_channel() -> dict:
    payload = youtube_oauth_get("channels", {"part": "snippet,contentDetails,statistics", "mine": "true"})
    items = payload.get("items", [])
    if not items:
        raise AppError("OAuth succeeded, but no YouTube channel was found.")
    item = items[0]
    info = {
        "id": item.get("id", ""),
        "title": item.get("snippet", {}).get("title", ""),
        "customUrl": item.get("snippet", {}).get("customUrl", ""),
        "uploads": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
        "connected_at": utc_now(),
    }
    write_json(CHANNEL_CONFIG_FILE, info)
    return info


def latest_channel_videos(count: int) -> list[dict]:
    channel = read_json(CHANNEL_CONFIG_FILE) or connected_channel()
    uploads = channel.get("uploads")
    if not uploads:
        raise AppError("Connected channel has no uploads playlist.")
    playlist = youtube_oauth_get(
        "playlistItems",
        {"part": "contentDetails", "playlistId": uploads, "maxResults": str(max(1, min(count, 50)))},
    )
    ids = [item.get("contentDetails", {}).get("videoId") for item in playlist.get("items", [])]
    ids = [item for item in ids if item]
    if not ids:
        return []
    videos = data_api("videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(ids)})
    return videos.get("items", [])


def channel_analytics(video_ids: list[str], window_days: int) -> dict:
    if not video_ids:
        return {"rows": [], "columnHeaders": []}
    end = dt.date.today()
    start = end - dt.timedelta(days=window_days)
    params = {
        "ids": "channel==MINE",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
        "dimensions": "video",
        "filters": "video==" + ",".join(video_ids),
        "maxResults": str(len(video_ids)),
    }
    return analytics_query(params)


def reach_status() -> tuple[str, str]:
    try:
        report_types = reporting_get("reportTypes", {"includeSystemManaged": "true"}).get("reportTypes", [])
        reach_types = [rt for rt in report_types if "channel_reach" in rt.get("id", "")]
        if not reach_types:
            return "PENDING", "Reach report type is not available yet."
        return "PENDING", "Reach report type exists; bulk download is deferred in this personal MVP."
    except Exception as exc:
        return "PENDING", str(exc)


def write_competitor_reference(path: Path, video: dict, url: str, thumb_source: str, thumb_local: str) -> None:
    snippet = video.get("snippet", {})
    stats = video.get("statistics", {})
    content = video.get("contentDetails", {})
    tags = snippet.get("tags") or []
    lines = [
        "# Competitor Reference",
        "",
        "## Video Metadata",
        f"- Video ID: {video.get('id', '')}",
        f"- Title: {snippet.get('title', '')}",
        f"- Channel: {snippet.get('channelTitle', '')}",
        f"- Channel ID: {snippet.get('channelId', '')}",
        f"- URL: {url}",
        f"- Published: {snippet.get('publishedAt', '')}",
        f"- Duration: {content.get('duration', '')}",
        f"- Views at collection: {stats.get('viewCount', 'UNAVAILABLE')}",
        f"- Likes at collection: {stats.get('likeCount', 'UNAVAILABLE')}",
        f"- Comments at collection: {stats.get('commentCount', 'UNAVAILABLE')}",
        "",
        "## Description",
        snippet.get("description", ""),
        "",
        "## Tags",
    ]
    lines.extend([f"- {tag}" for tag in tags] or ["- UNAVAILABLE"])
    lines.extend(
        [
            "",
            "## Thumbnail",
            f"- Source URL: {thumb_source or 'UNAVAILABLE'}",
            f"- Local path: {thumb_local or 'UNAVAILABLE'}",
            "",
            "## Collection Information",
            f"- Collected at: {utc_now()}",
            "- Data source: YouTube Data API v3",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def create_transcript_template(path: Path, video: dict, url: str) -> None:
    if path.exists():
        return
    snippet = video.get("snippet", {})
    content = video.get("contentDetails", {})
    text = f"""# Competitor Transcript

## Video Information
- Title: {snippet.get('title', '')}
- URL: {url}
- Channel: {snippet.get('channelTitle', '')}
- Language:
- Duration: {content.get('duration', '')}
- Transcript source: Manual
- Added at:

## Transcript
Paste the manually collected transcript below.
Preserve timestamps at meaningful section boundaries where possible.
"""
    path.write_text(text, encoding="utf-8")


def transcript_has_content(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8").strip()
    placeholder_text = "Paste the manually collected transcript below."
    marker = "## Transcript"
    if placeholder_text not in text:
        after = text.split(marker, 1)[-1].strip() if marker in text else text
        return len(after) >= 80
    after = text.split(placeholder_text, 1)[-1].strip()
    after = after.replace("Preserve timestamps at meaningful section boundaries where possible.", "").strip()
    return len(after) >= 80


def workflow_status(project_dir: Path) -> str:
    content = project_dir / "content.md"
    package = project_dir / "publishing_package.md"
    transcript = project_dir / "research" / "competitor_transcript.md"
    workflow_dir = project_dir / "workflow"
    if content.exists() and "## Narration" in content.read_text(encoding="utf-8", errors="ignore") and package.exists():
        return "CONTENT_READY"
    if any(p.exists() and p.stat().st_size > 80 and "TODO: Fill manually" not in p.read_text(encoding="utf-8", errors="ignore") for p in workflow_dir.glob("*.md")):
        return "WORKFLOW_IN_PROGRESS"
    if transcript_has_content(transcript):
        return "READY_FOR_WORKFLOW"
    return "WAITING_FOR_TRANSCRIPT"


def write_channel_files(project_dir: Path, count: int, window_days: int) -> dict:
    input_dir = project_dir / "input"
    raw_dir = input_dir / "_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    channel = read_json(CHANNEL_CONFIG_FILE)
    if not channel:
        try:
            channel = connected_channel()
        except Exception as exc:
            write_channel_learnings(input_dir / "channel_learnings.md", {}, [], {}, "UNAVAILABLE", str(exc), window_days)
            return {"status": "WARNING", "message": str(exc)}

    videos = latest_channel_videos(count)
    video_ids = [item.get("id", "") for item in videos if item.get("id")]
    analytics = {}
    analytics_error = ""
    try:
        analytics = channel_analytics(video_ids, window_days)
    except Exception as exc:
        analytics_error = str(exc)
        analytics = {"rows": [], "columnHeaders": []}
    raw_dir.joinpath("channel_analytics.json").write_text(json.dumps(analytics, indent=2, ensure_ascii=False), encoding="utf-8")

    reach, reach_message = reach_status()
    rows = make_metric_rows(videos, analytics)
    write_metrics_csv(input_dir / "channel_metrics.csv", rows)
    write_channel_learnings(
        input_dir / "channel_learnings.md",
        channel,
        rows,
        analytics,
        reach,
        reach_message or analytics_error,
        window_days,
    )
    return {"status": "PASS" if not analytics_error else "WARNING", "reach": reach, "message": analytics_error or reach_message}


def make_metric_rows(videos: list[dict], analytics: dict) -> list[dict]:
    by_video = {}
    for row in analytics.get("rows", []) or []:
        video_id = row[0]
        by_video[video_id] = {
            "views": row[1] if len(row) > 1 else "",
            "watch_time": row[2] if len(row) > 2 else "",
            "avd": row[3] if len(row) > 3 else "",
            "apv": row[4] if len(row) > 4 else "",
        }
    rows = []
    for video in videos:
        snippet = video.get("snippet", {})
        stats = video.get("statistics", {})
        metrics = by_video.get(video.get("id"), {})
        rows.append(
            {
                "video": snippet.get("title", ""),
                "video_id": video.get("id", ""),
                "published": snippet.get("publishedAt", ""),
                "impressions": "",
                "ctr": "",
                "views": metrics.get("views", stats.get("viewCount", "")),
                "avd": metrics.get("avd", ""),
                "apv": metrics.get("apv", ""),
            }
        )
    return rows


def write_metrics_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["video", "video_id", "published", "impressions", "ctr", "views", "avd", "apv"])
        writer.writeheader()
        writer.writerows(rows)


def write_channel_learnings(path: Path, channel: dict, rows: list[dict], analytics: dict, reach: str, caution: str, window_days: int) -> None:
    approved = MASTER_LEARNINGS_FILE.read_text(encoding="utf-8") if MASTER_LEARNINGS_FILE.exists() else "No approved learnings yet."
    lines = [
        "# Mist of Ages - Channel Learnings",
        "",
        "## Channel Identity",
        f"- Channel: {channel.get('title', 'UNAVAILABLE')}",
        f"- Channel ID: {channel.get('id', 'UNAVAILABLE')}",
        f"- Data window: {window_days} days",
        f"- Collected at: {utc_now()}",
        "",
        "## Current API Snapshot",
        "| Video | Published | Impressions | CTR | Views | AVD | APV |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if rows:
        for row in rows:
            title = str(row["video"]).replace("|", "\\|")
            lines.append(f"| {title} | {row['published']} | {row['impressions'] or 'PENDING'} | {row['ctr'] or 'PENDING'} | {row['views']} | {row['avd']} | {row['apv']} |")
    else:
        lines.append("| UNAVAILABLE |  |  |  |  |  |  |")
    lines.extend(
        [
            "",
            "## Reach Data Status",
            reach,
            "",
            "## Approved Learnings",
            approved.strip(),
            "",
            "## Data Cautions",
            "- Do not declare a winner from low-sample data.",
            "- Compare similar traffic and time windows.",
            "- Missing reach data is not proof of poor distribution.",
        ]
    )
    if caution:
        lines.append(f"- Collection note: {caution}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_project(payload: dict) -> dict:
    ensure_dirs()
    url = (payload.get("url") or "").strip()
    video_id = parse_video_id(url)
    video = fetch_competitor_video(video_id)
    snippet = video.get("snippet", {})
    title = payload.get("project_name") or snippet.get("title") or video_id
    slug = safe_slug(title, video_id)
    if not slug.endswith(video_id.lower()[:6]):
        slug = f"{slug}-{video_id[:6]}"
    project_dir = PROJECTS_DIR / slug
    suffix = 2
    while project_dir.exists() and read_json(project_dir / "project.json").get("source_video_id") != video_id:
        project_dir = PROJECTS_DIR / f"{slug}-{suffix}"
        suffix += 1

    input_dir = project_dir / "input"
    assets_dir = input_dir / "assets"
    raw_dir = input_dir / "_raw"
    research_dir = project_dir / "research"
    workflow_dir = project_dir / "workflow"
    for directory in (assets_dir, raw_dir, research_dir, workflow_dir):
        directory.mkdir(parents=True, exist_ok=True)

    raw_dir.joinpath("competitor_video.json").write_text(json.dumps(video, indent=2, ensure_ascii=False), encoding="utf-8")
    _, thumb_url = choose_thumbnail(snippet.get("thumbnails", {}))
    thumb_local = download_thumbnail(thumb_url, assets_dir)
    write_competitor_reference(input_dir / "competitor_reference.md", video, url, thumb_url, thumb_local)
    create_transcript_template(research_dir / "competitor_transcript.md", video, url)

    channel_result = write_channel_files(
        project_dir,
        int(payload.get("recent_count") or 10),
        int(payload.get("window_days") or 28),
    )
    status = workflow_status(project_dir)
    project_json = {
        "project_type": "mist_of_ages_research",
        "project_slug": project_dir.name,
        "source_video_id": video_id,
        "source_video_url": url,
        "mist_of_ages_channel_id": read_json(CHANNEL_CONFIG_FILE).get("id", ""),
        "status": status,
        "runnable": status == "CONTENT_READY",
        "created_at": read_json(project_dir / "project.json").get("created_at", utc_now()),
        "updated_at": utc_now(),
    }
    write_json(project_dir / "project.json", project_json)
    return {
        "project": project_json,
        "project_path": str(project_dir),
        "thumbnail": thumb_local,
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "duration": video.get("contentDetails", {}).get("duration", ""),
        "channel_result": channel_result,
        "validation": validate_project(project_dir.name),
    }


def validate_project(slug: str) -> dict:
    project_dir = PROJECTS_DIR / slug
    input_dir = project_dir / "input"
    transcript = project_dir / "research" / "competitor_transcript.md"
    checks = {
        "Reference": (input_dir / "competitor_reference.md").exists(),
        "Thumbnail": any((input_dir / "assets").glob("competitor_thumbnail.*")),
        "Channel Learnings": (input_dir / "channel_learnings.md").exists(),
        "Channel Metrics": (input_dir / "channel_metrics.csv").exists(),
        "Manual Transcript": transcript_has_content(transcript),
    }
    status = workflow_status(project_dir)
    write_json(
        project_dir / "project.json",
        {**read_json(project_dir / "project.json"), "status": status, "runnable": status == "CONTENT_READY", "updated_at": utc_now()},
    )
    next_action = "Run Prompt 1 with the three input files." if status == "READY_FOR_WORKFLOW" else "Paste transcript into research/competitor_transcript.md."
    if status == "CONTENT_READY":
        next_action = "Existing video pipeline can use content.md."
    return {"checks": checks, "workflow_status": status, "next_action": next_action}


def save_transcript(payload: dict) -> dict:
    slug = payload.get("project_slug")
    text = payload.get("transcript", "")
    if not slug:
        raise AppError("project_slug is required.")
    path = PROJECTS_DIR / slug / "research" / "competitor_transcript.md"
    if not path.exists():
        raise AppError("Transcript file does not exist.")
    current = path.read_text(encoding="utf-8")
    header = current.split("## Transcript", 1)[0].rstrip()
    saved = f"{header}\n\n## Transcript\n{text.strip()}\n"
    path.write_text(saved, encoding="utf-8")
    return validate_project(slug)


def app_status() -> dict:
    channel = read_json(CHANNEL_CONFIG_FILE)
    token = read_json(OAUTH_TOKEN_FILE)
    return {
        "api_key": mask_secret(first_valid_api_key()),
        "oauth_client": "FOUND" if OAUTH_CLIENT_FILE.exists() else "MISSING",
        "oauth_token": "FOUND" if token else "MISSING",
        "channel": channel,
        "master_learnings": str(MASTER_LEARNINGS_FILE),
        "projects": sorted([p.name for p in PROJECTS_DIR.glob("*") if p.is_dir()]) if PROJECTS_DIR.exists() else [],
    }


def default_token_provider(root: Path | str, channel_slug: str) -> str:
    return channel_oauth.get_access_token_for_channel(root, channel_slug, transport=default_transport)


def default_data_api_fetcher(
    *,
    root: Path | str,
    channel_slug: str,
    access_token: str,
    path: str,
    params: dict[str, str],
) -> dict:
    return request_json(
        f"{DATA_API}/{path}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def default_analytics_query_api_fetcher(
    *,
    root: Path | str,
    channel_slug: str,
    access_token: str,
    params: dict[str, str],
) -> dict:
    return request_json(
        f"{ANALYTICS_API}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def default_reporting_api_fetcher(
    *,
    root: Path | str,
    channel_slug: str,
    access_token: str,
    method: str,
    path: str,
    params: dict[str, str] | None,
    payload: dict | None,
) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    suffix = f"?{urllib.parse.urlencode(params)}" if params else ""
    return request_json(
        f"{REPORTING_API}/{path}{suffix}",
        headers=headers,
        data=body,
    )


def default_report_download_fetcher(
    *,
    root: Path | str,
    channel_slug: str,
    access_token: str,
    url: str,
) -> bytes:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AppError(detail or str(exc), exc.code) from exc
    except urllib.error.URLError as exc:
        raise AppError(f"Network error: {exc.reason}") from exc


def default_recent_videos_fetcher(
    *,
    root: Path | str,
    channel_slug: str,
    access_token: str,
    recent_count: int,
    channel: dict,
) -> dict:
    channel_payload = request_json(
        f"{DATA_API}/channels?{urllib.parse.urlencode({'part': 'contentDetails', 'id': channel['youtube_channel_id']})}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    items = channel_payload.get("items", [])
    if not items:
        raise AppError("No uploads playlist found for the selected channel.", 404)
    uploads = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads:
        raise AppError("Selected channel has no uploads playlist.", 404)
    playlist_payload = request_json(
        f"{DATA_API}/playlistItems?{urllib.parse.urlencode({'part': 'contentDetails', 'playlistId': uploads, 'maxResults': str(max(1, min(recent_count, 50)))})}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    ids = [item.get("contentDetails", {}).get("videoId") for item in playlist_payload.get("items", [])]
    ids = [item for item in ids if item]
    videos = (
        request_json(
            f"{DATA_API}/videos?{urllib.parse.urlencode({'part': 'snippet,statistics', 'id': ','.join(ids)})}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if ids
        else {"items": []}
    )
    return {"items": videos.get("items", [])}


def default_analytics_fetcher(
    *,
    root: Path | str,
    channel_slug: str,
    access_token: str,
    window_days: int,
    recent_count: int,
    channel: dict,
    recent_payload: dict,
) -> dict:
    video_ids = [item.get("id") for item in recent_payload.get("items", []) if item.get("id")]
    if not video_ids:
        return {"columnHeaders": [], "rows": []}
    end = dt.date.today()
    start = end - dt.timedelta(days=window_days)
    params = {
        "ids": "channel==MINE",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
        "dimensions": "video",
        "filters": "video==" + ",".join(video_ids),
        "maxResults": str(len(video_ids)),
    }
    return request_json(
        f"{ANALYTICS_API}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def default_reporting_fetcher(
    *,
    root: Path | str,
    channel_slug: str,
    access_token: str,
    window_days: int,
    recent_count: int,
    channel: dict,
    recent_payload: dict,
) -> dict:
    report_types = request_json(
        f"{REPORTING_API}/reportTypes?{urllib.parse.urlencode({'includeSystemManaged': 'true'})}",
        headers={"Authorization": f"Bearer {access_token}"},
    ).get("reportTypes", [])
    reach_types = [rt for rt in report_types if "channel_reach" in rt.get("id", "")]
    if not reach_types:
        return {
            "status": "PENDING",
            "report_type": None,
            "message": "Reach report type is not available yet.",
            "available_metrics": [],
            "pending_metrics": ["thumbnail_impressions", "thumbnail_ctr"],
            "rows": [],
        }
    return {
        "status": "PENDING",
        "report_type": reach_types[0].get("id"),
        "message": "Reach report type exists; reach metrics are pending.",
        "available_metrics": [],
        "pending_metrics": ["thumbnail_impressions", "thumbnail_ctr"],
        "rows": [],
    }


def normalize_competitor_metadata(video: dict, source_url: str, thumbnail_url: str | None) -> dict:
    snippet = video.get("snippet", {})
    statistics = video.get("statistics", {})
    content = video.get("contentDetails", {})
    return {
        "title": snippet.get("title", ""),
        "channelTitle": snippet.get("channelTitle", ""),
        "channelId": snippet.get("channelId", ""),
        "publishedAt": snippet.get("publishedAt", ""),
        "duration": content.get("duration", ""),
        "description": snippet.get("description", ""),
        "tags": snippet.get("tags") or [],
        "viewCount": statistics.get("viewCount", "0"),
        "likeCount": statistics.get("likeCount", "0"),
        "commentCount": statistics.get("commentCount", "0"),
        "thumbnailUrl": thumbnail_url or "",
        "url": source_url,
    }


def build_app_context(
    *,
    root: Path | str | None = None,
    competitor_video_fetcher=None,
    thumbnail_fetcher=None,
    metrics_syncer=None,
    token_provider=None,
    recent_videos_fetcher=None,
    analytics_fetcher=None,
    reporting_fetcher=None,
    oauth_flow_starter=None,
    oauth_transport=None,
    path_opener=None,
) -> dict:
    return {
        "root": Path(root or ROOT).resolve(),
        "competitor_video_fetcher": competitor_video_fetcher or fetch_competitor_video,
        "thumbnail_fetcher": thumbnail_fetcher or fetch_competitor_thumbnail,
        "metrics_syncer": metrics_syncer or channel_metrics.sync_channel_metrics,
        "token_provider": token_provider or default_token_provider,
        "data_api_fetcher": default_data_api_fetcher,
        "analytics_query_api_fetcher": default_analytics_query_api_fetcher,
        "reporting_api_fetcher": default_reporting_api_fetcher,
        "report_download_fetcher": default_report_download_fetcher,
        "recent_videos_fetcher": recent_videos_fetcher or default_recent_videos_fetcher,
        "analytics_fetcher": analytics_fetcher or default_analytics_fetcher,
        "reporting_fetcher": reporting_fetcher or default_reporting_fetcher,
        "oauth_flow_starter": oauth_flow_starter or channel_oauth_browser.start_oauth_browser_flow,
        "oauth_transport": oauth_transport or default_transport,
        "path_opener": path_opener or (lambda path: os.startfile(str(path))),
    }


APP_CONTEXT = build_app_context()


def _v2_error(code: str, message: str, status: int) -> V2Error:
    return V2Error(code, message, status)


def _sanitize_channel_summary(root: Path | str, channel: dict) -> dict:
    project_count = len(channel_projects.list_channel_projects(root, channel["channel_slug"]))
    return {
        "channel_slug": channel["channel_slug"],
        "display_name": channel["display_name"],
        "youtube_channel_id": channel["youtube_channel_id"],
        "youtube_handle": channel["youtube_handle"],
        "status": channel["status"],
        "last_connected_at": channel["last_connected_at"],
        "last_metrics_sync_at": channel["last_metrics_sync_at"],
        "project_count": project_count,
    }


def _load_channel_or_error(root: Path | str, channel_slug: str) -> dict:
    try:
        valid_slug = channel_workspace.validate_channel_slug(channel_slug)
    except channel_workspace.ChannelWorkspaceError as exc:
        raise _v2_error("INVALID_CHANNEL_SLUG", str(exc), 400) from exc
    try:
        return channel_workspace.load_channel(root, valid_slug)
    except channel_workspace.ChannelWorkspaceError as exc:
        raise _v2_error("CHANNEL_NOT_FOUND", "Selected channel was not found.", 404) from exc


def _map_project_error(exc: Exception) -> V2Error:
    message = str(exc)
    if "Duplicate source_video_id" in message:
        return _v2_error("SOURCE_VIDEO_ALREADY_EXISTS", "This competitor video already exists in the selected channel.", 409)
    if "Transcript already contains real content" in message:
        return _v2_error("TRANSCRIPT_OVERWRITE_REQUIRED", "Transcript already contains real content. Set overwrite to replace it.", 409)
    if "project.json does not exist" in message:
        return _v2_error("PROJECT_NOT_FOUND", "Selected project was not found.", 404)
    if "Required channel" in message:
        return _v2_error("CHANNEL_METRICS_NOT_READY", "Channel learnings or metrics are not ready. Sync metrics first.", 409)
    return _v2_error("INVALID_REQUEST", message, 400)


def _map_workflow_error(exc: channel_workflow.ChannelWorkflowError) -> V2Error:
    return _v2_error(exc.code, exc.message, exc.status)


def _map_prompt_bundle_error(exc: channel_prompt_bundle.PromptBundleError) -> V2Error:
    return _v2_error(exc.code, exc.message, exc.status)


def _map_output_parser_error(exc: channel_output_parser.ChannelOutputParserError) -> V2Error:
    return _v2_error(exc.code, exc.message, exc.status)


def _map_production_export_error(exc: channel_production_export.ProductionExportError) -> V2Error:
    return _v2_error(exc.code, exc.message, exc.status)


def _map_channel_analytics_error(exc: channel_analytics_collector.ChannelAnalyticsCollectorError) -> V2Error:
    return _v2_error(exc.code, exc.message, exc.status)


def _map_workflow_write_error(exc: channel_workflow_write.ChannelWorkflowWriteError) -> V2Error:
    return _v2_error(exc.code, exc.message, exc.status)


def _channel_status_payload(root: Path | str, channel_slug: str) -> dict:
    channel = _load_channel_or_error(root, channel_slug)
    paths = channel_workspace.canonical_channel_paths(root, channel_slug)
    reporting_state = {}
    if paths.reporting_state_json.exists():
        try:
            reporting_state = json.loads(paths.reporting_state_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            reporting_state = {}
    return {
        "channel": _sanitize_channel_summary(root, channel),
        "available_workflows": channel_workflow.list_channel_workflow_options(root, channel_slug),
        "learnings": {
            "path": paths.channel_learnings_master.relative_to(Path(root)).as_posix(),
            "exists": paths.channel_learnings_master.exists(),
            "non_empty": paths.channel_learnings_master.exists() and bool(paths.channel_learnings_master.read_bytes().strip()),
        },
        "metrics": {
            "path": paths.channel_metrics_csv.relative_to(Path(root)).as_posix(),
            "exists": paths.channel_metrics_csv.exists(),
            "non_empty": paths.channel_metrics_csv.exists() and bool(paths.channel_metrics_csv.read_bytes().strip()),
        },
        "reporting": reporting_state,
        "project_count": len(channel_projects.list_channel_projects(root, channel_slug)),
    }


def _load_project_or_error(root: Path | str, channel_slug: str, project_slug: str) -> dict:
    _load_channel_or_error(root, channel_slug)
    try:
        return channel_projects.load_channel_project(root, channel_slug, project_slug)
    except channel_projects.ChannelProjectError as exc:
        raise _map_project_error(exc) from exc


def _safe_open_path(root: Path | str, target: Path, opener) -> dict:
    resolved_root = Path(root).resolve()
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise _v2_error("PATH_OPEN_FAILED", "Requested path is outside the repository root.", 400) from exc
    banned_parts = {"secrets", "youtube_oauth_client.json", "youtube_oauth_token.json", "youtube_api_key.txt"}
    lowered = {part.lower() for part in resolved_target.parts}
    if "secrets" in lowered:
        raise _v2_error("PATH_OPEN_FAILED", "Secret paths cannot be opened through the API.", 403)
    try:
        opener(resolved_target)
    except Exception as exc:
        raise _v2_error("PATH_OPEN_FAILED", "The requested path could not be opened.", 500) from exc
    return {"ok": True}


def _client_prefers_json_redirect(headers) -> bool:
    if not headers:
        return False
    accept = ""
    try:
        accept = headers.get("Accept", "")
    except Exception:
        accept = ""
    return "application/json" in (accept or "").lower()


def dispatch_v2_request(method: str, path: str, payload: dict | None = None, *, context: dict | None = None) -> tuple[int, dict]:
    ctx = context or APP_CONTEXT
    root = ctx["root"]
    payload = payload or {}
    parsed = urllib.parse.urlparse(path)
    route = parsed.path
    query = urllib.parse.parse_qs(parsed.query)
    parts = [part for part in route.split("/") if part]
    if len(parts) < 2 or parts[0] != "api" or parts[1] != "v2":
        raise _v2_error("INVALID_REQUEST", "Invalid v2 route.", 404)

    try:
        if method == "GET" and parts == ["api", "v2", "channels"]:
            channels = channel_workspace.list_channels(root)
            return 200, {"channels": [_sanitize_channel_summary(root, channel) for channel in channels]}

        if method == "GET" and parts == ["api", "v2", "oauth", "start"]:
            channel_slug = (query.get("channel_slug") or [""])[0]
            mode = (query.get("mode") or [""])[0]
            try:
                flow = ctx["oauth_flow_starter"](
                    root=root,
                    channel_slug=channel_slug,
                    mode=mode,
                    transport=ctx["oauth_transport"],
                )
            except channel_oauth_browser.OAuthFlowInvalidError as exc:
                if "already exists" in str(exc):
                    raise _v2_error("CHANNEL_ALREADY_EXISTS", "Channel workspace already exists.", 409) from exc
                if "does not exist" in str(exc):
                    raise _v2_error("CHANNEL_NOT_FOUND", "Selected channel was not found for reconnect.", 404) from exc
                raise _v2_error("OAUTH_FLOW_INVALID", str(exc), 400) from exc
            except channel_oauth.OAuthConfigurationError as exc:
                raise _v2_error("OAUTH_CONNECTION_FAILED", str(exc), 500) from exc
            return 302, {"redirect_url": flow.authorization_url}

        if len(parts) >= 4 and parts[0:3] == ["api", "v2", "channels"]:
            channel_slug = parts[3]
            if method == "GET" and len(parts) == 4:
                return 200, _channel_status_payload(root, channel_slug)
            if method == "GET" and len(parts) == 5 and parts[4] == "analytics":
                _load_channel_or_error(root, channel_slug)
                try:
                    analytics_status = channel_analytics_collector.load_channel_analytics_status(root, channel_slug)
                except channel_analytics_collector.ChannelAnalyticsCollectorError as exc:
                    raise _map_channel_analytics_error(exc) from exc
                return 200, {"analytics": analytics_status}
            if method == "POST" and len(parts) == 6 and parts[4] == "analytics" and parts[5] == "discover":
                _load_channel_or_error(root, channel_slug)
                try:
                    snapshot = channel_analytics_collector.discover_channel_analytics_capabilities(
                        root,
                        channel_slug,
                        token_provider=ctx["token_provider"],
                        reporting_api_fetcher=ctx["reporting_api_fetcher"],
                    )
                except channel_analytics_collector.ChannelAnalyticsCollectorError as exc:
                    raise _map_channel_analytics_error(exc) from exc
                return 200, {"capabilities": snapshot}
            if method == "POST" and len(parts) == 6 and parts[4] == "analytics" and parts[5] == "sync":
                _load_channel_or_error(root, channel_slug)
                window_days = int(payload.get("window_days", 365))
                try:
                    analytics_status = channel_analytics_collector.sync_channel_analytics(
                        root,
                        channel_slug,
                        token_provider=ctx["token_provider"],
                        data_api_fetcher=ctx["data_api_fetcher"],
                        analytics_query_fetcher=ctx["analytics_query_api_fetcher"],
                        reporting_api_fetcher=ctx["reporting_api_fetcher"],
                        report_download_fetcher=ctx["report_download_fetcher"],
                        window_days=window_days,
                    )
                except channel_analytics_collector.ChannelAnalyticsCollectorError as exc:
                    raise _map_channel_analytics_error(exc) from exc
                return 200, {"analytics": analytics_status}
            if method == "GET" and len(parts) == 6 and parts[4] == "analytics" and parts[5] == "export":
                _load_channel_or_error(root, channel_slug)
                try:
                    download = channel_analytics_collector.build_channel_analytics_export(root, channel_slug)
                except channel_analytics_collector.ChannelAnalyticsCollectorError as exc:
                    raise _map_channel_analytics_error(exc) from exc
                return 200, {
                    "__binary__": download["body_bytes"],
                    "content_type": download["content_type"],
                    "filename": download["filename"],
                }
            if method == "GET" and len(parts) == 5 and parts[4] == "projects":
                _load_channel_or_error(root, channel_slug)
                return 200, {"projects": channel_projects.list_channel_projects(root, channel_slug)}
            if method == "POST" and len(parts) == 5 and parts[4] == "open":
                channel = _load_channel_or_error(root, channel_slug)
                target = channel_workspace.canonical_channel_paths(root, channel["channel_slug"]).channel_dir
                return 200, _safe_open_path(root, target, ctx["path_opener"])
            if method == "POST" and len(parts) == 5 and parts[4] == "sync_metrics":
                _load_channel_or_error(root, channel_slug)
                window_days = int(payload.get("window_days", 90))
                recent_count = int(payload.get("recent_count", 12))
                if window_days < 1 or window_days > 365 or recent_count < 1 or recent_count > 50:
                    raise _v2_error("INVALID_REQUEST", "window_days or recent_count is out of range.", 400)
                try:
                    result = ctx["metrics_syncer"](
                        root,
                        channel_slug,
                        analytics_fetcher=ctx["analytics_fetcher"],
                        recent_videos_fetcher=ctx["recent_videos_fetcher"],
                        reporting_fetcher=ctx["reporting_fetcher"],
                        token_provider=ctx["token_provider"],
                        window_days=window_days,
                        recent_count=recent_count,
                    )
                except channel_metrics.ChannelMetricsReconnectRequiredError as exc:
                    raise _v2_error("OAUTH_RECONNECT_REQUIRED", str(exc), 409) from exc
                except channel_metrics.ChannelMetricsError as exc:
                    raise _v2_error("INVALID_REQUEST", str(exc), 400) from exc
                return 200, {"sync": result}
            if method == "POST" and len(parts) == 5 and parts[4] == "projects":
                _load_channel_or_error(root, channel_slug)
                unsupported_authority_fields = {
                    "workflow_definition_sha256",
                    "workflow_definition_path",
                    "prompt_manifest_path",
                    "artifact_paths",
                    "registry_path",
                }
                unsupported = sorted(field for field in unsupported_authority_fields if field in payload)
                if unsupported:
                    raise _v2_error("INVALID_REQUEST", f"Unsupported workflow authority fields: {', '.join(unsupported)}.", 400)
                competitor_url = payload.get("competitor_url", payload.get("url", ""))
                project_name = payload.get("project_name")
                try:
                    workflow_binding = channel_workflow.resolve_explicit_channel_workflow_binding(
                        root,
                        channel_slug,
                        payload.get("workflow_id"),
                        payload.get("workflow_version"),
                    )
                except channel_workflow.ChannelWorkflowError as exc:
                    raise _map_workflow_error(exc) from exc
                try:
                    video_id = parse_video_id(competitor_url)
                    video = ctx["competitor_video_fetcher"](video_id)
                except AppError as exc:
                    raise _v2_error("YOUTUBE_API_ERROR", exc.message, exc.status) from exc
                except Exception as exc:
                    raise _v2_error("YOUTUBE_API_ERROR", str(exc), 400) from exc
                _, thumb_url = choose_thumbnail(video.get("snippet", {}).get("thumbnails", {}))
                thumb_bytes, thumb_ext = ctx["thumbnail_fetcher"](thumb_url)
                metadata = normalize_competitor_metadata(video, competitor_url, thumb_url)
                try:
                    project = channel_projects.create_channel_project(
                        root,
                        channel_slug,
                        source_video_id=video_id,
                        source_video_url=competitor_url,
                        source_metadata=metadata,
                        project_name=project_name,
                        thumbnail_bytes=thumb_bytes,
                        thumbnail_extension=thumb_ext,
                        workflow_binding=workflow_binding,
                    )
                except channel_projects.ChannelProjectError as exc:
                    raise _map_project_error(exc) from exc
                return 200, {"project": channel_projects._project_summary(project)}
            if len(parts) == 6 and parts[4] == "projects" and method == "GET":
                project_slug = parts[5]
                project = _load_project_or_error(root, channel_slug, project_slug)
                project_path = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug
                summary = channel_projects.list_channel_projects(root, channel_slug)
                item = next((entry for entry in summary if entry["project_slug"] == project_slug), None)
                if not item:
                    item = {
                        "project_slug": project["project_slug"],
                        "channel_slug": project["channel_slug"],
                        "youtube_channel_id": project["youtube_channel_id"],
                        "source_video_id": project["source_video_id"],
                        "source_video_url": project["source_video_url"],
                        "status": project["status"],
                        "workflow_input_status": project["workflow_input_status"],
                        "runnable": project["runnable"],
                        "created_at": project["created_at"],
                        "updated_at": project["updated_at"],
                    }
                item["has_content"] = (project_path / "content.md").exists()
                item["has_publishing_package"] = (project_path / "publishing_package.md").exists()
                return 200, {"project": item}
            if len(parts) == 7 and parts[4] == "projects" and parts[6] == "workflow" and method == "GET":
                project_slug = parts[5]
                project = _load_project_or_error(root, channel_slug, project_slug)
                project_dir = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug
                try:
                    workflow = channel_workflow.build_workflow_read_model(
                        root,
                        channel_slug,
                        project_slug,
                        project,
                        project_dir,
                    )
                except channel_workflow.ChannelWorkflowError as exc:
                    raise _map_workflow_error(exc) from exc
                return 200, workflow
            if len(parts) == 7 and parts[4] == "projects" and parts[6] == "production-package" and method == "GET":
                project_slug = parts[5]
                project = _load_project_or_error(root, channel_slug, project_slug)
                project_dir = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug
                try:
                    summary = channel_production_export.build_production_package_summary(
                        root,
                        channel_slug,
                        project_slug,
                        project=project,
                        project_dir=project_dir,
                    )
                except channel_production_export.ProductionExportError as exc:
                    raise _map_production_export_error(exc) from exc
                except channel_workflow.ChannelWorkflowError as exc:
                    raise _map_workflow_error(exc) from exc
                except channel_workflow_write.ChannelWorkflowWriteError as exc:
                    raise _map_workflow_write_error(exc) from exc
                return 200, {"production_package": summary}
            if len(parts) == 8 and parts[4] == "projects" and parts[6] == "production-package" and parts[7] == "download" and method == "GET":
                project_slug = parts[5]
                project = _load_project_or_error(root, channel_slug, project_slug)
                project_dir = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug
                try:
                    download = channel_production_export.build_production_package_download(
                        root,
                        channel_slug,
                        project_slug,
                        project=project,
                        project_dir=project_dir,
                    )
                except channel_production_export.ProductionExportError as exc:
                    raise _map_production_export_error(exc) from exc
                except channel_workflow.ChannelWorkflowError as exc:
                    raise _map_workflow_error(exc) from exc
                except channel_workflow_write.ChannelWorkflowWriteError as exc:
                    raise _map_workflow_write_error(exc) from exc
                return 200, {
                    "__binary__": download["body_bytes"],
                    "content_type": download["content_type"],
                    "filename": download["filename"],
                }
            if len(parts) == 10 and parts[4] == "projects" and parts[6] == "workflow" and parts[7] == "steps" and parts[9] == "bundle" and method == "GET":
                project_slug = parts[5]
                step_id = parts[8]
                project = _load_project_or_error(root, channel_slug, project_slug)
                project_dir = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug
                try:
                    bundle = channel_prompt_bundle.build_prompt_bundle(
                        root,
                        channel_slug,
                        project_slug,
                        step_id,
                        project,
                        project_dir,
                    )
                except channel_prompt_bundle.PromptBundleError as exc:
                    raise _map_prompt_bundle_error(exc) from exc
                except channel_workflow_write.ChannelWorkflowWriteError as exc:
                    raise _map_workflow_write_error(exc) from exc
                except channel_workflow.ChannelWorkflowError as exc:
                    raise _map_workflow_error(exc) from exc
                return 200, bundle
            if len(parts) == 10 and parts[4] == "projects" and parts[6] == "workflow" and parts[7] == "steps" and parts[9] == "parse-output" and method == "POST":
                project_slug = parts[5]
                step_id = parts[8]
                project = _load_project_or_error(root, channel_slug, project_slug)
                project_dir = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug
                try:
                    parsed_output = channel_output_parser.parse_channel_output(
                        root,
                        channel_slug,
                        project_slug,
                        step_id,
                        payload.get("bundle_sha256"),
                        payload.get("output_text"),
                        project,
                        project_dir,
                    )
                except channel_output_parser.ChannelOutputParserError as exc:
                    raise _map_output_parser_error(exc) from exc
                except channel_prompt_bundle.PromptBundleError as exc:
                    raise _map_prompt_bundle_error(exc) from exc
                except channel_workflow_write.ChannelWorkflowWriteError as exc:
                    raise _map_workflow_write_error(exc) from exc
                except channel_workflow.ChannelWorkflowError as exc:
                    raise _map_workflow_error(exc) from exc
                return 200, parsed_output
            if len(parts) == 10 and parts[4] == "projects" and parts[6] == "workflow" and parts[7] == "steps" and parts[9] == "revisions" and method == "POST":
                project_slug = parts[5]
                step_id = parts[8]
                try:
                    status, data = channel_workflow_write.save_candidate(
                        root,
                        channel_slug,
                        project_slug,
                        step_id,
                        payload.get("bundle_sha256"),
                        payload.get("output_text"),
                        payload.get("expected_state_revision"),
                    )
                except channel_workflow_write.ChannelWorkflowWriteError as exc:
                    raise _map_workflow_write_error(exc) from exc
                return status, data
            if len(parts) == 11 and parts[4] == "projects" and parts[6] == "workflow" and parts[7] == "steps" and parts[9] == "candidate" and parts[10] in {"approve", "reject"} and method == "POST":
                project_slug = parts[5]
                step_id = parts[8]
                try:
                    if parts[10] == "approve":
                        status, data = channel_workflow_write.approve_candidate(
                            root,
                            channel_slug,
                            project_slug,
                            step_id,
                            payload.get("candidate_group_id"),
                            payload.get("expected_state_revision"),
                        )
                    else:
                        status, data = channel_workflow_write.reject_candidate(
                            root,
                            channel_slug,
                            project_slug,
                            step_id,
                            payload.get("candidate_group_id"),
                            payload.get("expected_state_revision"),
                        )
                except channel_workflow_write.ChannelWorkflowWriteError as exc:
                    raise _map_workflow_write_error(exc) from exc
                return status, data
            if len(parts) == 7 and parts[4] == "projects" and parts[6] == "transcript" and method == "POST":
                project_slug = parts[5]
                try:
                    result = channel_projects.save_project_transcript(
                        root,
                        channel_slug,
                        project_slug,
                        payload.get("transcript", ""),
                        overwrite=bool(payload.get("overwrite", False)),
                    )
                except channel_projects.ChannelProjectError as exc:
                    raise _map_project_error(exc) from exc
                return 200, result
            if len(parts) == 7 and parts[4] == "projects" and parts[6] == "transcript" and method == "GET":
                project_slug = parts[5]
                try:
                    channel_projects.load_channel_project(root, channel_slug, project_slug)
                except channel_projects.ChannelProjectError as exc:
                    mapped = _map_project_error(exc)
                    if mapped.code == "PROJECT_NOT_FOUND":
                        raise _v2_error("TRANSCRIPT_NOT_FOUND", "Transcript file was not found.", 404) from exc
                    raise mapped from exc
                transcript_path = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug / "research" / "competitor_transcript.md"
                if not transcript_path.exists():
                    raise _v2_error("TRANSCRIPT_NOT_FOUND", "Transcript file was not found.", 404)
                content = transcript_path.read_text(encoding="utf-8")
                return 200, {
                    "transcript": content,
                    "is_template": channel_projects.is_transcript_template(transcript_path),
                    "has_real_content": channel_projects.transcript_has_real_content(transcript_path),
                }
            if len(parts) == 7 and parts[4] == "projects" and parts[6] == "open" and method == "POST":
                project_slug = parts[5]
                _load_project_or_error(root, channel_slug, project_slug)
                target = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug
                return 200, _safe_open_path(root, target, ctx["path_opener"])
            if len(parts) == 7 and parts[4] == "projects" and parts[6] == "open_transcript" and method == "POST":
                project_slug = parts[5]
                _load_project_or_error(root, channel_slug, project_slug)
                target = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug / "research" / "competitor_transcript.md"
                if not target.exists():
                    raise _v2_error("TRANSCRIPT_NOT_FOUND", "Transcript file was not found.", 404)
                return 200, _safe_open_path(root, target, ctx["path_opener"])
            if len(parts) == 7 and parts[4] == "projects" and parts[6] == "validate" and method == "POST":
                project_slug = parts[5]
                try:
                    result = channel_projects.validate_channel_project(root, channel_slug, project_slug)
                except channel_projects.ChannelProjectError as exc:
                    raise _map_project_error(exc) from exc
                return 200, result
    except V2Error:
        raise
    except Exception as exc:
        raise _v2_error("INTERNAL_ERROR", "An unexpected server error occurred.", 500) from exc

    raise _v2_error("INVALID_REQUEST", "Route not found.", 404)


HTML_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mist of Ages Research</title>
  <style>
    :root { color-scheme: light; --ink:#1f2933; --muted:#667085; --line:#d6dde6; --soft-line:#e7edf3; --bg:#f3f6fa; --panel:#ffffff; --accent:#0f766e; --accent-2:#155eef; --warn:#b45309; --bad:#b42318; --good:#027a48; --shadow:0 1px 2px rgba(16,24,40,.04); }
    * { box-sizing:border-box; }
    body { margin:0; font-family: Arial, Helvetica, sans-serif; background:var(--bg); color:var(--ink); }
    a { color:var(--accent-2); text-decoration:none; }
    a:hover { text-decoration:underline; }
    button, a, select, input, textarea, summary { outline-offset:2px; }
    .app-header { padding:18px 24px; background:#102a43; color:#fff; display:flex; justify-content:space-between; gap:18px; align-items:flex-start; }
    .app-header h1 { margin:0; font-size:24px; letter-spacing:0; }
    .app-header p { margin:6px 0 0; color:#d9e2ec; font-size:14px; }
    .app-header-tools { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:10px; align-items:stretch; }
    .header-chip { min-width:160px; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.12); border-radius:8px; padding:10px 12px; }
    .header-chip span { display:block; color:#bcccdc; font-size:12px; margin-bottom:4px; }
    .header-chip strong { display:block; font-size:14px; line-height:1.35; }
    .header-chip .pill { margin-top:2px; }
    .app-shell { max-width:1320px; margin:0 auto; padding:20px; display:grid; grid-template-columns: 300px minmax(0, 1fr); gap:18px; align-items:start; }
    .sidebar { display:grid; gap:16px; position:sticky; top:16px; }
    .workspace { min-width:0; display:grid; gap:16px; }
    .panel { background:var(--panel); border:1px solid var(--soft-line); border-radius:8px; padding:16px; box-shadow:var(--shadow); }
    .panel-muted { background:#f8fafc; }
    h2 { margin:0 0 12px; font-size:18px; }
    h3 { margin:0 0 8px; font-size:15px; }
    label { display:block; margin:12px 0 6px; font-weight:700; font-size:13px; }
    input, select, textarea { width:100%; border:1px solid #c7d1dd; border-radius:6px; padding:10px; font:inherit; background:#fff; }
    textarea { min-height:190px; resize:vertical; }
    button { border:0; border-radius:6px; padding:10px 12px; background:var(--accent); color:#fff; font-weight:700; cursor:pointer; }
    button.primary { background:var(--accent); color:#fff; }
    button.secondary { background:#334e68; color:#fff; }
    button.success { background:var(--good); color:#fff; }
    button.ghost { background:#eef2f6; color:#243b53; border:1px solid #c7d1dd; }
    button.danger { background:#b42318; }
    button:disabled { opacity:.5; cursor:not-allowed; }
    .action-link { display:inline-flex; align-items:center; justify-content:center; border-radius:6px; padding:10px 12px; font-weight:700; border:1px solid transparent; text-decoration:none; }
    .action-link.primary { background:var(--accent); color:#fff; }
    .action-link.secondary { background:#eef2f6; color:#243b53; border-color:#c7d1dd; }
    .action-link.success { background:#ecfdf3; color:#027a48; border-color:#abefc6; }
    .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .status { display:grid; gap:8px; }
    .pill { display:inline-flex; align-items:center; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:700; background:#eef2f6; color:#334e68; }
    .pass { color:#027a48; background:#ecfdf3; }
    .missing { color:var(--bad); background:#fef3f2; }
    .pending { color:var(--warn); background:#fffaeb; }
    .result { display:grid; gap:14px; }
    .meta { color:var(--muted); font-size:14px; line-height:1.5; overflow-wrap:anywhere; }
    .checks { display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap:8px; }
    .check { border:1px solid var(--soft-line); border-radius:6px; padding:10px; display:flex; justify-content:space-between; gap:8px; background:#fff; }
    .path { font-family: Consolas, monospace; font-size:13px; background:#f8fafc; border:1px solid var(--line); border-radius:6px; padding:10px; overflow-wrap:anywhere; }
    .card { border:1px solid var(--soft-line); border-radius:6px; padding:12px; background:#fbfcfe; }
    .stack { display:grid; gap:12px; }
    .summary-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:10px; }
    .notice { border:1px solid #c7d1dd; background:#f8fafc; border-radius:6px; padding:12px; }
    .notice strong { display:block; margin-bottom:6px; }
    .mono { font-family: Consolas, monospace; font-size:13px; }
    .hidden { display:none; }
    .compact-label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.03em; }
    .workspace-tabs { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:8px; }
    .workspace-tab { width:100%; background:#eef2f6; color:#243b53; border:1px solid #d6dde6; text-align:left; }
    .workspace-tab.active { background:#102a43; color:#fff; border-color:#102a43; box-shadow: inset 0 0 0 1px rgba(255,255,255,.12); }
    .workspace-view { display:grid; gap:16px; }
    .overview-hero { display:grid; gap:12px; }
    .next-action { border:1px solid #c7d1dd; background:#f8fafc; border-radius:8px; padding:14px; }
    .next-action strong { display:block; margin-bottom:6px; font-size:15px; }
    .mini-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:10px; }
    .summary-item { padding:12px 0; border-top:1px solid var(--soft-line); }
    .summary-item:first-child { border-top:0; padding-top:0; }
    .summary-item strong { display:block; margin-bottom:4px; }
    .workspace-block { display:grid; gap:12px; }
    .workspace-block-header { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
    .step-rail { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:8px; align-items:stretch; }
    .step-rail button { width:100%; text-align:left; background:#f8fafc; color:#243b53; border:1px solid #d6dde6; padding:10px; min-height:76px; display:grid; gap:6px; }
    .step-rail button.active { background:#102a43; color:#fff; border-color:#102a43; }
    .step-rail button.completed { background:#ecfdf3; color:#054f31; border-color:#abefc6; }
    .step-rail button.current { background:#eff8ff; color:#1849a9; border-color:#b2ddff; }
    .step-heading { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
    .step-rail-top { display:flex; justify-content:space-between; gap:8px; align-items:center; }
    .step-token { font-weight:700; font-size:13px; }
    .step-title { font-size:13px; line-height:1.35; }
    .compact-table { width:100%; border-collapse:collapse; font-size:14px; }
    .compact-table th, .compact-table td { text-align:left; padding:10px 8px; border-bottom:1px solid var(--soft-line); vertical-align:top; }
    .compact-table th { font-size:12px; text-transform:uppercase; letter-spacing:.03em; color:var(--muted); }
    details { border:1px solid var(--soft-line); border-radius:6px; padding:10px 12px; background:#fff; }
    summary { cursor:pointer; font-weight:700; }
    .empty-state { padding:18px; border:1px dashed #c7d1dd; border-radius:8px; background:#f8fafc; }
    .empty-state strong { display:block; margin-bottom:6px; }
    .maintenance-actions { display:grid; gap:10px; }
    @media (max-width: 980px) {
      .app-shell { grid-template-columns:1fr; padding:14px; }
      .sidebar { position:static; }
    }
    @media (max-width: 860px) {
      .app-header { align-items:flex-start; flex-direction:column; }
      .app-header-tools { justify-content:flex-start; width:100%; }
      .workspace-tabs { grid-template-columns:1fr; }
    }
  </style>
</head>
<body>
  <header class="app-header">
    <div>
      <h1>YT Input Collector</h1>
      <p>Operational workspace for the selected channel, workflow handoff, and analytics exports.</p>
    </div>
    <div class="app-header-tools">
      <div class="header-chip">
        <span>Selected Channel</span>
        <strong id="appSelectedChannel">No channel selected</strong>
      </div>
      <div class="header-chip">
        <span>Selected Project</span>
        <strong id="appSelectedProject">No project selected</strong>
      </div>
      <div class="header-chip">
        <span id="appOverallStateLabel">Workflow Status</span>
        <div id="appOverallState" class="pill pending">WAITING</div>
      </div>
      <button class="secondary" id="refreshBtn" onclick="refreshStatus()">Refresh Channels</button>
    </div>
  </header>
  <main class="app-shell">
    <aside class="sidebar">
      <section class="panel">
      <h2>Channel</h2>
      <label for="channelSelect">Selected Channel</label>
      <select id="channelSelect">
        <option value="">Loading channels...</option>
      </select>
      <div class="status" id="channelState" style="margin-top:12px"></div>
      </section>
      <section class="panel panel-muted">
        <h2>Workspace</h2>
        <div id="workspaceNav" class="workspace-tabs" role="tablist" aria-label="Collector work areas">
          <button type="button" class="workspace-tab" id="navOverviewBtn" data-workspace="overview">Overview</button>
          <button type="button" class="workspace-tab" id="navWorkflowBtn" data-workspace="workflow">Content Workflow</button>
          <button type="button" class="workspace-tab" id="navAnalyticsBtn" data-workspace="analytics">Analytics</button>
        </div>
      </section>
      <section class="panel">
        <details>
          <summary>Channel Settings</summary>
          <div id="actionState" class="status" style="margin-top:12px"></div>
          <div class="maintenance-actions" style="margin-top:12px">
            <div class="row">
              <button class="secondary" id="connectChannelBtn" disabled>Connect Channel</button>
              <button class="secondary" id="syncMetricsBtn" disabled>Sync Metrics</button>
              <button class="ghost" id="openLearningsBtn" disabled data-cutover-state="disabled">Open Learnings</button>
            </div>
            <div class="row">
              <div style="flex:1">
                <label for="recent">Recent Channel Videos</label>
                <input id="recent" type="number" min="1" max="50" value="10">
              </div>
              <div style="flex:1">
                <label for="window">Performance Window</label>
                <select id="window">
                  <option value="7">7 days</option>
                  <option value="28" selected>28 days</option>
                  <option value="90">90 days</option>
                </select>
              </div>
            </div>
          </div>
        </details>
      </section>
    </aside>

    <section class="workspace">
      <section class="panel">
        <h2>Operational Workspace</h2>
        <p class="meta" id="message">Loading channels...</p>
      </section>

      <section id="overviewWorkspace" class="workspace-view">
        <div id="summaryPanel" class="result"></div>
      </section>

      <section id="workflowWorkspace" class="workspace-view hidden">
        <div class="panel">
          <h3 style="margin:0">Content Workflow</h3>
          <div id="projectListState" class="status" style="margin-top:12px"></div>
          <div id="projectListPanel" class="stack" style="margin-top:12px"></div>
        </div>
        <div class="panel">
          <div class="row" id="projectDetailShellHeader" style="justify-content:space-between;align-items:flex-start;gap:12px">
            <div>
              <h3 style="margin:0">Project Detail</h3>
              <div class="meta" id="projectDetailShellMeta">Selected project workflow, candidate controls, and production handoff.</div>
            </div>
          </div>
          <div id="projectDetailState" class="status" style="margin-top:12px"></div>
          <div id="projectTranscriptPanel" class="result" style="margin-top:12px"></div>
          <div id="projectDetailPanel" class="result" style="margin-top:12px"></div>
          <div id="validationPanel" class="result" style="margin-top:12px"></div>
        </div>
      </section>

      <section id="analyticsWorkspace" class="workspace-view hidden">
        <div id="analyticsPanel" class="result"></div>
      </section>
    </section>
  </main>

<script>
const SELECTED_CHANNEL_STORAGE_KEY = "yt_input_collector.selectedChannelSlug";
const SELECTED_PROJECTS_STORAGE_KEY = "yt_input_collector.selectedProjectsByChannel";
const state = {
  activeWorkspace: "overview",
  channels: [],
  selectedChannelSlug: null,
  selectedChannelSummary: null,
  selectedChannelAnalytics: null,
  projects: [],
  selectedProjectSlug: null,
  selectedProjectDetail: null,
  selectedProjectProductionPackage: null,
  selectedProjectTranscript: null,
  selectedProjectValidation: null,
  selectedProjectWorkflow: null,
  selectedWorkflowStepId: null,
  selectedWorkflowBundle: null,
  pastedOutputDraft: "",
  parsedOutputResult: null,
  parsedOutputError: "",
  isCreateProjectPanelOpen: false,
  isChangeProjectPanelOpen: false,
  createProjectUrlDraft: "",
  createProjectNameDraft: "",
  createProjectWorkflowValue: "",
  createProjectFocusPending: false,
  workflowStartFocusPending: false,
  transcriptFocusPendingProjectKey: null,
  transcriptDraft: "",
  transcriptDraftByProjectKey: {},
  isLoadingChannels: false,
  isLoadingSummary: false,
  isLoadingChannelAnalytics: false,
  isLoadingProjects: false,
  isLoadingProjectDetail: false,
  isLoadingProductionPackage: false,
  isLoadingWorkflow: false,
  errorMessage: "",
  channelAnalyticsError: "",
  projectListError: "",
  projectDetailError: "",
  productionPackageError: "",
  workflowError: "",
  bundleError: "",
  summaryRequestId: 0,
  summaryAbortController: null,
  channelAnalyticsRequestId: 0,
  projectListRequestId: 0,
  projectDetailRequestId: 0,
  productionPackageRequestId: 0,
  workflowRequestId: 0,
  bundleAction: { busy: false, channelSlug: null, projectSlug: null, stepId: null, requestId: 0 },
  parseOutputAction: { busy: false, channelSlug: null, projectSlug: null, workflowId: null, workflowVersion: null, stepId: null, bundleSha256: null, outputText: "", requestId: 0 },
  saveCandidateAction: { busy: false, channelSlug: null, projectSlug: null, workflowId: null, workflowVersion: null, stepId: null, bundleSha256: null, rawOutputSha256: null, expectedStateRevision: null, requestId: 0 },
  candidateDecisionAction: { busy: false, channelSlug: null, projectSlug: null, workflowId: null, workflowVersion: null, stepId: null, candidateGroupId: null, expectedStateRevision: null, action: null, requestId: 0 },
  oauthAction: { busy: false, slug: null, requestId: 0 },
  metricsAction: { busy: false, slug: null, requestId: 0 },
  analyticsDiscoveryAction: { busy: false, slug: null, requestId: 0 },
  analyticsSyncAction: { busy: false, slug: null, requestId: 0 },
  actionFeedback: { kind: "", slug: null, text: "" },
  analyticsFeedback: { kind: "", slug: null, text: "" },
  createProjectAction: { busy: false, slug: null, requestId: 0 },
  transcriptSaveAction: { busy: false, slug: null, projectSlug: null, requestId: 0 },
  validationAction: { busy: false, slug: null, projectSlug: null, requestId: 0 },
  projectFeedback: { kind: "", channelSlug: null, projectSlug: null, text: "" },
  bundleFeedback: { kind: "", channelSlug: null, projectSlug: null, stepId: null, text: "" },
  candidateSaveFeedback: { kind: "", channelSlug: null, projectSlug: null, stepId: null, text: "" },
  lastSaveCandidateResult: null
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTime(value) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function pill(value) {
  const normalized = String(value ?? "UNKNOWN");
  const upper = normalized.toUpperCase();
  const ok = ["CONNECTED", "FOUND", "PASS", "READY_FOR_WORKFLOW", "READY", "SUCCESS", "APPROVED", "PRODUCTION_READY", "AVAILABLE"].includes(upper);
  const missing = ["MISSING", "DISCONNECTED", "FAILED", "ERROR"].includes(upper);
  const cls = ok ? "pass" : missing ? "missing" : "pending";
  return `<span class="pill ${cls}">${escapeHtml(friendlyStatusLabel(normalized))}</span>`;
}

function describeError(error, fallback) {
  if (!error) return fallback;
  if (error.name === "AbortError") return "Request was replaced by a newer channel selection.";
  return error.message || fallback;
}

function workflowErrorSummary(error, fallback) {
  const code = error && typeof error.code === "string" ? error.code : "";
  const known = {
    WORKFLOW_NOT_CONFIGURED: "No workflow is configured for this channel yet.",
    WORKFLOW_STATE_INVALID: "The saved workflow state could not be read safely.",
    WORKFLOW_RECOVERY_REQUIRED: "An incomplete workflow transaction requires review before this workflow can be read safely.",
    PROMPT_SET_UNAVAILABLE: "Prompt bundle unavailable for this workflow version.",
    PROMPT_MANIFEST_INVALID: "The workflow prompt manifest is not currently usable.",
    PROMPT_FILE_NOT_FOUND: "A workflow prompt file is missing.",
    PROMPT_FILE_DIGEST_MISMATCH: "A workflow prompt file did not match its expected digest.",
    WORKFLOW_STEP_NOT_FOUND: "The selected workflow step is no longer available.",
    BUNDLE_REQUIRED_INPUT_MISSING: "Required workflow inputs are still missing for this step.",
    BUNDLE_PROJECT_CONTEXT_MISSING: "A required project context value is missing for this workflow step.",
    PROMPT_BUNDLE_INVALID: "The workflow bundle response was not valid.",
  };
  return known[code] || describeError(error, fallback);
}

function parseOutputErrorSummary(error, fallback) {
  const code = error && typeof error.code === "string" ? error.code : "";
  const known = {
    BUNDLE_IDENTITY_MISMATCH: "The pasted output no longer matches the currently loaded bundle. Load the bundle again before parsing.",
    OUTPUT_TEXT_REQUIRED: "Paste the AI output before parsing.",
    OUTPUT_CONTRACT_INVALID: "This workflow step does not expose a usable output contract for preview.",
    PROMPT_OUTPUT_PARSE_FAILED: "The pasted output could not be parsed for preview.",
    WORKFLOW_STEP_NOT_FOUND: "The selected workflow step is no longer available.",
    WORKFLOW_RECOVERY_REQUIRED: "An incomplete workflow transaction requires review before parsing can continue.",
  };
  return known[code] || describeError(error, fallback);
}

function saveCandidateErrorSummary(error, fallback) {
  const code = error && typeof error.code === "string" ? error.code : "";
  const known = {
    BUNDLE_IDENTITY_MISMATCH: "The loaded bundle is stale. Build it again before saving a candidate.",
    OUTPUT_TEXT_REQUIRED: "Paste the AI output before saving a candidate.",
    PROMPT_OUTPUT_INVALID: "The current parsed output is not valid enough to save as a candidate.",
    OUTPUT_CONTRACT_INVALID: "This workflow step output contract is not currently writable.",
    WORKFLOW_STATE_INVALID: "The saved workflow state could not be read safely.",
    WORKFLOW_STATE_VERSION_UNSUPPORTED: "This workflow state version cannot be written safely yet.",
    STATE_REVISION_CONFLICT: "The workflow changed before the candidate save completed. Refresh the workflow and try again.",
    WORKFLOW_STEP_NOT_WRITABLE: "This workflow step is not currently writable.",
    CANDIDATE_EXISTS: "A candidate already exists for this workflow step.",
    PROJECT_WORKFLOW_BUSY: "Another workflow save is already running for this project.",
    PROJECT_WORKFLOW_LOCK_STALE: "The workflow lock is stale and requires review before another save.",
    WORKFLOW_RECOVERY_REQUIRED: "An incomplete workflow transaction requires review before another save.",
    REVISION_STORAGE_INVALID: "The workflow revision storage paths are not safe to use.",
    REVISION_ID_CONFLICT: "A workflow revision id conflict was detected.",
    WORKFLOW_WRITE_FAILED: "The workflow candidate could not be saved safely.",
  };
  return known[code] || describeError(error, fallback);
}

function candidateDecisionErrorSummary(error, fallback) {
  const code = error && typeof error.code === "string" ? error.code : "";
  const known = {
    STATE_REVISION_CONFLICT: "The workflow changed before the candidate decision completed. Refresh the workflow and try again.",
    WORKFLOW_STEP_NOT_DECIDABLE: "This workflow step does not currently expose a candidate decision.",
    CANDIDATE_GROUP_MISMATCH: "The selected candidate is stale. Refresh the workflow and try again.",
    CANDIDATE_NOT_FOUND: "The selected candidate could not be found safely.",
    CANDIDATE_DECISION_CONFLICT: "This candidate already has the opposite final decision recorded.",
    CANDIDATE_ALREADY_DECIDED: "This candidate has already been finalized.",
    CANDIDATE_ALREADY_APPROVED: "This candidate was already approved.",
    CANDIDATE_ALREADY_REJECTED: "This candidate was already rejected.",
    STABLE_ARTIFACT_CONFLICT: "A stable workflow output already exists for this step.",
    PROJECT_WORKFLOW_BUSY: "Another workflow save is already running for this project.",
    PROJECT_WORKFLOW_LOCK_STALE: "The workflow lock is stale and requires review before another decision.",
    WORKFLOW_RECOVERY_REQUIRED: "An incomplete workflow transaction requires review before another decision.",
    WORKFLOW_STATE_INVALID: "The saved workflow state could not be read safely.",
    WORKFLOW_WRITE_FAILED: "The candidate decision could not be completed safely.",
  };
  return known[code] || describeError(error, fallback);
}

async function v2Api(path, options = {}) {
  const requestPath = "/api/v2/" + path.replace(/^\/+/, "");
  const config = {
    method: options.method || "GET",
    headers: { "Accept": "application/json", "Content-Type": "application/json", ...(options.headers || {}) },
    signal: options.signal
  };
  if (options.body !== undefined) config.body = options.body;

  let response;
  try {
    response = await fetch(requestPath, config);
  } catch (error) {
    if (error && error.name === "AbortError") throw error;
    throw new Error("Could not reach the local collector UI.");
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (error) {
      payload = null;
    }
  }

  if (!response.ok) {
    const nested = payload && payload.error && typeof payload.error.message === "string" ? payload.error.message : "";
    const direct = payload && typeof payload.error === "string" ? payload.error : "";
    const message = nested || direct || response.statusText || "The request could not be completed.";
    const err = new Error(message);
    err.code = payload && payload.error && typeof payload.error.code === "string" ? payload.error.code : `HTTP_${response.status}`;
    throw err;
  }

  if (payload && typeof payload === "object") return payload;
  return {};
}

function selectedChannelRecord() {
  if (state.selectedChannelSummary && state.selectedChannelSummary.channel) {
    return state.selectedChannelSummary.channel;
  }
  return state.channels.find((item) => item.channel_slug === state.selectedChannelSlug) || null;
}

function activeWorkspaceList() {
  return ["overview", "workflow", "analytics"];
}

function currentWorkflowState() {
  return state.selectedProjectWorkflow && state.selectedProjectWorkflow.state ? state.selectedProjectWorkflow.state : {};
}

function projectSelectionKey(channelSlugArg, projectSlugArg) {
  const channelSlug = String(channelSlugArg || "").trim();
  const projectSlug = String(projectSlugArg || "").trim();
  if (!channelSlug || !projectSlug) return "";
  return `${channelSlug}::${projectSlug}`;
}

function currentProjectSelectionKey() {
  return projectSelectionKey(state.selectedChannelSlug, state.selectedProjectSlug);
}

function transcriptDraftForProject(channelSlugArg, projectSlugArg) {
  const key = projectSelectionKey(channelSlugArg, projectSlugArg);
  if (!key) return "";
  return typeof state.transcriptDraftByProjectKey[key] === "string" ? state.transcriptDraftByProjectKey[key] : "";
}

function rememberTranscriptDraftForProject(channelSlugArg, projectSlugArg, draftValue) {
  const key = projectSelectionKey(channelSlugArg, projectSlugArg);
  if (!key) return;
  state.transcriptDraftByProjectKey[key] = typeof draftValue === "string" ? draftValue : "";
}

function currentWorkflowStepRecord() {
  const workflowState = currentWorkflowState();
  if (!workflowState.current_step_id) return null;
  return workflowStepList().find((step) => step.step_id === workflowState.current_step_id) || null;
}

function selectedProjectHasSavedTranscript() {
  return !!(state.selectedProjectTranscript && state.selectedProjectTranscript.has_real_content);
}

function isTranscriptAnalysisStep(step) {
  if (!step) return false;
  const stepId = String(step.step_id || "").toLowerCase();
  const displayName = String(step.display_name || "").toLowerCase();
  return stepId.includes("transcript") || displayName.includes("transcript");
}

function transcriptPanelProjectState() {
  const currentStep = currentWorkflowStepRecord();
  const currentCandidate = currentStep ? stepCandidateSummary(currentStep.step_id) : null;
  const workflowCompleted = !!(state.selectedProjectProductionPackage && (state.selectedProjectProductionPackage.lifecycle === "PRODUCTION_READY" || state.selectedProjectProductionPackage.ready_for_export));
  const hasDraft = !!String(state.transcriptDraft || "").trim();
  const transcriptSaved = selectedProjectHasSavedTranscript();
  const hasWorkflowProgress = !!(
    activeBundleRecord()
    || parsedOutputMatchesSelection(state.parsedOutputResult)
    || String(state.pastedOutputDraft || "").trim()
    || (currentCandidate && (currentCandidate.candidate_group_id || currentCandidate.approved_group_id || currentCandidate.status === "CANDIDATE" || currentCandidate.status === "APPROVED"))
  );
  const transcriptRequired = !!(
    state.selectedProjectSlug
    && state.selectedProjectDetail
    && state.selectedProjectWorkflow
    && !workflowCompleted
    && currentStep
    && Number(currentStep.order || 0) === 1
    && isTranscriptAnalysisStep(currentStep)
    && !transcriptSaved
    && !hasWorkflowProgress
  );
  return {
    current_step: currentStep,
    workflow_completed: workflowCompleted,
    transcript_required: transcriptRequired,
    transcript_saved: transcriptSaved,
    has_draft: hasDraft,
    show_primary_panel: transcriptRequired,
    show_collapsed_panel: !transcriptRequired && !workflowCompleted && (transcriptSaved || hasDraft),
  };
}

function currentWorkflowLifecycle() {
  const productionPackage = state.selectedProjectProductionPackage;
  const workflowState = currentWorkflowState();
  return (
    (productionPackage && productionPackage.lifecycle)
    || workflowState.current_lifecycle_state
    || (state.selectedProjectDetail && state.selectedProjectDetail.project && state.selectedProjectDetail.project.status)
    || "WAITING"
  );
}

function humanizeIdentifier(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text
    .replace(/^[0-9]{8}_/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function selectedProjectDisplayName() {
  const detail = state.selectedProjectDetail && state.selectedProjectDetail.project ? state.selectedProjectDetail.project : {};
  const summary = selectedProjectSummaryRecord() || {};
  return (
    detail.project_name
    || detail.display_name
    || summary.project_name
    || summary.display_name
    || humanizeIdentifier(detail.project_slug || summary.project_slug || "")
    || "No project selected"
  );
}

function loadSavedProjectSelections() {
  try {
    const raw = localStorage.getItem(SELECTED_PROJECTS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const normalized = {};
    Object.entries(parsed).forEach(([channelSlug, projectSlug]) => {
      if (typeof channelSlug === "string" && typeof projectSlug === "string" && channelSlug.trim() && projectSlug.trim()) {
        normalized[channelSlug] = projectSlug;
      }
    });
    return normalized;
  } catch (error) {
    return {};
  }
}

function saveProjectSelections(map) {
  const normalized = {};
  Object.entries(map || {}).forEach(([channelSlug, projectSlug]) => {
    if (typeof channelSlug === "string" && typeof projectSlug === "string" && channelSlug.trim() && projectSlug.trim()) {
      normalized[channelSlug] = projectSlug;
    }
  });
  if (Object.keys(normalized).length === 0) {
    localStorage.removeItem(SELECTED_PROJECTS_STORAGE_KEY);
    return;
  }
  localStorage.setItem(SELECTED_PROJECTS_STORAGE_KEY, JSON.stringify(normalized));
}

function savedProjectSlugForChannel(channelSlug) {
  if (!channelSlug) return null;
  const selections = loadSavedProjectSelections();
  return typeof selections[channelSlug] === "string" && selections[channelSlug] ? selections[channelSlug] : null;
}

function rememberProjectSlugForChannel(channelSlug, projectSlug) {
  if (!channelSlug) return;
  const selections = loadSavedProjectSelections();
  if (projectSlug) {
    selections[channelSlug] = projectSlug;
  } else {
    delete selections[channelSlug];
  }
  saveProjectSelections(selections);
}

function friendlyStatusLabel(value) {
  const raw = String(value || "").trim();
  const upper = raw.toUpperCase();
  const known = {
    PRODUCTION_READY: "Production ready",
    APPROVED: "Approved",
    PARTIAL: "Completed with missing data",
    PENDING: "Waiting for YouTube",
    CONNECTED: "Connected",
    DISCONNECTED: "Disconnected",
    READY: "Ready",
    WAITING: "Waiting",
    LOADING: "Loading",
    ERROR: "Needs attention",
    SUCCESS: "Ready",
    CANDIDATE: "Candidate review needed",
    INPUT_READY: "Ready for workflow",
    READY_FOR_WORKFLOW: "Ready for workflow",
  };
  if (known[upper]) return known[upper];
  return raw ? humanizeIdentifier(raw) : "Waiting";
}

function productionStatusSentence(productionPackage) {
  if (!productionPackage) return "Not ready yet";
  if (productionPackage.ready_for_export || productionPackage.lifecycle === "PRODUCTION_READY") return "Ready to download";
  return "Still in progress";
}

function generatedReportsSummary(analytics) {
  const readiness = analytics && analytics.report_readiness_counts ? analytics.report_readiness_counts : {};
  const ready = Number(readiness.READY || 0);
  const pending = Number(readiness.PENDING || 0);
  const error = Number(readiness.ERROR || 0);
  if (ready > 0 && pending === 0 && error === 0) return "Reports ready";
  if (pending > 0 && error === 0) return `${pending} bulk reports still pending`;
  if (error > 0) return `${error} bulk reports need attention`;
  return "No generated reports yet";
}

function defaultPrimaryActionForWorkspace(workspaceId) {
  if (workspaceId === "overview") return "recommendedActionBtn";
  if (workspaceId === "workflow") return "workflowPrimaryAction";
  if (workspaceId === "analytics") return "syncAnalyticsCollectorBtn";
  return "";
}

function normalizeWorkspace(value) {
  return activeWorkspaceList().includes(value) ? value : "overview";
}

function setActiveWorkspace(nextWorkspace) {
  const normalized = normalizeWorkspace(nextWorkspace);
  if (normalized === state.activeWorkspace) return;
  state.activeWorkspace = normalized;
  if (normalized === "workflow") {
    const panelState = transcriptPanelProjectState();
    if (panelState.show_primary_panel) {
      state.transcriptFocusPendingProjectKey = currentProjectSelectionKey();
    }
  }
  render();
}

function currentWorkflowStepCandidate() {
  const workflowState = currentWorkflowState();
  if (workflowState && workflowState.current_step_id) {
    return stepCandidateSummary(workflowState.current_step_id);
  }
  return null;
}

function headerStateModel() {
  const channel = selectedChannelRecord();
  if (!state.selectedChannelSlug) {
    return { label: "Analytics Status", value: "WAITING" };
  }
  if (!channel) {
    return { label: "Analytics Status", value: "LOADING" };
  }
  if (channel.status && channel.status !== "CONNECTED") {
    return { label: "Analytics Status", value: channel.status };
  }
  if (state.selectedProjectSlug) {
    const productionPackage = state.selectedProjectProductionPackage;
    if (productionPackage && productionPackage.ready_for_export) {
      return { label: "Workflow Status", value: "PRODUCTION_READY" };
    }
    const workflowState = currentWorkflowState();
    if (workflowState.current_step_status) {
      return { label: "Workflow Status", value: workflowState.current_step_status };
    }
    const detailProject = state.selectedProjectDetail && state.selectedProjectDetail.project ? state.selectedProjectDetail.project : {};
    return { label: "Workflow Status", value: detailProject.status || "WAITING" };
  }
  const analytics = state.selectedChannelAnalytics;
  const sourceResults = analytics && analytics.source_results ? analytics.source_results : {};
  if (sourceResults.analytics_queries && sourceResults.analytics_queries.status) {
    return { label: "Analytics Status", value: sourceResults.analytics_queries.status };
  }
  return { label: "Analytics Status", value: channel.status || "READY" };
}

function analyticsPlainLanguageSummary(analytics) {
  if (!analytics) {
    return {
      label: "Needs attention",
      detail: "Analytics capability discovery has not been recorded for this channel yet.",
    };
  }
  const readiness = analytics.report_readiness_counts || {};
  const sourceResults = analytics.source_results || {};
  const queryStatus = sourceResults.analytics_queries && sourceResults.analytics_queries.status ? sourceResults.analytics_queries.status : "";
  const pendingCount = Number(readiness.PENDING || 0);
  const errorCount = Number(readiness.ERROR || 0);
  if (queryStatus === "PARTIAL") {
    return {
      label: "Completed with some unavailable data",
      detail: "Most analytics data is ready. One YouTube query failed temporarily, and bulk reports are still being prepared.",
    };
  }
  if (pendingCount > 0 && !errorCount) {
    return {
      label: "Waiting for YouTube",
      detail: "Bulk reporting jobs exist, but generated reports are still being prepared by YouTube.",
    };
  }
  if (queryStatus === "SUCCESS") {
    return {
      label: "Ready",
      detail: "Analytics collection has completed with the currently available data for this channel.",
    };
  }
  return {
    label: "Needs attention",
    detail: "Analytics data has not completed successfully yet for this channel.",
  };
}

function analyticsStatusTone(value) {
  if (value === "Ready") return "PASS";
  if (value === "Completed with some unavailable data" || value === "Waiting for YouTube") return "PENDING";
  return "ERROR";
}

function normalizedTableReason(table) {
  const raw = String((table && (table.availability_reason || table.reason || table.status_detail || table.technical_status || "")) || "").trim();
  const normalized = raw.toLowerCase();
  if (normalized.includes("bulk") || normalized.includes("generated report") || normalized.includes("pending")) return "Waiting for YouTube bulk report";
  if (normalized.includes("unauthor")) return "Unauthorized";
  if (normalized.includes("temporary") || normalized.includes("internal api error") || normalized.includes("error")) return "Temporary YouTube error";
  if (normalized.includes("no channel data")) return "No channel data";
  if (normalized.includes("empty")) return "Empty successful result";
  return raw || "No data available yet";
}

function normalizedTableAvailabilityLabel(table) {
  if (table && Number(table.row_count || 0) > 0) return "Ready";
  const reason = normalizedTableReason(table);
  if (reason === "Waiting for YouTube bulk report") return "Waiting for YouTube";
  if (reason === "Unauthorized") return "Unauthorized";
  if (reason === "Temporary YouTube error") return "Needs attention";
  if (reason === "No channel data") return "No channel data";
  return "Empty";
}

function recommendedNextAction() {
  const channel = selectedChannelRecord();
  if (!state.selectedChannelSlug) {
    return {
      title: "Select Channel",
      detail: "Choose a channel to load its current workflow and analytics state.",
      workspace: "overview",
      status: "WAITING",
      button_label: "Open Overview",
    };
  }
  if (channel && channel.status && channel.status !== "CONNECTED") {
    return {
      title: "Connect Channel",
      detail: "Reconnect the selected channel before running workflow or analytics operations.",
      workspace: "overview",
      status: "WAITING",
      button_label: "Open Overview",
    };
  }
  const productionPackage = state.selectedProjectProductionPackage;
  if (productionPackage && productionPackage.ready_for_export) {
    return {
      title: "Download Production Package",
      detail: "The workflow is complete and the production ZIP is ready for handoff.",
      workspace: "workflow",
      status: "READY",
      button_label: "Download Production Package",
      download_url: productionPackage.download_url || "",
    };
  }
  const workflowState = currentWorkflowState();
  const currentCandidate = currentWorkflowStepCandidate();
  if (currentCandidate && currentCandidate.candidate_group_id) {
    return {
      title: "Review Candidate",
      detail: "A saved candidate is waiting for approval or rejection.",
      workspace: "workflow",
      status: "READY",
      button_label: "Open Content Workflow",
    };
  }
  if (workflowState.current_step_id && workflowState.current_step_status === "READY") {
    return {
      title: "Continue Workflow",
      detail: "Build the next bundle and continue the selected project's workflow.",
      workspace: "workflow",
      status: "READY",
      button_label: "Open Content Workflow",
    };
  }
  const analytics = state.selectedChannelAnalytics;
  const analyticsSummary = analyticsPlainLanguageSummary(analytics);
  if (!analytics || !analytics.last_completed_sync_at) {
    return {
      title: "Sync Analytics",
      detail: "Run the supported analytics collector for this selected channel.",
      workspace: "analytics",
      status: "WAITING",
      button_label: "Open Analytics",
    };
  }
  if (analytics && analytics.export_url && analyticsSummary.label === "Completed with some unavailable data") {
    return {
      title: "Download Analytics Package",
      detail: "Export the current normalized analytics package while YouTube finishes the remaining bulk reports.",
      workspace: "analytics",
      status: "READY",
      button_label: "Open Analytics",
    };
  }
  if (analytics && Number((analytics.report_readiness_counts || {}).PENDING || 0) > 0) {
    return {
      title: "Waiting for YouTube bulk reports",
      detail: "Collector jobs are in place. The remaining bulk reports are still pending from YouTube.",
      workspace: "analytics",
      status: "PENDING",
      button_label: "Open Analytics",
    };
  }
  return {
    title: "No action required",
    detail: "The current selected channel has no immediate supported operation waiting in this UI.",
    workspace: "overview",
    status: "PASS",
    button_label: "Open Overview",
  };
}

function channelWorkflowOptions() {
  const summary = state.selectedChannelSummary;
  const options = summary && Array.isArray(summary.available_workflows) ? summary.available_workflows : [];
  return options.filter((item) =>
    item
    && typeof item.workflow_id === "string"
    && typeof item.workflow_version === "string"
  );
}

function createEligibleWorkflowOptions() {
  const options = channelWorkflowOptions();
  return options.filter((item) => String(item.version_status || "").toUpperCase() === "ACTIVE");
}

function compareWorkflowVersions(left, right) {
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && String(leftNumber) === String(left) && String(rightNumber) === String(right)) {
    return leftNumber - rightNumber;
  }
  return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
}

function preferredWorkflowOption(options) {
  if (!options.length) return null;
  return options.slice().sort((left, right) => compareWorkflowVersions(left.workflow_version, right.workflow_version)).slice(-1)[0];
}

function createSelectableWorkflowOptions() {
  const options = createEligibleWorkflowOptions();
  if (options.length <= 1) return options;
  const workflowIds = Array.from(new Set(options.map((item) => item.workflow_id)));
  if (workflowIds.length === 1) {
    const preferred = preferredWorkflowOption(options);
    return preferred ? [preferred] : [];
  }
  return options;
}

function workflowOptionValue(option) {
  return `${option.workflow_id}@@${option.workflow_version}`;
}

function workflowOptionLabel(option) {
  return `${option.display_name || option.workflow_id} - v${option.workflow_version}`;
}

function parseWorkflowOptionValue(value) {
  if (typeof value !== "string" || !value.includes("@@")) return null;
  const parts = value.split("@@");
  if (parts.length !== 2 || !parts[0] || !parts[1]) return null;
  return { workflow_id: parts[0], workflow_version: parts[1] };
}

function selectedCreateWorkflowOption() {
  const options = createSelectableWorkflowOptions();
  if (!options.length) return null;
  if (!state.createProjectWorkflowValue && options.length === 1) {
    return options[0];
  }
  const parsed = parseWorkflowOptionValue(String(state.createProjectWorkflowValue || ""));
  if (!parsed) return null;
  return options.find((option) =>
    option.workflow_id === parsed.workflow_id && option.workflow_version === parsed.workflow_version
  ) || null;
}

function selectedCreateWorkflowValue() {
  const option = selectedCreateWorkflowOption();
  if (option) return workflowOptionValue(option);
  return "";
}

function syncCreateProjectWorkflowSelection() {
  const options = createSelectableWorkflowOptions();
  if (!options.length) {
    state.createProjectWorkflowValue = "";
    return;
  }
  const current = String(state.createProjectWorkflowValue || "");
  if (current) {
    const parsed = parseWorkflowOptionValue(current);
    if (parsed && options.some((option) =>
      option.workflow_id === parsed.workflow_id && option.workflow_version === parsed.workflow_version
    )) {
      return;
    }
  }
  state.createProjectWorkflowValue = options.length === 1 ? workflowOptionValue(options[0]) : "";
}

function createProjectUrlValidationMessage(value) {
  const text = String(value || "");
  const normalized = text.trim();
  if (!normalized) return "Competitor video URL is required.";
  const supported = /^(https?:\/\/)?((www|m)\.)?(youtube\.com\/watch\?[^#\s]*\bv=[A-Za-z0-9_-]{6,}|youtube\.com\/shorts\/[A-Za-z0-9_-]{6,}|youtu\.be\/[A-Za-z0-9_-]{6,})(?:[^\s]*)?$/i;
  if (supported.test(normalized)) return "";
  return "Enter a supported YouTube video URL.";
}

function openCreateProjectPanel() {
  syncCreateProjectWorkflowSelection();
  state.isCreateProjectPanelOpen = true;
  state.isChangeProjectPanelOpen = false;
  state.createProjectFocusPending = true;
  clearProjectFeedback();
  render();
}

function closeCreateProjectPanel() {
  state.isCreateProjectPanelOpen = false;
  state.createProjectUrlDraft = "";
  state.createProjectNameDraft = "";
  if (!createSelectableWorkflowOptions().length) {
    state.createProjectWorkflowValue = "";
  }
  clearProjectFeedback();
  render();
}

function toggleChangeProjectPanel(forceOpen) {
  const nextOpen = typeof forceOpen === "boolean" ? forceOpen : !state.isChangeProjectPanelOpen;
  state.isChangeProjectPanelOpen = nextOpen;
  if (nextOpen) state.isCreateProjectPanelOpen = false;
  clearProjectFeedback();
  render();
}

function clearActionFeedback() {
  state.actionFeedback = { kind: "", slug: null, text: "" };
}

function setActionFeedback(kind, slug, text) {
  state.actionFeedback = { kind, slug, text };
}

function clearAnalyticsFeedback() {
  state.analyticsFeedback = { kind: "", slug: null, text: "" };
}

function setAnalyticsFeedback(kind, slug, text) {
  state.analyticsFeedback = { kind, slug, text };
}

function clearProjectFeedback() {
  state.projectFeedback = { kind: "", channelSlug: null, projectSlug: null, text: "" };
}

function setProjectFeedback(kind, channelSlug, projectSlug, text) {
  state.projectFeedback = { kind, channelSlug, projectSlug, text };
}

function projectFeedbackForSelection() {
  const feedback = state.projectFeedback;
  if (!feedback.text || feedback.channelSlug !== state.selectedChannelSlug) return { kind: "", text: "" };
  if (feedback.projectSlug && feedback.projectSlug !== state.selectedProjectSlug) return { kind: "", text: "" };
  return feedback;
}

function clearProjectSelectionState() {
  state.selectedProjectSlug = null;
  state.selectedProjectDetail = null;
  state.selectedProjectProductionPackage = null;
  state.selectedProjectTranscript = null;
  state.selectedProjectValidation = null;
  state.selectedProjectWorkflow = null;
  state.selectedWorkflowStepId = null;
  state.selectedWorkflowBundle = null;
  state.pastedOutputDraft = "";
  state.parsedOutputResult = null;
  state.parsedOutputError = "";
  state.transcriptDraft = "";
  state.projectDetailError = "";
  state.productionPackageError = "";
  state.workflowError = "";
  state.bundleError = "";
  state.parseOutputAction = { busy: false, channelSlug: null, projectSlug: null, workflowId: null, workflowVersion: null, stepId: null, bundleSha256: null, outputText: "", requestId: 0 };
  state.saveCandidateAction = { busy: false, channelSlug: null, projectSlug: null, workflowId: null, workflowVersion: null, stepId: null, bundleSha256: null, rawOutputSha256: null, expectedStateRevision: null, requestId: 0 };
  state.candidateDecisionAction = { busy: false, channelSlug: null, projectSlug: null, workflowId: null, workflowVersion: null, stepId: null, candidateGroupId: null, expectedStateRevision: null, action: null, requestId: 0 };
  state.bundleFeedback = { kind: "", channelSlug: null, projectSlug: null, stepId: null, text: "" };
  state.candidateSaveFeedback = { kind: "", channelSlug: null, projectSlug: null, stepId: null, text: "" };
  state.lastSaveCandidateResult = null;
  state.transcriptFocusPendingProjectKey = null;
}

function clearSelectedChannelAnalyticsState() {
  state.selectedChannelAnalytics = null;
  state.isLoadingChannelAnalytics = false;
  state.channelAnalyticsError = "";
  clearAnalyticsFeedback();
}

function clearProjectState() {
  state.projects = [];
  state.projectListError = "";
  state.isCreateProjectPanelOpen = false;
  state.isChangeProjectPanelOpen = false;
  state.createProjectUrlDraft = "";
  state.createProjectNameDraft = "";
  state.createProjectWorkflowValue = "";
  state.createProjectFocusPending = false;
  state.workflowStartFocusPending = false;
  clearProjectSelectionState();
  clearProjectFeedback();
}

function selectedProjectSummaryRecord() {
  if (state.selectedProjectDetail && state.selectedProjectDetail.project) {
    return state.selectedProjectDetail.project;
  }
  return state.projects.find((item) => item.project_slug === state.selectedProjectSlug) || null;
}

function clearBundleFeedback() {
  state.bundleFeedback = { kind: "", channelSlug: null, projectSlug: null, stepId: null, text: "" };
}

function setBundleFeedback(kind, channelSlug, projectSlug, stepId, text) {
  state.bundleFeedback = { kind, channelSlug, projectSlug, stepId, text };
}

function bundleFeedbackForSelection() {
  const feedback = state.bundleFeedback;
  if (!feedback.text) return { kind: "", text: "" };
  if (feedback.channelSlug !== state.selectedChannelSlug || feedback.projectSlug !== state.selectedProjectSlug) return { kind: "", text: "" };
  if (feedback.stepId && feedback.stepId !== state.selectedWorkflowStepId) return { kind: "", text: "" };
  return feedback;
}

function clearCandidateSaveFeedback() {
  state.candidateSaveFeedback = { kind: "", channelSlug: null, projectSlug: null, stepId: null, text: "" };
}

function setCandidateSaveFeedback(kind, channelSlug, projectSlug, stepId, text) {
  state.candidateSaveFeedback = { kind, channelSlug, projectSlug, stepId, text };
}

function candidateSaveFeedbackForSelection() {
  const feedback = state.candidateSaveFeedback;
  if (!feedback.text) return { kind: "", text: "" };
  if (feedback.channelSlug !== state.selectedChannelSlug || feedback.projectSlug !== state.selectedProjectSlug) return { kind: "", text: "" };
  if (feedback.stepId && feedback.stepId !== state.selectedWorkflowStepId) return { kind: "", text: "" };
  return feedback;
}

function invalidateLoadedBundle() {
  state.selectedWorkflowBundle = null;
  state.bundleError = "";
  state.pastedOutputDraft = "";
  state.parsedOutputResult = null;
  state.parsedOutputError = "";
  state.parseOutputAction = { busy: false, channelSlug: null, projectSlug: null, workflowId: null, workflowVersion: null, stepId: null, bundleSha256: null, outputText: "", requestId: 0 };
  state.saveCandidateAction = { busy: false, channelSlug: null, projectSlug: null, workflowId: null, workflowVersion: null, stepId: null, bundleSha256: null, rawOutputSha256: null, expectedStateRevision: null, requestId: 0 };
  state.candidateDecisionAction = { busy: false, channelSlug: null, projectSlug: null, workflowId: null, workflowVersion: null, stepId: null, candidateGroupId: null, expectedStateRevision: null, action: null, requestId: 0 };
  state.lastSaveCandidateResult = null;
  clearBundleFeedback();
  clearCandidateSaveFeedback();
}

function clearWorkflowState() {
  state.selectedProjectWorkflow = null;
  state.selectedProjectProductionPackage = null;
  state.selectedWorkflowStepId = null;
  state.isLoadingWorkflow = false;
  state.isLoadingProductionPackage = false;
  state.productionPackageError = "";
  state.workflowError = "";
  invalidateLoadedBundle();
}

function workflowDefinition() {
  return state.selectedProjectWorkflow && state.selectedProjectWorkflow.definition ? state.selectedProjectWorkflow.definition : null;
}

function workflowStepList() {
  const definition = workflowDefinition();
  return definition && Array.isArray(definition.steps) ? definition.steps : [];
}

function workflowArtifactMap() {
  const workflow = state.selectedProjectWorkflow;
  const artifacts = workflow && Array.isArray(workflow.artifacts) ? workflow.artifacts : [];
  const mapped = {};
  for (const artifact of artifacts) {
    if (artifact && artifact.artifact_id) mapped[artifact.artifact_id] = artifact;
  }
  return mapped;
}

function selectedWorkflowStepRecord() {
  return workflowStepList().find((step) => step.step_id === state.selectedWorkflowStepId) || null;
}

function bundleIdentityForSelection(stepIdArg) {
  const workflow = state.selectedProjectWorkflow;
  const binding = workflow && workflow.binding ? workflow.binding : null;
  const definition = workflow && workflow.definition ? workflow.definition : null;
  const stepId = stepIdArg || state.selectedWorkflowStepId;
  if (!binding || !definition || !state.selectedChannelSlug || !state.selectedProjectSlug || !stepId) return null;
  return {
    channel_slug: state.selectedChannelSlug,
    project_slug: state.selectedProjectSlug,
    workflow_id: binding.workflow_id,
    workflow_version: binding.workflow_version,
    step_id: stepId,
    workflow_definition_sha256: binding.workflow_definition_sha256
  };
}

function bundleMatchesSelection(bundle) {
  if (!bundle || !bundle.identity) return false;
  const current = bundleIdentityForSelection();
  if (!current) return false;
  return (
    bundle.identity.channel_slug === current.channel_slug
    && bundle.identity.project_slug === current.project_slug
    && bundle.identity.workflow_id === current.workflow_id
    && bundle.identity.workflow_version === current.workflow_version
    && bundle.identity.step_id === current.step_id
    && bundle.identity.workflow_definition_sha256 === current.workflow_definition_sha256
  );
}

function unicodeCodePointCount(value) {
  if (typeof value !== "string") return NaN;
  return Array.from(value).length;
}

function bundleValidationError(bundle) {
  if (!bundle || typeof bundle !== "object") return "Load a valid bundle for the selected step before copying.";
  if (typeof bundle.bundle !== "string") return "The loaded workflow bundle is missing its text payload.";
  if (typeof bundle.bundle_character_count !== "number" || !Number.isInteger(bundle.bundle_character_count) || bundle.bundle_character_count < 0) return "The loaded workflow bundle is missing a valid character count.";
  if (unicodeCodePointCount(bundle.bundle) !== bundle.bundle_character_count) return "The loaded workflow bundle metadata is inconsistent.";
  return "";
}

function activeBundleRecord() {
  if (!bundleMatchesSelection(state.selectedWorkflowBundle)) return null;
  if (bundleValidationError(state.selectedWorkflowBundle)) return null;
  return state.selectedWorkflowBundle;
}

function parsedOutputIdentityForSelection(outputTextArg) {
  const bundle = activeBundleRecord();
  const current = bundleIdentityForSelection();
  const outputText = outputTextArg !== undefined ? outputTextArg : state.pastedOutputDraft;
  if (!bundle || !current) return null;
  const rawOutputText = typeof outputText === "string" ? outputText : "";
  let rawOutputSha256 = "";
  const currentParsed = state.parsedOutputResult;
  if (
    currentParsed
    && currentParsed.identity
    && currentParsed.raw_output
    && typeof currentParsed.raw_output.sha256 === "string"
    && currentParsed.identity.channel_slug === current.channel_slug
    && currentParsed.identity.project_slug === current.project_slug
    && currentParsed.identity.workflow_id === current.workflow_id
    && currentParsed.identity.workflow_version === current.workflow_version
    && currentParsed.identity.step_id === current.step_id
    && currentParsed.identity.bundle_sha256 === bundle.bundle_sha256
    && currentParsed.raw_output.character_count === rawOutputText.length
  ) {
    rawOutputSha256 = currentParsed.raw_output.sha256;
  }
  return {
    channel_slug: current.channel_slug,
    project_slug: current.project_slug,
    workflow_id: current.workflow_id,
    workflow_version: current.workflow_version,
    step_id: current.step_id,
    bundle_sha256: bundle.bundle_sha256,
    output_text: rawOutputText,
    raw_output_sha256: rawOutputSha256
  };
}

function parsedOutputMatchesSelection(result) {
  if (!result || !result.identity) return false;
  const current = parsedOutputIdentityForSelection();
  if (!current) return false;
  return (
    result.identity.channel_slug === current.channel_slug
    && result.identity.project_slug === current.project_slug
    && result.identity.workflow_id === current.workflow_id
    && result.identity.workflow_version === current.workflow_version
    && result.identity.step_id === current.step_id
    && result.identity.bundle_sha256 === current.bundle_sha256
    && result.raw_output
    && result.raw_output.character_count === current.output_text.length
  );
}

function invalidateParsedOutputResult() {
  state.parsedOutputResult = null;
  state.parsedOutputError = "";
}

function setSelectedWorkflowStepId(nextStepId) {
  const normalized = nextStepId && workflowStepList().some((step) => step.step_id === nextStepId) ? nextStepId : null;
  if (normalized === state.selectedWorkflowStepId) return;
  state.selectedWorkflowStepId = normalized;
  invalidateLoadedBundle();
  render();
}

function describeConversationConstraint(step) {
  if (!step || !Array.isArray(step.constraints) || step.constraints.length === 0) {
    return "No same-conversation requirement";
  }
  return step.constraints.map((constraint) => {
    if (constraint && constraint.type === "SAME_MODEL_CONVERSATION_REQUIRED" && constraint.group_id) {
      return `Continue in the same ${step.required_model || "selected"} conversation: ${constraint.group_id}`;
    }
    if (constraint && constraint.group_id) return `${constraint.type || "Constraint"}: ${constraint.group_id}`;
    return constraint && constraint.type ? String(constraint.type) : "Constraint required";
  }).join(" | ");
}

function artifactListForIds(ids) {
  const artifactsById = workflowArtifactMap();
  return (Array.isArray(ids) ? ids : []).map((artifactId) => artifactsById[artifactId] || {
    artifact_id: artifactId,
    display_name: artifactId,
    relative_path: "",
    required: true,
    exists: false
  });
}

function stepCandidateSummary(stepId) {
  const workflow = state.selectedProjectWorkflow;
  const stepStates = workflow && workflow.state && workflow.state.step_states ? workflow.state.step_states : {};
  return stepStates && typeof stepStates === "object" ? (stepStates[stepId] || null) : null;
}

function stepStatusLabel(step) {
  const candidate = step && stepCandidateSummary(step.step_id);
  if (candidate && candidate.status) return candidate.status;
  if (candidate && candidate.approved_group_id) return "APPROVED";
  if (candidate && candidate.candidate_group_id) return "CANDIDATE";
  const workflow = state.selectedProjectWorkflow;
  if (workflow && workflow.state && workflow.state.current_step_id === step.step_id) {
    return workflow.state.current_step_status || "UNKNOWN";
  }
  return "READY";
}

function staleReasonSummary(step) {
  const candidate = step && stepCandidateSummary(step.step_id);
  const staleReason = candidate && candidate.stale_reason ? candidate.stale_reason : null;
  if (!staleReason) return "";
  const upstream = Array.isArray(staleReason.upstream_artifact_ids) && staleReason.upstream_artifact_ids.length
    ? staleReason.upstream_artifact_ids.join(", ")
    : "upstream workflow output";
  return `Stale because ${upstream} changed.`;
}

function stepAvailabilitySummary(step) {
  const workflow = state.selectedProjectWorkflow;
  if (!workflow || !step) return "Waiting for workflow data";
  const candidate = stepCandidateSummary(step.step_id);
  if (candidate && candidate.stale_reason) return staleReasonSummary(step);
  if (candidate && candidate.invalidated_candidate_group_id) return `Candidate ${candidate.invalidated_candidate_group_id} was invalidated by an upstream approved change.`;
  const promptSet = workflow.definition && workflow.definition.prompt_set ? workflow.definition.prompt_set : {};
  if (promptSet.status !== "AVAILABLE" || !promptSet.bundle_available) {
    return "Prompt bundle unavailable for this workflow version.";
  }
  const requiredArtifacts = artifactListForIds(step.input_artifact_ids);
  if (requiredArtifacts.some((artifact) => !artifact.exists)) return "Required inputs missing";
  if (workflow.state && workflow.state.current_step_id === step.step_id) {
    return `Current step: ${workflow.state.current_step_status || "UNKNOWN"}`;
  }
  return "Ready to request bundle";
}

function bundleButtonModel() {
  const workflow = state.selectedProjectWorkflow;
  const step = selectedWorkflowStepRecord();
  const transcriptState = transcriptPanelProjectState();
  if (!state.selectedChannelSlug || !state.selectedProjectSlug || !workflow || !step) {
    return { disabled: true, label: "Build Complete Bundle", helper: "Load a selected project workflow before requesting a bundle." };
  }
  if (transcriptState.transcript_required) {
    return { disabled: true, label: "Build Complete Bundle", helper: "Save the manual transcript before building the first workflow bundle." };
  }
  const promptSet = workflow.definition && workflow.definition.prompt_set ? workflow.definition.prompt_set : {};
  if (promptSet.status !== "AVAILABLE" || !promptSet.bundle_available) {
    return { disabled: true, label: "Build Complete Bundle", helper: "Prompt bundle unavailable for this workflow version." };
  }
  const busy = state.bundleAction.busy
    && state.bundleAction.channelSlug === state.selectedChannelSlug
    && state.bundleAction.projectSlug === state.selectedProjectSlug
    && state.bundleAction.stepId === step.step_id;
  return {
    disabled: busy,
    label: busy ? "Building bundle..." : "Build Complete Bundle",
    helper: busy ? "Loading the exact workflow bundle for the selected step..." : "Request the complete bundle for the selected step only when you need it."
  };
}

function copyBundleButtonModel() {
  if (!activeBundleRecord()) {
    return { disabled: true, label: "Copy Complete Bundle", helper: "Load a valid bundle for the selected step before copying." };
  }
  return { disabled: false, label: "Copy Complete Bundle", helper: "Copy the exact full bundle returned by the local API." };
}

function parseOutputButtonModel() {
  const bundle = activeBundleRecord();
  const step = selectedWorkflowStepRecord();
  const validationStatus = validationStatusModel();
  if (!state.selectedChannelSlug || !state.selectedProjectSlug || !step || !bundle) {
    return { disabled: true, label: "Parse and Preview", helper: "Load a valid bundle for the selected step before parsing output." };
  }
  if (validationStatus.state === "RUNNING") {
    return { disabled: true, label: "Parse and Preview", helper: "Validation is still running for the selected project." };
  }
  if (!validationStatus.passed) {
    return { disabled: true, label: "Parse and Preview", helper: "Run validation first." };
  }
  if (!String(state.pastedOutputDraft || "").trim()) {
    return { disabled: true, label: "Parse and Preview", helper: "Paste the AI output before parsing." };
  }
  const busy = state.parseOutputAction.busy
    && state.parseOutputAction.channelSlug === state.selectedChannelSlug
    && state.parseOutputAction.projectSlug === state.selectedProjectSlug
    && state.parseOutputAction.workflowId === (bundle.identity && bundle.identity.workflow_id)
    && state.parseOutputAction.workflowVersion === (bundle.identity && bundle.identity.workflow_version)
    && state.parseOutputAction.stepId === step.step_id
    && state.parseOutputAction.bundleSha256 === bundle.bundle_sha256
    && state.parseOutputAction.outputText === state.pastedOutputDraft;
  return {
    disabled: busy,
    label: busy ? "Parsing Output..." : "Parse and Preview",
    helper: busy ? "Checking the pasted output against the current bundle..." : "Preview parsed output in memory only. Nothing is written to project files."
  };
}

function saveCandidateButtonModel() {
  const workflow = state.selectedProjectWorkflow;
  const bundle = activeBundleRecord();
  const step = selectedWorkflowStepRecord();
  const parsedOutput = parsedOutputMatchesSelection(state.parsedOutputResult) ? state.parsedOutputResult : null;
  const stepState = step ? stepCandidateSummary(step.step_id) : null;
  const replacementSave = !!(stepState && stepState.status === "APPROVED");
  const idleLabel = replacementSave ? "Save Replacement Candidate" : "Save Candidate";
  const busyLabel = replacementSave ? "Saving Replacement..." : "Saving Candidate...";
  if (!state.selectedChannelSlug || !state.selectedProjectSlug || !workflow || !bundle || !step || !parsedOutput) {
    return { disabled: true, label: idleLabel, helper: "Parse a current valid output preview before saving a candidate." };
  }
  if (parsedOutput.status !== "VALID") {
    return { disabled: true, label: idleLabel, helper: "Only a valid parsed output preview can be saved as a candidate." };
  }
  const action = workflow.available_actions && workflow.available_actions[step.step_id] ? workflow.available_actions[step.step_id] : {};
  if (!action.save_candidate) {
    return { disabled: true, label: idleLabel, helper: "This workflow step does not currently allow candidate save." };
  }
  if (!parsedOutput.raw_output || typeof parsedOutput.raw_output.sha256 !== "string") {
    return { disabled: true, label: idleLabel, helper: "The current parsed output preview is missing its raw-output identity." };
  }
  const busy = state.saveCandidateAction.busy
    && state.saveCandidateAction.channelSlug === state.selectedChannelSlug
    && state.saveCandidateAction.projectSlug === state.selectedProjectSlug
    && state.saveCandidateAction.workflowId === (bundle.identity && bundle.identity.workflow_id)
    && state.saveCandidateAction.workflowVersion === (bundle.identity && bundle.identity.workflow_version)
    && state.saveCandidateAction.stepId === step.step_id
    && state.saveCandidateAction.bundleSha256 === bundle.bundle_sha256
    && state.saveCandidateAction.rawOutputSha256 === parsedOutput.raw_output.sha256
    && state.saveCandidateAction.expectedStateRevision === (workflow.state && workflow.state.state_revision);
  return {
    disabled: busy,
    label: busy ? busyLabel : idleLabel,
    helper: busy
      ? "Persisting immutable candidate revisions for the current parsed output..."
      : (replacementSave
        ? "Save a replacement candidate while the current approved stable output remains authoritative."
        : "Save a candidate revision group only. No stable artifact files are published in this phase.")
  };
}

function candidateDecisionButtonModel(actionName) {
  const workflow = state.selectedProjectWorkflow;
  const step = selectedWorkflowStepRecord();
  const candidate = step && stepCandidateSummary(step.step_id);
  const action = workflow && workflow.available_actions && step ? (workflow.available_actions[step.step_id] || {}) : {};
  if (!state.selectedChannelSlug || !state.selectedProjectSlug || !workflow || !step || !candidate || !candidate.candidate_group_id) {
    return {
      disabled: true,
      label: actionName === "APPROVE" ? "Approve Candidate" : "Reject Candidate",
      helper: "Load the current candidate state for this workflow step before deciding."
    };
  }
  const actionKey = actionName === "APPROVE" ? "approve_candidate" : "reject_candidate";
  if (!action[actionKey]) {
    return {
      disabled: true,
      label: actionName === "APPROVE" ? "Approve Candidate" : "Reject Candidate",
      helper: "This workflow step does not currently allow that candidate decision."
    };
  }
  const busy = state.candidateDecisionAction.busy
    && state.candidateDecisionAction.channelSlug === state.selectedChannelSlug
    && state.candidateDecisionAction.projectSlug === state.selectedProjectSlug
    && state.candidateDecisionAction.workflowId === (workflow.binding && workflow.binding.workflow_id)
    && state.candidateDecisionAction.workflowVersion === (workflow.binding && workflow.binding.workflow_version)
    && state.candidateDecisionAction.stepId === step.step_id
    && state.candidateDecisionAction.candidateGroupId === candidate.candidate_group_id
    && state.candidateDecisionAction.expectedStateRevision === (workflow.state && workflow.state.state_revision)
    && state.candidateDecisionAction.action === actionName;
  return {
    disabled: busy,
    label: busy
      ? (actionName === "APPROVE" ? "Approving Candidate..." : "Rejecting Candidate...")
      : (actionName === "APPROVE" ? "Approve Candidate" : "Reject Candidate"),
    helper: busy
      ? (actionName === "APPROVE"
        ? "Publishing the candidate into stable workflow outputs..."
        : "Finalizing the candidate rejection without publishing stable artifacts...")
      : (actionName === "APPROVE"
        ? "Approve this candidate and publish its stable workflow output files."
        : "Reject this candidate and return the step to READY without publishing stable outputs.")
  };
}

function oauthButtonModel() {
  const channel = selectedChannelRecord();
  if (!state.selectedChannelSlug) {
    return { disabled: true, label: "Connect Channel", mode: null, helper: "Select a channel first." };
  }
  if (state.isLoadingSummary || !state.selectedChannelSummary || !channel) {
    return { disabled: true, label: "Connect Channel", mode: null, helper: "Load the selected channel summary before starting OAuth." };
  }
  const isConnected = channel.status === "CONNECTED";
  const busy = state.oauthAction.busy && state.oauthAction.slug === state.selectedChannelSlug;
  return {
    disabled: busy,
    label: busy ? (isConnected ? "Starting reconnect..." : "Starting connection...") : (isConnected ? "Reconnect Channel" : "Connect Channel"),
    mode: "reconnect",
    helper: isConnected ? "Use the canonical reconnect route for the selected channel." : "This channel workspace exists but is not connected yet. Start the canonical OAuth flow for this selected channel."
  };
}

function metricsButtonModel() {
  const channel = selectedChannelRecord();
  if (!state.selectedChannelSlug) {
    return { disabled: true, label: "Sync Metrics", helper: "Select a channel first." };
  }
  if (state.isLoadingSummary || !state.selectedChannelSummary || !channel) {
    return { disabled: true, label: "Sync Metrics", helper: "Load the selected channel summary before syncing metrics." };
  }
  if (channel.status !== "CONNECTED") {
    return { disabled: true, label: "Sync Metrics", helper: "Metrics sync is available only when the selected channel is connected." };
  }
  const busy = state.metricsAction.busy && state.metricsAction.slug === state.selectedChannelSlug;
  return {
    disabled: busy,
    label: busy ? "Syncing Metrics..." : "Sync Metrics",
    helper: "Sync channel metrics for the selected canonical channel only."
  };
}

function analyticsDiscoveryModel() {
  const channel = selectedChannelRecord();
  if (!state.selectedChannelSlug) {
    return { disabled: true, label: "Discover Capabilities", helper: "Select a channel first." };
  }
  if (state.isLoadingSummary || !state.selectedChannelSummary || !channel) {
    return { disabled: true, label: "Discover Capabilities", helper: "Load the selected channel summary before discovering analytics capabilities." };
  }
  if (channel.status !== "CONNECTED") {
    return { disabled: true, label: "Discover Capabilities", helper: "Capability discovery is available only when the selected channel is connected." };
  }
  const busy = state.analyticsDiscoveryAction.busy && state.analyticsDiscoveryAction.slug === state.selectedChannelSlug;
  return {
    disabled: busy,
    label: busy ? "Discovering..." : "Discover Capabilities",
    helper: "Call the Reporting API capability discovery route for the selected channel."
  };
}

function analyticsSyncModel() {
  const channel = selectedChannelRecord();
  if (!state.selectedChannelSlug) {
    return { disabled: true, label: "Sync Analytics", helper: "Select a channel first." };
  }
  if (state.isLoadingSummary || !state.selectedChannelSummary || !channel) {
    return { disabled: true, label: "Sync Analytics", helper: "Load the selected channel summary before syncing analytics." };
  }
  if (channel.status !== "CONNECTED") {
    return { disabled: true, label: "Sync Analytics", helper: "Analytics sync is available only when the selected channel is connected." };
  }
  const busy = state.analyticsSyncAction.busy && state.analyticsSyncAction.slug === state.selectedChannelSlug;
  return {
    disabled: busy,
    label: busy ? "Syncing Analytics..." : "Sync Analytics",
    helper: "Collect canonical data, reporting, and targeted analytics for the selected channel only."
  };
}

function projectsRefreshModel() {
  if (!state.selectedChannelSlug) {
    return { disabled: true, label: "Refresh Projects", helper: "Select a channel first." };
  }
  if (state.isLoadingSummary || !state.selectedChannelSummary) {
    return { disabled: true, label: "Refresh Projects", helper: "Load the selected channel summary before listing projects." };
  }
  return {
    disabled: state.isLoadingProjects,
    label: state.isLoadingProjects ? "Refreshing Projects..." : "Refresh Projects",
    helper: "List canonical projects for the selected channel only."
  };
}

function createProjectModel() {
  const channel = selectedChannelRecord();
  const trimmedUrl = String(state.createProjectUrlDraft || "").trim();
  const workflowOption = selectedCreateWorkflowOption();
  const eligibleWorkflowOptions = createSelectableWorkflowOptions();
  const urlValidation = trimmedUrl ? createProjectUrlValidationMessage(trimmedUrl) : "";
  const busy = state.createProjectAction.busy && state.createProjectAction.slug === state.selectedChannelSlug;
  const canEditInputs = !!(
    state.selectedChannelSlug
    && !state.isLoadingSummary
    && state.selectedChannelSummary
    && channel
    && channel.status === "CONNECTED"
    && !busy
  );
  if (!state.selectedChannelSlug) {
    return { disabled: true, label: "Create Project", helper: "Select a channel first.", inputDisabled: true, workflowDisabled: true, urlValidation: "", canEditInputs };
  }
  if (state.isLoadingSummary || !state.selectedChannelSummary || !channel) {
    return { disabled: true, label: "Create Project", helper: "Load the selected channel summary before creating a project.", inputDisabled: true, workflowDisabled: true, urlValidation: "", canEditInputs };
  }
  if (channel.status !== "CONNECTED") {
    return { disabled: true, label: "Create Project", helper: "Project creation is available only when the selected channel is connected.", inputDisabled: true, workflowDisabled: true, urlValidation: "", canEditInputs };
  }
  if (!eligibleWorkflowOptions.length) {
    return { disabled: true, label: "Create Project", helper: "No project workflow is available for this channel.", inputDisabled: false, workflowDisabled: true, urlValidation: "", canEditInputs };
  }
  if (!workflowOption) {
    return { disabled: true, label: "Create Project", helper: "Select a workflow before creating a project.", inputDisabled: false, workflowDisabled: false, urlValidation, canEditInputs };
  }
  if (urlValidation) {
    return { disabled: true, label: "Create Project", helper: urlValidation, inputDisabled: false, workflowDisabled: false, urlValidation, canEditInputs };
  }
  if (!trimmedUrl) {
    return { disabled: true, label: "Create Project", helper: "Paste a competitor YouTube URL to start a new project.", inputDisabled: false, workflowDisabled: false, urlValidation: "", canEditInputs };
  }
  return {
    disabled: busy,
    label: busy ? "Creating Project..." : "Create Project",
    helper: busy ? "Creating a canonical project for the selected channel..." : "Create a canonical project under the selected channel with an explicit server-approved workflow binding.",
    inputDisabled: false,
    workflowDisabled: false,
    urlValidation: "",
    canEditInputs
  };
}

function transcriptSaveModel() {
  if (!state.selectedChannelSlug) {
    return { disabled: true, label: "Save Transcript", helper: "Select a channel first." };
  }
  if (!state.selectedProjectSlug) {
    return { disabled: true, label: "Save Transcript", helper: "Select a project first." };
  }
  if (state.isLoadingProjectDetail || !state.selectedProjectDetail) {
    return { disabled: true, label: "Save Transcript", helper: "Load the selected project detail before saving its transcript." };
  }
  if (!String(state.transcriptDraft || "").trim()) {
    return { disabled: true, label: "Save Transcript", helper: "Transcript text must not be empty." };
  }
  const busy = state.transcriptSaveAction.busy
    && state.transcriptSaveAction.slug === state.selectedChannelSlug
    && state.transcriptSaveAction.projectSlug === state.selectedProjectSlug;
  return {
    disabled: busy,
    label: busy ? "Saving Transcript..." : "Save Transcript",
    helper: "Save transcript text through the canonical selected-channel project route."
  };
}

function validationModel() {
  if (!state.selectedChannelSlug) {
    return { disabled: true, label: "Validate Inputs", helper: "Select a channel first." };
  }
  if (!state.selectedProjectSlug) {
    return { disabled: true, label: "Validate Inputs", helper: "Select a project first." };
  }
  if (state.isLoadingProjectDetail || !state.selectedProjectDetail) {
    return { disabled: true, label: "Validate Inputs", helper: "Load the selected project detail before validating inputs." };
  }
  const busy = state.validationAction.busy
    && state.validationAction.slug === state.selectedChannelSlug
    && state.validationAction.projectSlug === state.selectedProjectSlug;
  return {
    disabled: busy,
    label: busy ? "Validating Inputs..." : "Validate Inputs",
    helper: "Run local canonical validation for the selected project only."
  };
}

function validationResultPasses(result) {
  if (!result || typeof result !== "object") return false;
  const checks = result.checks;
  if (!checks || typeof checks !== "object") return false;
  const values = Object.values(checks);
  if (!values.length) return false;
  return values.every((value) => value === true);
}

function validationCheckLabel(key) {
  const labels = {
    project_json: "Project metadata exists",
    competitor_reference: "Competitor reference exists",
    channel_learnings: "Channel learnings snapshot is present",
    channel_metrics: "Channel metrics snapshot is present",
    competitor_raw_json: "Competitor source metadata exists",
    transcript_real_content: "Transcript has real content",
    workflow_directory: "Workflow directory exists",
    ownership: "Project ownership matches the selected channel",
    safe_snapshot_paths: "Snapshot paths stay inside the canonical project",
  };
  return labels[key] || key.replace(/_/g, " ");
}

function failedValidationCheckNames(result) {
  if (!result || typeof result !== "object" || !result.checks || typeof result.checks !== "object") return [];
  return Object.keys(result.checks).filter((key) => result.checks[key] !== true).map(validationCheckLabel);
}

function validationStatusModel() {
  const validate = validationModel();
  const busy = state.validationAction.busy
    && state.validationAction.slug === state.selectedChannelSlug
    && state.validationAction.projectSlug === state.selectedProjectSlug;
  const feedback = projectFeedbackForSelection();
  const result = state.selectedProjectValidation;
  const passed = validationResultPasses(result)
    && !!(result && result.project && result.project.workflow_input_status === "READY" && result.project.runnable === true);
  const failedChecks = failedValidationCheckNames(result);

  if (!state.selectedChannelSlug || !state.selectedProjectSlug || !state.selectedProjectDetail) {
    return {
      state: "UNAVAILABLE",
      passed: false,
      buttonClass: "secondary",
      buttonLabel: validate.label,
      buttonDisabled: true,
      helper: validate.helper,
      statusLabel: "WAITING",
      title: "Validation unavailable",
      detail: validate.helper,
      failedChecks: [],
    };
  }
  if (busy) {
    return {
      state: "RUNNING",
      passed: false,
      buttonClass: "primary",
      buttonLabel: validate.label,
      buttonDisabled: true,
      helper: "Validation is still running for the selected project.",
      statusLabel: "RUNNING",
      title: "Validation running",
      detail: "Checking canonical project inputs and refreshing workflow readiness.",
      failedChecks: [],
    };
  }
  if (!result) {
    return {
      state: "REQUIRED",
      passed: false,
      buttonClass: "primary",
      buttonLabel: "Run Validation",
      buttonDisabled: validate.disabled,
      helper: "Run validation first.",
      statusLabel: "REQUIRED",
      title: "Validation required",
      detail: "Run canonical validation for the selected project before parsing the pasted output.",
      failedChecks: [],
    };
  }
  if (!passed) {
    const failedSummary = failedChecks.length
      ? `Fix these checks before parsing: ${failedChecks.join(", ")}`
      : "Canonical validation did not mark this project ready for workflow parsing.";
    return {
      state: "FAILED",
      passed: false,
      buttonClass: "primary",
      buttonLabel: "Run Validation Again",
      buttonDisabled: validate.disabled,
      helper: failedSummary,
      statusLabel: "FAILED",
      title: "Validation failed",
      detail: feedback.kind === "error" && feedback.text ? feedback.text : failedSummary,
      failedChecks,
    };
  }
  return {
    state: "PASSED",
    passed: true,
    buttonClass: "secondary",
    buttonLabel: "Run Validation Again",
    buttonDisabled: validate.disabled,
    helper: "Validation passed. Parse and Preview can now check the pasted output.",
    statusLabel: "PASS",
    title: "Validation passed",
    detail: "Canonical validation confirms the selected project is ready for workflow parsing.",
    failedChecks: [],
  };
}

function setSelectedChannelSlug(nextSlug) {
  if (!nextSlug) {
    localStorage.removeItem(SELECTED_CHANNEL_STORAGE_KEY);
    state.selectedChannelSlug = null;
  } else {
    localStorage.setItem(SELECTED_CHANNEL_STORAGE_KEY, nextSlug);
    state.selectedChannelSlug = nextSlug;
  }
  state.selectedChannelSummary = null;
  clearSelectedChannelAnalyticsState();
  state.errorMessage = "";
  clearActionFeedback();
  clearProjectState();
  if (state.summaryAbortController) state.summaryAbortController.abort();
  render();
  if (state.selectedChannelSlug) {
    loadSelectedChannelSummary();
  }
}

function setSelectedProjectSlug(nextSlug) {
  const normalized = nextSlug && state.projects.some((item) => item.project_slug === nextSlug) ? nextSlug : null;
  if (normalized === state.selectedProjectSlug && state.selectedProjectDetail) return;
  rememberProjectSlugForChannel(state.selectedChannelSlug, normalized);
  state.selectedProjectSlug = normalized;
  state.selectedProjectDetail = null;
  state.selectedProjectTranscript = null;
  state.selectedProjectValidation = null;
  clearWorkflowState();
  state.projectDetailError = "";
  state.transcriptDraft = transcriptDraftForProject(state.selectedChannelSlug, normalized);
  state.transcriptFocusPendingProjectKey = normalized ? projectSelectionKey(state.selectedChannelSlug, normalized) : null;
  clearProjectFeedback();
  render();
  if (state.selectedProjectSlug) {
    loadSelectedProjectDetail();
  }
}

function syncChannelSelector() {
  const select = document.getElementById("channelSelect");
  const options = ['<option value="">Select a channel</option>'];
  for (const channel of state.channels) {
    const selected = channel.channel_slug === state.selectedChannelSlug ? " selected" : "";
    options.push(`<option value="${escapeHtml(channel.channel_slug)}"${selected}>${escapeHtml(channel.display_name)}</option>`);
  }
  select.innerHTML = options.join("");
  select.disabled = state.isLoadingChannels || state.channels.length === 0;
}

function renderWorkspaceNavigation() {
  activeWorkspaceList().forEach((workspaceId) => {
    const button = document.getElementById(`nav${workspaceId.charAt(0).toUpperCase()}${workspaceId.slice(1)}Btn`);
    if (!button) return;
    const active = state.activeWorkspace === workspaceId;
    button.className = active ? "workspace-tab active" : "workspace-tab";
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const overview = document.getElementById("overviewWorkspace");
  const workflow = document.getElementById("workflowWorkspace");
  const analytics = document.getElementById("analyticsWorkspace");
  if (overview) overview.style.display = state.activeWorkspace === "overview" ? "grid" : "none";
  if (workflow) workflow.style.display = state.activeWorkspace === "workflow" ? "grid" : "none";
  if (analytics) analytics.style.display = state.activeWorkspace === "analytics" ? "grid" : "none";
}

function renderAppHeaderState() {
  const channelTarget = document.getElementById("appSelectedChannel");
  const projectTarget = document.getElementById("appSelectedProject");
  const overallLabelTarget = document.getElementById("appOverallStateLabel");
  const overallTarget = document.getElementById("appOverallState");
  const channel = selectedChannelRecord();
  const headerState = headerStateModel();
  const overall = headerState.value;
  if (channelTarget) {
    channelTarget.textContent = channel ? (channel.display_name || channel.channel_slug || "Selected channel") : "No channel selected";
  }
  if (projectTarget) {
    projectTarget.textContent = state.selectedProjectSlug ? selectedProjectDisplayName() : "No project selected";
  }
  if (overallLabelTarget) {
    overallLabelTarget.textContent = headerState.label;
  }
  if (overallTarget) {
    overallTarget.className = `pill ${["CONNECTED", "READY", "PRODUCTION_READY", "PASS", "APPROVED"].includes(String(overall).toUpperCase()) ? "pass" : (["ERROR", "FAILED", "DISCONNECTED"].includes(String(overall).toUpperCase()) ? "missing" : "pending")}`;
    overallTarget.textContent = friendlyStatusLabel(overall);
  }
}

function renderWorkspaceIntro() {
  const message = document.getElementById("message");
  if (!message) return;
  if (state.errorMessage) {
    message.textContent = state.errorMessage;
    return;
  }
  if (state.isLoadingSummary) {
    message.textContent = "Loading selected channel summary...";
    return;
  }
  if (!state.selectedChannelSlug) {
    message.textContent = "Select a channel to load the current workspace.";
    return;
  }
  if (state.activeWorkspace === "workflow") {
    message.textContent = "Content Workflow covers creating, continuing, reviewing, and exporting content for the selected project.";
    return;
  }
  if (state.activeWorkspace === "analytics") {
    message.textContent = "Analytics focuses on syncing, checking, and exporting channel data.";
    return;
  }
  message.textContent = "Overview focuses on current status and the next supported action.";
}

function renderOverviewWorkspace() {
  const panel = document.getElementById("summaryPanel");
  const action = recommendedNextAction();
  const channel = selectedChannelRecord();
  const project = selectedProjectSummaryRecord();
  const analytics = state.selectedChannelAnalytics;
  const analyticsSummary = analyticsPlainLanguageSummary(analytics);
  const productionPackage = state.selectedProjectProductionPackage;
  const workflowState = currentWorkflowState();
  if (!state.selectedChannelSlug) {
    panel.innerHTML = `
      <div class="empty-state">
        <strong>Selection required</strong>
        <div class="meta">Choose a channel to load its operational overview.</div>
      </div>
    `;
    return;
  }

  panel.innerHTML = `
    <section class="panel overview-hero">
      <div class="workspace-block-header">
        <div>
          <h3 style="margin:0">Overview</h3>
          <div class="meta">Where you are, what is ready, and what to do next.</div>
        </div>
        <div>${pill(action.status)}</div>
      </div>
      <div class="mini-grid">
        <div class="card summary-item"><strong>Channel</strong><div class="meta">${escapeHtml(channel ? (channel.display_name || friendlyStatusLabel(channel.status)) : "Loading selected channel")}</div><div>${pill(channel ? (channel.status || "LOADING") : "LOADING")}</div></div>
        <div class="card summary-item"><strong>Content workflow</strong><div class="meta">${escapeHtml(state.selectedProjectSlug ? selectedProjectDisplayName() : "Choose a project to continue")}</div><div>${pill(workflowState.current_step_status || currentWorkflowLifecycle())}</div></div>
        <div class="card summary-item"><strong>Production package</strong><div class="meta">${escapeHtml(productionStatusSentence(productionPackage))}</div><div>${pill(productionPackage && productionPackage.ready_for_export ? "PRODUCTION_READY" : "WAITING")}</div></div>
        <div class="card summary-item"><strong>Analytics</strong><div class="meta">${escapeHtml(analyticsSummary.detail)}</div><div>${pill(analyticsSummary.label)}</div></div>
      </div>
      <div class="next-action">
        <strong>Recommended Next Action: ${escapeHtml(action.title)}</strong>
        <div class="meta">${escapeHtml(action.detail)}</div>
        <div class="row" style="margin-top:12px">
          <button type="button" class="primary" id="recommendedActionBtn">${escapeHtml(action.button_label || (action.workspace === "workflow" ? "Open Content Workflow" : (action.workspace === "analytics" ? "Open Analytics" : "Open Overview")))}</button>
        </div>
      </div>
      <details>
        <summary>Technical Details</summary>
        <div class="stack" style="margin-top:12px">
          <div class="check"><strong>Channel Slug</strong><div class="meta mono">${escapeHtml(state.selectedChannelSlug || "")}</div></div>
          <div class="check"><strong>Workflow State Revision</strong><div class="meta">${escapeHtml(String(workflowState.state_revision ?? ""))}</div></div>
          <div class="check"><strong>Production Approved Group</strong><div class="meta mono">${escapeHtml((productionPackage && productionPackage.approved_group_id) || "")}</div></div>
          <div class="check"><strong>Current Step ID</strong><div class="meta mono">${escapeHtml(workflowState.current_step_id || "")}</div></div>
          <div class="check"><strong>Current Lifecycle Code</strong><div class="meta mono">${escapeHtml(currentWorkflowLifecycle())}</div></div>
          <div class="check"><strong>Analytics Export</strong><div class="meta">${escapeHtml(analytics && analytics.export_url ? "Available" : "Unavailable")}</div></div>
        </div>
      </details>
    </section>
  `;
}

function renderChannelState() {
  const target = document.getElementById("channelState");
  if (state.isLoadingChannels && state.channels.length === 0) {
    target.innerHTML = `<div class="meta">Loading available channels...</div>`;
    return;
  }
  if (state.channels.length === 0) {
    target.innerHTML = `
      <div class="check"><strong>Channels</strong>${pill("MISSING")}</div>
      <div class="meta">No canonical channels are available yet. Create or migrate a channel workspace before using the UI.</div>
    `;
    return;
  }
  if (!state.selectedChannelSlug) {
    target.innerHTML = `
      <div class="check"><strong>Selection</strong>${pill("REQUIRED")}</div>
      <div class="meta">Choose a channel to load its canonical summary. The UI will not guess a fallback channel.</div>
    `;
    return;
  }
  const selected = state.channels.find((item) => item.channel_slug === state.selectedChannelSlug);
  const summary = state.selectedChannelSummary ? state.selectedChannelSummary.channel : selected;
  const disconnected = summary && summary.status && summary.status !== "CONNECTED";
  target.innerHTML = `
    <div class="check"><strong>Status</strong>${pill(summary ? summary.status : "LOADING")}</div>
    <div class="meta">${escapeHtml(summary ? summary.display_name : state.selectedChannelSlug)}</div>
    ${disconnected ? '<div class="meta">This channel is disconnected. Read-only summary is available, but workflow actions stay unavailable.</div>' : ""}
  `;
}

function renderActionState() {
  const target = document.getElementById("actionState");
  const oauthButton = document.getElementById("connectChannelBtn");
  const metricsButton = document.getElementById("syncMetricsBtn");
  const recent = document.getElementById("recent");
  const windowSelect = document.getElementById("window");
  const oauth = oauthButtonModel();
  const metrics = metricsButtonModel();
  const canEditMetricsInputs = !!state.selectedChannelSlug && !!state.selectedChannelSummary;
  oauthButton.disabled = oauth.disabled;
  oauthButton.textContent = oauth.label;
  metricsButton.disabled = metrics.disabled;
  metricsButton.textContent = metrics.label;
  recent.disabled = !canEditMetricsInputs || (state.metricsAction.busy && state.metricsAction.slug === state.selectedChannelSlug);
  windowSelect.disabled = !canEditMetricsInputs || (state.metricsAction.busy && state.metricsAction.slug === state.selectedChannelSlug);

  const feedback = state.actionFeedback.slug === state.selectedChannelSlug ? state.actionFeedback : { kind: "", text: "" };
  const feedbackHtml = feedback.text
    ? `<div class="check"><strong>${feedback.kind === "error" ? "Action Error" : "Action Status"}</strong>${pill(feedback.kind === "error" ? "ERROR" : "PASS")}</div><div class="meta">${escapeHtml(feedback.text)}</div>`
    : `<div class="meta">Channel maintenance actions are available here when needed.</div>`;

  target.innerHTML = `
    <div class="check"><strong>Connection</strong>${pill(oauth.disabled ? "WAITING" : "READY")}</div>
    <div class="meta">${escapeHtml(oauth.helper)}</div>
    <div class="check"><strong>Maintenance</strong>${pill(metrics.disabled ? "WAITING" : "READY")}</div>
    <div class="meta">${escapeHtml(metrics.helper)}</div>
    ${feedbackHtml}
  `;
}

function projectManagementSectionHtml() {
  const refresh = projectsRefreshModel();
  const create = createProjectModel();
  const channel = selectedChannelRecord();
  const workflowOptions = createSelectableWorkflowOptions();
  const currentWorkflowValue = selectedCreateWorkflowValue();
  const feedback = state.projectFeedback.channelSlug === state.selectedChannelSlug && !state.projectFeedback.projectSlug
    ? state.projectFeedback
    : { kind: "", text: "" };
  const urlValidation = state.isCreateProjectPanelOpen && state.createProjectUrlDraft ? createProjectUrlValidationMessage(state.createProjectUrlDraft) : "";
  const items = state.projects.map((project) => {
    const selected = project.project_slug === state.selectedProjectSlug;
    return `
      <button
        class="${selected ? "primary" : "secondary"}"
        data-project-slug="${escapeHtml(project.project_slug)}"
        style="width:100%;text-align:left"
      >
        <div class="check"><strong>${escapeHtml(project.project_name || project.display_name || humanizeIdentifier(project.project_slug || ""))}</strong>${pill(project.status || "UNKNOWN")}</div>
        <div class="meta">${escapeHtml(project.workflow_input_status ? friendlyStatusLabel(project.workflow_input_status) : "Ready for workflow review")}</div>
      </button>
    `;
  });
  const createStatusHtml = feedback.text
    ? `
      <div id="projectCreateState" class="status" role="status" aria-live="polite">
        <div class="check"><strong>${feedback.kind === "error" ? "Create Error" : "Create Status"}</strong>${pill(feedback.kind === "error" ? "ERROR" : "PASS")}</div>
        <div class="meta">${escapeHtml(feedback.text)}</div>
      </div>
    `
    : urlValidation
    ? `
      <div id="projectCreateState" class="status" role="status" aria-live="polite">
        <div class="check"><strong>Validation</strong>${pill("WAITING")}</div>
        <div class="meta">${escapeHtml(urlValidation)}</div>
      </div>
    `
    : `
      <div id="projectCreateState" class="status" role="status" aria-live="polite">
        <div class="check"><strong>Create</strong>${pill(create.disabled ? "WAITING" : "READY")}</div>
        <div class="meta">${escapeHtml(create.helper)}</div>
      </div>
    `;
  const workflowFieldHtml = workflowOptions.length > 1
    ? `
      <label for="createProjectWorkflowBinding">Workflow Version</label>
      <select id="createProjectWorkflowBinding" ${create.workflowDisabled ? "disabled" : ""}>
        <option value="">Select a workflow</option>
        ${workflowOptions.map((option) => {
          const value = workflowOptionValue(option);
          const selected = currentWorkflowValue === value ? " selected" : "";
          const label = workflowOptionLabel(option);
          return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(label)}</option>`;
        }).join("")}
      </select>
    `
    : "";
  const createPanelHtml = state.isCreateProjectPanelOpen
    ? `
      <section class="card" id="createProjectPanel">
        <div class="step-heading">
          <div>
            <strong>Create New Project</strong>
            <div class="meta">Start a new content project without leaving the current workflow view.</div>
          </div>
        </div>
        <label for="createProjectChannelDisplay">Channel</label>
        <input id="createProjectChannelDisplay" value="${escapeHtml(channel ? (channel.display_name || channel.channel_slug || "") : "")}" readonly aria-readonly="true">
        <label for="createProjectUrlInput">Competitor video URL *</label>
        <input id="createProjectUrlInput" placeholder="https://www.youtube.com/watch?v=..." value="${escapeHtml(state.createProjectUrlDraft)}" ${create.inputDisabled ? "disabled" : ""} aria-describedby="projectCreateState">
        <label for="createProjectNameInput">Project Name (optional)</label>
        <input id="createProjectNameInput" placeholder="Optional project title override" value="${escapeHtml(state.createProjectNameDraft)}" ${create.inputDisabled ? "disabled" : ""}>
        ${workflowFieldHtml}
        ${createStatusHtml}
        <div class="row">
          <button type="button" class="secondary" id="cancelCreateProjectBtn">Cancel</button>
          <button type="button" class="primary" id="submitCreateProjectBtn" ${create.disabled ? "disabled" : ""}>${escapeHtml(create.label)}</button>
        </div>
      </section>
    `
    : "";
  const changeProjectHtml = state.isChangeProjectPanelOpen
    ? `
      <section class="card" id="changeProjectPanel">
        <div class="step-heading">
          <div>
            <strong>Change Project</strong>
            <div class="meta">Choose another canonical project for the selected channel.</div>
          </div>
        </div>
        <div class="row">
          <button class="secondary" id="refreshProjectsBtn" ${refresh.disabled ? "disabled" : ""}>${escapeHtml(refresh.label)}</button>
        </div>
        <div class="meta" style="margin-top:12px">${escapeHtml(refresh.helper)}</div>
        ${state.projects.length ? `<div class="stack" style="margin-top:12px">${items.join("")}</div>` : `<div class="notice" style="margin-top:12px"><strong>No canonical projects yet</strong><span class="meta">Create one to begin the workflow.</span></div>`}
      </section>
    `
    : "";
  return `
    <div class="row" id="projectActionBar" style="align-items:center;justify-content:flex-start">
      <button type="button" class="primary" id="openCreateProjectBtn" aria-expanded="${state.isCreateProjectPanelOpen ? "true" : "false"}">+ New Project</button>
      <button type="button" class="secondary" id="openChangeProjectBtn" aria-expanded="${state.isChangeProjectPanelOpen ? "true" : "false"}">Change Project</button>
    </div>
    ${createPanelHtml}
    ${changeProjectHtml}
  `;
}

function syncProjectManagementControls() {
  const refresh = projectsRefreshModel();
  const create = createProjectModel();
  const newProjectButton = document.getElementById("openCreateProjectBtn");
  if (newProjectButton) {
    newProjectButton.disabled = !state.selectedChannelSlug || (state.createProjectAction.busy && state.createProjectAction.slug === state.selectedChannelSlug);
    newProjectButton.textContent = "+ New Project";
  }
  const changeProjectButton = document.getElementById("openChangeProjectBtn");
  if (changeProjectButton) {
    changeProjectButton.disabled = !state.selectedChannelSlug;
    changeProjectButton.textContent = "Change Project";
  }
  const refreshButton = document.getElementById("refreshProjectsBtn");
  if (refreshButton) {
    refreshButton.disabled = refresh.disabled;
    refreshButton.textContent = refresh.label;
  }
  const submitButton = document.getElementById("submitCreateProjectBtn");
  if (submitButton) {
    submitButton.disabled = create.disabled;
    submitButton.textContent = create.label;
  }
  const cancelButton = document.getElementById("cancelCreateProjectBtn");
  if (cancelButton) {
    cancelButton.disabled = state.createProjectAction.busy && state.createProjectAction.slug === state.selectedChannelSlug;
  }
  const urlInput = document.getElementById("createProjectUrlInput");
  if (urlInput) {
    urlInput.disabled = create.inputDisabled;
    urlInput.value = state.createProjectUrlDraft;
  }
  const nameInput = document.getElementById("createProjectNameInput");
  if (nameInput) {
    nameInput.disabled = create.inputDisabled;
    nameInput.value = state.createProjectNameDraft;
  }
  const channelDisplay = document.getElementById("createProjectChannelDisplay");
  const channel = selectedChannelRecord();
  if (channelDisplay) {
    channelDisplay.value = channel ? (channel.display_name || channel.channel_slug || "") : "";
  }
  const workflowSelect = document.getElementById("createProjectWorkflowBinding");
  if (workflowSelect) {
    workflowSelect.disabled = create.workflowDisabled;
    workflowSelect.value = selectedCreateWorkflowValue();
  }
}

function renderProjectListState() {
  const stateTarget = document.getElementById("projectListState");
  const listTarget = document.getElementById("projectListPanel");

  if (!state.selectedChannelSlug) {
    stateTarget.innerHTML = `
      <div class="check"><strong>Project</strong>${pill("WAITING")}</div>
      <div class="meta">Select a channel to load its canonical project list.</div>
    `;
    listTarget.innerHTML = "";
    return;
  }

  if (state.isLoadingProjects && state.projects.length === 0) {
    stateTarget.innerHTML = `
      <div class="check"><strong>Project</strong>${pill("LOADING")}</div>
      <div class="meta">Loading canonical projects for the selected channel...</div>
    `;
    listTarget.innerHTML = "";
    return;
  }

  if (state.projectListError) {
    stateTarget.innerHTML = `
      <div class="check"><strong>Project</strong>${pill("ERROR")}</div>
      <div class="meta">${escapeHtml(state.projectListError)}</div>
    `;
  } else {
    stateTarget.innerHTML = `
      <div class="check"><strong>Selected Project</strong>${pill(state.selectedProjectSlug ? "READY" : "WAITING")}</div>
      <div class="meta">${escapeHtml(state.selectedProjectSlug ? selectedProjectDisplayName() : "Start a new project or choose an existing one.")}</div>
    `;
  }

  listTarget.innerHTML = projectManagementSectionHtml();
  syncProjectManagementControls();
}

function renderProjectCreateState() {
  syncProjectManagementControls();
}

function renderProjectDetailState() {
  const target = document.getElementById("projectDetailState");
  const shellHeader = document.getElementById("projectDetailShellHeader");
  const transcriptPanel = document.getElementById("projectTranscriptPanel");
  const panel = document.getElementById("projectDetailPanel");
  const validationPanel = document.getElementById("validationPanel");
  const save = transcriptSaveModel();
  const validate = validationModel();
  const validationStatus = validationStatusModel();
  const feedback = projectFeedbackForSelection();
  const project = selectedProjectSummaryRecord();

  if (!state.selectedChannelSlug) {
    target.innerHTML = `
      <div class="check"><strong>Project Detail</strong>${pill("WAITING")}</div>
      <div class="meta">Select a channel before choosing a project.</div>
    `;
    transcriptPanel.innerHTML = "";
    panel.innerHTML = "";
    validationPanel.innerHTML = "";
    return;
  }

  if (!state.selectedProjectSlug) {
    target.innerHTML = `
      <div class="check"><strong>Project Detail</strong>${pill("WAITING")}</div>
      <div class="meta">Select a canonical project to load its detail, transcript, and workflow controls.</div>
    `;
    transcriptPanel.innerHTML = "";
    panel.innerHTML = "";
    validationPanel.innerHTML = "";
    return;
  }

  target.innerHTML = `
    <div class="check"><strong>Project</strong>${pill(state.isLoadingProjectDetail ? "LOADING" : "READY")}</div>
    <div class="meta">${escapeHtml(selectedProjectDisplayName())}</div>
    <div class="meta">${escapeHtml(feedback.text || state.projectDetailError || validate.helper || save.helper)}</div>
  `;

  if (state.isLoadingProjectDetail && !state.selectedProjectDetail) {
    transcriptPanel.innerHTML = "";
    panel.innerHTML = `<div class="notice"><strong>Loading</strong><span class="meta">Fetching canonical project detail and transcript...</span></div>`;
    validationPanel.innerHTML = "";
    return;
  }

  if (!state.selectedProjectDetail) {
    transcriptPanel.innerHTML = "";
    panel.innerHTML = `
      <div class="notice">
        <strong>Project detail unavailable</strong>
        <span class="meta">${escapeHtml(state.projectDetailError || "The selected project detail is not available yet.")}</span>
      </div>
    `;
    validationPanel.innerHTML = "";
    return;
  }

  const detail = state.selectedProjectDetail.project || {};
  const workflow = state.selectedProjectWorkflow;
  const workflowState = workflow && workflow.state ? workflow.state : {};
  const binding = workflow && workflow.binding ? workflow.binding : {};
  const definition = workflow && workflow.definition ? workflow.definition : {};
  const promptSet = definition.prompt_set || {};
  const workflowSteps = workflowStepList();
  const selectedStep = selectedWorkflowStepRecord();
  const bundle = activeBundleRecord();
  const bundleFeedback = bundleFeedbackForSelection();
  const bundleButton = bundleButtonModel();
  const copyButton = copyBundleButtonModel();
  const parseButton = parseOutputButtonModel();
  const saveCandidateButton = saveCandidateButtonModel();
  const approveCandidateButton = candidateDecisionButtonModel("APPROVE");
  const rejectCandidateButton = candidateDecisionButtonModel("REJECT");
  const candidateSaveFeedback = candidateSaveFeedbackForSelection();
  const parsedOutput = parsedOutputMatchesSelection(state.parsedOutputResult) ? state.parsedOutputResult : null;
  const currentStepLabel = workflowSteps.find((step) => step.step_id === workflowState.current_step_id);
  const nextStepLabel = workflowSteps.find((step) => step.step_id === workflowState.next_step_id);
  const productionPackage = state.selectedProjectProductionPackage;
  const productionArtifacts = productionPackage && Array.isArray(productionPackage.artifacts) ? productionPackage.artifacts : [];
  const productionStatus = state.isLoadingProductionPackage ? "LOADING" : (productionPackage && productionPackage.ready_for_export ? "READY" : (productionPackage ? "WAITING" : "UNKNOWN"));
  const selectedCandidate = selectedStep ? stepCandidateSummary(selectedStep.step_id) : null;
  const lastSavedCandidate = state.lastSaveCandidateResult
    && state.lastSaveCandidateResult.identity
    && state.lastSaveCandidateResult.identity.channel_slug === state.selectedChannelSlug
    && state.lastSaveCandidateResult.identity.project_slug === state.selectedProjectSlug
    && state.lastSaveCandidateResult.identity.step_id === (selectedStep && selectedStep.step_id)
      ? state.lastSaveCandidateResult
      : null;
  const workflowCompleted = !!(productionPackage && (productionPackage.lifecycle === "PRODUCTION_READY" || productionPackage.ready_for_export));
  const transcriptPanelState = transcriptPanelProjectState();
  const transcriptSummaryLabel = transcriptPanelState.transcript_saved ? "Transcript saved" : (transcriptPanelState.has_draft ? "Draft preserved" : "Manual Transcript");
  const transcriptDisabled = save.disabled && !(state.selectedChannelSlug && state.selectedProjectSlug && state.selectedProjectDetail);
  const compactProjectDetailShell = !!(transcriptPanelState.show_primary_panel || workflowCompleted);
  if (shellHeader) {
    shellHeader.hidden = compactProjectDetailShell;
    shellHeader.style.display = compactProjectDetailShell ? "none" : "flex";
  }

  if (compactProjectDetailShell) {
    target.innerHTML = "";
  }

  const transcriptPanelStatusHtml = `
    <div class="status" style="margin-top:12px" role="status" aria-live="polite">
      <div class="check"><strong>${escapeHtml(transcriptSummaryLabel)}</strong>${pill(transcriptPanelState.transcript_required ? "READY" : (transcriptPanelState.transcript_saved ? "APPROVED" : (transcriptPanelState.has_draft ? "WAITING" : "READY")))}</div>
      <div class="meta">${escapeHtml(transcriptPanelState.transcript_required ? "Paste the competitor transcript here to begin Prompt 1." : (save.helper || "Manual transcript input is available when this project needs it again."))}</div>
    </div>
  `;
  const transcriptLabelHtml = transcriptPanelState.show_primary_panel ? "" : `<label for="transcript" style="margin-top:12px">Manual Transcript</label>`;
  const transcriptTextareaStyle = transcriptPanelState.show_primary_panel ? ` style="min-height:140px;height:140px"` : "";
  const transcriptControlsHtml = `
    ${transcriptLabelHtml}
    <textarea id="transcript" aria-label="Manual Transcript" placeholder="Paste the manually collected competitor transcript here."${transcriptTextareaStyle}${transcriptDisabled ? " disabled" : ""}>${escapeHtml(state.transcriptDraft)}</textarea>
    <div class="row" style="margin-top:12px">
      <button id="saveTranscriptBtn" class="primary"${save.disabled ? " disabled" : ""}>${escapeHtml(save.label)}</button>
    </div>
  `;
  const transcriptSecondaryControlsHtml = `
    <div class="row" style="margin-top:12px">
      <button class="ghost" id="openProjectBtn" disabled data-cutover-state="disabled">Open Project Folder</button>
      <button class="ghost" id="openTranscriptBtn" disabled data-cutover-state="disabled">Open Transcript File</button>
    </div>
  `;

  if (transcriptPanelState.show_primary_panel) {
    transcriptPanel.innerHTML = `
      <section class="panel" id="manualTranscriptPrimaryPanel">
        <div class="workspace-block-header">
          <div>
            <h3 style="margin:0">Manual Transcript</h3>
            <div class="meta">Paste the competitor transcript here to begin Prompt 1.</div>
          </div>
          <div>${pill("READY")}</div>
        </div>
        ${transcriptControlsHtml}
        ${transcriptPanelStatusHtml}
      </section>
    `;
  } else if (transcriptPanelState.show_collapsed_panel) {
    transcriptPanel.innerHTML = `
      <details>
        <summary>Manual Transcript</summary>
        <div class="card" style="margin-top:12px">
          <div class="meta">${escapeHtml(transcriptPanelState.transcript_saved ? "The transcript is already available for this project." : "This unsent transcript draft is preserved for the selected project only.")}</div>
          ${transcriptControlsHtml}
          ${transcriptPanelStatusHtml}
        </div>
      </details>
    `;
  } else {
    transcriptPanel.innerHTML = "";
  }

  const renderArtifacts = (items, requiredLabel) => {
    if (!items.length) {
      return `<div class="notice"><strong>No ${requiredLabel.toLowerCase()} artifacts</strong><span class="meta">This step does not declare any ${requiredLabel.toLowerCase()} artifacts.</span></div>`;
    }
    return items.map((artifact) => `
      <div class="check">
        <div>
          <strong>${escapeHtml(artifact.display_name || artifact.artifact_id || "Artifact")}</strong>
          <div class="meta mono">${escapeHtml(artifact.relative_path || "")}</div>
        </div>
        <div>${pill(artifact.exists ? "FOUND" : "MISSING")}</div>
      </div>
    `).join("");
  };

  const workflowRows = workflowSteps.map((step) => {
    const selected = step.step_id === state.selectedWorkflowStepId;
    const candidate = stepCandidateSummary(step.step_id);
    const isCurrent = workflowState.current_step_id === step.step_id;
    const isApproved = !!(candidate && candidate.approved_group_id);
    const statusLabel = isApproved ? "APPROVED" : (candidate && candidate.candidate_group_id ? "CANDIDATE" : (isCurrent ? (workflowState.current_step_status || "READY") : "READY"));
    const icon = isApproved ? "✓" : (candidate && candidate.candidate_group_id ? "●" : (isCurrent ? "→" : "•"));
    const buttonClass = selected ? "active" : (isApproved ? "completed" : (isCurrent ? "current" : ""));
    return `
      <button
        type="button"
        class="${buttonClass}"
        data-workflow-step-id="${escapeHtml(step.step_id)}"
      >
        <div class="step-heading">
          <div>
            <strong>${escapeHtml(`${icon} Prompt ${step.order}`)}</strong>
            <div class="meta">${escapeHtml(step.display_name)}</div>
          </div>
          <div>${pill(selected ? "READY" : statusLabel)}</div>
        </div>
      </button>
    `;
  }).join("");
  const compactWorkflowRows = workflowSteps.map((step) => {
    const selected = step.step_id === state.selectedWorkflowStepId;
    const statusLabel = stepStatusLabel(step);
    const isCurrent = workflowState.current_step_id === step.step_id;
    const isApproved = statusLabel === "APPROVED";
    const isCandidate = statusLabel === "CANDIDATE";
    const icon = isApproved ? "✓" : (isCandidate ? "•" : String(step.order));
    const buttonClass = selected ? "active" : (isApproved ? "completed" : (isCurrent ? "current" : ""));
    const conciseStatus = (isApproved || isCandidate || (isCurrent && statusLabel !== "READY")) ? friendlyStatusLabel(statusLabel) : "";
    return `
      <button
        type="button"
        class="${buttonClass}"
        data-workflow-step-id="${escapeHtml(step.step_id)}"
        aria-pressed="${selected ? "true" : "false"}"
      >
        <div class="step-rail-top">
          <span class="step-token">${escapeHtml(icon)}</span>
          <span class="meta">${escapeHtml(conciseStatus || (selected ? "Selected" : ""))}</span>
        </div>
        <strong>${escapeHtml(`Prompt ${step.order}`)}</strong>
        <div class="step-title">${escapeHtml(step.display_name)}</div>
      </button>
    `;
  }).join("");

  const bundleReady = !!bundle;
  const bundleBuildError = !!(bundleFeedback.kind === "error" || state.bundleError);
  const bundleNotYetAvailable = !bundleReady && !bundleBuildError && transcriptPanelState.transcript_required;
  const bundleFeedbackHtml = bundleBuildError
    ? `<div class="check"><strong>Bundle Error</strong>${pill("ERROR")}</div><div class="meta">${escapeHtml(bundleFeedback.text || state.bundleError)}</div>`
    : bundleReady
    ? `<div class="check"><strong>Bundle Status</strong>${pill("PASS")}</div><div class="meta">${escapeHtml(bundleFeedback.text || copyButton.helper)}</div>`
    : bundleNotYetAvailable
    ? `<div class="meta">Bundle tools will appear after the required transcript is saved.</div>`
    : `<div class="meta">${escapeHtml(bundleButton.helper || copyButton.helper)}</div>`;
  const parseFeedbackHtml = state.parsedOutputError
    ? `<div class="check"><strong>Output Preview Error</strong>${pill("ERROR")}</div><div class="meta">${escapeHtml(state.parsedOutputError)}</div>`
    : `<div class="meta">${escapeHtml(parseButton.helper)}</div>`;
  const candidateFeedbackHtml = candidateSaveFeedback.text
    ? `<div class="check"><strong>${candidateSaveFeedback.kind === "error" ? "Candidate Save Error" : "Candidate Save Status"}</strong>${pill(candidateSaveFeedback.kind === "error" ? "ERROR" : "PASS")}</div><div class="meta">${escapeHtml(candidateSaveFeedback.text)}</div>`
    : `<div class="meta">${escapeHtml(saveCandidateButton.helper)}</div>`;
  const validationStatusHtml = `
    <div class="check"><strong>${escapeHtml(validationStatus.title)}</strong>${pill(validationStatus.statusLabel)}</div>
    <div class="meta">${escapeHtml(validationStatus.detail)}</div>
    ${validationStatus.failedChecks.length ? `<div class="meta" style="margin-top:8px">${escapeHtml(validationStatus.failedChecks.join(" | "))}</div>` : ""}
  `;
  const parsedArtifactsHtml = parsedOutput && Array.isArray(parsedOutput.artifacts) && parsedOutput.artifacts.length
    ? parsedOutput.artifacts.map((artifact, index) => `
      <div class="card" style="margin-top:12px">
        <div class="step-heading">
          <div>
            <strong>${escapeHtml(artifact.display_name || artifact.artifact_id || "Artifact")}</strong>
            <div class="meta mono">${escapeHtml(artifact.filename || artifact.artifact_id || "")}</div>
          </div>
          <div>${pill(artifact.validation && artifact.validation.status ? artifact.validation.status : "UNKNOWN")}</div>
        </div>
        <div class="summary-grid" style="margin-top:12px">
          <div class="card"><strong>Artifact ID</strong><div class="meta mono">${escapeHtml(artifact.artifact_id || "")}</div></div>
          <div class="card"><strong>SHA-256</strong><div class="meta mono">${escapeHtml(artifact.sha256 || "")}</div></div>
          <div class="card"><strong>Character Count</strong><div class="meta">${escapeHtml(String(artifact.character_count ?? ""))}</div></div>
        </div>
        ${(artifact.validation && Array.isArray(artifact.validation.errors) && artifact.validation.errors.length)
          ? `<div class="notice" style="margin-top:12px"><strong>Validation Errors</strong><span class="meta">${escapeHtml(artifact.validation.errors.join(" | "))}</span></div>`
          : ""
        }
        <label for="parsedArtifactPreview${index}" style="margin-top:12px">Parsed Artifact Preview</label>
        <textarea id="parsedArtifactPreview${index}" readonly spellcheck="false"></textarea>
      </div>
    `).join("")
    : "";

  const productionArtifactsHtml = productionArtifacts.length
    ? productionArtifacts.map((artifact) => `
      <div class="check">
        <div>
          <strong>${escapeHtml(artifact.filename || artifact.artifact_id || "Artifact")}</strong>
          <div class="meta">${escapeHtml(String(artifact.character_count ?? artifact.approved_character_count ?? ""))} characters</div>
          <div class="meta"><a href="${escapeHtml(artifact.file_url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(artifact.filename || artifact.artifact_id || "")}</a></div>
        </div>
        <div>${pill(artifact.exists && artifact.matches_approved_revision_metadata ? "READY" : (artifact.exists ? "CHECK" : "MISSING"))}</div>
      </div>
    `).join("")
    : `<div class="notice"><strong>No production artifacts</strong><span class="meta">The selected project has not reached a supported production handoff state yet.</span></div>`;
  const productionSectionHtml = productionPackage
    ? `
      <div class="mini-grid" style="margin-top:12px">
        <div class="card"><strong>Status</strong><div>${pill(productionPackage.ready_for_export ? "PRODUCTION_READY" : (productionPackage.lifecycle || "WAITING"))}</div></div>
        <div class="card"><strong>Download</strong><div class="meta">${escapeHtml(productionPackage.ready_for_export ? "Ready to hand off" : "Still blocked")}</div></div>
      </div>
      ${(productionPackage.lifecycle === "PRODUCTION_READY" || productionPackage.ready_for_export) ? `<div class="notice" style="margin-top:12px"><strong>Workflow completed</strong><span class="meta">This project is ready for production handoff.</span></div>` : ""}
      ${productionPackage.errors && productionPackage.errors.length ? `<div class="notice" style="margin-top:12px"><strong>Export Checks</strong><span class="meta">${escapeHtml(productionPackage.errors.join(" | "))}</span></div>` : ""}
      <div class="row" style="margin-top:12px;align-items:center">
        <a id="downloadProductionZipLink" class="action-link success" href="${escapeHtml(productionPackage.download_url || "#")}"${productionPackage.ready_for_export ? " download" : " aria-disabled=\"true\""} rel="noreferrer">${escapeHtml(productionPackage.ready_for_export ? "Download Production ZIP" : "Production ZIP unavailable")}</a>
      </div>
      <div class="stack" style="margin-top:12px">${productionArtifactsHtml}</div>
      <details style="margin-top:12px">
        <summary>Technical Details</summary>
        <div class="stack" style="margin-top:12px">
          <div class="check"><strong>Lifecycle Code</strong><div class="meta mono">${escapeHtml(productionPackage.lifecycle || "")}</div></div>
          <div class="check"><strong>Approved Group</strong><div class="meta mono">${escapeHtml(productionPackage.approved_group_id || "")}</div></div>
          <div class="check"><strong>State Revision</strong><div class="meta">${escapeHtml(String(productionPackage.state_revision ?? ""))}</div></div>
          ${productionArtifacts.map((artifact) => `<div class="check"><strong>${escapeHtml(artifact.filename || artifact.artifact_id || "Artifact")}</strong><div class="meta mono">${escapeHtml(artifact.sha256 || "")}</div></div>`).join("")}
        </div>
      </details>
    `
    : `<div class="meta" style="margin-top:12px">${escapeHtml(state.isLoadingProductionPackage ? "Loading the production handoff summary..." : "Production handoff details will appear here once the project workflow is loaded.")}</div>`;
  const selectedStepHtml = selectedStep && !workflowCompleted ? (() => {
    const invalidatedNotice = selectedCandidate && selectedCandidate.invalidated_candidate_group_id
      ? `<div class="notice" style="margin-top:12px"><strong>Invalidated Candidate</strong><span class="meta">${escapeHtml(`Candidate ${selectedCandidate.invalidated_candidate_group_id} is no longer actionable because an upstream approved output changed.`)}</span></div>`
      : "";
    const staleNotice = selectedCandidate && selectedCandidate.stale_reason
      ? `<div class="notice" style="margin-top:12px"><strong>Stale Output</strong><span class="meta">${escapeHtml(staleReasonSummary(selectedStep))}</span></div>`
      : "";
    const parsedOutputHtml = parsedOutput ? `
      <div class="summary-grid" style="margin-top:12px">
        <div class="card"><strong>Preview Status</strong><div>${pill(parsedOutput.status || "UNKNOWN")}</div></div>
        <div class="card"><strong>Response Mode</strong><div class="meta">${escapeHtml(parsedOutput.contract && parsedOutput.contract.response_mode ? parsedOutput.contract.response_mode : "Unknown")}</div></div>
        <div class="card"><strong>Raw Output SHA-256</strong><div class="meta mono">${escapeHtml(parsedOutput.raw_output && parsedOutput.raw_output.sha256 ? parsedOutput.raw_output.sha256 : "")}</div></div>
        <div class="card"><strong>Raw Character Count</strong><div class="meta">${escapeHtml(String(parsedOutput.raw_output && parsedOutput.raw_output.character_count !== undefined ? parsedOutput.raw_output.character_count : ""))}</div></div>
        <div class="card"><strong>Artifact Count</strong><div class="meta">${escapeHtml(String((parsedOutput.artifacts || []).length))}</div></div>
      </div>
      ${(parsedOutput.validation && Array.isArray(parsedOutput.validation.errors) && parsedOutput.validation.errors.length) ? `<div class="notice" style="margin-top:12px"><strong>Parse Validation Errors</strong><span class="meta">${escapeHtml(parsedOutput.validation.errors.join(" | "))}</span></div>` : ""}
      ${(selectedCandidate || lastSavedCandidate) ? `
        <div class="card" style="margin-top:12px">
          <strong>Candidate Summary</strong>
          <div class="summary-grid" style="margin-top:12px">
            <div class="card"><strong>Candidate Group</strong><div class="meta mono">${escapeHtml(selectedCandidate && selectedCandidate.candidate_group_id ? selectedCandidate.candidate_group_id : (lastSavedCandidate && lastSavedCandidate.revision_group && lastSavedCandidate.revision_group.revision_group_id) || "")}</div></div>
            <div class="card"><strong>Candidate Status</strong><div>${pill(selectedCandidate && selectedCandidate.status ? selectedCandidate.status : "CANDIDATE")}</div></div>
          </div>
        </div>
      ` : ""}
      ${parsedArtifactsHtml}
    ` : "";
    return `
      <div class="card" style="margin-top:12px">
        <div class="step-heading">
          <div>
            <strong>Selected Step Detail</strong>
            <div class="meta">Prompt ${escapeHtml(String(selectedStep.order))}: ${escapeHtml(selectedStep.display_name)}</div>
          </div>
          <div>${pill(stepStatusLabel(selectedStep))}</div>
        </div>
        <div class="summary-grid" style="margin-top:12px">
          <div class="card"><strong>Model</strong><div class="meta">${escapeHtml(selectedStep.required_model || "Unspecified")}</div></div>
          <div class="card"><strong>Conversation</strong><div class="meta">${escapeHtml(describeConversationConstraint(selectedStep))}</div></div>
          <div class="card"><strong>Save</strong><div>${pill(workflow.available_actions && workflow.available_actions[selectedStep.step_id] && workflow.available_actions[selectedStep.step_id].save_candidate ? "READY" : "WAITING")}</div></div>
          <div class="card"><strong>Approve</strong><div>${pill(workflow.available_actions && workflow.available_actions[selectedStep.step_id] && workflow.available_actions[selectedStep.step_id].approve_candidate ? "READY" : "WAITING")}</div></div>
        </div>
        ${staleNotice}
        ${invalidatedNotice}
        ${transcriptPanelState.show_primary_panel ? "" : `
        <div class="row" style="margin-top:12px">
          ${!bundleNotYetAvailable ? `<button type="button" class="primary" id="buildBundleBtn" ${bundleButton.disabled ? "disabled" : ""}>${escapeHtml(bundleButton.label)}</button>` : ""}
          ${(bundleReady || bundleBuildError) ? `<button type="button" class="secondary" id="copyBundleBtn" ${copyButton.disabled ? "disabled" : ""}>${escapeHtml(copyButton.label)}</button>` : ""}
        </div>
        <div class="status" style="margin-top:12px" role="status" aria-live="polite">${bundleFeedbackHtml}</div>
        ${bundleReady ? `
        <div class="card" style="margin-top:12px">
          <strong>Bundle Preview</strong>
          <div class="meta">The preview below is plain text from the API. Copy Complete Bundle uses the exact full stored bundle.</div>
          ${bundle ? `
            <div class="summary-grid" style="margin-top:12px">
              <div class="card"><strong>Bundle SHA-256</strong><div class="meta mono">${escapeHtml(bundle.bundle_sha256 || "")}</div></div>
              <div class="card"><strong>Character Count</strong><div class="meta">${escapeHtml(String(bundle.bundle_character_count ?? ""))}</div></div>
              <div class="card"><strong>Required Model</strong><div class="meta">${escapeHtml(bundle.required_model || "")}</div></div>
              <div class="card"><strong>Response Mode</strong><div class="meta">${escapeHtml(bundle.output_contract && bundle.output_contract.response_mode ? bundle.output_contract.response_mode : "Unknown")}</div></div>
            </div>
            <label for="bundlePreviewText" style="margin-top:12px">Complete Prompt Bundle Preview</label>
            <textarea id="bundlePreviewText" readonly spellcheck="false"></textarea>
          ` : ""}
        </div>
        ` : ""}
        <div class="card" style="margin-top:12px">
          <strong>Paste AI Output</strong>
          <div class="meta">Paste the model response for the loaded bundle. Parse and Preview checks it in memory only and does not write any artifact files.</div>
          <label for="pastedOutputText" style="margin-top:12px">AI Output</label>
          <textarea id="pastedOutputText" placeholder="Paste the exact AI output for the selected step here." ${bundle ? "" : "disabled"} spellcheck="false"></textarea>
          <div class="status" style="margin-top:12px" role="status" aria-live="polite">${validationStatusHtml}</div>
          <div class="row" style="margin-top:12px">
            <button type="button" class="${escapeHtml(validationStatus.buttonClass)}" id="validateProjectBtn" ${validationStatus.buttonDisabled ? "disabled" : ""}>${escapeHtml(validationStatus.buttonLabel)}</button>
          </div>
          <div class="row" style="margin-top:12px">
            <button type="button" class="${parseButton.disabled ? "secondary" : "primary"}" id="parseOutputBtn" ${parseButton.disabled ? "disabled" : ""}>${escapeHtml(parseButton.label)}</button>
          </div>
          <div class="status" style="margin-top:12px" role="status" aria-live="polite">${parseFeedbackHtml}</div>
          <div class="row" style="margin-top:12px">
            <button type="button" class="secondary" id="saveCandidateBtn" ${saveCandidateButton.disabled ? "disabled" : ""}>${escapeHtml(saveCandidateButton.label)}</button>
            <button type="button" class="success" id="approveCandidateBtn" ${approveCandidateButton.disabled ? "disabled" : ""}>${escapeHtml(approveCandidateButton.label)}</button>
            <button type="button" class="danger" id="rejectCandidateBtn" ${rejectCandidateButton.disabled ? "disabled" : ""}>${escapeHtml(rejectCandidateButton.label)}</button>
          </div>
          <div class="status" style="margin-top:12px" role="status" aria-live="polite">${candidateFeedbackHtml}</div>
          ${parsedOutputHtml}
        </div>
        `}
        <details style="margin-top:12px">
          <summary>Technical Details</summary>
          <div class="stack" style="margin-top:12px">
            <div class="check"><strong>Workflow ID</strong><div class="meta mono">${escapeHtml(binding.workflow_id || "")}</div></div>
            <div class="check"><strong>Workflow Version</strong><div class="meta">${escapeHtml(binding.workflow_version || "")}</div></div>
            <div class="check"><strong>Workflow Definition SHA-256</strong><div class="meta mono">${escapeHtml(binding.workflow_definition_sha256 || "")}</div></div>
            <div class="check"><strong>Binding Source</strong><div>${pill(binding.binding_source || "UNKNOWN")}</div></div>
            <div class="check"><strong>Prompt Set</strong><div>${pill(promptSet.status || "UNKNOWN")}</div></div>
            <div class="check"><strong>Execution Mode</strong><div class="meta">${escapeHtml(definition.execution_mode || "Unknown")}</div></div>
            <div class="check"><strong>State Revision</strong><div class="meta">${escapeHtml(String(workflowState.state_revision ?? 0))}</div></div>
            <div class="check"><strong>State Persisted</strong><div>${pill(workflowState.state_persisted ? "FOUND" : "MISSING")}</div></div>
            <div class="check"><strong>Current Step ID</strong><div class="meta mono">${escapeHtml(workflowState.current_step_id || "")}</div></div>
            <div class="check"><strong>Next Step ID</strong><div class="meta mono">${escapeHtml(workflowState.next_step_id || "")}</div></div>
            <div class="card">
              <strong>Required Input Artifacts</strong>
              <div class="stack" style="margin-top:12px">${renderArtifacts(artifactListForIds(selectedStep.input_artifact_ids), "Required")}</div>
            </div>
            <div class="card">
              <strong>Optional Input Artifacts</strong>
              <div class="stack" style="margin-top:12px">${renderArtifacts(artifactListForIds(selectedStep.optional_input_artifact_ids), "Optional")}</div>
            </div>
            <div class="card">
              <strong>Output Artifact IDs</strong>
              <div class="stack" style="margin-top:12px">
                ${(selectedStep.output_artifact_ids || []).length
                  ? selectedStep.output_artifact_ids.map((artifactId) => {
                    const artifact = workflowArtifactMap()[artifactId];
                    return `<div class="check"><div><strong>${escapeHtml(artifact ? artifact.display_name : artifactId)}</strong><div class="meta mono">${escapeHtml(artifact ? artifact.relative_path : artifactId)}</div></div><div>${pill("OUTPUT")}</div></div>`;
                  }).join("")
                  : `<div class="notice"><strong>No output artifacts</strong><span class="meta">This step does not declare output artifacts.</span></div>`
                }
              </div>
            </div>
          </div>
        </details>
      </div>
    `;
  })() : "";
  const completedWorkflowDetailsHtml = selectedStep && workflowCompleted ? `
    <details style="margin-top:12px">
      <summary>Workflow Details</summary>
      <div class="stack" style="margin-top:12px">
        <div class="check"><strong>Selected Step</strong><div>${pill(stepStatusLabel(selectedStep))}</div></div>
        <div class="meta">${escapeHtml(`Prompt ${selectedStep.order}: ${selectedStep.display_name}`)}</div>
        <div class="check"><strong>Workflow ID</strong><div class="meta mono">${escapeHtml(binding.workflow_id || "")}</div></div>
        <div class="check"><strong>Workflow Version</strong><div class="meta">${escapeHtml(binding.workflow_version || "")}</div></div>
        <div class="check"><strong>State Revision</strong><div class="meta">${escapeHtml(String(workflowState.state_revision ?? 0))}</div></div>
      </div>
    </details>
  ` : "";
  const completedWorkflowSectionHtml = workflowCompleted ? `
      <div class="notice" style="margin-top:12px">
        <strong>Workflow completed</strong>
        <span class="meta">This project is ready for production handoff.</span>
      </div>
      <div class="card" style="margin-top:12px">
        <div class="step-heading">
          <div>
            <strong>Workflow Steps</strong>
            <div class="meta">Compact workflow rail</div>
          </div>
          <div class="meta">${escapeHtml(String(workflowSteps.length))} step(s)</div>
        </div>
        <label for="workflowStepSelect">Selected Workflow Step</label>
        <select id="workflowStepSelect">
          ${workflowSteps.map((step) => `<option value="${escapeHtml(step.step_id)}"${step.step_id === state.selectedWorkflowStepId ? " selected" : ""}>${escapeHtml(String(step.order))}. ${escapeHtml(step.display_name)}</option>`).join("")}
        </select>
        <div class="step-rail" style="margin-top:12px">${compactWorkflowRows}</div>
      </div>
      <div class="row" style="margin-top:12px">
        <a id="workflowPrimaryAction" class="action-link success" href="${escapeHtml(productionPackage && productionPackage.download_url ? productionPackage.download_url : "#")}"${productionPackage && productionPackage.ready_for_export ? " download" : " aria-disabled=\"true\""} rel="noreferrer">Download Production Package</a>
      </div>
      <div class="stack" style="margin-top:12px">${productionArtifactsHtml}</div>
      ${productionPackage && productionPackage.errors && productionPackage.errors.length ? `<div class="notice" style="margin-top:12px"><strong>Export Checks</strong><span class="meta">${escapeHtml(productionPackage.errors.join(" | "))}</span></div>` : ""}
      ${completedWorkflowDetailsHtml}
      <details style="margin-top:12px">
        <summary>Technical Details</summary>
        <div class="stack" style="margin-top:12px">
          <div class="check"><strong>Lifecycle Code</strong><div class="meta mono">${escapeHtml(productionPackage && productionPackage.lifecycle ? productionPackage.lifecycle : "")}</div></div>
          <div class="check"><strong>Approved Group</strong><div class="meta mono">${escapeHtml(productionPackage && productionPackage.approved_group_id ? productionPackage.approved_group_id : "")}</div></div>
          <div class="check"><strong>Current Step ID</strong><div class="meta mono">${escapeHtml(workflowState.current_step_id || "")}</div></div>
          ${productionArtifacts.map((artifact) => `<div class="check"><strong>${escapeHtml(artifact.filename || artifact.artifact_id || "Artifact")}</strong><div class="meta mono">${escapeHtml(artifact.sha256 || "")}</div></div>`).join("")}
        </div>
      </details>
  ` : "";
  const workflowSectionHtml = workflowCompleted && !workflow && !state.workflowError
    ? `
      <div class="meta" style="margin-top:12px">${escapeHtml(productionStatusSentence(productionPackage))}</div>
      ${completedWorkflowSectionHtml}
    `
    : workflow && !state.workflowError
    ? `
      <div class="meta" style="margin-top:12px">${escapeHtml(definition.display_name || "Workflow")}</div>
      ${workflowState.blocking_reason ? `<div class="notice" style="margin-top:12px"><strong>Blocking Reason</strong><span class="meta">${escapeHtml(workflowState.blocking_reason)}</span></div>` : ""}
      ${workflowCompleted ? completedWorkflowSectionHtml : `<div class="card" style="margin-top:12px">
        <div class="step-heading">
          <div>
            <strong>Workflow Steps</strong>
            <div class="meta">Compact workflow rail</div>
          </div>
          <div class="meta">${escapeHtml(String(workflowSteps.length))} step(s)</div>
        </div>
        <label for="workflowStepSelect">Selected Workflow Step</label>
        <select id="workflowStepSelect">
          ${workflowSteps.map((step) => `<option value="${escapeHtml(step.step_id)}"${step.step_id === state.selectedWorkflowStepId ? " selected" : ""}>${escapeHtml(String(step.order))}. ${escapeHtml(step.display_name)}</option>`).join("")}
        </select>
        <div class="step-rail" style="margin-top:12px">${compactWorkflowRows}</div>
      </div>`}
      ${transcriptPanelState.show_primary_panel ? `<details style="margin-top:12px"><summary>Workflow Details</summary>${selectedStepHtml}</details>` : selectedStepHtml}
    `
    : `<div class="notice" style="margin-top:12px"><strong>${state.workflowError ? "Workflow unavailable" : "Workflow loading"}</strong><span class="meta">${escapeHtml(state.workflowError || (state.isLoadingWorkflow ? "Fetching the selected project workflow..." : "Workflow data will appear here after the selected project detail loads."))}</span></div>`;

  panel.innerHTML = `
    <section class="panel">
      <div class="step-heading">
        <div>
          <h3 style="margin:0">Content Workflow</h3>
          <div class="meta">${escapeHtml(workflowCompleted ? "Completed workflow result with the full prompt rail and handoff-ready output first." : (transcriptPanelState.show_primary_panel ? "Complete the current transcript input first, then continue the workflow." : "Selected project workflow with only the current step expanded."))}</div>
        </div>
        <div>${pill(state.isLoadingWorkflow ? "LOADING" : (workflow ? "READY" : "WAITING"))}</div>
      </div>
      ${state.productionPackageError && !workflowCompleted ? `<div class="notice" style="margin-top:12px"><strong>Production Handoff Error</strong><span class="meta">${escapeHtml(state.productionPackageError)}</span></div>` : ""}
      ${!workflowCompleted ? `<div class="meta" style="margin-top:12px">${escapeHtml(productionStatusSentence(productionPackage))}</div>` : ""}
      ${workflowSectionHtml}
    </section>
  `;
  syncProjectManagementControls();
  const bundlePreviewText = document.getElementById("bundlePreviewText");
  if (bundlePreviewText && bundle) {
    bundlePreviewText.value = typeof bundle.bundle === "string" ? bundle.bundle : "";
  }
  const pastedOutputText = document.getElementById("pastedOutputText");
  if (pastedOutputText) {
    pastedOutputText.value = typeof state.pastedOutputDraft === "string" ? state.pastedOutputDraft : "";
  }
  if (parsedOutput && Array.isArray(parsedOutput.artifacts)) {
    parsedOutput.artifacts.forEach((artifact, index) => {
      const artifactPreview = document.getElementById(`parsedArtifactPreview${index}`);
      if (artifactPreview) artifactPreview.value = typeof artifact.content === "string" ? artifact.content : "";
    });
  }

  validationPanel.innerHTML = transcriptPanelState.show_primary_panel
    ? `<details><summary>Secondary Details</summary><div class="card" style="margin-top:12px">${transcriptSecondaryControlsHtml}<div class="meta" style="margin-top:12px">Technical maintenance actions stay collapsed until the transcript-required step is complete.</div></div></details>`
    : "";
}

function renderAnalyticsWorkspace() {
  const panel = document.getElementById("analyticsPanel");
  if (!panel) return;
  if (!state.selectedChannelSlug) {
    panel.innerHTML = `
      <section class="panel">
        <div class="empty-state">
          <strong>Selection required</strong>
          <div class="meta">Select a channel to inspect analytics readiness and exports.</div>
        </div>
      </section>
    `;
    return;
  }
  const summary = state.selectedChannelSummary || {};
  const channel = summary.channel || {};
  const reporting = summary.reporting || {};
  const analytics = state.selectedChannelAnalytics;
  const analyticsFeedback = state.analyticsFeedback.slug === state.selectedChannelSlug ? state.analyticsFeedback : { kind: "", text: "" };
  const discoverModel = analyticsDiscoveryModel();
  const syncModel = analyticsSyncModel();
  const capabilityCounts = analytics && analytics.capability_counts ? analytics.capability_counts : {};
  const reportReadinessCounts = analytics && analytics.report_readiness_counts ? analytics.report_readiness_counts : {};
  const queryCounts = analytics && analytics.query_group_counts ? analytics.query_group_counts : {};
  const normalizedTables = analytics && Array.isArray(analytics.normalized_tables) ? analytics.normalized_tables : [];
  const sourceResults = analytics && analytics.source_results ? analytics.source_results : {};
  const analyticsSummary = analyticsPlainLanguageSummary(analytics);
  const downloadLabel = analytics && analytics.export_url ? "Download Analytics ZIP" : "Analytics ZIP unavailable";
  const tablesWithDataCount = normalizedTables.filter((table) => Number(table.row_count || 0) > 0).length;
  const feedbackHtml = analyticsFeedback.text
    ? `<div class="notice"><strong>${analyticsFeedback.kind === "error" ? "Collector Error" : "Collector Status"}</strong><span class="meta">${escapeHtml(analyticsFeedback.text)}</span></div>`
    : "";
  const normalizedTableHtml = normalizedTables.length
    ? normalizedTables.map((table) => `
      <tr>
        <td><strong>${escapeHtml(humanizeIdentifier(String(table.filename || "").replace(/\.csv$/i, "")) || "Table")}</strong></td>
        <td>${escapeHtml(String(table.row_count ?? 0))}</td>
        <td>${escapeHtml(normalizedTableAvailabilityLabel(table))}</td>
        <td>${escapeHtml(Number(table.row_count || 0) > 0 ? "Ready" : normalizedTableReason(table))}</td>
      </tr>
    `).join("")
    : `<tr><td colspan="4" class="meta">No normalized analytics files exist yet.</td></tr>`;
  const sourceResultHtml = Object.keys(sourceResults).length
    ? Object.keys(sourceResults).sort().map((key) => {
      const item = sourceResults[key] || {};
      return `<div class="check"><strong>${escapeHtml(key)}</strong><div>${pill(item.status || "UNKNOWN")}</div></div>`;
    }).join("")
    : `<div class="meta">No analytics collector state has been recorded yet.</div>`;

  panel.innerHTML = `
    <section class="panel">
      <div class="workspace-block-header">
        <div>
          <h3 style="margin:0">Analytics</h3>
          <div class="meta">${escapeHtml(analyticsSummary.detail)}</div>
        </div>
        <div>${pill(state.isLoadingChannelAnalytics ? "LOADING" : analyticsStatusTone(analyticsSummary.label))}</div>
      </div>
      <div class="mini-grid" style="margin-top:12px">
        <div class="card"><strong>Status</strong><div class="meta">${escapeHtml(analyticsSummary.label)}</div></div>
        <div class="card"><strong>Last completed sync</strong><div class="meta">${escapeHtml(formatTime(analytics && analytics.last_completed_sync_at))}</div></div>
        <div class="card"><strong>Tables with data</strong><div class="meta">${escapeHtml(String(tablesWithDataCount))}</div></div>
        <div class="card"><strong>Bulk reports</strong><div class="meta">${escapeHtml(generatedReportsSummary(analytics))}</div></div>
      </div>
      <div class="row" style="margin-top:12px">
        <button id="syncAnalyticsCollectorBtn" class="primary"${syncModel.disabled ? " disabled" : ""}>${escapeHtml(syncModel.label)}</button>
        <a id="downloadAnalyticsZipLink" class="action-link success" href="${escapeHtml(analytics && analytics.export_url ? analytics.export_url : "#")}"${analytics && analytics.export_url ? " download" : " aria-disabled=\"true\""} rel="noreferrer">${escapeHtml(downloadLabel)}</a>
      </div>
      <div class="meta" style="margin-top:12px">${escapeHtml(syncModel.helper)}</div>
      ${feedbackHtml}
      ${state.channelAnalyticsError ? `<div class="notice"><strong>Analytics Status Error</strong><span class="meta">${escapeHtml(state.channelAnalyticsError)}</span></div>` : ""}
    </section>
    <section class="panel">
      <h3>Normalized Tables</h3>
      <table class="compact-table">
        <thead>
          <tr>
            <th>Table</th>
            <th>Rows</th>
            <th>Status</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>${normalizedTableHtml}</tbody>
      </table>
    </section>
    <section class="panel">
      <details>
        <summary>Technical Details</summary>
        <div class="stack" style="margin-top:12px">
          <div class="row">
            <button id="discoverAnalyticsBtn" class="secondary"${discoverModel.disabled ? " disabled" : ""}>${escapeHtml(discoverModel.label)}</button>
          </div>
          <div class="meta">${escapeHtml(discoverModel.helper)}</div>
          <div class="check"><strong>Report Type Availability</strong><div class="meta">${escapeHtml(String(capabilityCounts.AVAILABLE || 0))} available / ${escapeHtml(String(capabilityCounts.ERROR || 0))} error</div></div>
          <div class="check"><strong>Generated Report Readiness</strong><div class="meta">${escapeHtml(String(reportReadinessCounts.READY || 0))} ready / ${escapeHtml(String(reportReadinessCounts.PENDING || 0))} pending / ${escapeHtml(String(reportReadinessCounts.ERROR || 0))} error</div></div>
          <div class="check"><strong>Query Groups</strong><div class="meta">${escapeHtml(String(queryCounts.SUCCESS || 0))} success / ${escapeHtml(String(queryCounts.EMPTY || 0))} empty / ${escapeHtml(String(queryCounts.UNAVAILABLE || 0))} unavailable / ${escapeHtml(String(queryCounts.UNAUTHORIZED || 0))} unauthorized / ${escapeHtml(String(queryCounts.ERROR || 0))} error</div></div>
          <div class="check"><strong>Source Status</strong><div class="meta">${escapeHtml(Object.keys(sourceResults).length ? "Loaded" : "Not recorded yet")}</div></div>
          <div class="stack">${sourceResultHtml}</div>
        </div>
      </details>
    </section>
  `;
}

function render() {
  renderWorkspaceIntro();
  syncChannelSelector();
  renderAppHeaderState();
  renderWorkspaceNavigation();
  renderChannelState();
  renderActionState();
  renderOverviewWorkspace();
  renderProjectListState();
  renderProjectCreateState();
  renderProjectDetailState();
  renderAnalyticsWorkspace();
  if (state.createProjectFocusPending) {
    state.createProjectFocusPending = false;
    setTimeout(() => {
      const input = document.getElementById("createProjectUrlInput");
      if (input && !input.disabled) input.focus();
    }, 0);
  }
  if (state.workflowStartFocusPending) {
    state.workflowStartFocusPending = false;
    setTimeout(() => {
      const stepSelect = document.getElementById("workflowStepSelect");
      const primaryAction = document.getElementById("workflowPrimaryAction");
      const target = stepSelect || primaryAction;
      if (target && !target.disabled) target.focus();
    }, 0);
  }
  if (state.transcriptFocusPendingProjectKey && state.transcriptFocusPendingProjectKey === currentProjectSelectionKey()) {
    const panelState = transcriptPanelProjectState();
    if (panelState.show_primary_panel) {
      state.transcriptFocusPendingProjectKey = null;
      setTimeout(() => {
        const transcriptInput = document.getElementById("transcript");
        if (transcriptInput && !transcriptInput.disabled) transcriptInput.focus();
      }, 0);
    }
  }
}

async function refreshSelectedSummaryForAction(slug) {
  if (!slug || slug !== state.selectedChannelSlug) return;
  await loadSelectedChannelSummary();
}

async function startOAuthAction() {
  const oauth = oauthButtonModel();
  const slug = state.selectedChannelSlug;
  if (!slug || !state.selectedChannelSummary || !selectedChannelRecord()) {
    setActionFeedback("error", slug, "Select a channel and wait for its summary before starting OAuth.");
    render();
    return;
  }
  if (oauth.disabled) {
    if (!(state.oauthAction.busy && state.oauthAction.slug === slug)) {
      setActionFeedback("error", slug, oauth.helper);
      render();
    }
    return;
  }

  const requestId = state.oauthAction.requestId + 1;
  const mode = oauth.mode;
  state.oauthAction = { busy: true, slug, requestId };
  setActionFeedback("info", slug, "Starting OAuth for the selected channel...");
  render();

  try {
    const data = await v2Api(`oauth/start?channel_slug=${encodeURIComponent(slug)}&mode=${encodeURIComponent(mode)}`);
    if (state.oauthAction.requestId !== requestId || state.oauthAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    if (typeof data.redirect_url !== "string" || !data.redirect_url) {
      throw new Error("OAuth start did not return a usable redirect URL.");
    }
    const popup = window.open(data.redirect_url, "_blank", "noopener");
    if (!popup) {
      throw new Error("OAuth start was accepted, but the browser blocked the new tab.");
    }
    setActionFeedback("success", slug, "OAuth start accepted for the selected channel. Finish the flow in the opened browser tab.");
    await refreshSelectedSummaryForAction(slug);
  } catch (error) {
    if (state.oauthAction.requestId !== requestId || state.oauthAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    setActionFeedback("error", slug, describeError(error, "Could not start OAuth for the selected channel."));
  } finally {
    if (state.oauthAction.requestId === requestId && state.oauthAction.slug === slug) {
      state.oauthAction.busy = false;
      render();
    }
  }
}

async function syncMetricsAction() {
  const metrics = metricsButtonModel();
  const slug = state.selectedChannelSlug;
  if (!slug || !state.selectedChannelSummary || !selectedChannelRecord()) {
    setActionFeedback("error", slug, "Select a channel and wait for its summary before syncing metrics.");
    render();
    return;
  }
  if (metrics.disabled) {
    if (!(state.metricsAction.busy && state.metricsAction.slug === slug)) {
      setActionFeedback("error", slug, metrics.helper);
      render();
    }
    return;
  }

  const requestId = state.metricsAction.requestId + 1;
  const priorSummary = state.selectedChannelSummary;
  const windowDays = Number(document.getElementById("window").value || 28);
  const recentCount = Number(document.getElementById("recent").value || 10);
  state.metricsAction = { busy: true, slug, requestId };
  setActionFeedback("info", slug, "Starting metrics sync for the selected channel...");
  render();

  try {
    await v2Api(`channels/${encodeURIComponent(slug)}/sync_metrics`, {
      method: "POST",
      body: JSON.stringify({ window_days: windowDays, recent_count: recentCount })
    });
    if (state.metricsAction.requestId !== requestId || state.metricsAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    await refreshSelectedSummaryForAction(slug);
    if (state.selectedChannelSlug === slug) {
      setActionFeedback("success", slug, "Metrics sync completed for the selected channel.");
    }
  } catch (error) {
    if (state.metricsAction.requestId !== requestId || state.metricsAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    state.selectedChannelSummary = priorSummary;
    setActionFeedback("error", slug, describeError(error, "Could not sync metrics for the selected channel."));
  } finally {
    if (state.metricsAction.requestId === requestId && state.metricsAction.slug === slug) {
      state.metricsAction.busy = false;
      render();
    }
  }
}

async function discoverAnalyticsAction() {
  const model = analyticsDiscoveryModel();
  const slug = state.selectedChannelSlug;
  if (!slug || !state.selectedChannelSummary || !selectedChannelRecord()) {
    setAnalyticsFeedback("error", slug, "Select a channel and wait for its summary before discovering analytics capabilities.");
    render();
    return;
  }
  if (model.disabled) {
    if (!(state.analyticsDiscoveryAction.busy && state.analyticsDiscoveryAction.slug === slug)) {
      setAnalyticsFeedback("error", slug, model.helper);
      render();
    }
    return;
  }

  const requestId = state.analyticsDiscoveryAction.requestId + 1;
  state.analyticsDiscoveryAction = { busy: true, slug, requestId };
  clearAnalyticsFeedback();
  setAnalyticsFeedback("info", slug, "Discovering analytics capabilities for the selected channel...");
  render();

  try {
    await v2Api(`channels/${encodeURIComponent(slug)}/analytics/discover`, {
      method: "POST",
      body: JSON.stringify({})
    });
    if (state.analyticsDiscoveryAction.requestId !== requestId || state.analyticsDiscoveryAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    await loadSelectedChannelAnalytics(slug);
    setAnalyticsFeedback("success", slug, "Capability discovery completed for the selected channel.");
  } catch (error) {
    if (state.analyticsDiscoveryAction.requestId !== requestId || state.analyticsDiscoveryAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    setAnalyticsFeedback("error", slug, describeError(error, "Could not discover analytics capabilities for the selected channel."));
  } finally {
    if (state.analyticsDiscoveryAction.requestId === requestId && state.analyticsDiscoveryAction.slug === slug) {
      state.analyticsDiscoveryAction.busy = false;
      render();
    }
  }
}

async function syncAnalyticsCollectorAction() {
  const model = analyticsSyncModel();
  const slug = state.selectedChannelSlug;
  if (!slug || !state.selectedChannelSummary || !selectedChannelRecord()) {
    setAnalyticsFeedback("error", slug, "Select a channel and wait for its summary before syncing analytics.");
    render();
    return;
  }
  if (model.disabled) {
    if (!(state.analyticsSyncAction.busy && state.analyticsSyncAction.slug === slug)) {
      setAnalyticsFeedback("error", slug, model.helper);
      render();
    }
    return;
  }

  const requestId = state.analyticsSyncAction.requestId + 1;
  state.analyticsSyncAction = { busy: true, slug, requestId };
  clearAnalyticsFeedback();
  setAnalyticsFeedback("info", slug, "Starting analytics collector sync for the selected channel...");
  render();

  try {
    await v2Api(`channels/${encodeURIComponent(slug)}/analytics/sync`, {
      method: "POST",
      body: JSON.stringify({ window_days: 365 })
    });
    if (state.analyticsSyncAction.requestId !== requestId || state.analyticsSyncAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    await loadSelectedChannelAnalytics(slug);
    await refreshSelectedSummaryForAction(slug);
    setAnalyticsFeedback("success", slug, "Analytics collector sync completed for the selected channel.");
  } catch (error) {
    if (state.analyticsSyncAction.requestId !== requestId || state.analyticsSyncAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    setAnalyticsFeedback("error", slug, describeError(error, "Could not sync analytics for the selected channel."));
  } finally {
    if (state.analyticsSyncAction.requestId === requestId && state.analyticsSyncAction.slug === slug) {
      state.analyticsSyncAction.busy = false;
      render();
    }
  }
}

async function loadProjectsForChannel(slug, options = {}) {
  if (!slug || slug !== state.selectedChannelSlug) return;
  const requestId = ++state.projectListRequestId;
  state.isLoadingProjects = true;
  state.projectListError = "";
  render();
  try {
    const data = await v2Api(`channels/${encodeURIComponent(slug)}/projects`);
    if (requestId !== state.projectListRequestId || slug !== state.selectedChannelSlug) return;
    const projects = Array.isArray(data.projects) ? data.projects : [];
    state.projects = projects;
    const savedProjectSlug = savedProjectSlugForChannel(slug);
    const hasProject = (projectSlug) => !!projectSlug && projects.some((item) => item.project_slug === projectSlug);
    let nextSelectedSlug = null;
    if (options.preferProjectSlug && projects.some((item) => item.project_slug === options.preferProjectSlug)) {
      nextSelectedSlug = options.preferProjectSlug;
    } else if (hasProject(state.selectedProjectSlug)) {
      nextSelectedSlug = state.selectedProjectSlug;
    } else if (hasProject(savedProjectSlug)) {
      nextSelectedSlug = savedProjectSlug;
    } else if (savedProjectSlug) {
      rememberProjectSlugForChannel(slug, null);
    } else if (projects.length === 1) {
      nextSelectedSlug = projects[0].project_slug;
    }
    const selectionChanged = nextSelectedSlug !== state.selectedProjectSlug;
    if (selectionChanged) {
      clearProjectSelectionState();
      state.selectedProjectSlug = nextSelectedSlug;
    }
    rememberProjectSlugForChannel(slug, nextSelectedSlug);
    render();
    if (state.selectedProjectSlug) {
      await loadSelectedProjectDetail(state.selectedProjectSlug, slug);
    }
  } catch (error) {
    if (requestId !== state.projectListRequestId || slug !== state.selectedChannelSlug) return;
    state.projectListError = describeError(error, "Could not load canonical projects for the selected channel.");
  } finally {
    if (requestId === state.projectListRequestId) {
      state.isLoadingProjects = false;
      render();
    }
  }
}

async function refreshProjectsAction() {
  if (!state.selectedChannelSlug || !state.selectedChannelSummary) {
    setProjectFeedback("error", state.selectedChannelSlug, null, "Select a channel and wait for its summary before refreshing projects.");
    render();
    return;
  }
  clearProjectFeedback();
  await loadProjectsForChannel(state.selectedChannelSlug);
}

async function createProjectAction() {
  const create = createProjectModel();
  const slug = state.selectedChannelSlug;
  if (!slug || !state.selectedChannelSummary || !selectedChannelRecord()) {
    setProjectFeedback("error", slug, null, "Select a channel and wait for its summary before creating a project.");
    render();
    return;
  }
  if (create.disabled) {
    if (!(state.createProjectAction.busy && state.createProjectAction.slug === slug)) {
      setProjectFeedback("error", slug, null, create.helper);
      render();
    }
    return;
  }

  const url = String(state.createProjectUrlDraft || "").trim();
  const projectName = String(state.createProjectNameDraft || "").trim();
  const workflowOption = selectedCreateWorkflowOption();
  const urlValidation = createProjectUrlValidationMessage(url);
  if (urlValidation) {
    setProjectFeedback("error", slug, null, urlValidation);
    render();
    return;
  }
  if (!workflowOption) {
    setProjectFeedback("error", slug, null, createSelectableWorkflowOptions().length ? "Select a workflow before creating a project." : "No project workflow is available for this channel.");
    render();
    return;
  }

  const requestId = state.createProjectAction.requestId + 1;
  state.createProjectAction = { busy: true, slug, requestId };
  setProjectFeedback("info", slug, null, "Creating a canonical project for the selected channel...");
  render();

  try {
    const payload = {
      competitor_url: url,
      workflow_id: workflowOption.workflow_id,
      workflow_version: workflowOption.workflow_version
    };
    if (projectName) payload.project_name = projectName;
    const data = await v2Api(`channels/${encodeURIComponent(slug)}/projects`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
    if (state.createProjectAction.requestId !== requestId || state.createProjectAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    const createdSlug = data && data.project && data.project.channel_slug === slug && typeof data.project.project_slug === "string"
      ? data.project.project_slug
      : null;
    await loadProjectsForChannel(slug, { preferProjectSlug: createdSlug });
    if (state.selectedChannelSlug === slug) {
      setProjectFeedback("success", slug, createdSlug, "Canonical project created for the selected channel.");
      state.createProjectUrlDraft = "";
      state.createProjectNameDraft = "";
      state.isCreateProjectPanelOpen = false;
      state.isChangeProjectPanelOpen = false;
      if (createdSlug && state.projects.some((item) => item.project_slug === createdSlug)) {
        state.workflowStartFocusPending = true;
        setSelectedProjectSlug(createdSlug);
      } else {
        render();
      }
    }
  } catch (error) {
    if (state.createProjectAction.requestId !== requestId || state.createProjectAction.slug !== slug || state.selectedChannelSlug !== slug) return;
    setProjectFeedback("error", slug, null, describeError(error, "Could not create a canonical project for the selected channel."));
  } finally {
    if (state.createProjectAction.requestId === requestId && state.createProjectAction.slug === slug) {
      state.createProjectAction.busy = false;
      render();
    }
  }
}

async function loadSelectedProjectDetail(projectSlugArg, channelSlugArg) {
  const channelSlug = channelSlugArg || state.selectedChannelSlug;
  const projectSlug = projectSlugArg || state.selectedProjectSlug;
  if (!channelSlug || !projectSlug || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;

  const requestId = ++state.projectDetailRequestId;
  state.isLoadingProjectDetail = true;
  state.projectDetailError = "";
  state.selectedProjectDetail = null;
  state.selectedProjectTranscript = null;
  state.selectedProjectValidation = null;
  state.transcriptDraft = "";
  clearWorkflowState();
  render();

  try {
    const detail = await v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}`);
    if (requestId !== state.projectDetailRequestId || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;
    state.selectedProjectDetail = detail;
    await loadSelectedProjectWorkflow(projectSlug, channelSlug);

    try {
      const transcript = await v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/transcript`);
      if (requestId !== state.projectDetailRequestId || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;
      state.selectedProjectTranscript = transcript;
      const preservedDraft = transcriptDraftForProject(channelSlug, projectSlug);
      state.transcriptDraft = preservedDraft || (typeof transcript.transcript === "string" ? transcript.transcript : "");
      rememberTranscriptDraftForProject(channelSlug, projectSlug, state.transcriptDraft);
    } catch (error) {
      if (requestId !== state.projectDetailRequestId || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;
      state.selectedProjectTranscript = null;
      state.transcriptDraft = transcriptDraftForProject(channelSlug, projectSlug);
      state.projectDetailError = describeError(error, "Could not load the selected project transcript.");
    }
  } catch (error) {
    if (requestId !== state.projectDetailRequestId || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;
    state.selectedProjectDetail = null;
    state.selectedProjectTranscript = null;
    state.transcriptDraft = transcriptDraftForProject(channelSlug, projectSlug);
    state.projectDetailError = describeError(error, "Could not load the selected project detail.");
  } finally {
    if (requestId === state.projectDetailRequestId) {
      state.isLoadingProjectDetail = false;
      render();
    }
  }
}

async function loadSelectedProjectWorkflow(projectSlugArg, channelSlugArg, preserveBundleStateArg, preserveVisibleWorkflowArg) {
  const channelSlug = channelSlugArg || state.selectedChannelSlug;
  const projectSlug = projectSlugArg || state.selectedProjectSlug;
  const preserveBundleState = !!preserveBundleStateArg;
  const preserveVisibleWorkflow = !!preserveVisibleWorkflowArg;
  if (!channelSlug || !projectSlug || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;

  const requestId = ++state.workflowRequestId;
  const previousWorkflow = state.selectedProjectWorkflow;
  state.isLoadingWorkflow = true;
  state.workflowError = "";
  if (!preserveVisibleWorkflow) {
    state.selectedProjectWorkflow = null;
  }
  if (!preserveBundleState) {
    state.selectedWorkflowStepId = null;
    invalidateLoadedBundle();
  }
  render();

  try {
    const data = await v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow`);
    if (requestId !== state.workflowRequestId || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;
    state.selectedProjectWorkflow = data;
    const definitionSteps = data && data.definition && Array.isArray(data.definition.steps) ? data.definition.steps : [];
    const currentStepId = data && data.state && typeof data.state.current_step_id === "string" ? data.state.current_step_id : null;
    const hasCurrentStep = currentStepId && definitionSteps.some((step) => step.step_id === currentStepId);
    if (!preserveBundleState || !state.selectedWorkflowStepId || !definitionSteps.some((step) => step.step_id === state.selectedWorkflowStepId)) {
      state.selectedWorkflowStepId = hasCurrentStep ? currentStepId : (definitionSteps[0] ? definitionSteps[0].step_id : null);
    }
    await loadSelectedProjectProductionPackage(projectSlug, channelSlug);
  } catch (error) {
    if (requestId !== state.workflowRequestId || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;
    state.selectedProjectWorkflow = preserveVisibleWorkflow ? previousWorkflow : null;
    if (!preserveBundleState) state.selectedWorkflowStepId = null;
    state.workflowError = workflowErrorSummary(error, "Could not load the selected project workflow.");
  } finally {
    if (requestId === state.workflowRequestId) {
      state.isLoadingWorkflow = false;
      render();
    }
  }
}

async function loadSelectedProjectProductionPackage(projectSlugArg, channelSlugArg) {
  const channelSlug = channelSlugArg || state.selectedChannelSlug;
  const projectSlug = projectSlugArg || state.selectedProjectSlug;
  if (!channelSlug || !projectSlug || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;

  const requestId = ++state.productionPackageRequestId;
  state.isLoadingProductionPackage = true;
  state.productionPackageError = "";
  state.selectedProjectProductionPackage = null;
  render();

  try {
    const data = await v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/production-package`);
    if (requestId !== state.productionPackageRequestId || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;
    state.selectedProjectProductionPackage = data && data.production_package ? data.production_package : null;
  } catch (error) {
    if (requestId !== state.productionPackageRequestId || channelSlug !== state.selectedChannelSlug || projectSlug !== state.selectedProjectSlug) return;
    state.selectedProjectProductionPackage = null;
    state.productionPackageError = describeError(error, "Could not load the production handoff summary.");
  } finally {
    if (requestId === state.productionPackageRequestId) {
      state.isLoadingProductionPackage = false;
      render();
    }
  }
}

async function buildBundleAction() {
  const channelSlug = state.selectedChannelSlug;
  const projectSlug = state.selectedProjectSlug;
  const step = selectedWorkflowStepRecord();
  const button = bundleButtonModel();
  if (!channelSlug || !projectSlug || !state.selectedProjectWorkflow || !step) {
    setBundleFeedback("error", channelSlug, projectSlug, state.selectedWorkflowStepId, "Load a selected project workflow before requesting a bundle.");
    render();
    return;
  }
  if (button.disabled) {
    if (!(state.bundleAction.busy && state.bundleAction.channelSlug === channelSlug && state.bundleAction.projectSlug === projectSlug && state.bundleAction.stepId === step.step_id)) {
      setBundleFeedback("error", channelSlug, projectSlug, step.step_id, button.helper);
      render();
    }
    return;
  }

  const requestId = state.bundleAction.requestId + 1;
  state.bundleAction = { busy: true, channelSlug, projectSlug, stepId: step.step_id, requestId };
  state.bundleError = "";
  state.selectedWorkflowBundle = null;
  setBundleFeedback("info", channelSlug, projectSlug, step.step_id, "Building the exact prompt bundle for the selected workflow step...");
  render();

  try {
    const data = await v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/bundle`);
    if (
      state.bundleAction.requestId !== requestId
      || state.bundleAction.channelSlug !== channelSlug
      || state.bundleAction.projectSlug !== projectSlug
      || state.bundleAction.stepId !== step.step_id
      || channelSlug !== state.selectedChannelSlug
      || projectSlug !== state.selectedProjectSlug
      || step.step_id !== state.selectedWorkflowStepId
    ) return;
    const nextBundle = {
      ...data,
      identity: {
        channel_slug: data.channel_slug,
        project_slug: data.project_slug,
        workflow_id: data.binding && data.binding.workflow_id,
        workflow_version: data.binding && data.binding.workflow_version,
        workflow_definition_sha256: data.binding && data.binding.workflow_definition_sha256,
        step_id: data.step_id,
        bundle_sha256: data.bundle_sha256
      }
    };
    const validationError = bundleValidationError(nextBundle);
    if (validationError) {
      invalidateLoadedBundle();
      state.bundleError = validationError;
      setBundleFeedback("error", channelSlug, projectSlug, step.step_id, validationError);
      render();
      return;
    }
    state.selectedWorkflowBundle = nextBundle;
    setBundleFeedback("success", channelSlug, projectSlug, step.step_id, "Complete bundle loaded and ready to copy.");
  } catch (error) {
    if (
      state.bundleAction.requestId !== requestId
      || state.bundleAction.channelSlug !== channelSlug
      || state.bundleAction.projectSlug !== projectSlug
      || state.bundleAction.stepId !== step.step_id
      || channelSlug !== state.selectedChannelSlug
      || projectSlug !== state.selectedProjectSlug
      || step.step_id !== state.selectedWorkflowStepId
    ) return;
    state.bundleError = workflowErrorSummary(error, "Could not build the selected workflow bundle.");
    setBundleFeedback("error", channelSlug, projectSlug, step.step_id, state.bundleError);
  } finally {
    if (
      state.bundleAction.requestId === requestId
      && state.bundleAction.channelSlug === channelSlug
      && state.bundleAction.projectSlug === projectSlug
      && state.bundleAction.stepId === step.step_id
    ) {
      state.bundleAction.busy = false;
      render();
    }
  }
}

async function fallbackCopyBundleText(bundleText) {
  const helper = document.createElement("textarea");
  const previousActive = document.activeElement && typeof document.activeElement.focus === "function" ? document.activeElement : null;
  helper.value = bundleText;
  helper.setAttribute("readonly", "readonly");
  helper.style.position = "fixed";
  helper.style.top = "-1000px";
  helper.style.left = "-1000px";
  document.body.appendChild(helper);
  helper.focus();
  helper.select();
  try {
    const copied = document.execCommand("copy");
    if (!copied) throw new Error("Clipboard copy is unavailable in this browser.");
  } finally {
    document.body.removeChild(helper);
    if (previousActive) previousActive.focus();
  }
}

async function copyBundleAction() {
  const bundle = state.selectedWorkflowBundle;
  const channelSlug = state.selectedChannelSlug;
  const projectSlug = state.selectedProjectSlug;
  const stepId = state.selectedWorkflowStepId;
  if (!bundleMatchesSelection(bundle)) {
    invalidateLoadedBundle();
    setBundleFeedback("error", channelSlug, projectSlug, stepId, "The loaded bundle is stale. Build it again for the current selection.");
    render();
    return;
  }
  const validationError = bundleValidationError(bundle);
  if (validationError) {
    invalidateLoadedBundle();
    setBundleFeedback("error", channelSlug, projectSlug, stepId, validationError);
    render();
    return;
  }

  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      try {
        await navigator.clipboard.writeText(bundle.bundle);
      } catch (error) {
        await fallbackCopyBundleText(bundle.bundle);
      }
    } else {
      await fallbackCopyBundleText(bundle.bundle);
    }
    if (!bundleMatchesSelection(bundle)) {
      invalidateLoadedBundle();
      setBundleFeedback("error", channelSlug, projectSlug, stepId, "The selected bundle changed before copy completed.");
    } else {
      setBundleFeedback("success", channelSlug, projectSlug, stepId, "Copied the exact complete bundle.");
    }
  } catch (error) {
    setBundleFeedback("error", channelSlug, projectSlug, stepId, describeError(error, "Could not copy the complete bundle."));
  }
  render();
}

async function parseOutputAction() {
  const channelSlug = state.selectedChannelSlug;
  const projectSlug = state.selectedProjectSlug;
  const step = selectedWorkflowStepRecord();
  const bundle = activeBundleRecord();
  const button = parseOutputButtonModel();
  if (!channelSlug || !projectSlug || !step || !bundle) {
    invalidateParsedOutputResult();
    state.parsedOutputError = "Load a valid bundle for the selected step before parsing output.";
    render();
    return;
  }
  if (button.disabled) {
    if (!(state.parseOutputAction.busy
      && state.parseOutputAction.channelSlug === channelSlug
      && state.parseOutputAction.projectSlug === projectSlug
      && state.parseOutputAction.stepId === step.step_id)) {
      invalidateParsedOutputResult();
      state.parsedOutputError = button.helper;
      render();
    }
    return;
  }

  const parseIdentity = parsedOutputIdentityForSelection(state.pastedOutputDraft);
  if (!parseIdentity) {
    invalidateParsedOutputResult();
    state.parsedOutputError = "Load a valid bundle for the selected step before parsing output.";
    render();
    return;
  }

  const requestId = state.parseOutputAction.requestId + 1;
  state.parseOutputAction = {
    busy: true,
    channelSlug,
    projectSlug,
    workflowId: parseIdentity.workflow_id,
    workflowVersion: parseIdentity.workflow_version,
    stepId: step.step_id,
    bundleSha256: parseIdentity.bundle_sha256,
    outputText: parseIdentity.output_text,
    requestId
  };
  invalidateParsedOutputResult();
  render();

  try {
    const data = await v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/parse-output`, {
      method: "POST",
      body: JSON.stringify({
        bundle_sha256: bundle.bundle_sha256,
        output_text: parseIdentity.output_text
      })
    });
    const activeBundle = activeBundleRecord();
    if (
      state.parseOutputAction.requestId !== requestId
      || state.parseOutputAction.channelSlug !== channelSlug
      || state.parseOutputAction.projectSlug !== projectSlug
      || state.parseOutputAction.workflowId !== parseIdentity.workflow_id
      || state.parseOutputAction.workflowVersion !== parseIdentity.workflow_version
      || state.parseOutputAction.stepId !== step.step_id
      || state.parseOutputAction.bundleSha256 !== parseIdentity.bundle_sha256
      || state.parseOutputAction.outputText !== parseIdentity.output_text
      || channelSlug !== state.selectedChannelSlug
      || projectSlug !== state.selectedProjectSlug
      || step.step_id !== state.selectedWorkflowStepId
      || !activeBundle
      || activeBundle.bundle_sha256 !== parseIdentity.bundle_sha256
      || state.pastedOutputDraft !== parseIdentity.output_text
    ) return;
    state.parsedOutputResult = data;
    state.parsedOutputError = "";
    await loadSelectedProjectWorkflow(projectSlug, channelSlug, true, true);
  } catch (error) {
    if (
      state.parseOutputAction.requestId !== requestId
      || state.parseOutputAction.channelSlug !== channelSlug
      || state.parseOutputAction.projectSlug !== projectSlug
      || state.parseOutputAction.workflowId !== parseIdentity.workflow_id
      || state.parseOutputAction.workflowVersion !== parseIdentity.workflow_version
      || state.parseOutputAction.stepId !== step.step_id
      || state.parseOutputAction.bundleSha256 !== parseIdentity.bundle_sha256
      || state.parseOutputAction.outputText !== parseIdentity.output_text
      || channelSlug !== state.selectedChannelSlug
      || projectSlug !== state.selectedProjectSlug
      || step.step_id !== state.selectedWorkflowStepId
      || state.pastedOutputDraft !== parseIdentity.output_text
    ) return;
    invalidateParsedOutputResult();
    state.parsedOutputError = parseOutputErrorSummary(error, "Could not parse the pasted output preview.");
  } finally {
    if (
      state.parseOutputAction.requestId === requestId
      && state.parseOutputAction.channelSlug === channelSlug
      && state.parseOutputAction.projectSlug === projectSlug
      && state.parseOutputAction.workflowId === parseIdentity.workflow_id
      && state.parseOutputAction.workflowVersion === parseIdentity.workflow_version
      && state.parseOutputAction.stepId === step.step_id
      && state.parseOutputAction.bundleSha256 === parseIdentity.bundle_sha256
      && state.parseOutputAction.outputText === parseIdentity.output_text
    ) {
      state.parseOutputAction.busy = false;
      render();
    }
  }
}

async function saveCandidateAction() {
  const channelSlug = state.selectedChannelSlug;
  const projectSlug = state.selectedProjectSlug;
  const workflow = state.selectedProjectWorkflow;
  const step = selectedWorkflowStepRecord();
  const bundle = activeBundleRecord();
  const parsedOutput = parsedOutputMatchesSelection(state.parsedOutputResult) ? state.parsedOutputResult : null;
  const button = saveCandidateButtonModel();
  if (!channelSlug || !projectSlug || !workflow || !step || !bundle || !parsedOutput) {
    setCandidateSaveFeedback("error", channelSlug, projectSlug, state.selectedWorkflowStepId, "Parse a current valid output preview before saving a candidate.");
    render();
    return;
  }
  if (button.disabled) {
    if (!(state.saveCandidateAction.busy
      && state.saveCandidateAction.channelSlug === channelSlug
      && state.saveCandidateAction.projectSlug === projectSlug
      && state.saveCandidateAction.stepId === step.step_id)) {
      setCandidateSaveFeedback("error", channelSlug, projectSlug, step.step_id, button.helper);
      render();
    }
    return;
  }

  const parseIdentity = parsedOutputIdentityForSelection(state.pastedOutputDraft);
  const expectedStateRevision = workflow.state && typeof workflow.state.state_revision === "number" ? workflow.state.state_revision : 0;
  if (!parseIdentity || !parseIdentity.raw_output_sha256) {
    setCandidateSaveFeedback("error", channelSlug, projectSlug, step.step_id, "The current parsed output preview no longer matches the selected workflow state.");
    render();
    return;
  }

  const requestId = state.saveCandidateAction.requestId + 1;
  state.saveCandidateAction = {
    busy: true,
    channelSlug,
    projectSlug,
    workflowId: parseIdentity.workflow_id,
    workflowVersion: parseIdentity.workflow_version,
    stepId: step.step_id,
    bundleSha256: parseIdentity.bundle_sha256,
    rawOutputSha256: parseIdentity.raw_output_sha256,
    expectedStateRevision,
    requestId
  };
  setCandidateSaveFeedback("info", channelSlug, projectSlug, step.step_id, "Saving immutable candidate revisions for the selected workflow step...");
  render();

  try {
    const data = await v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/revisions`, {
      method: "POST",
      body: JSON.stringify({
        bundle_sha256: bundle.bundle_sha256,
        output_text: parseIdentity.output_text,
        expected_state_revision: expectedStateRevision
      })
    });
    const currentWorkflow = state.selectedProjectWorkflow;
    const currentParsed = parsedOutputMatchesSelection(state.parsedOutputResult) ? state.parsedOutputResult : null;
    const currentBundle = activeBundleRecord();
    if (
      state.saveCandidateAction.requestId !== requestId
      || channelSlug !== state.selectedChannelSlug
      || projectSlug !== state.selectedProjectSlug
      || step.step_id !== state.selectedWorkflowStepId
      || !currentWorkflow
      || !currentBundle
      || currentBundle.bundle_sha256 !== parseIdentity.bundle_sha256
      || !currentParsed
      || !currentParsed.raw_output
      || currentParsed.raw_output.sha256 !== parseIdentity.raw_output_sha256
      || state.pastedOutputDraft !== parseIdentity.output_text
    ) {
      if (
        state.saveCandidateAction.requestId === requestId
        && state.saveCandidateAction.channelSlug === channelSlug
        && state.saveCandidateAction.projectSlug === projectSlug
        && state.saveCandidateAction.stepId === step.step_id
      ) {
        state.saveCandidateAction.busy = false;
        clearCandidateSaveFeedback();
        render();
      }
      return;
    }
    state.lastSaveCandidateResult = data;
    setCandidateSaveFeedback(
      "success",
      channelSlug,
      projectSlug,
      step.step_id,
      data.status === "CANDIDATE_ALREADY_SAVED"
        ? `Candidate already saved as ${data.revision_group && data.revision_group.revision_group_id ? data.revision_group.revision_group_id : "existing group"}.`
        : `Candidate saved as ${data.revision_group && data.revision_group.revision_group_id ? data.revision_group.revision_group_id : "new group"}.`
    );
    await loadSelectedProjectWorkflow(projectSlug, channelSlug, true);
  } catch (error) {
    if (
      state.saveCandidateAction.requestId !== requestId
      || channelSlug !== state.selectedChannelSlug
      || projectSlug !== state.selectedProjectSlug
      || step.step_id !== state.selectedWorkflowStepId
    ) {
      if (
        state.saveCandidateAction.requestId === requestId
        && state.saveCandidateAction.channelSlug === channelSlug
        && state.saveCandidateAction.projectSlug === projectSlug
        && state.saveCandidateAction.stepId === step.step_id
      ) {
        state.saveCandidateAction.busy = false;
        clearCandidateSaveFeedback();
        render();
      }
      return;
    }
    setCandidateSaveFeedback("error", channelSlug, projectSlug, step.step_id, saveCandidateErrorSummary(error, "Could not save the current candidate output."));
  } finally {
    if (
      state.saveCandidateAction.requestId === requestId
      && state.saveCandidateAction.channelSlug === channelSlug
      && state.saveCandidateAction.projectSlug === projectSlug
      && state.saveCandidateAction.stepId === step.step_id
    ) {
      state.saveCandidateAction.busy = false;
      render();
    }
  }
}

async function candidateDecisionAction(actionName) {
  const channelSlug = state.selectedChannelSlug;
  const projectSlug = state.selectedProjectSlug;
  const workflow = state.selectedProjectWorkflow;
  const step = selectedWorkflowStepRecord();
  const candidate = step && stepCandidateSummary(step.step_id);
  const button = candidateDecisionButtonModel(actionName);
  if (!channelSlug || !projectSlug || !workflow || !step || !candidate || !candidate.candidate_group_id) {
    setCandidateSaveFeedback("error", channelSlug, projectSlug, state.selectedWorkflowStepId, "Load the current candidate state for this workflow step before deciding.");
    render();
    return;
  }
  if (button.disabled) {
    if (!(state.candidateDecisionAction.busy
      && state.candidateDecisionAction.channelSlug === channelSlug
      && state.candidateDecisionAction.projectSlug === projectSlug
      && state.candidateDecisionAction.stepId === step.step_id
      && state.candidateDecisionAction.action === actionName)) {
      setCandidateSaveFeedback("error", channelSlug, projectSlug, step.step_id, button.helper);
      render();
    }
    return;
  }

  const binding = workflow.binding || {};
  const expectedStateRevision = workflow.state && typeof workflow.state.state_revision === "number" ? workflow.state.state_revision : 0;
  const requestId = state.candidateDecisionAction.requestId + 1;
  state.candidateDecisionAction = {
    busy: true,
    channelSlug,
    projectSlug,
    workflowId: binding.workflow_id || null,
    workflowVersion: binding.workflow_version || null,
    stepId: step.step_id,
    candidateGroupId: candidate.candidate_group_id,
    expectedStateRevision,
    action: actionName,
    requestId
  };
  setCandidateSaveFeedback(
    "info",
    channelSlug,
    projectSlug,
    step.step_id,
    actionName === "APPROVE"
      ? "Approving the current candidate and publishing stable workflow outputs..."
      : "Rejecting the current candidate and returning the step to READY..."
  );
  render();

  try {
    const data = await v2Api(
      `channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/candidate/${actionName === "APPROVE" ? "approve" : "reject"}`,
      {
        method: "POST",
        body: JSON.stringify({
          candidate_group_id: candidate.candidate_group_id,
          expected_state_revision: expectedStateRevision
        })
      }
    );
    const currentWorkflow = state.selectedProjectWorkflow;
    const currentStep = selectedWorkflowStepRecord();
    const currentCandidate = currentStep && stepCandidateSummary(currentStep.step_id);
    if (
      state.candidateDecisionAction.requestId !== requestId
      || channelSlug !== state.selectedChannelSlug
      || projectSlug !== state.selectedProjectSlug
      || !currentWorkflow
      || !currentStep
      || currentStep.step_id !== step.step_id
      || (currentCandidate && currentCandidate.candidate_group_id !== candidate.candidate_group_id)
    ) {
      if (
        state.candidateDecisionAction.requestId === requestId
        && state.candidateDecisionAction.channelSlug === channelSlug
        && state.candidateDecisionAction.projectSlug === projectSlug
        && state.candidateDecisionAction.stepId === step.step_id
        && state.candidateDecisionAction.action === actionName
      ) {
        state.candidateDecisionAction.busy = false;
        clearCandidateSaveFeedback();
        render();
      }
      return;
    }
    if (actionName === "APPROVE") {
      invalidateLoadedBundle();
    } else {
      invalidateParsedOutputResult();
    }
    setCandidateSaveFeedback(
      "success",
      channelSlug,
      projectSlug,
      step.step_id,
      actionName === "APPROVE"
        ? `Candidate approved as ${data.revision_group_id || candidate.candidate_group_id}.`
        : `Candidate rejected for ${data.revision_group_id || candidate.candidate_group_id}.`
    );
    await loadSelectedProjectWorkflow(projectSlug, channelSlug, true);
  } catch (error) {
    if (
      state.candidateDecisionAction.requestId !== requestId
      || channelSlug !== state.selectedChannelSlug
      || projectSlug !== state.selectedProjectSlug
      || step.step_id !== state.selectedWorkflowStepId
    ) {
      if (
        state.candidateDecisionAction.requestId === requestId
        && state.candidateDecisionAction.channelSlug === channelSlug
        && state.candidateDecisionAction.projectSlug === projectSlug
        && state.candidateDecisionAction.stepId === step.step_id
        && state.candidateDecisionAction.action === actionName
      ) {
        state.candidateDecisionAction.busy = false;
        clearCandidateSaveFeedback();
        render();
      }
      return;
    }
    setCandidateSaveFeedback(
      "error",
      channelSlug,
      projectSlug,
      step.step_id,
      candidateDecisionErrorSummary(error, `Could not ${actionName === "APPROVE" ? "approve" : "reject"} the current candidate.`)
    );
  } finally {
    if (
      state.candidateDecisionAction.requestId === requestId
      && state.candidateDecisionAction.channelSlug === channelSlug
      && state.candidateDecisionAction.projectSlug === projectSlug
      && state.candidateDecisionAction.stepId === step.step_id
      && state.candidateDecisionAction.action === actionName
    ) {
      state.candidateDecisionAction.busy = false;
      render();
    }
  }
}

async function saveTranscriptAction() {
  const save = transcriptSaveModel();
  const slug = state.selectedChannelSlug;
  const projectSlug = state.selectedProjectSlug;
  const transcriptText = state.transcriptDraft;
  if (!slug || !projectSlug || !state.selectedProjectDetail) {
    setProjectFeedback("error", slug, projectSlug, "Select a project and load its detail before saving a transcript.");
    render();
    return;
  }
  if (save.disabled) {
    if (!(state.transcriptSaveAction.busy && state.transcriptSaveAction.slug === slug && state.transcriptSaveAction.projectSlug === projectSlug)) {
      setProjectFeedback("error", slug, projectSlug, save.helper);
      render();
    }
    return;
  }

  const requestId = state.transcriptSaveAction.requestId + 1;
  const shouldOverwrite = !!(state.selectedProjectTranscript && state.selectedProjectTranscript.has_real_content);
  state.transcriptSaveAction = { busy: true, slug, projectSlug, requestId };
  rememberTranscriptDraftForProject(slug, projectSlug, transcriptText);
  setProjectFeedback("info", slug, projectSlug, "Saving transcript for the selected project...");
  render();

  try {
    const body = { transcript: transcriptText };
    if (shouldOverwrite) body.overwrite = true;
    const data = await v2Api(`channels/${encodeURIComponent(slug)}/projects/${encodeURIComponent(projectSlug)}/transcript`, {
      method: "POST",
      body: JSON.stringify(body)
    });
    if (
      state.transcriptSaveAction.requestId !== requestId
      || state.transcriptSaveAction.slug !== slug
      || state.transcriptSaveAction.projectSlug !== projectSlug
      || state.selectedChannelSlug !== slug
      || state.selectedProjectSlug !== projectSlug
    ) return;
    state.selectedProjectValidation = data;
    setProjectFeedback("success", slug, projectSlug, "Transcript saved for the selected project.");
    await loadSelectedProjectDetail(projectSlug, slug);
  } catch (error) {
    if (
      state.transcriptSaveAction.requestId !== requestId
      || state.transcriptSaveAction.slug !== slug
      || state.transcriptSaveAction.projectSlug !== projectSlug
      || state.selectedChannelSlug !== slug
      || state.selectedProjectSlug !== projectSlug
    ) return;
    setProjectFeedback("error", slug, projectSlug, describeError(error, "Could not save the selected project transcript."));
  } finally {
    if (state.transcriptSaveAction.requestId === requestId && state.transcriptSaveAction.slug === slug && state.transcriptSaveAction.projectSlug === projectSlug) {
      state.transcriptSaveAction.busy = false;
      render();
    }
  }
}

async function validateProjectAction() {
  const validate = validationModel();
  const slug = state.selectedChannelSlug;
  const projectSlug = state.selectedProjectSlug;
  if (!slug || !projectSlug || !state.selectedProjectDetail) {
    setProjectFeedback("error", slug, projectSlug, "Select a project and load its detail before validating inputs.");
    render();
    return;
  }
  if (validate.disabled) {
    if (!(state.validationAction.busy && state.validationAction.slug === slug && state.validationAction.projectSlug === projectSlug)) {
      setProjectFeedback("error", slug, projectSlug, validate.helper);
      render();
    }
    return;
  }

  const requestId = state.validationAction.requestId + 1;
  state.validationAction = { busy: true, slug, projectSlug, requestId };
  setProjectFeedback("info", slug, projectSlug, "Running canonical validation for the selected project...");
  render();

  try {
    const data = await v2Api(`channels/${encodeURIComponent(slug)}/projects/${encodeURIComponent(projectSlug)}/validate`, {
      method: "POST",
      body: JSON.stringify({})
    });
    if (
      state.validationAction.requestId !== requestId
      || state.validationAction.slug !== slug
      || state.validationAction.projectSlug !== projectSlug
      || state.selectedChannelSlug !== slug
      || state.selectedProjectSlug !== projectSlug
    ) return;
    state.selectedProjectValidation = data;
    if (state.selectedProjectDetail && state.selectedProjectDetail.project && data.project) {
      state.selectedProjectDetail = { project: { ...state.selectedProjectDetail.project, ...data.project } };
    }
    if (validationResultPasses(data) && data.project && data.project.workflow_input_status === "READY" && data.project.runnable === true) {
      setProjectFeedback("success", slug, projectSlug, "Validation passed for the selected project.");
    } else {
      const failedChecks = failedValidationCheckNames(data);
      setProjectFeedback(
        "error",
        slug,
        projectSlug,
        failedChecks.length
          ? `Validation failed. Fix these checks first: ${failedChecks.join(", ")}`
          : "Validation failed for the selected project."
      );
    }
  } catch (error) {
    if (
      state.validationAction.requestId !== requestId
      || state.validationAction.slug !== slug
      || state.validationAction.projectSlug !== projectSlug
      || state.selectedChannelSlug !== slug
      || state.selectedProjectSlug !== projectSlug
    ) return;
    setProjectFeedback("error", slug, projectSlug, describeError(error, "Could not validate the selected project inputs."));
  } finally {
    if (state.validationAction.requestId === requestId && state.validationAction.slug === slug && state.validationAction.projectSlug === projectSlug) {
      state.validationAction.busy = false;
      render();
    }
  }
}

async function loadSelectedChannelSummary() {
  const slug = state.selectedChannelSlug;
  if (!slug) {
    state.selectedChannelSummary = null;
    state.isLoadingSummary = false;
    render();
    return;
  }

  if (state.summaryAbortController) state.summaryAbortController.abort();
  const controller = new AbortController();
  state.summaryAbortController = controller;
  const requestId = ++state.summaryRequestId;
  state.isLoadingSummary = true;
  state.errorMessage = "";
  render();

  try {
    const data = await v2Api(`channels/${encodeURIComponent(slug)}`, { signal: controller.signal });
    if (requestId !== state.summaryRequestId || slug !== state.selectedChannelSlug) return;
    state.selectedChannelSummary = data;
    syncCreateProjectWorkflowSelection();
    await loadSelectedChannelAnalytics(slug);
    await loadProjectsForChannel(slug);
  } catch (error) {
    if (error && error.name === "AbortError") return;
    if (requestId !== state.summaryRequestId || slug !== state.selectedChannelSlug) return;
    state.selectedChannelSummary = null;
    if (error && error.code === "CHANNEL_NOT_FOUND") {
      localStorage.removeItem(SELECTED_CHANNEL_STORAGE_KEY);
      state.selectedChannelSlug = null;
      clearSelectedChannelAnalyticsState();
      clearProjectState();
      state.errorMessage = "The previously selected channel is no longer available. Please select another channel.";
    } else {
      state.errorMessage = describeError(error, "Could not load the selected channel summary.");
    }
  } finally {
    if (requestId === state.summaryRequestId) {
      state.isLoadingSummary = false;
      if (state.summaryAbortController === controller) state.summaryAbortController = null;
      render();
    }
  }
}

async function loadSelectedChannelAnalytics(slugArg) {
  const slug = slugArg || state.selectedChannelSlug;
  if (!slug || slug !== state.selectedChannelSlug) return;
  const requestId = ++state.channelAnalyticsRequestId;
  state.isLoadingChannelAnalytics = true;
  state.channelAnalyticsError = "";
  state.selectedChannelAnalytics = null;
  render();
  try {
    const data = await v2Api(`channels/${encodeURIComponent(slug)}/analytics`);
    if (requestId !== state.channelAnalyticsRequestId || slug !== state.selectedChannelSlug) return;
    state.selectedChannelAnalytics = data && data.analytics ? data.analytics : null;
  } catch (error) {
    if (requestId !== state.channelAnalyticsRequestId || slug !== state.selectedChannelSlug) return;
    state.selectedChannelAnalytics = null;
    state.channelAnalyticsError = describeError(error, "Could not load analytics collector status.");
  } finally {
    if (requestId === state.channelAnalyticsRequestId) {
      state.isLoadingChannelAnalytics = false;
      render();
    }
  }
}

async function loadChannels() {
  state.isLoadingChannels = true;
  state.errorMessage = "";
  render();
  try {
    const data = await v2Api("channels");
    state.channels = Array.isArray(data.channels) ? data.channels : [];
    const savedSlug = localStorage.getItem(SELECTED_CHANNEL_STORAGE_KEY);
    const validSavedSlug = savedSlug && state.channels.some((item) => item.channel_slug === savedSlug) ? savedSlug : null;
    if (savedSlug && !validSavedSlug) localStorage.removeItem(SELECTED_CHANNEL_STORAGE_KEY);
    if (!state.channels.some((item) => item.channel_slug === state.selectedChannelSlug)) {
      state.selectedChannelSlug = validSavedSlug;
      state.selectedChannelSummary = null;
      clearSelectedChannelAnalyticsState();
      clearProjectState();
    }
    render();
    if (state.selectedChannelSlug) {
      await loadSelectedChannelSummary();
    }
  } catch (error) {
    state.channels = [];
    state.selectedChannelSlug = null;
    state.selectedChannelSummary = null;
    clearSelectedChannelAnalyticsState();
    state.errorMessage = describeError(error, "Could not load the channel list.");
    render();
  } finally {
    state.isLoadingChannels = false;
    render();
  }
}

function refreshStatus() {
  loadChannels();
}

document.getElementById("channelSelect").addEventListener("change", (event) => {
  setSelectedChannelSlug(event.target.value || null);
});
document.getElementById("connectChannelBtn").addEventListener("click", startOAuthAction);
document.getElementById("syncMetricsBtn").addEventListener("click", syncMetricsAction);
document.getElementById("workspaceNav").addEventListener("click", (event) => {
  const button = event.target.closest("[data-workspace]");
  if (!button) return;
  setActiveWorkspace(button.getAttribute("data-workspace") || "overview");
});
document.getElementById("analyticsPanel").addEventListener("click", (event) => {
  const discoverButton = event.target.closest("#discoverAnalyticsBtn");
  if (discoverButton) {
    discoverAnalyticsAction();
    return;
  }
  const syncButton = event.target.closest("#syncAnalyticsCollectorBtn");
  if (syncButton) {
    syncAnalyticsCollectorAction();
  }
});
document.getElementById("projectListPanel").addEventListener("click", (event) => {
  const button = event.target.closest("[data-project-slug]");
  if (button) {
    setSelectedProjectSlug(button.getAttribute("data-project-slug") || null);
    return;
  }
  if (event.target.id === "openCreateProjectBtn") {
    openCreateProjectPanel();
    return;
  }
  if (event.target.id === "openChangeProjectBtn") {
    toggleChangeProjectPanel();
    return;
  }
  if (event.target.id === "cancelCreateProjectBtn") {
    closeCreateProjectPanel();
    return;
  }
  if (event.target.id === "refreshProjectsBtn") {
    refreshProjectsAction();
    return;
  }
  if (event.target.id === "submitCreateProjectBtn") {
    createProjectAction();
  }
});
document.getElementById("projectListPanel").addEventListener("change", (event) => {
  if (event.target.id === "createProjectWorkflowBinding") {
    state.createProjectWorkflowValue = event.target.value || "";
    clearProjectFeedback();
    render();
  }
});
document.getElementById("projectListPanel").addEventListener("input", (event) => {
  if (event.target.id === "createProjectUrlInput") {
    state.createProjectUrlDraft = event.target.value;
    clearProjectFeedback();
    render();
    return;
  }
  if (event.target.id === "createProjectNameInput") {
    state.createProjectNameDraft = event.target.value;
    render();
  }
});
document.getElementById("projectListPanel").addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.isCreateProjectPanelOpen) {
    closeCreateProjectPanel();
    return;
  }
  if (event.key === "Enter" && event.target.id === "createProjectUrlInput" && !createProjectModel().disabled) {
    event.preventDefault();
    createProjectAction();
    return;
  }
  if (event.key === "Enter" && event.target.id === "createProjectNameInput" && !createProjectModel().disabled) {
    event.preventDefault();
    createProjectAction();
    return;
  }
});
document.getElementById("projectDetailPanel").addEventListener("click", (event) => {
  if (event.target.id === "openCreateProjectBtn") {
    openCreateProjectPanel();
    return;
  }
  if (event.target.id === "openChangeProjectBtn") {
    toggleChangeProjectPanel();
    return;
  }
  const button = event.target.closest("[data-project-slug]");
  if (button) {
    setSelectedProjectSlug(button.getAttribute("data-project-slug") || null);
    return;
  }
  if (event.target.id === "refreshProjectsBtn") {
    refreshProjectsAction();
    return;
  }
  if (event.target.id === "cancelCreateProjectBtn") {
    closeCreateProjectPanel();
    return;
  }
  if (event.target.id === "submitCreateProjectBtn") {
    createProjectAction();
  }
});
document.getElementById("projectDetailPanel").addEventListener("change", (event) => {
  if (event.target.id === "createProjectWorkflowBinding") {
    state.createProjectWorkflowValue = event.target.value || "";
    clearProjectFeedback();
    render();
  }
});
document.getElementById("projectDetailPanel").addEventListener("input", (event) => {
  if (event.target.id === "createProjectUrlInput") {
    state.createProjectUrlDraft = event.target.value;
    clearProjectFeedback();
    render();
    return;
  }
  if (event.target.id === "createProjectNameInput") {
    state.createProjectNameDraft = event.target.value;
    render();
    return;
  }
  if (event.target.id === "pastedOutputText") {
    state.pastedOutputDraft = event.target.value;
    if (state.parsedOutputResult || state.parsedOutputError) {
      invalidateParsedOutputResult();
      render();
    }
  }
});
document.getElementById("projectDetailPanel").addEventListener("change", (event) => {
  if (event.target.id === "workflowStepSelect") {
    setSelectedWorkflowStepId(event.target.value || null);
  }
});
document.getElementById("projectDetailPanel").addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.isCreateProjectPanelOpen) {
    closeCreateProjectPanel();
    return;
  }
  if ((event.target.id === "createProjectUrlInput" || event.target.id === "createProjectNameInput") && event.key === "Enter" && !createProjectModel().disabled) {
    event.preventDefault();
    createProjectAction();
  }
});
document.getElementById("projectDetailPanel").addEventListener("click", (event) => {
  const stepButton = event.target.closest("[data-workflow-step-id]");
  if (stepButton) {
    setSelectedWorkflowStepId(stepButton.getAttribute("data-workflow-step-id") || null);
    return;
  }
  if (event.target.id === "buildBundleBtn") {
    buildBundleAction();
    return;
  }
  if (event.target.id === "copyBundleBtn") {
    copyBundleAction();
    return;
  }
  if (event.target.id === "parseOutputBtn") {
    parseOutputAction();
    return;
  }
  if (event.target.id === "saveCandidateBtn") {
    saveCandidateAction();
    return;
  }
  if (event.target.id === "approveCandidateBtn") {
    candidateDecisionAction("APPROVE");
    return;
  }
  if (event.target.id === "rejectCandidateBtn") {
    candidateDecisionAction("REJECT");
  }
});
document.getElementById("workflowWorkspace").addEventListener("click", (event) => {
  if (event.target.id === "saveTranscriptBtn") {
    saveTranscriptAction();
    return;
  }
  if (event.target.id === "validateProjectBtn") {
    validateProjectAction();
  }
});
document.getElementById("workflowWorkspace").addEventListener("input", (event) => {
  if (event.target.id === "transcript") {
    state.transcriptDraft = event.target.value;
    rememberTranscriptDraftForProject(state.selectedChannelSlug, state.selectedProjectSlug, state.transcriptDraft);
  }
});
document.getElementById("summaryPanel").addEventListener("click", (event) => {
  if (event.target.id === "recommendedActionBtn") {
    const action = recommendedNextAction();
    if (action.download_url) {
      window.location.href = action.download_url;
      return;
    }
    setActiveWorkspace(action.workspace || "overview");
  }
});

loadChannels();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "MistOfAgesCollector/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_v2_error(self, code: str, message: str, status: int) -> None:
        self.send_json({"error": {"code": code, "message": message}}, status)

    def send_bytes(self, body: bytes, *, content_type: str, filename: str | None = None, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path.startswith("/api/v2/"):
                status, data = dispatch_v2_request("GET", self.path, context=APP_CONTEXT)
                if "__binary__" in data:
                    self.send_bytes(data["__binary__"], content_type=data.get("content_type", "application/octet-stream"), filename=data.get("filename"), status=status)
                elif status in {301, 302, 303, 307, 308} and "redirect_url" in data:
                    if _client_prefers_json_redirect(self.headers):
                        self.send_json(data, 200)
                    else:
                        self.send_response(status)
                        self.send_header("Location", data["redirect_url"])
                        self.end_headers()
                else:
                    self.send_json(data, status)
                return
            if parsed.path == "/":
                body = HTML_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/status":
                ensure_dirs()
                self.send_json(app_status())
                return
            if parsed.path == "/oauth/start":
                self.start_oauth()
                return
            if parsed.path == "/oauth/callback":
                self.oauth_callback(parsed)
                return
            self.serve_file(parsed.path)
        except V2Error as exc:
            self.send_v2_error(exc.code, exc.message, exc.status)
        except AppError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        try:
            try:
                payload = self.read_body()
            except json.JSONDecodeError as exc:
                if self.path.startswith("/api/v2/"):
                    raise _v2_error("INVALID_REQUEST", "Request body must be valid JSON.", 400) from exc
                raise
            if self.path.startswith("/api/v2/"):
                status, data = dispatch_v2_request("POST", self.path, payload=payload, context=APP_CONTEXT)
                self.send_json(data, status)
                return
            if self.path == "/api/create_project":
                self.send_json(create_project(payload))
                return
            if self.path == "/api/validate":
                self.send_json(validate_project(payload.get("project_slug", "")))
                return
            if self.path == "/api/save_transcript":
                self.send_json(save_transcript(payload))
                return
            if self.path == "/api/open_path":
                target = Path(payload.get("path", "")).resolve()
                if not target.exists():
                    raise AppError("Path does not exist.")
                os.startfile(str(target))
                self.send_json({"ok": True})
                return
            self.send_json({"error": "Not found"}, 404)
        except V2Error as exc:
            self.send_v2_error(exc.code, exc.message, exc.status)
        except AppError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def start_oauth(self) -> None:
        state = uuid.uuid4().hex
        port = find_free_port()
        callback_server = ThreadingHTTPServer(("127.0.0.1", port), OAuthCallbackHandler)
        callback_server.expected_state = state
        callback_server.redirect_uri = f"http://127.0.0.1:{port}/oauth/callback"
        thread = threading.Thread(target=callback_server.serve_forever, daemon=True)
        thread.start()
        url = build_oauth_url(port, state)
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def oauth_callback(self, parsed: urllib.parse.ParseResult) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [""])[0]
        if not code:
            raise AppError("OAuth callback did not include a code.")
        exchange_oauth_code(code, f"http://{self.headers.get('Host')}/oauth/callback")
        channel = connected_channel()
        body = f"<html><body><h1>Connected</h1><p>{html.escape(channel.get('title', ''))}</p><p>You can close this tab.</p></body></html>".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, path: str) -> None:
        target = (ROOT / path.lstrip("/")).resolve()
        if not str(target).startswith(str(ROOT)) or not target.exists() or not target.is_file():
            self.send_json({"error": "Not found"}, 404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if params.get("state", [""])[0] != self.server.expected_state:
                raise AppError("OAuth state mismatch.")
            code = params.get("code", [""])[0]
            if not code:
                raise AppError("OAuth callback did not include a code.")
            exchange_oauth_code(code, self.server.redirect_uri)
            channel = connected_channel()
            body = f"<html><body><h1>Connected</h1><p>{html.escape(channel.get('title', ''))}</p><p>You can close this tab and return to Codex.</p></body></html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = f"<html><body><h1>Connection failed</h1><p>{html.escape(str(exc))}</p></body></html>".encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        finally:
            threading.Thread(target=self.server.shutdown, daemon=True).start()


def main() -> None:
    ensure_dirs()
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Mist of Ages Research UI: http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
