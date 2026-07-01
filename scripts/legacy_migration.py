from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import channel_workspace


FORBIDDEN_REPORT_ROOTS = {"secrets", "channels", "channel", "projects", ".local", "jesus"}
APPROVED_CHANNEL_FILES = {"channel_learnings_master.md"}
APPROVED_PROJECT_TOP_LEVEL = {"project.json", "input", "research", "workflow", "content.md", "publishing_package.md"}
RESULT_READY = "READY_FOR_REAL_MIGRATION"
RESULT_BLOCKED = "BLOCKED"
STATUS_CONNECTED = "CONNECTED"
STATUS_NEEDS_RECONNECT = "NEEDS_RECONNECT"
DEFAULT_EXPECTED_SOURCE_HASHES = {
    ".local/mist_of_ages_channel.json": "E734AE2E98EC60B4E21A3A174A3CF0A61C9D30A4843B1A2F952797BF0CBDA92F",
    "channel/mist_of_ages/channel_learnings_master.md": "CA738615A10B3592B013C9C9829AFDB86BE6E69EC375BDC7E3F6154F94E51B10",
    "youtube_oauth_token.json": "1347976926280F505AA8F5060D7918F385703742D522999B858EA5598D3DE053",
}


class LegacyMigrationError(Exception):
    pass


