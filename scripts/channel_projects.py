from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts import channel_workflow, channel_workspace


PLACEHOLDER_TEXT = "Paste the manually collected transcript below."
TRANSCRIPT_HINT = "Preserve timestamps at meaningful section boundaries where possible."
THUMBNAIL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SECRET_MARKERS = ("access_token", "refresh_token", "client_secret", "authorization", "oauth")
SLUG_TEXT_RE = re.compile(r"[^a-z0-9]+")


class ChannelProjectError(Exception):
    pass


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    channel_slug: str
    channel_dir: Path
    projects_dir: Path
    project_dir: Path
    project_json: Path
    input_dir: Path
    assets_dir: Path
    raw_dir: Path
    research_dir: Path
    workflow_dir: Path
    competitor_reference: Path
    channel_learnings: Path
    channel_metrics: Path
    competitor_raw_json: Path
    transcript_file: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    _write_bytes_atomic(path, payload.encode("utf-8"))


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


def _write_text_atomic(path: Path, text: str) -> None:
    _write_bytes_atomic(path, text.encode("utf-8"))


def _safe_slug_text(text: str, fallback: str) -> str:
    value = SLUG_TEXT_RE.sub("-", text.lower()).strip("-")
    value = re.sub(r"-{2,}", "-", value)
    return (value[:70].strip("-") or fallback)


def _parse_timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChannelProjectError("created_at must be timezone-aware.")
    return parsed.replace(microsecond=0)


def _validate_source_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ChannelProjectError("source_video_url is required.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ChannelProjectError("source_video_url must be an absolute http(s) URL.")
    return url.strip()


def _validate_source_metadata(source_metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source_metadata, dict):
        raise ChannelProjectError("source_metadata must be a dict.")
    title = source_metadata.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ChannelProjectError("source_metadata.title is required.")
    dumped = json.dumps(source_metadata, ensure_ascii=False).lower()
    if any(marker in dumped for marker in SECRET_MARKERS):
        raise ChannelProjectError("source_metadata must not contain credentials or OAuth data.")
    return source_metadata


def _validate_thumbnail(thumbnail_bytes: bytes | None, thumbnail_extension: str | None) -> str | None:
    if thumbnail_bytes is None:
        return None
    if not isinstance(thumbnail_bytes, (bytes, bytearray)) or not thumbnail_bytes:
        raise ChannelProjectError("thumbnail_bytes must be non-empty bytes when supplied.")
    if not isinstance(thumbnail_extension, str) or not thumbnail_extension.strip():
        raise ChannelProjectError("thumbnail_extension is required when thumbnail_bytes are supplied.")
    ext = thumbnail_extension.strip().lower()
    if not ext.startswith("."):
        ext = "." + ext
    if ext not in THUMBNAIL_EXTENSIONS:
        raise ChannelProjectError("thumbnail_extension is not supported.")
    return ext


def _relative_input_path(value: str) -> bool:
    pure = Path(value)
    return (
        isinstance(value, str)
        and value
        and not pure.is_absolute()
        and ".." not in pure.parts
        and str(pure).replace("\\", "/").startswith("input/")
    )


def _read_required_snapshot(path: Path, *, name: str, csv: bool = False) -> bytes:
    if not path.exists():
        raise ChannelProjectError(f"Required {name} file is missing.")
    data = path.read_bytes()
    if not data.strip():
        raise ChannelProjectError(f"Required {name} file is empty.")
    if csv:
        text = data.decode("utf-8")
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) < 2 or "," not in lines[0]:
            raise ChannelProjectError(f"Required {name} file is malformed.")
    return data


def _workflow_generated_output_relative_paths(
    root: Path | str,
    workflow_binding: dict[str, Any] | None,
) -> set[str]:
    if workflow_binding is None:
        return set()
    definition = channel_workflow.load_workflow_definition(
        root,
        workflow_binding["workflow_id"],
        workflow_binding["workflow_version"],
    )
    output_ids = {
        artifact_id
        for step in definition["steps"]
        for artifact_id in step["output_artifact_ids"]
    }
    return {
        artifact["relative_path"]
        for artifact in definition["artifacts"]
        if artifact["artifact_id"] in output_ids
    }


