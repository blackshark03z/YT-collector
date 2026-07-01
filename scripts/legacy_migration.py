from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import channel_workspace


FORBIDDEN_REPORT_ROOTS = {"secrets", "channels", "channel", "projects", ".local", "jesus"}
APPROVED_CHANNEL_FILES = {"channel_learnings_master.md"}
APPROVED_PROJECT_TOP_LEVEL = {"project.json", "input", "research", "workflow", "content.md", "publishing_package.md"}
RESULT_READY = "READY_FOR_REAL_MIGRATION"
RESULT_BLOCKED = "BLOCKED"


class LegacyMigrationError(Exception):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_legacy_migration_plan(
    root: Path | str,
    channel_slug: str = "mist_of_ages",
    *,
    planned_at: str | None = None,
) -> dict[str, Any]:
    repo_root = _resolve_repo_root(root)
    slug = channel_workspace.validate_channel_slug(channel_slug)
    migration_time = planned_at or utc_now_iso()

    blockers: list[str] = []
    warnings: list[str] = []

    legacy_identity = _inspect_legacy_identity(repo_root, slug, blockers, warnings)
    legacy_learnings = _inspect_legacy_learnings(repo_root, slug, blockers)
    legacy_token = _inspect_legacy_oauth_token(repo_root, warnings)
    legacy_projects = _inspect_legacy_projects(repo_root, slug, blockers, warnings)
    protected_paths = [_inspect_protected_manual_folder(repo_root)]
    legacy_channel_unknown = _inspect_legacy_channel_unknown_files(repo_root, slug)
    if legacy_channel_unknown:
        warnings.append("Legacy channel folder contains unclassified files that require review.")

    canonical = _inspect_canonical_destinations(
        repo_root,
        slug,
        legacy_projects["projects"],
        blockers,
        warnings,
    )
    proposed_channel = _build_proposed_channel_metadata(
        channel_slug=slug,
        legacy_identity=legacy_identity,
        legacy_token=legacy_token,
        planned_at=migration_time,
    )
    operations, post_migration_actions = _build_operations(
        slug,
        legacy_identity,
        legacy_learnings,
        legacy_token,
        legacy_projects["projects"],
        canonical,
        proposed_channel,
    )

    blockers.extend(legacy_projects["blockers"])
    warnings.extend(legacy_projects["warnings"])
    blockers.extend(canonical["blockers"])
    warnings.extend(canonical["warnings"])

    if legacy_identity["display_name"] is None:
        blockers.append("Legacy channel identity is missing a display name.")

    result = RESULT_BLOCKED if blockers else RESULT_READY
    plan = {
        "schema_version": 1,
        "mode": "DRY_RUN",
        "result": result,
        "channel_slug": slug,
        "planned_at": migration_time,
        "legacy": {
            "channel_identity": legacy_identity,
            "learnings": legacy_learnings,
            "oauth_token": legacy_token,
            "projects": legacy_projects["projects"],
            "project_count": len(legacy_projects["projects"]),
            "protected_paths": protected_paths,
            "unclassified_files": sorted(legacy_channel_unknown + legacy_projects["unclassified_files"]),
        },
        "canonical": {
            "channel_workspace": canonical["channel_workspace"],
            "channel_json": proposed_channel,
            "channel_profile": {
                "path": f"channels/{slug}/channel_profile.md",
                "state": "PLANNED_GENERATION",
            },
            "metrics": {
                "path": f"channels/{slug}/metrics",
                "state": "POST_MIGRATION_SYNC_REQUIRED",
            },
            "token_destination": canonical["token_destination"],
            "project_destinations": canonical["project_destinations"],
        },
        "operations": operations,
        "blockers": sorted(dict.fromkeys(blockers)),
        "warnings": sorted(dict.fromkeys(warnings)),
        "post_migration_actions": post_migration_actions,
    }
    return plan