WriteBytesAtomic = Callable[[Path, bytes], None]


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
    return {
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
        lines.append(
            f"- {project['legacy_project_path']}: schema={project['current_project_schema']}, transcript={project['manual_transcript_present']}, workflow_files={project['workflow_artifact_count']}, content={project['content_md_present']}, publishing_package={project['publishing_package_md_present']}, collision={project['collision_state']}, classification={project['classification']}"
        )
    lines.extend(["", "### Protected Exclusions"])
    for protected in plan["legacy"]["protected_paths"]:
        lines.append(f"- {protected['path']}: {protected['classification']} (exists={protected['exists']})")
    lines.extend(["", "### Unclassified Files"])
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

    lines.extend(["", "## Project Migration Matrix"])
    if plan["legacy"]["projects"]:
        lines.append("| Legacy Project | Destination | Collision | Classification |")
        lines.append("| --- | --- | --- | --- |")
        for project in plan["legacy"]["projects"]:
            lines.append(
                f"| {project['legacy_project_path']} | {project['destination_project_path']} | {project['collision_state']} | {project['classification']} |"
            )
    else:
        lines.append("- No legacy projects found.")

    lines.extend(["", "## Blockers"])
    if plan["blockers"]:
        lines.extend([f"- {item}" for item in plan["blockers"]])
    else:
        lines.append("- None")

    lines.extend(["", "## Warnings"])
    if plan["warnings"]:
        lines.extend([f"- {item}" for item in plan["warnings"]])
    else:
        lines.append("- None")

    lines.extend(["", "## Post-Migration Required Actions"])
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


def apply_legacy_migration(
    root: Path | str,
    channel_slug: str = "mist_of_ages",
    *,
    expected_source_hashes: dict[str, str] | None = None,
    planned_at: str | None = None,
    write_bytes_atomic: WriteBytesAtomic | None = None,
) -> dict[str, Any]:
    repo_root = _resolve_repo_root(root)
    slug = channel_workspace.validate_channel_slug(channel_slug)
    workspace = channel_workspace.canonical_channel_paths(repo_root, slug)
    _ensure_apply_destinations_absent(workspace)
    plan = build_legacy_migration_plan(repo_root, channel_slug=slug, planned_at=planned_at)
    _validate_apply_plan(plan)
    source_hashes = verify_source_hashes(repo_root, expected_source_hashes or DEFAULT_EXPECTED_SOURCE_HASHES)

    identity_path = repo_root / plan["legacy"]["channel_identity"]["path"]
    learnings_path = repo_root / plan["legacy"]["learnings"]["path"]
    token_path = repo_root / plan["legacy"]["oauth_token"]["path"]

    identity_payload = json.loads(identity_path.read_text(encoding="utf-8"))
    channel_metadata = _build_apply_channel_metadata(plan, identity_payload)
    channel_profile_bytes = _build_channel_profile_bytes(channel_metadata)
    channel_json_bytes = _json_bytes(channel_metadata)
    learnings_bytes = learnings_path.read_bytes()
    token_bytes = token_path.read_bytes()
    _validate_oauth_token_bytes(token_bytes)

    writer = write_bytes_atomic or _write_bytes_atomic
    created_files: list[Path] = []
    created_dirs: list[Path] = []
    token_copied = False

    try:
        _ensure_parent_dirs(workspace.channel_json.parent, created_dirs)
        _ensure_parent_dirs(workspace.oauth_token_file.parent, created_dirs)
        _write_new_file(workspace.channel_json, channel_json_bytes, writer)
        created_files.append(workspace.channel_json)
        _write_new_file(workspace.channel_profile, channel_profile_bytes, writer)
        created_files.append(workspace.channel_profile)
        _write_new_file(workspace.channel_learnings_master, learnings_bytes, writer)
        created_files.append(workspace.channel_learnings_master)
        _write_new_file(workspace.oauth_token_file, token_bytes, writer, restrict_permissions=True)
        created_files.append(workspace.oauth_token_file)
        token_copied = True
    except Exception as exc:
        _rollback_created_paths(created_files, created_dirs)
        raise LegacyMigrationError("Legacy migration apply failed before completion.") from exc

    return {
        "mode": "APPLY",
        "channel_slug": slug,
        "planned_at": plan["planned_at"],
        "source_hashes": source_hashes,
        "created_files": [_relative_path(path, repo_root) for path in created_files],
        "token_copied": token_copied,
        "project_count": plan["legacy"]["project_count"],
        "status": channel_metadata["status"],
    }


def verify_source_hashes(
    root: Path | str,
    expected_hashes: dict[str, str],
) -> dict[str, str]:
    repo_root = _resolve_repo_root(root)
    resolved: dict[str, str] = {}
    for relative_path, expected_hash in expected_hashes.items():
        path = repo_root / relative_path
        if not path.exists() or not path.is_file():
            raise LegacyMigrationError(f"Required source file is missing: {relative_path}")
        actual_hash = _hash_file(path).upper()
        if actual_hash != expected_hash.upper():
            raise LegacyMigrationError(f"Source hash mismatch for {relative_path}.")
        resolved[relative_path] = actual_hash
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Legacy migration planner and apply tool.")
    parser.add_argument("--root", default=".", help="Repository root to inspect.")
    parser.add_argument("--channel-slug", default="mist_of_ages", help="Legacy channel slug to inspect.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a read-only migration dry run.")
    parser.add_argument("--apply", action="store_true", help="Apply the authorized migration.")
    parser.add_argument("--report", help="Optional report path inside the repository root.")
    parser.add_argument(
        "--expected-source-hash",
        action="append",
        default=[],
        help="Optional apply precondition in the form relative/path=SHA256.",
    )
    args = parser.parse_args(argv)

    if args.dry_run == args.apply:
        print("Choose exactly one mode: --dry-run or --apply.")
        return 2
    if args.report and args.apply:
        print("Report output is supported only with --dry-run.")
        return 2

    try:
        if args.dry_run:
            result = run_dry_run(
                args.root,
                channel_slug=args.channel_slug,
                report_path=args.report,
            )
            plan = result["plan"]
            print(f"Result: {plan['result']}")
            if result["report_path"]:
                print(f"Report: {result['report_path']}")
            return 0 if plan["result"] == RESULT_READY else 1

        result = apply_legacy_migration(
            args.root,
            channel_slug=args.channel_slug,
            expected_source_hashes=_parse_expected_source_hash_args(args.expected_source_hash) or DEFAULT_EXPECTED_SOURCE_HASHES,
        )
    except LegacyMigrationError as exc:
        print(str(exc))
        return 2

    print("Result: APPLIED")
    print(f"Channel: {result['channel_slug']}")
    print(f"Created files: {len(result['created_files'])}")
    return 0


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
        "status": STATUS_NEEDS_RECONNECT,
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
        result["status"] = STATUS_CONNECTED
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
                metadata_conversion_required = (
                    payload.get("schema_version") != 2 or payload.get("channel_slug") != channel_slug
                )
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
    status = STATUS_CONNECTED
    if (
        legacy_identity["youtube_channel_id"] is None
        or not legacy_token["TOKEN_VALID_STRUCTURE"]
        or not legacy_token["REFRESH_TOKEN_PRESENT"]
    ):
        status = STATUS_NEEDS_RECONNECT
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
                "note": "Project migration remains out of scope for this authorized run.",
            }
        )
    post_migration_actions = ["Run a selected-channel metrics sync after migration before creating new projects."]
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