def _transcript_template(title: str, url: str, channel: str, duration: str) -> str:
    return (
        "# Competitor Transcript\n\n"
        "## Video Information\n"
        f"- Title: {title}\n"
        f"- URL: {url}\n"
        f"- Channel: {channel}\n"
        "- Language:\n"
        f"- Duration: {duration}\n"
        "- Transcript source: Manual\n"
        "- Added at:\n\n"
        "## Transcript\n"
        f"{PLACEHOLDER_TEXT}\n"
        f"{TRANSCRIPT_HINT}\n"
    )


def transcript_has_real_content(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8").strip()
    if "## Transcript" not in text:
        return len(text) >= 80
    body = text.split("## Transcript", 1)[1].strip()
    body = body.replace(PLACEHOLDER_TEXT, "").replace(TRANSCRIPT_HINT, "").strip()
    return len(body) >= 80


def is_transcript_template(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return PLACEHOLDER_TEXT in text and not transcript_has_real_content(path)


def _competitor_reference_text(
    source_video_id: str,
    source_video_url: str,
    source_metadata: dict[str, Any],
    thumbnail_rel_path: str | None,
) -> str:
    tags = source_metadata.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    lines = [
        "# Competitor Reference",
        "",
        "## Video Metadata",
        f"- Video ID: {source_video_id}",
        f"- Title: {source_metadata.get('title', '')}",
        f"- Channel: {source_metadata.get('channelTitle', '')}",
        f"- Channel ID: {source_metadata.get('channelId', '')}",
        f"- URL: {source_video_url}",
        f"- Published: {source_metadata.get('publishedAt', '')}",
        f"- Duration: {source_metadata.get('duration', '')}",
        f"- Views at collection: {source_metadata.get('viewCount', 'UNAVAILABLE')}",
        f"- Likes at collection: {source_metadata.get('likeCount', 'UNAVAILABLE')}",
        f"- Comments at collection: {source_metadata.get('commentCount', 'UNAVAILABLE')}",
        "",
        "## Description",
        source_metadata.get("description", ""),
        "",
        "## Tags",
    ]
    lines.extend([f"- {tag}" for tag in tags] or ["- UNAVAILABLE"])
    lines.extend(
        [
            "",
            "## Thumbnail",
            f"- Source URL: {source_metadata.get('thumbnailUrl', 'UNAVAILABLE')}",
            f"- Local path: {thumbnail_rel_path or 'UNAVAILABLE'}",
            "",
            "## Collection Information",
            f"- Collected at: {utc_now_iso()}",
            "- Data source: User-supplied public metadata",
            "",
        ]
    )
    return "\n".join(lines)


def _project_slug_root(project_name: str | None, source_metadata: dict[str, Any], source_video_id: str) -> str:
    basis = (project_name or source_metadata.get("title") or source_video_id).strip()
    return _safe_slug_text(basis, source_video_id.lower())


def _validate_project_slug(slug: str) -> str:
    if not isinstance(slug, str) or not slug.strip():
        raise ChannelProjectError("project_slug is required.")
    if Path(slug).is_absolute() or any(part in {"..", "."} for part in Path(slug).parts):
        raise ChannelProjectError("project_slug must be a safe relative slug.")
    if "/" in slug or "\\" in slug:
        raise ChannelProjectError("project_slug must not contain path separators.")
    return slug.strip()


def _project_paths(root: Path | str, channel_slug: str, project_slug: str) -> ProjectPaths:
    channel = channel_workspace.load_channel(root, channel_slug)
    workspace = channel_workspace.canonical_channel_paths(root, channel_slug)
    slug = _validate_project_slug(project_slug)
    project_dir = workspace.projects_dir / slug
    return ProjectPaths(
        root=Path(root).resolve(),
        channel_slug=channel["channel_slug"],
        channel_dir=workspace.channel_dir,
        projects_dir=workspace.projects_dir,
        project_dir=project_dir,
        project_json=project_dir / "project.json",
        input_dir=project_dir / "input",
        assets_dir=project_dir / "input" / "assets",
        raw_dir=project_dir / "input" / "_raw",
        research_dir=project_dir / "research",
        workflow_dir=project_dir / "workflow",
        competitor_reference=project_dir / "input" / "competitor_reference.md",
        channel_learnings=project_dir / "input" / "channel_learnings.md",
        channel_metrics=project_dir / "input" / "channel_metrics.csv",
        competitor_raw_json=project_dir / "input" / "_raw" / "competitor_video.json",
        transcript_file=project_dir / "research" / "competitor_transcript.md",
    )


def _project_summary(project: dict[str, Any]) -> dict[str, Any]:
    return {
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


def load_channel_project(root: Path | str, channel_slug: str, project_slug: str) -> dict[str, Any]:
    paths = _project_paths(root, channel_slug, project_slug)
    if not paths.project_json.exists():
        raise ChannelProjectError("project.json does not exist.")
    data = json.loads(paths.project_json.read_text(encoding="utf-8"))
    _validate_project_metadata(root, channel_slug, project_slug, data)
    return data


def _validate_project_metadata(root: Path | str, channel_slug: str, project_slug: str, data: dict[str, Any]) -> None:
    channel = channel_workspace.load_channel(root, channel_slug)
    required = {
        "schema_version",
        "project_type",
        "project_slug",
        "channel_slug",
        "youtube_channel_id",
        "source_video_id",
        "source_video_url",
        "status",
        "workflow_input_status",
        "runnable",
        "created_at",
        "updated_at",
        "channel_snapshot",
    }
    if not isinstance(data, dict) or required - set(data):
        raise ChannelProjectError("project.json is malformed.")
    if data["schema_version"] != 2 or data["project_type"] != "youtube_research":
        raise ChannelProjectError("project.json schema is invalid.")
    if data["channel_slug"] != channel_slug or data["project_slug"] != project_slug:
        raise ChannelProjectError("Project ownership does not match the requested channel/project.")
    if data["youtube_channel_id"] != channel["youtube_channel_id"]:
        raise ChannelProjectError("Project youtube_channel_id does not match the selected channel.")
    _validate_project_slug(project_slug)
    _validate_source_url(data["source_video_url"])
    for field in ("created_at", "updated_at"):
        parsed = datetime.fromisoformat(data[field])
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ChannelProjectError(f"{field} must be timezone-aware.")
    snapshot = data["channel_snapshot"]
    if not isinstance(snapshot, dict):
        raise ChannelProjectError("channel_snapshot is malformed.")
    if not _relative_input_path(snapshot.get("learnings_path", "")) or not _relative_input_path(snapshot.get("metrics_path", "")):
        raise ChannelProjectError("channel_snapshot paths must be safe relative input paths.")
    captured_at = snapshot.get("captured_at")
    parsed = datetime.fromisoformat(captured_at)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChannelProjectError("channel_snapshot.captured_at must be timezone-aware.")
    if "workflow_binding" in data and data["workflow_binding"] is not None:
        try:
            channel_workflow.validate_project_workflow_binding(data["workflow_binding"])
        except channel_workflow.ChannelWorkflowError as exc:
            raise ChannelProjectError(exc.message) from exc


def create_channel_project(
    root: Path | str,
    channel_slug: str,
    source_video_id: str,
    source_video_url: str,
    source_metadata: dict[str, Any],
    project_name: str | None = None,
    thumbnail_bytes: bytes | None = None,
    thumbnail_extension: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if not isinstance(source_video_id, str) or not source_video_id.strip():
        raise ChannelProjectError("source_video_id is required.")
    source_video_id = source_video_id.strip()
    source_video_url = _validate_source_url(source_video_url)
    source_metadata = _validate_source_metadata(source_metadata)
    thumb_ext = _validate_thumbnail(thumbnail_bytes, thumbnail_extension)
    channel = channel_workspace.load_channel(root, channel_slug)
    if not channel.get("youtube_channel_id"):
        raise ChannelProjectError("Selected channel workspace has no valid youtube_channel_id.")
    workspace = channel_workspace.canonical_channel_paths(root, channel_slug)
    try:
        workflow_binding = channel_workflow.get_channel_default_workflow(root, channel_slug)
    except channel_workflow.ChannelWorkflowError as exc:
        raise ChannelProjectError(exc.message) from exc
    workflow_generated_outputs = _workflow_generated_output_relative_paths(root, workflow_binding)
    learnings_bytes = _read_required_snapshot(
        workspace.channel_learnings_master, name="channel learnings"
    )
    metrics_bytes = _read_required_snapshot(
        workspace.channel_metrics_csv, name="channel metrics", csv=True
    )

    for project in list_channel_projects(root, channel_slug):
        if project["source_video_id"] == source_video_id:
            raise ChannelProjectError("Duplicate source_video_id is not allowed within the same channel.")

    created_dt = _parse_timestamp(created_at)
    date_prefix = created_dt.strftime("%Y%m%d")
    slug_root = _project_slug_root(project_name, source_metadata, source_video_id)
    project_slug = f"{date_prefix}_{slug_root}"
    final_dir = workspace.projects_dir / project_slug
    if final_dir.exists():
        project_slug = f"{project_slug}-{source_video_id[:6].lower()}"
        final_dir = workspace.projects_dir / project_slug
    suffix = 2
    while final_dir.exists():
        final_dir = workspace.projects_dir / f"{project_slug}-{suffix}"
        suffix += 1

    temp_dir = workspace.projects_dir / f".tmp-{final_dir.name}-{uuid.uuid4().hex[:8]}"
    if temp_dir.exists():
        raise ChannelProjectError("Temporary project directory collision.")

    try:
        (temp_dir / "input" / "assets").mkdir(parents=True, exist_ok=False)
        (temp_dir / "input" / "_raw").mkdir(parents=True, exist_ok=False)
        (temp_dir / "research").mkdir(parents=True, exist_ok=False)
        (temp_dir / "workflow").mkdir(parents=True, exist_ok=False)

        thumbnail_rel_path = None
        if thumbnail_bytes is not None and thumb_ext is not None:
            thumbnail_rel_path = f"input/assets/competitor_thumbnail{thumb_ext}"
            (temp_dir / thumbnail_rel_path).write_bytes(bytes(thumbnail_bytes))

        competitor_reference = _competitor_reference_text(
            source_video_id, source_video_url, source_metadata, thumbnail_rel_path
        )
        (temp_dir / "input" / "competitor_reference.md").write_text(
            competitor_reference, encoding="utf-8", newline="\n"
        )
        (temp_dir / "input" / "channel_learnings.md").write_bytes(learnings_bytes)
        (temp_dir / "input" / "channel_metrics.csv").write_bytes(metrics_bytes)
        raw_payload = json.dumps(source_metadata, indent=2, ensure_ascii=False) + "\n"
        (temp_dir / "input" / "_raw" / "competitor_video.json").write_text(
            raw_payload, encoding="utf-8", newline="\n"
        )
        transcript_text = _transcript_template(
            title=source_metadata.get("title", ""),
            url=source_video_url,
            channel=source_metadata.get("channelTitle", ""),
            duration=str(source_metadata.get("duration", "")),
        )
        (temp_dir / "research" / "competitor_transcript.md").write_text(
            transcript_text, encoding="utf-8", newline="\n"
        )
        for relative_path in workflow_generated_outputs:
            target = temp_dir / Path(relative_path)
            if target.exists():
                raise ChannelProjectError("Workflow-generated artifacts must not be scaffolded during project creation.")

        snapshot_time = created_dt.isoformat()
        project_json = {
            "schema_version": 2,
            "project_type": "youtube_research",
            "project_slug": final_dir.name,
            "channel_slug": channel_slug,
            "youtube_channel_id": channel["youtube_channel_id"],
            "source_video_id": source_video_id,
            "source_video_url": source_video_url,
            "status": "WAITING_FOR_TRANSCRIPT",
            "workflow_input_status": "NOT_READY",
            "runnable": False,
            "created_at": snapshot_time,
            "updated_at": snapshot_time,
            "channel_snapshot": {
                "learnings_path": "input/channel_learnings.md",
                "metrics_path": "input/channel_metrics.csv",
                "captured_at": snapshot_time,
            },
        }
        if workflow_binding is not None:
            project_json["workflow_binding"] = workflow_binding
        (temp_dir / "project.json").write_text(
            json.dumps(project_json, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temp_dir, final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return load_channel_project(root, channel_slug, final_dir.name)


def list_channel_projects(root: Path | str, channel_slug: str) -> list[dict[str, Any]]:
    workspace = channel_workspace.canonical_channel_paths(root, channel_slug)
    channel_workspace.load_channel(root, channel_slug)
    if not workspace.projects_dir.exists():
        return []
    projects = []
    for entry in workspace.projects_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith(".tmp-"):
            continue
        project_json = entry / "project.json"
        if not project_json.exists():
            continue
        try:
            project = load_channel_project(root, channel_slug, entry.name)
        except ChannelProjectError:
            continue
        projects.append(project)
    projects.sort(key=lambda item: item["created_at"], reverse=True)
    return [_project_summary(item) for item in projects]


def save_project_transcript(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    transcript_text: str,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    if not isinstance(transcript_text, str) or not transcript_text.strip():
        raise ChannelProjectError("Transcript text must be non-empty.")
    paths = _project_paths(root, channel_slug, project_slug)
    load_channel_project(root, channel_slug, project_slug)
    if not paths.transcript_file.exists():
        raise ChannelProjectError("Transcript file does not exist.")
    current_bytes = paths.transcript_file.read_bytes()
    if transcript_has_real_content(paths.transcript_file) and not overwrite:
        raise ChannelProjectError("Transcript already contains real content. Use overwrite=True to replace it.")
    header = paths.transcript_file.read_text(encoding="utf-8").split("## Transcript", 1)[0].rstrip()
    updated = f"{header}\n\n## Transcript\n{transcript_text.strip()}\n"
    try:
        _write_text_atomic(paths.transcript_file, updated)
    except Exception:
        if paths.transcript_file.exists():
            _write_bytes_atomic(paths.transcript_file, current_bytes)
        raise
    return validate_channel_project(root, channel_slug, project_slug)


def _update_project_status_atomic(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    *,
    status: str,
    workflow_input_status: str,
    runnable: bool,
) -> dict[str, Any]:
    paths = _project_paths(root, channel_slug, project_slug)
    current = load_channel_project(root, channel_slug, project_slug)
    updated = dict(current)
    updated["status"] = status
    updated["workflow_input_status"] = workflow_input_status
    updated["runnable"] = runnable
    updated["updated_at"] = utc_now_iso()
    _validate_project_metadata(root, channel_slug, project_slug, updated)
    _write_json_atomic(paths.project_json, updated)
    return updated


def validate_channel_project(root: Path | str, channel_slug: str, project_slug: str) -> dict[str, Any]:
    project = load_channel_project(root, channel_slug, project_slug)
    paths = _project_paths(root, channel_slug, project_slug)
    checks = {
        "project_json": paths.project_json.exists(),
        "competitor_reference": paths.competitor_reference.exists(),
        "channel_learnings": paths.channel_learnings.exists() and bool(paths.channel_learnings.read_bytes().strip()),
        "channel_metrics": paths.channel_metrics.exists() and bool(paths.channel_metrics.read_bytes().strip()),
        "competitor_raw_json": paths.competitor_raw_json.exists(),
        "transcript_real_content": transcript_has_real_content(paths.transcript_file),
        "workflow_directory": paths.workflow_dir.exists() and paths.workflow_dir.is_dir(),
        "ownership": project["channel_slug"] == channel_slug == project["channel_slug"],
    }
    snapshot = project["channel_snapshot"]
    checks["safe_snapshot_paths"] = _relative_input_path(snapshot["learnings_path"]) and _relative_input_path(
        snapshot["metrics_path"]
    )
    if checks["transcript_real_content"] and all(
        checks[key]
        for key in (
            "project_json",
            "competitor_reference",
            "channel_learnings",
            "channel_metrics",
            "competitor_raw_json",
            "workflow_directory",
            "ownership",
            "safe_snapshot_paths",
        )
    ):
        updated = _update_project_status_atomic(
            root,
            channel_slug,
            project_slug,
            status="READY_FOR_WORKFLOW",
            workflow_input_status="READY",
            runnable=True,
        )
    else:
        updated = _update_project_status_atomic(
            root,
            channel_slug,
            project_slug,
            status="WAITING_FOR_TRANSCRIPT",
            workflow_input_status="NOT_READY",
            runnable=False,
        )
    return {"checks": checks, "project": _project_summary(updated)}
