from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from scripts import channel_projects, channel_workflow, channel_workspace


SUPPORTED_PRODUCTION_EXPORT_SCHEMA_VERSION = 1
REQUIRED_PRODUCTION_ARTIFACT_IDS = ("content", "publishing_package")


class ProductionExportError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error(code: str, message: str, status: int = 400) -> ProductionExportError:
    return ProductionExportError(code, message, status)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _artifact_by_id(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        artifact["artifact_id"]: artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and isinstance(artifact.get("artifact_id"), str)
    }


def _project_dir(root: Path | str, channel_slug: str, project_slug: str) -> Path:
    return channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug


def _project_file_url(root: Path, path: Path) -> str:
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    return f"/{relative}"


def _stable_artifact_entry(
    *,
    root: Path,
    project_dir: Path,
    artifact_definition: dict[str, Any],
    approved_summary: dict[str, Any] | None,
    approved_group_id: str | None,
    final_step_id: str,
) -> dict[str, Any]:
    relative_path = artifact_definition["relative_path"]
    artifact_path = project_dir / PurePosixPath(relative_path)
    artifact_id = artifact_definition["artifact_id"]
    entry: dict[str, Any] = {
        "artifact_id": artifact_id,
        "display_name": artifact_definition.get("display_name", artifact_id),
        "filename": Path(relative_path).name,
        "relative_path": relative_path,
        "file_url": _project_file_url(root, artifact_path),
        "exists": artifact_path.exists() and artifact_path.is_file(),
        "approved_group_id": approved_group_id,
        "approved_revision_id": approved_summary.get("revision_id") if isinstance(approved_summary, dict) else None,
        "approved_content_sha256": approved_summary.get("content_sha256") if isinstance(approved_summary, dict) else None,
        "approved_character_count": approved_summary.get("character_count") if isinstance(approved_summary, dict) else None,
        "matches_approved_revision_metadata": False,
    }
    if not entry["exists"]:
        return entry

    content = artifact_path.read_text(encoding="utf-8")
    entry["character_count"] = len(content)
    entry["sha256"] = _sha256_text(content)

    revision_id = entry["approved_revision_id"]
    if not isinstance(revision_id, str) or not revision_id.startswith("rev_"):
        return entry

    metadata_path = project_dir / "workflow" / "revisions" / "artifacts" / artifact_id / revision_id / "metadata.json"
    entry["approved_metadata_path"] = str(metadata_path)
    if not metadata_path.exists():
        return entry

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    entry["source_step_id"] = metadata.get("source_step_id")
    entry["matches_approved_revision_metadata"] = (
        metadata.get("revision_group_id") == approved_group_id
        and metadata.get("source_step_id") == final_step_id
        and metadata.get("content_sha256") == entry["sha256"]
        and metadata.get("character_count") == entry["character_count"]
    )
    return entry


