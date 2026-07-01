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

from scripts import channel_metrics, channel_oauth, channel_oauth_browser, channel_projects, channel_workspace


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


def request_json(url: str, headers: dict | None = None, data: bytes | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = res.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(detail)
            message = payload.get("error", {}).get("message", detail)
        except json.JSONDecodeError:
            message = detail or str(exc)
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


def placeholder(path: Path, title: str) -> None:
    if not path.exists():
        path.write_text(f"# {title}\n\nTODO: Fill manually during Workflow V2.\n", encoding="utf-8")


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

    for filename, title_text in {
        "transcript_analysis.md": "Transcript Analysis",
        "research_pack.md": "Research Pack",
        "evidence_ledger.md": "Evidence Ledger",
        "locked_creative_package.md": "Locked Creative Package",
        "retention_outline.md": "Retention Outline",
        "narration_v1.md": "Narration V1",
        "red_team_report.md": "Red Team Report",
    }.items():
        placeholder(workflow_dir / filename, title_text)

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
                competitor_url = payload.get("url", "")
                project_name = payload.get("project_name")
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
                    )
                except channel_projects.ChannelProjectError as exc:
                    raise _map_project_error(exc) from exc
                return 200, {"project": channel_projects.list_channel_projects(root, channel_slug)[0]}
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
    :root { color-scheme: light; --ink:#1f2933; --muted:#667085; --line:#d6dde6; --bg:#f6f8fb; --panel:#ffffff; --accent:#0f766e; --warn:#b45309; --bad:#b42318; }
    * { box-sizing:border-box; }
    body { margin:0; font-family: Arial, Helvetica, sans-serif; background:var(--bg); color:var(--ink); }
    header { padding:18px 28px; background:#102a43; color:#fff; display:flex; justify-content:space-between; gap:16px; align-items:center; }
    header h1 { margin:0; font-size:22px; letter-spacing:0; }
    header span { color:#bcccdc; font-size:14px; }
    main { max-width:1180px; margin:0 auto; padding:22px; display:grid; grid-template-columns: 360px 1fr; gap:18px; }
    section, aside { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }
    h2 { margin:0 0 12px; font-size:17px; }
    h3 { margin:0 0 8px; font-size:15px; }
    label { display:block; margin:12px 0 6px; font-weight:700; font-size:13px; }
    input, select, textarea { width:100%; border:1px solid #c7d1dd; border-radius:6px; padding:10px; font:inherit; background:#fff; }
    textarea { min-height:190px; resize:vertical; }
    button { border:0; border-radius:6px; padding:10px 12px; background:var(--accent); color:#fff; font-weight:700; cursor:pointer; }
    button.secondary { background:#334e68; }
    button.ghost { background:#eef2f6; color:#243b53; border:1px solid #c7d1dd; }
    button:disabled { opacity:.5; cursor:not-allowed; }
    .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .status { display:grid; gap:8px; }
    .pill { display:inline-flex; align-items:center; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:700; background:#eef2f6; color:#334e68; }
    .pass { color:#027a48; background:#ecfdf3; }
    .missing { color:var(--bad); background:#fef3f2; }
    .pending { color:var(--warn); background:#fffaeb; }
    .result { display:grid; gap:14px; }
    .meta { color:var(--muted); font-size:14px; line-height:1.5; overflow-wrap:anywhere; }
    .checks { display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap:8px; }
    .check { border:1px solid var(--line); border-radius:6px; padding:10px; display:flex; justify-content:space-between; gap:8px; }
    .path { font-family: Consolas, monospace; font-size:13px; background:#f8fafc; border:1px solid var(--line); border-radius:6px; padding:10px; overflow-wrap:anywhere; }
    .card { border:1px solid var(--line); border-radius:6px; padding:12px; background:#fbfcfe; }
    .stack { display:grid; gap:12px; }
    .summary-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:10px; }
    .notice { border:1px solid #c7d1dd; background:#f8fafc; border-radius:6px; padding:12px; }
    .notice strong { display:block; margin-bottom:6px; }
    .mono { font-family: Consolas, monospace; font-size:13px; }
    .hidden { display:none; }
    @media (max-width: 860px) { main { grid-template-columns:1fr; padding:14px; } header { align-items:flex-start; flex-direction:column; } }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Mist of Ages Research</h1>
      <span>Selected-channel reader for the multi-channel collector</span>
    </div>
    <button class="ghost" id="refreshBtn" onclick="refreshStatus()">Refresh Channels</button>
  </header>
  <main>
    <aside>
      <h2>Channel Context</h2>
      <label for="channelSelect">Selected Channel</label>
      <select id="channelSelect">
        <option value="">Loading channels...</option>
      </select>
      <div class="status" id="channelState" style="margin-top:12px"></div>
      <div class="row" style="margin-top:12px">
        <button id="connectChannelBtn" disabled>Connect Channel</button>
        <button id="syncMetricsBtn" class="secondary" disabled>Sync Metrics</button>
        <button class="ghost" id="openLearningsBtn" disabled data-cutover-state="disabled">Open Learnings</button>
      </div>
      <p class="meta">OAuth and metrics actions now use selected-channel `/api/v2/` routes. Learnings and project/collector actions stay disabled until later phases.</p>
    </aside>

    <section>
      <h2>Selected Channel Summary</h2>
      <p class="meta" id="message">Loading channels...</p>
      <div id="summaryPanel" class="result"></div>

      <div class="stack" style="margin-top:18px">
        <div class="card">
          <h3>Selected Channel Actions</h3>
          <div id="actionState" class="status"></div>
          <div class="row" style="margin-top:12px">
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
        <div class="notice">
          <strong>Project workflow cutover is not active yet.</strong>
          <span class="meta">Project creation, transcript save, validation, collector submission, and open-path actions are still held back until later phases.</span>
        </div>
        <div class="card">
          <h3>Create Research Project</h3>
          <label for="url">Competitor YouTube URL</label>
          <input id="url" placeholder="Available after channel workflow cutover" disabled>
          <label for="name">Project Name (optional)</label>
          <input id="name" placeholder="Available after channel workflow cutover" disabled>
          <div class="row" style="margin-top:14px">
            <button id="createBtn" disabled data-cutover-state="disabled">Create Research Project</button>
          </div>
        </div>
        <div class="card">
          <h3>Project Actions</h3>
          <div class="row">
            <button class="secondary" disabled data-cutover-state="disabled">Open Project Folder</button>
            <button class="ghost" disabled data-cutover-state="disabled">Open Transcript File</button>
            <button class="ghost" disabled data-cutover-state="disabled">Validate Inputs</button>
          </div>
          <label for="transcript">Manual Transcript</label>
          <textarea id="transcript" placeholder="Available after channel workflow cutover." disabled></textarea>
          <div class="row" style="margin-top:10px">
            <button disabled data-cutover-state="disabled">Save Transcript</button>
          </div>
        </div>
      </div>
    </section>
  </main>

<script>
const SELECTED_CHANNEL_STORAGE_KEY = "yt_input_collector.selectedChannelSlug";
const CUTOVER_PENDING_MESSAGE = "Available after channel workflow cutover.";
const state = {
  channels: [],
  selectedChannelSlug: null,
  selectedChannelSummary: null,
  isLoadingChannels: false,
  isLoadingSummary: false,
  errorMessage: "",
  summaryRequestId: 0,
  summaryAbortController: null,
  oauthAction: { busy: false, slug: null, requestId: 0 },
  metricsAction: { busy: false, slug: null, requestId: 0 },
  actionFeedback: { kind: "", slug: null, text: "" }
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
  const ok = ["CONNECTED", "FOUND", "PASS", "READY_FOR_WORKFLOW"].includes(upper);
  const missing = ["MISSING", "DISCONNECTED", "FAILED", "ERROR"].includes(upper);
  const cls = ok ? "pass" : missing ? "missing" : "pending";
  return `<span class="pill ${cls}">${escapeHtml(normalized)}</span>`;
}

function describeError(error, fallback) {
  if (!error) return fallback;
  if (error.name === "AbortError") return "Request was replaced by a newer channel selection.";
  return error.message || fallback;
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

function clearActionFeedback() {
  state.actionFeedback = { kind: "", slug: null, text: "" };
}

function setActionFeedback(kind, slug, text) {
  state.actionFeedback = { kind, slug, text };
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

function setSelectedChannelSlug(nextSlug) {
  if (!nextSlug) {
    localStorage.removeItem(SELECTED_CHANNEL_STORAGE_KEY);
    state.selectedChannelSlug = null;
  } else {
    localStorage.setItem(SELECTED_CHANNEL_STORAGE_KEY, nextSlug);
    state.selectedChannelSlug = nextSlug;
  }
  state.selectedChannelSummary = null;
  state.errorMessage = "";
  clearActionFeedback();
  if (state.summaryAbortController) state.summaryAbortController.abort();
  render();
  if (state.selectedChannelSlug) {
    loadSelectedChannelSummary();
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
    <div class="check"><strong>Selected</strong>${pill(summary ? summary.status : "LOADING")}</div>
    <div class="meta">${escapeHtml(summary ? summary.display_name : state.selectedChannelSlug)}</div>
    <div class="meta mono">${escapeHtml(summary ? summary.channel_slug : state.selectedChannelSlug)}</div>
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
    : `<div class="meta">Use the selected canonical channel for OAuth and metrics actions. Project and collector actions remain disabled.</div>`;

  target.innerHTML = `
    <div class="check"><strong>OAuth</strong>${pill(oauth.disabled ? "WAITING" : "READY")}</div>
    <div class="meta">${escapeHtml(oauth.helper)}</div>
    <div class="check"><strong>Metrics</strong>${pill(metrics.disabled ? "WAITING" : "READY")}</div>
    <div class="meta">${escapeHtml(metrics.helper)}</div>
    ${feedbackHtml}
  `;
}

function renderSelectedChannelSummary() {
  const panel = document.getElementById("summaryPanel");
  const message = document.getElementById("message");
  if (state.errorMessage) {
    message.textContent = state.errorMessage;
  } else if (state.isLoadingSummary) {
    message.textContent = "Loading selected channel summary...";
  } else if (!state.selectedChannelSlug) {
    message.textContent = "Select a channel to load its summary.";
  } else {
    message.textContent = "Selected channel summary is loaded from the canonical /api/v2 routes.";
  }

  if (!state.selectedChannelSlug) {
    panel.innerHTML = `
      <div class="notice">
        <strong>Selection required</strong>
        <span class="meta">No channel is selected. Choose a channel from the list before using the read-only summary view.</span>
      </div>
    `;
    return;
  }
  if (state.isLoadingSummary && !state.selectedChannelSummary) {
    panel.innerHTML = `<div class="notice"><strong>Loading</strong><span class="meta">Fetching the selected channel summary...</span></div>`;
    return;
  }
  if (!state.selectedChannelSummary) {
    panel.innerHTML = `
      <div class="notice">
        <strong>Summary unavailable</strong>
        <span class="meta">${escapeHtml(state.errorMessage || "The selected channel summary is not available yet.")}</span>
      </div>
    `;
    return;
  }

  const summary = state.selectedChannelSummary;
  const channel = summary.channel || {};
  const reporting = summary.reporting || {};
  const availableMetrics = Array.isArray(reporting.available_metrics) && reporting.available_metrics.length ? reporting.available_metrics.join(", ") : "None reported";
  const pendingMetrics = Array.isArray(reporting.pending_metrics) && reporting.pending_metrics.length ? reporting.pending_metrics.join(", ") : "None";
  const disconnected = channel.status && channel.status !== "CONNECTED";

  panel.innerHTML = `
    <div class="summary-grid">
      <div class="card"><strong>Display Name</strong><div class="meta">${escapeHtml(channel.display_name || "")}</div></div>
      <div class="card"><strong>Handle</strong><div class="meta">${escapeHtml(channel.youtube_handle || "Not set")}</div></div>
      <div class="card"><strong>Channel ID</strong><div class="meta mono">${escapeHtml(channel.youtube_channel_id || "")}</div></div>
      <div class="card"><strong>Status</strong><div>${pill(channel.status || "UNKNOWN")}</div></div>
      <div class="card"><strong>Last Metrics Sync</strong><div class="meta">${escapeHtml(formatTime(channel.last_metrics_sync_at))}</div></div>
      <div class="card"><strong>Projects</strong><div class="meta">${escapeHtml(String(summary.project_count ?? channel.project_count ?? 0))}</div></div>
      <div class="card"><strong>Reporting</strong><div>${pill(reporting.status || "UNAVAILABLE")}</div></div>
      <div class="card"><strong>Metrics File</strong><div>${pill(summary.metrics && summary.metrics.exists ? "FOUND" : "MISSING")}</div></div>
      <div class="card"><strong>Learnings File</strong><div>${pill(summary.learnings && summary.learnings.exists ? "FOUND" : "MISSING")}</div></div>
    </div>
    <div class="card">
      <strong>Reporting Detail</strong>
      <div class="meta">Available metrics: ${escapeHtml(availableMetrics)}</div>
      <div class="meta">Pending metrics: ${escapeHtml(pendingMetrics)}</div>
      <div class="meta">Last checked: ${escapeHtml(formatTime(reporting.last_checked_at))}</div>
    </div>
    ${disconnected ? `
      <div class="notice">
        <strong>Channel disconnected</strong>
        <span class="meta">This selected channel is not currently connected. Read-only details are visible, but workflow actions remain blocked until later cutover phases.</span>
      </div>
    ` : ""}
  `;
}

function render() {
  syncChannelSelector();
  renderChannelState();
  renderActionState();
  renderSelectedChannelSummary();
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
  } catch (error) {
    if (error && error.name === "AbortError") return;
    if (requestId !== state.summaryRequestId || slug !== state.selectedChannelSlug) return;
    state.selectedChannelSummary = null;
    if (error && error.code === "CHANNEL_NOT_FOUND") {
      localStorage.removeItem(SELECTED_CHANNEL_STORAGE_KEY);
      state.selectedChannelSlug = null;
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
    }
    render();
    if (state.selectedChannelSlug) {
      await loadSelectedChannelSummary();
    }
  } catch (error) {
    state.channels = [];
    state.selectedChannelSlug = null;
    state.selectedChannelSummary = null;
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
                if status in {301, 302, 303, 307, 308} and "redirect_url" in data:
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
            payload = self.read_body()
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
