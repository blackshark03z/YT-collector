from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class ChannelWorkspaceError(Exception):
    pass


@dataclass(frozen=True)
class ChannelPaths:
    root: Path
    channels_dir: Path
    channel_dir: Path
    channel_json: Path
    channel_profile: Path
    channel_learnings_master: Path
    metrics_dir: Path
    channel_metrics_csv: Path
    reporting_state_json: Path
    metrics_raw_dir: Path
    projects_dir: Path
    secrets_dir: Path
    oauth_token_file: Path
    oauth_token_ref: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_channel_slug(slug: str) -> str:
    if not isinstance(slug, str):
        raise ChannelWorkspaceError("Channel slug must be a string.")
    value = slug.strip()
    if not value:
        raise ChannelWorkspaceError("Channel slug is required.")
    if not SLUG_RE.fullmatch(value):
        raise ChannelWorkspaceError(
            "Channel slug must use lowercase ASCII letters, digits, and single underscores."
        )
    return value


def ensure_descendant(path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ChannelWorkspaceError(f"Resolved path escapes the repository root: {path}") from exc
    return resolved_path


def canonical_channel_paths(root: Path | str, slug: str) -> ChannelPaths:
    repo_root = Path(root).resolve()
    channel_slug = validate_channel_slug(slug)
    channels_dir = repo_root / "channels"
    channel_dir = channels_dir / channel_slug
    metrics_dir = channel_dir / "metrics"
    metrics_raw_dir = metrics_dir / "_raw"
    projects_dir = channel_dir / "projects"
    secrets_dir = repo_root / "secrets" / "youtube"
    oauth_token_file = secrets_dir / f"{channel_slug}_oauth_token.json"
    oauth_token_ref = oauth_token_file.relative_to(repo_root).as_posix()

    paths = ChannelPaths(
        root=repo_root,
        channels_dir=channels_dir,
        channel_dir=channel_dir,
        channel_json=channel_dir / "channel.json",
        channel_profile=channel_dir / "channel_profile.md",
        channel_learnings_master=channel_dir / "channel_learnings_master.md",
        metrics_dir=metrics_dir,
        channel_metrics_csv=metrics_dir / "channel_metrics.csv",
        reporting_state_json=metrics_dir / "reporting_state.json",
        metrics_raw_dir=metrics_raw_dir,
        projects_dir=projects_dir,
        secrets_dir=secrets_dir,
        oauth_token_file=oauth_token_file,
        oauth_token_ref=oauth_token_ref,
    )

    for value in asdict(paths).values():
        if isinstance(value, Path):
            ensure_descendant(value, repo_root)
    return paths


def validate_channel_metadata(data: dict[str, Any], expected_slug: str | None = None) -> dict[str, Any]:
    required = {
        "schema_version",
        "channel_slug",
        "display_name",
        "youtube_channel_id",
        "youtube_handle",
        "oauth_token_ref",
        "status",
        "created_at",
        "last_connected_at",
        "last_metrics_sync_at",
        "analytics_window_days",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ChannelWorkspaceError(f"channel.json is missing required fields: {', '.join(missing)}")

    slug = validate_channel_slug(data["channel_slug"])
    if expected_slug and slug != expected_slug:
        raise ChannelWorkspaceError("channel.json slug does not match the workspace folder.")

    if data["schema_version"] != 1:
        raise ChannelWorkspaceError("Unsupported channel schema_version.")
    if not isinstance(data["display_name"], str) or not data["display_name"].strip():
        raise ChannelWorkspaceError("display_name is required.")
    if not isinstance(data["youtube_channel_id"], str) or not data["youtube_channel_id"].strip():
        raise ChannelWorkspaceError("youtube_channel_id is required.")
    if not isinstance(data["youtube_handle"], str) or not data["youtube_handle"].strip():
        raise ChannelWorkspaceError("youtube_handle is required.")
    if not isinstance(data["status"], str) or not data["status"].strip():
        raise ChannelWorkspaceError("status is required.")
    if not isinstance(data["analytics_window_days"], int) or data["analytics_window_days"] <= 0:
        raise ChannelWorkspaceError("analytics_window_days must be a positive integer.")
    if not isinstance(data["oauth_token_ref"], str) or not data["oauth_token_ref"]:
        raise ChannelWorkspaceError("oauth_token_ref is required.")
    if Path(data["oauth_token_ref"]).is_absolute() or "\\" in data["oauth_token_ref"]:
        raise ChannelWorkspaceError("oauth_token_ref must be a relative POSIX-style path.")
    if not data["oauth_token_ref"].startswith("secrets/youtube/"):
        raise ChannelWorkspaceError("oauth_token_ref must live under secrets/youtube/.")
    if any(part in {".", ".."} for part in Path(data["oauth_token_ref"]).parts):
        raise ChannelWorkspaceError("oauth_token_ref must not contain path traversal.")

    secret_markers = {"access_token", "refresh_token", "client_secret", "token", "oauth_client"}
    lowered_keys = {key.lower() for key in data}
    if lowered_keys & secret_markers:
        raise ChannelWorkspaceError("channel.json must not store secret fields.")
    joined = json.dumps(data, ensure_ascii=False).lower()
    for marker in ("access_token", "refresh_token", "client_secret"):
        if marker in joined:
            raise ChannelWorkspaceError("channel.json contains secret-looking values.")

    _ensure_iso_timestamp(data["created_at"], "created_at")
    _ensure_nullable_iso_timestamp(data["last_connected_at"], "last_connected_at")
    _ensure_nullable_iso_timestamp(data["last_metrics_sync_at"], "last_metrics_sync_at")
    return data


def _ensure_iso_timestamp(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ChannelWorkspaceError(f"{field_name} must be a timezone-aware ISO timestamp.")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChannelWorkspaceError(f"{field_name} must be timezone-aware.")


def _ensure_nullable_iso_timestamp(value: Any, field_name: str) -> None:
    if value is None:
        return
    _ensure_iso_timestamp(value, field_name)


def build_channel_metadata(
    slug: str,
    display_name: str,
    youtube_channel_id: str,
    youtube_handle: str,
    oauth_token_ref: str,
    analytics_window_days: int = 90,
) -> dict[str, Any]:
    channel_slug = validate_channel_slug(slug)
    metadata = {
        "schema_version": 1,
        "channel_slug": channel_slug,
        "display_name": display_name.strip(),
        "youtube_channel_id": youtube_channel_id.strip(),
        "youtube_handle": youtube_handle.strip(),
        "oauth_token_ref": oauth_token_ref,
        "status": "NOT_CONNECTED",
        "created_at": utc_now_iso(),
        "last_connected_at": None,
        "last_metrics_sync_at": None,
        "analytics_window_days": analytics_window_days,
    }
    return validate_channel_metadata(metadata, expected_slug=channel_slug)


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
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


def _write_text_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8", newline="\n")


def load_channel(root: Path | str, slug: str) -> dict[str, Any]:
    paths = canonical_channel_paths(root, slug)
    if not paths.channel_json.exists():
        raise ChannelWorkspaceError("channel.json does not exist.")
    data = json.loads(paths.channel_json.read_text(encoding="utf-8"))
    return validate_channel_metadata(data, expected_slug=slug)


def list_channels(root: Path | str) -> list[dict[str, Any]]:
    repo_root = Path(root).resolve()
    channels_dir = repo_root / "channels"
    if not channels_dir.exists():
        return []
    found: list[dict[str, Any]] = []
    seen_ids: dict[str, str] = {}
    for channel_json in sorted(channels_dir.glob("*/channel.json")):
        slug = channel_json.parent.name
        data = load_channel(repo_root, slug)
        channel_id = data["youtube_channel_id"]
        existing = seen_ids.get(channel_id)
        if existing and existing != slug:
            raise ChannelWorkspaceError(
                f"Duplicate youtube_channel_id found in channels/{existing} and channels/{slug}."
            )
        seen_ids[channel_id] = slug
        found.append(data)
    return found


def create_channel_workspace(
    root: Path | str,
    slug: str,
    display_name: str,
    youtube_channel_id: str,
    youtube_handle: str,
    analytics_window_days: int = 90,
) -> dict[str, Any]:
    paths = canonical_channel_paths(root, slug)
    if paths.channel_json.exists():
        raise ChannelWorkspaceError("Channel workspace already exists for this slug.")

    for channel in list_channels(paths.root):
        if channel["channel_slug"] == slug:
            raise ChannelWorkspaceError("Channel slug already exists.")
        if channel["youtube_channel_id"] == youtube_channel_id.strip():
            raise ChannelWorkspaceError("youtube_channel_id already exists in another workspace.")

    metadata = build_channel_metadata(
        slug=slug,
        display_name=display_name,
        youtube_channel_id=youtube_channel_id,
        youtube_handle=youtube_handle,
        oauth_token_ref=paths.oauth_token_ref,
        analytics_window_days=analytics_window_days,
    )

    paths.metrics_raw_dir.mkdir(parents=True, exist_ok=True)
    paths.projects_dir.mkdir(parents=True, exist_ok=True)
    paths.secrets_dir.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(paths.channel_json, metadata)
    _write_text_if_missing(
        paths.channel_profile,
        (
            f"# {display_name.strip()}\n\n"
            f"- Channel slug: {metadata['channel_slug']}\n"
            f"- YouTube channel ID: {metadata['youtube_channel_id']}\n"
            f"- YouTube handle: {metadata['youtube_handle']}\n"
            "- Notes: Add approved identity and operating context here.\n"
        ),
    )
    _write_text_if_missing(
        paths.channel_learnings_master,
        (
            f"# {display_name.strip()} - Approved Channel Learnings\n\n"
            "Only add learnings that have been reviewed and explicitly approved by the user.\n"
        ),
    )
    return metadata