def render_migration_report(plan: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Mist of Ages Legacy Migration Dry Run",
        "",
        "## Result",
        plan["result"],
        "",
        "## Repository Baseline",
        f"- Mode: {plan['mode']}",
        f"- Channel slug: {plan['channel_slug']}",
        f"- Planned at: {plan['planned_at']}",
        "",
        "## Legacy Sources",
        "### Channel Identity",
    ]
    identity = plan["legacy"]["channel_identity"]
    lines.extend(
        [
            f"- Path: {identity['path']}",
            f"- Exists: {identity['exists']}",
            f"- Valid JSON: {identity['valid_json']}",
            f"- Channel ID present: {identity['youtube_channel_id'] is not None}",
            f"- Display name present: {identity['display_name'] is not None}",
            f"- Handle present: {identity['youtube_handle'] is not None}",
            f"- Last connected at present: {identity['last_connected_at'] is not None}",
            "",
            "### Channel Learnings",
        ]
    )
    learnings = plan["legacy"]["learnings"]
    lines.extend(
        [
            f"- Path: {learnings['path']}",
            f"- Exists: {learnings['exists']}",
            f"- Non-empty: {learnings['non_empty']}",
            f"- Byte hash captured internally: {learnings['byte_hash'] is not None}",
            "",
            "### OAuth Token",
        ]
    )
    token = plan["legacy"]["oauth_token"]
    lines.extend(
        [
            f"- Path: {token['path']}",
            f"- TOKEN_PRESENT: {token['TOKEN_PRESENT']}",
            f"- TOKEN_VALID_STRUCTURE: {token['TOKEN_VALID_STRUCTURE']}",
            f"- REFRESH_TOKEN_PRESENT: {token['REFRESH_TOKEN_PRESENT']}",
            f"- RECONNECT_REQUIRED: {token['RECONNECT_REQUIRED']}",
            "",
            "### Legacy Projects",
            f"- Project count: {plan['legacy']['project_count']}",
        ]
    )
    for project in plan["legacy"]["projects"]:
        lines.extend(
            [
                f"- {project['legacy_project_path']}: schema={project['current_project_schema']}, transcript={project['manual_transcript_present']}, workflow_files={project['workflow_artifact_count']}, content={project['content_md_present']}, publishing_package={project['publishing_package_md_present']}, collision={project['collision_state']}, classification={project['classification']}",
            ]
        )
    lines.extend(
        [
            "",
            "### Protected Exclusions",
        ]
    )
    for protected in plan["legacy"]["protected_paths"]:
        lines.append(
            f"- {protected['path']}: {protected['classification']} (exists={protected['exists']})"
        )
    lines.extend(
        [
            "",
            "### Unclassified Files",
        ]
    )
    unclassified = plan["legacy"]["unclassified_files"]
    if unclassified:
        lines.extend([f"- {path}" for path in unclassified])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Canonical Destination State",
            f"- Channel workspace: {plan['canonical']['channel_workspace']['state']}",
            f"- Channel workspace path: {plan['canonical']['channel_workspace']['path']}",
            f"- Token destination: {plan['canonical']['token_destination']['state']}",
            f"- Token destination path: {plan['canonical']['token_destination']['path']}",
            f"- Metrics state: {plan['canonical']['metrics']['state']}",
            "",
            "## Proposed Operations",
        ]
    )
    for operation in plan["operations"]:
        lines.append(
            f"- {operation['action']}: {operation['source']} -> {operation['destination']} ({operation['note']})"
        )

    lines.extend(
        [
            "",
            "## Project Migration Matrix",
        ]
    )
    if plan["legacy"]["projects"]:
        lines.append("| Legacy Project | Destination | Collision | Classification |")
        lines.append("| --- | --- | --- | --- |")
        for project in plan["legacy"]["projects"]:
            lines.append(
                f"| {project['legacy_project_path']} | {project['destination_project_path']} | {project['collision_state']} | {project['classification']} |"
            )
    else:
        lines.append("- No legacy projects found.")

    lines.extend(
        [
            "",
            "## Blockers",
        ]
    )
    if plan["blockers"]:
        lines.extend([f"- {item}" for item in plan["blockers"]])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Warnings",
        ]
    )
    if plan["warnings"]:
        lines.extend([f"- {item}" for item in plan["warnings"]])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Post-Migration Required Actions",
        ]
    )
    if plan["post_migration_actions"]:
        lines.extend([f"- {item}" for item in plan["post_migration_actions"]])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Non-Mutation Evidence",
            "- Dry run inspects legacy sources read-only.",
            "- No canonical workspace, token destination, metrics files, or projects are created by the planner.",
            "- Protected `jesus/` contents are not enumerated or opened.",
            "",
            "## Approval Gate",
            "Real migration has not been performed.",
            "Wait for Tech Lead approval.",
            "",
        ]
    )
    return "\n".join(lines)