def _build_summary(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    *,
    project: dict[str, Any] | None = None,
    project_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_root = Path(root)
    loaded_project = project or channel_projects.load_channel_project(resolved_root, channel_slug, project_slug)
    resolved_project_dir = project_dir or _project_dir(resolved_root, channel_slug, project_slug)
    workflow = channel_workflow.build_workflow_read_model(
        resolved_root,
        channel_slug,
        project_slug,
        loaded_project,
        resolved_project_dir,
    )
    binding = workflow["binding"]
    definition = workflow["definition"]
    state = workflow["state"]
    steps = definition.get("steps", [])
    if not steps:
        raise _error("PRODUCTION_EXPORT_UNSUPPORTED", "The workflow definition does not declare any steps.", 409)

    final_step = steps[-1]
    final_step_id = final_step["step_id"]
    final_state = state["step_states"].get(final_step_id, {})
    approved_group_id = final_state.get("approved_group_id")
    approved_group = final_state.get("approved_group")
    approved_artifacts = {
        artifact["artifact_id"]: artifact
        for artifact in approved_group.get("artifacts", [])
    } if isinstance(approved_group, dict) else {}
    artifacts_by_id = _artifact_by_id(workflow.get("artifacts", []))

    errors: list[str] = []
    expected_ids = list(REQUIRED_PRODUCTION_ARTIFACT_IDS)
    if list(final_step.get("output_artifact_ids", [])) != expected_ids:
        errors.append("The final workflow step output contract is not the supported production handoff package.")

    lifecycle = state.get("current_lifecycle_state")
    ready_for_export = lifecycle == "PRODUCTION_READY"
    if lifecycle != "PRODUCTION_READY":
        errors.append("The workflow lifecycle is not PRODUCTION_READY.")
    if final_state.get("status") != "APPROVED":
        errors.append("The final workflow step is not approved.")
    if not isinstance(approved_group_id, str) or not approved_group_id.startswith("grp_"):
        errors.append("The final workflow step does not expose an approved revision group.")

    artifact_entries: list[dict[str, Any]] = []
    for artifact_id in expected_ids:
        definition_artifact = artifacts_by_id.get(artifact_id)
        if definition_artifact is None:
            errors.append(f"The workflow definition is missing artifact metadata for {artifact_id}.")
            continue
        entry = _stable_artifact_entry(
            root=resolved_root,
            project_dir=resolved_project_dir,
            artifact_definition=definition_artifact,
            approved_summary=approved_artifacts.get(artifact_id),
            approved_group_id=approved_group_id if isinstance(approved_group_id, str) else None,
            final_step_id=final_step_id,
        )
        artifact_entries.append(entry)
        if not entry["exists"]:
            errors.append(f"Required stable artifact is missing: {entry['filename']}.")
            ready_for_export = False
            continue
        if not entry["matches_approved_revision_metadata"]:
            errors.append(f"Stable artifact does not match approved revision metadata: {entry['filename']}.")
            ready_for_export = False

    download_url = f"/api/v2/channels/{channel_slug}/projects/{project_slug}/production-package/download"
    return {
        "schema_version": SUPPORTED_PRODUCTION_EXPORT_SCHEMA_VERSION,
        "channel_slug": channel_slug,
        "project_slug": project_slug,
        "workflow_id": binding["workflow_id"],
        "workflow_version": binding["workflow_version"],
        "workflow_definition_sha256": binding["workflow_definition_sha256"],
        "state_revision": state["state_revision"],
        "lifecycle": lifecycle,
        "current_step_id": state.get("current_step_id"),
        "current_step_status": state.get("current_step_status"),
        "next_step_id": state.get("next_step_id"),
        "production_step_id": final_step_id,
        "approved_group_id": approved_group_id,
        "candidate_group_id": final_state.get("candidate_group_id"),
        "ready_for_export": ready_for_export and not errors,
        "errors": errors,
        "artifacts": artifact_entries,
        "download_url": download_url,
    }


def build_production_package_summary(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    *,
    project: dict[str, Any] | None = None,
    project_dir: Path | None = None,
) -> dict[str, Any]:
    return _build_summary(root, channel_slug, project_slug, project=project, project_dir=project_dir)


def _manifest_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SUPPORTED_PRODUCTION_EXPORT_SCHEMA_VERSION,
        "channel_slug": summary["channel_slug"],
        "project_slug": summary["project_slug"],
        "workflow_id": summary["workflow_id"],
        "workflow_version": summary["workflow_version"],
        "state_revision": summary["state_revision"],
        "lifecycle": summary["lifecycle"],
        "approved_group_id": summary["approved_group_id"],
        "exported_at": _utc_now_iso(),
        "artifacts": [
            {
                "filename": artifact["filename"],
                "character_count": artifact["character_count"],
                "sha256": artifact["sha256"],
            }
            for artifact in summary["artifacts"]
        ],
    }


def _zip_bytes(*, summary: dict[str, Any], project_dir: Path) -> bytes:
    artifact_entries = {artifact["filename"]: artifact for artifact in summary["artifacts"]}
    manifest = _manifest_from_summary(summary)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in ("content.md", "publishing_package.md"):
            info = zipfile.ZipInfo(filename)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (project_dir / filename).read_text(encoding="utf-8"))
        manifest_info = zipfile.ZipInfo("manifest.json")
        manifest_info.date_time = (1980, 1, 1, 0, 0, 0)
        manifest_info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(manifest_info, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return buffer.getvalue()


def build_production_package_download(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    *,
    project: dict[str, Any] | None = None,
    project_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_root = Path(root)
    loaded_project = project or channel_projects.load_channel_project(resolved_root, channel_slug, project_slug)
    resolved_project_dir = project_dir or _project_dir(resolved_root, channel_slug, project_slug)
    summary = _build_summary(resolved_root, channel_slug, project_slug, project=loaded_project, project_dir=resolved_project_dir)
    if not summary["ready_for_export"]:
        approved_group_id = summary.get("approved_group_id")
        has_approved_group = isinstance(approved_group_id, str) and approved_group_id.startswith("grp_")
        if has_approved_group and any("missing" in message.lower() for message in summary["errors"]):
            raise _error("PRODUCTION_EXPORT_MISSING_ARTIFACT", "Required stable production artifacts are missing.", 409)
        if has_approved_group and any("approved revision metadata" in message.lower() for message in summary["errors"]):
            raise _error("PRODUCTION_EXPORT_IDENTITY_MISMATCH", "Stable production artifacts do not match the approved revision metadata.", 409)
        if summary.get("lifecycle") != "PRODUCTION_READY" or not has_approved_group:
            raise _error("PRODUCTION_EXPORT_NOT_READY", "The selected project is not in PRODUCTION_READY state.", 409)
        raise _error("PRODUCTION_EXPORT_IDENTITY_MISMATCH", "Stable production artifacts do not match the approved revision metadata.", 409)
    return {
        "filename": f"{project_slug}_production_package.zip",
        "content_type": "application/zip",
        "body_bytes": _zip_bytes(summary=summary, project_dir=resolved_project_dir),
        "summary": summary,
    }