def _parse_expected_source_hash_args(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise LegacyMigrationError("Expected source hash arguments must use relative/path=SHA256.")
        relative_path, hash_value = item.split("=", 1)
        relative_path = relative_path.strip().replace("\\", "/")
        hash_value = hash_value.strip().upper()
        if not relative_path or not hash_value or len(hash_value) != 64:
            raise LegacyMigrationError("Expected source hash arguments must use relative/path=SHA256.")
        parsed[relative_path] = hash_value
    return parsed


def _validate_apply_plan(plan: dict[str, Any]) -> None:
    if plan["result"] != RESULT_READY:
        raise LegacyMigrationError("Dry-run plan is not ready for real migration.")
    if plan["legacy"]["project_count"] != 0:
        raise LegacyMigrationError("Project migration is not authorized for this Phase 5B run.")
    if plan["legacy"]["unclassified_files"]:
        raise LegacyMigrationError("Unclassified legacy files block the authorized migration.")
    if plan["canonical"]["channel_workspace"]["state"] != "DESTINATION_ABSENT":
        raise LegacyMigrationError("Canonical channel destination must be absent before apply.")
    if plan["canonical"]["token_destination"]["state"] != "DESTINATION_ABSENT":
        raise LegacyMigrationError("Canonical token destination must be absent before apply.")
    token = plan["legacy"]["oauth_token"]
    if not token["TOKEN_VALID_STRUCTURE"] or not token["REFRESH_TOKEN_PRESENT"]:
        raise LegacyMigrationError("Legacy OAuth token is not valid enough for authorized apply.")


def _ensure_apply_destinations_absent(workspace: channel_workspace.ChannelPaths) -> None:
    destinations = [
        workspace.channel_json,
        workspace.channel_profile,
        workspace.channel_learnings_master,
        workspace.oauth_token_file,
    ]
    existing = [path for path in destinations if path.exists()]
    if existing:
        raise LegacyMigrationError("Authorized apply refuses to overwrite an existing canonical destination.")
    if workspace.channel_dir.exists():
        raise LegacyMigrationError("Authorized apply requires channels/mist_of_ages/ to be absent.")


def _build_apply_channel_metadata(plan: dict[str, Any], identity_payload: dict[str, Any]) -> dict[str, Any]:
    channel_json = dict(plan["canonical"]["channel_json"])
    channel_json.pop("path", None)
    validated = channel_workspace.validate_channel_metadata(channel_json, expected_slug=plan["channel_slug"])
    if validated["youtube_channel_id"] != identity_payload.get("id"):
        raise LegacyMigrationError("Legacy identity source changed before apply.")
    return validated


def _build_channel_profile_bytes(metadata: dict[str, Any]) -> bytes:
    text = (
        f"# {metadata['display_name']}\n\n"
        f"- Channel slug: {metadata['channel_slug']}\n"
        f"- YouTube channel ID: {metadata['youtube_channel_id']}\n"
        f"- YouTube handle: {metadata['youtube_handle']}\n"
        "- Notes: Migrated from approved legacy Mist of Ages identity.\n"
    )
    return text.encode("utf-8")


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _validate_oauth_token_bytes(data: bytes) -> None:
    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise LegacyMigrationError("Legacy OAuth token source is malformed.") from exc
    if not isinstance(payload, dict):
        raise LegacyMigrationError("Legacy OAuth token source is malformed.")
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise LegacyMigrationError("Legacy OAuth token source is missing an access token.")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise LegacyMigrationError("Legacy OAuth token source is missing a refresh token.")


def _ensure_parent_dirs(path: Path, created_dirs: list[Path]) -> None:
    pending: list[Path] = []
    current = path
    while not current.exists():
        pending.append(current)
        current = current.parent
    for directory in reversed(pending):
        directory.mkdir()
        created_dirs.append(directory)


def _write_new_file(
    path: Path,
    data: bytes,
    writer: WriteBytesAtomic,
    *,
    restrict_permissions: bool = False,
) -> None:
    if path.exists():
        raise LegacyMigrationError("Authorized apply refuses to overwrite an existing file.")
    writer(path, data)
    if restrict_permissions:
        _restrict_permissions(path)


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


def _restrict_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _rollback_created_paths(created_files: list[Path], created_dirs: list[Path]) -> None:
    for path in reversed(created_files):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    for directory in reversed(created_dirs):
        try:
            directory.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