def run_dry_run(
    root: Path | str,
    channel_slug: str = "mist_of_ages",
    report_path: Path | str | None = None,
    *,
    planned_at: str | None = None,
) -> dict[str, Any]:
    repo_root = _resolve_repo_root(root)
    plan = build_legacy_migration_plan(repo_root, channel_slug=channel_slug, planned_at=planned_at)
    report = render_migration_report(plan)
    report_rel_path = None
    if report_path is not None:
        report_target = _validate_report_path(repo_root, report_path)
        report_target.write_text(report, encoding="utf-8", newline="\n")
        report_rel_path = _relative_path(report_target, repo_root)
    return {
        "plan": plan,
        "report": report,
        "report_path": report_rel_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only legacy migration dry run.")
    parser.add_argument("--root", default=".", help="Repository root to inspect.")
    parser.add_argument("--channel-slug", default="mist_of_ages", help="Legacy channel slug to inspect.")
    parser.add_argument("--dry-run", action="store_true", help="Required in this phase.")
    parser.add_argument("--report", help="Optional report path inside the repository root.")
    args = parser.parse_args(argv)

    if not args.dry_run:
        print("Dry-run mode is required in this phase.")
        return 2

    try:
        result = run_dry_run(
            args.root,
            channel_slug=args.channel_slug,
            report_path=args.report,
        )
    except LegacyMigrationError as exc:
        print(str(exc))
        return 2

    plan = result["plan"]
    print(f"Result: {plan['result']}")
    if result["report_path"]:
        print(f"Report: {result['report_path']}")
    return 0 if plan["result"] == RESULT_READY else 1


def _resolve_repo_root(root: Path | str) -> Path:
    repo_root = Path(root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise LegacyMigrationError("Repository root does not exist or is not a directory.")
    return repo_root


def _relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path) -> str:
    return _hash_bytes(path.read_bytes())


def _inspect_legacy_identity(
    repo_root: Path,
    channel_slug: str,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    path = repo_root / ".local" / f"{channel_slug}_channel.json"
    result = {
        "path": _relative_path(path, repo_root),
        "exists": path.exists(),
        "valid_json": False,
        "youtube_channel_id": None,
        "display_name": None,
        "youtube_handle": None,
        "uploads_playlist_id": None,
        "last_connected_at": None,
    }
    if not path.exists():
        blockers.append("Legacy channel identity file is missing.")
        return result

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        blockers.append("Legacy channel identity file is malformed.")
        return result

    if not isinstance(payload, dict):
        blockers.append("Legacy channel identity file is malformed.")
        return result

    result["valid_json"] = True
    channel_id = payload.get("id")
    if isinstance(channel_id, str) and channel_id.strip():
        result["youtube_channel_id"] = channel_id.strip()
    else:
        blockers.append("Legacy channel identity is missing a valid channel ID.")

    title = payload.get("title")
    if isinstance(title, str) and title.strip():
        result["display_name"] = title.strip()
    else:
        warnings.append("Legacy channel identity is missing a display name.")

    handle = payload.get("customUrl")
    if isinstance(handle, str) and handle.strip():
        result["youtube_handle"] = handle.strip()

    uploads = payload.get("uploads")
    if isinstance(uploads, str) and uploads.strip():
        result["uploads_playlist_id"] = uploads.strip()

    connected_at = payload.get("connected_at")
    if isinstance(connected_at, str) and connected_at.strip():
        try:
            parsed = datetime.fromisoformat(connected_at)
        except ValueError:
            warnings.append("Legacy channel identity has an invalid connected_at timestamp.")
        else:
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                result["last_connected_at"] = connected_at
            else:
                warnings.append("Legacy channel identity has a non-timezone-aware connected_at timestamp.")

    return result


def _inspect_legacy_learnings(repo_root: Path, channel_slug: str, blockers: list[str]) -> dict[str, Any]:
    path = repo_root / "channel" / channel_slug / "channel_learnings_master.md"
    result = {
        "path": _relative_path(path, repo_root),
        "exists": path.exists(),
        "non_empty": False,
        "byte_hash": None,
    }
    if not path.exists():
        blockers.append("Legacy channel learnings file is missing.")
        return result

    data = path.read_bytes()
    if not data.strip():
        blockers.append("Legacy channel learnings file is empty.")
        return result

    result["non_empty"] = True
    result["byte_hash"] = _hash_bytes(data)
    return result


def _inspect_legacy_oauth_token(repo_root: Path, warnings: list[str]) -> dict[str, Any]:
    path = repo_root / "youtube_oauth_token.json"
    result = {
        "path": _relative_path(path, repo_root),
        "TOKEN_PRESENT": path.exists(),
        "TOKEN_VALID_STRUCTURE": False,
        "REFRESH_TOKEN_PRESENT": False,
        "RECONNECT_REQUIRED": False,
        "status": "NEEDS_RECONNECT",
    }
    if not path.exists():
        result["RECONNECT_REQUIRED"] = True
        warnings.append("Legacy OAuth token is missing; reconnect will be required after migration.")
        return result

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        result["RECONNECT_REQUIRED"] = True
        warnings.append("Legacy OAuth token is malformed; reconnect will be required after migration.")
        return result

    if not isinstance(payload, dict):
        result["RECONNECT_REQUIRED"] = True
        warnings.append("Legacy OAuth token is malformed; reconnect will be required after migration.")
        return result

    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if isinstance(access_token, str) and access_token.strip():
        result["TOKEN_VALID_STRUCTURE"] = True
    else:
        result["RECONNECT_REQUIRED"] = True
        warnings.append("Legacy OAuth token is missing an access token; reconnect will be required after migration.")
        return result

    if isinstance(refresh_token, str) and refresh_token.strip():
        result["REFRESH_TOKEN_PRESENT"] = True
        result["status"] = "CONNECTED"
        return result

    result["RECONNECT_REQUIRED"] = True
    warnings.append("Legacy OAuth token has no refresh token; reconnect will be required after migration.")
    return result


def _inspect_legacy_projects(
    repo_root: Path,
    channel_slug: str,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    projects_dir = repo_root / "projects"
    records: list[dict[str, Any]] = []
    unclassified_files: list[str] = []
    local_blockers: list[str] = []
    local_warnings: list[str] = []

    if not projects_dir.exists():
        return {
            "projects": [],
            "unclassified_files": [],
            "blockers": [],
            "warnings": [],
        }

    for entry in sorted(projects_dir.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            continue
        project_record, project_unclassified = _inspect_legacy_project(repo_root, channel_slug, entry)
        records.append(project_record)
        unclassified_files.extend(project_unclassified)
        if project_record["classification"] != "READY_TO_MIGRATE":
            local_warnings.append(
                f"Legacy project {project_record['legacy_project_path']} requires review before real migration."
            )

    if unclassified_files:
        blockers.append("Legacy projects contain unclassified files that require review.")

    return {
        "projects": records,
        "unclassified_files": sorted(unclassified_files),
        "blockers": sorted(dict.fromkeys(local_blockers)),
        "warnings": sorted(dict.fromkeys(local_warnings)),
    }


def _inspect_legacy_project(repo_root: Path, channel_slug: str, project_dir: Path) -> tuple[dict[str, Any], list[str]]:
    relative_project = _relative_path(project_dir, repo_root)
    project_json_path = project_dir / "project.json"
    content_path = project_dir / "content.md"
    publishing_path = project_dir / "publishing_package.md"
    input_dir = project_dir / "input"
    research_dir = project_dir / "research"
    workflow_dir = project_dir / "workflow"

    schema_version: int | str | None = None
    source_video_id = None
    metadata_conversion_required = True
    metadata_malformed = False

    if project_json_path.exists():
        try:
            payload = json.loads(project_json_path.read_text(encoding="utf-8"))
        except Exception:
            metadata_malformed = True
            schema_version = "MALFORMED"
        else:
            if isinstance(payload, dict):
                schema_version = payload.get("schema_version")
                source_video_id = payload.get("source_video_id")
                metadata_conversion_required = payload.get("schema_version") != 2 or payload.get("channel_slug") != channel_slug
            else:
                metadata_malformed = True
                schema_version = "MALFORMED"
    else:
        schema_version = "MISSING"
        metadata_malformed = True

    transcript_paths = sorted(
        _relative_path(path, repo_root)
        for path in research_dir.rglob("*")
        if research_dir.exists() and path.is_file()
    )
    workflow_files = sorted(
        _relative_path(path, repo_root)
        for path in workflow_dir.rglob("*")
        if workflow_dir.exists() and path.is_file()
    )
    manual_file_hashes: dict[str, str] = {}
    if content_path.exists():
        manual_file_hashes[_relative_path(content_path, repo_root)] = _hash_file(content_path)
    if publishing_path.exists():
        manual_file_hashes[_relative_path(publishing_path, repo_root)] = _hash_file(publishing_path)
    for transcript in transcript_paths:
        manual_file_hashes[transcript] = _hash_file(repo_root / transcript)
    for workflow_file in workflow_files:
        manual_file_hashes[workflow_file] = _hash_file(repo_root / workflow_file)

    destination_project_path = f"channels/{channel_slug}/projects/{project_dir.name}"
    collision_state = _classify_project_destination(repo_root / destination_project_path)
    classification = "READY_TO_MIGRATE"
    if metadata_malformed:
        classification = "BLOCKED_MALFORMED_METADATA"
    elif collision_state != "DESTINATION_ABSENT":
        classification = "BLOCKED_DESTINATION_COLLISION"

    project_record = {
        "legacy_project_path": relative_project,
        "legacy_folder_name": project_dir.name,
        "source_video_id": source_video_id if isinstance(source_video_id, str) and source_video_id.strip() else None,
        "current_project_schema": schema_version,
        "destination_project_path": destination_project_path,
        "manual_transcript_present": bool(transcript_paths),
        "workflow_artifact_count": len(workflow_files),
        "content_md_present": content_path.exists(),
        "publishing_package_md_present": publishing_path.exists(),
        "metadata_conversion_required": metadata_conversion_required,
        "collision_state": collision_state,
        "classification": classification,
        "manual_file_hashes": manual_file_hashes,
    }
    return project_record, _find_unknown_project_files(repo_root, project_dir)


def _find_unknown_project_files(repo_root: Path, project_dir: Path) -> list[str]:
    unknown: list[str] = []
    for child in sorted(project_dir.iterdir(), key=lambda item: item.name):
        if child.name not in APPROVED_PROJECT_TOP_LEVEL:
            unknown.append(_relative_path(child, repo_root))
    return unknown


def _inspect_protected_manual_folder(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "jesus"
    return {
        "path": _relative_path(path, repo_root),
        "exists": path.exists(),
        "classification": "PROTECTED_EXCLUDED_FROM_MIGRATION",
    }


def _inspect_legacy_channel_unknown_files(repo_root: Path, channel_slug: str) -> list[str]:
    path = repo_root / "channel" / channel_slug
    if not path.exists():
        return []
    unknown: list[str] = []
    for child in sorted(path.iterdir(), key=lambda item: item.name):
        if child.name not in APPROVED_CHANNEL_FILES:
            unknown.append(_relative_path(child, repo_root))
    return unknown


def _inspect_canonical_destinations(
    repo_root: Path,
    channel_slug: str,
    projects: list[dict[str, Any]],
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    workspace_path = repo_root / "channels" / channel_slug
    token_path = repo_root / "secrets" / "youtube" / f"{channel_slug}_oauth_token.json"
    workspace_state = _classify_channel_workspace_destination(workspace_path)
    token_state = _classify_token_destination(token_path)

    local_blockers: list[str] = []
    local_warnings: list[str] = []
    if workspace_state == "DESTINATION_PARTIAL":
        local_blockers.append("Canonical channel workspace already exists in a partial state.")
    elif workspace_state in {"DESTINATION_CONFLICT", "DESTINATION_IDENTICAL"}:
        local_blockers.append("Canonical channel workspace already exists and requires review before migration.")

    if token_state != "DESTINATION_ABSENT":
        local_blockers.append("Canonical token destination already exists and requires review before migration.")

    project_destinations = []
    for project in projects:
        state = _classify_project_destination(repo_root / project["destination_project_path"])
        project_destinations.append(
            {
                "legacy_project_path": project["legacy_project_path"],
                "path": project["destination_project_path"],
                "state": state,
            }
        )
        if state != "DESTINATION_ABSENT":
            local_blockers.append(
                f"Canonical project destination already exists for {project['legacy_project_path']}."
            )

    return {
        "channel_workspace": {
            "path": f"channels/{channel_slug}",
            "state": workspace_state,
        },
        "token_destination": {
            "path": f"secrets/youtube/{channel_slug}_oauth_token.json",
            "state": token_state,
        },
        "project_destinations": project_destinations,
        "blockers": sorted(dict.fromkeys(local_blockers)),
        "warnings": sorted(dict.fromkeys(local_warnings)),
    }


def _build_proposed_channel_metadata(
    *,
    channel_slug: str,
    legacy_identity: dict[str, Any],
    legacy_token: dict[str, Any],
    planned_at: str,
) -> dict[str, Any]:
    status = "CONNECTED"
    if legacy_identity["youtube_channel_id"] is None or not legacy_token["TOKEN_VALID_STRUCTURE"] or not legacy_token["REFRESH_TOKEN_PRESENT"]:
        status = "NEEDS_RECONNECT"
    return {
        "path": f"channels/{channel_slug}/channel.json",
        "schema_version": 1,
        "channel_slug": channel_slug,
        "display_name": legacy_identity["display_name"],
        "youtube_channel_id": legacy_identity["youtube_channel_id"],
        "youtube_handle": legacy_identity["youtube_handle"],
        "oauth_token_ref": f"secrets/youtube/{channel_slug}_oauth_token.json",
        "status": status,
        "created_at": planned_at,
        "last_connected_at": legacy_identity["last_connected_at"],
        "last_metrics_sync_at": None,
        "analytics_window_days": 90,
    }


def _build_operations(
    channel_slug: str,
    legacy_identity: dict[str, Any],
    legacy_learnings: dict[str, Any],
    legacy_token: dict[str, Any],
    projects: list[dict[str, Any]],
    canonical: dict[str, Any],
    proposed_channel: dict[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    operations = [
        {
            "action": "PLAN_CREATE",
            "source": legacy_identity["path"],
            "destination": proposed_channel["path"],
            "note": f"Create canonical channel metadata with status {proposed_channel['status']}.",
        },
        {
            "action": "PLAN_GENERATE",
            "source": legacy_identity["path"],
            "destination": f"channels/{channel_slug}/channel_profile.md",
            "note": "Generate sanitized channel profile from legacy identity.",
        },
        {
            "action": "PLAN_COPY_BYTE_IDENTICAL",
            "source": legacy_learnings["path"],
            "destination": f"channels/{channel_slug}/channel_learnings_master.md",
            "note": "Copy approved learnings byte-for-byte during real migration.",
        },
    ]
    if legacy_token["TOKEN_VALID_STRUCTURE"]:
        operations.append(
            {
                "action": "PLAN_COPY_STRUCTURAL_TOKEN",
                "source": legacy_token["path"],
                "destination": canonical["token_destination"]["path"],
                "note": "Copy token file only during approved real migration; do not expose token values.",
            }
        )
    else:
        operations.append(
            {
                "action": "PLAN_SKIP_TOKEN_COPY",
                "source": legacy_token["path"],
                "destination": canonical["token_destination"]["path"],
                "note": "Do not copy malformed token; canonical channel will require reconnect.",
            }
        )
    for project in projects:
        operations.append(
            {
                "action": "PLAN_PROJECT_MIGRATION",
                "source": project["legacy_project_path"],
                "destination": project["destination_project_path"],
                "note": "Copy manual files byte-for-byte and rewrite metadata only if approved for real migration.",
            }
        )
    post_migration_actions = [
        "Run a selected-channel metrics sync after migration before creating new projects.",
    ]
    if legacy_token["RECONNECT_REQUIRED"]:
        post_migration_actions.append("Reconnect OAuth for the canonical channel workspace after migration.")
    return operations, post_migration_actions


def _classify_channel_workspace_destination(path: Path) -> str:
    if not path.exists():
        return "DESTINATION_ABSENT"
    if path.is_file():
        return "DESTINATION_CONFLICT"
    children = {child.name for child in path.iterdir()}
    if not children:
        return "DESTINATION_EMPTY"
    expected = {"channel.json", "channel_profile.md", "channel_learnings_master.md", "metrics", "projects"}
    if children == expected:
        return "DESTINATION_CONFLICT"
    if children & expected:
        return "DESTINATION_PARTIAL"
    return "DESTINATION_CONFLICT"


def _classify_token_destination(path: Path) -> str:
    if not path.exists():
        return "DESTINATION_ABSENT"
    if path.is_file() and path.stat().st_size == 0:
        return "DESTINATION_PARTIAL"
    return "DESTINATION_CONFLICT"


def _classify_project_destination(path: Path) -> str:
    if not path.exists():
        return "DESTINATION_ABSENT"
    if path.is_file():
        return "DESTINATION_CONFLICT"
    children = {child.name for child in path.iterdir()}
    if not children:
        return "DESTINATION_EMPTY"
    expected = {"project.json", "input", "research", "workflow", "content.md", "publishing_package.md"}
    if children == expected:
        return "DESTINATION_CONFLICT"
    if children & expected:
        return "DESTINATION_PARTIAL"
    return "DESTINATION_CONFLICT"


def _validate_report_path(repo_root: Path, report_path: Path | str) -> Path:
    target = Path(report_path)
    if not target.is_absolute():
        target = repo_root / target
    target = target.resolve()
    try:
        relative = target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise LegacyMigrationError("Report path must stay inside the repository root.") from exc

    if not relative.parts:
        raise LegacyMigrationError("Report path must point to a file.")
    if relative.parts[0] in FORBIDDEN_REPORT_ROOTS:
        raise LegacyMigrationError("Report path cannot point into runtime, secret, or protected folders.")
    if target.name in {"", ".", ".."}:
        raise LegacyMigrationError("Report path must point to a file.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


if __name__ == "__main__":
    raise SystemExit(main())
