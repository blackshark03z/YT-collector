from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from scripts import channel_workspace


SUPPORTED_STATE_SCHEMA_VERSION = 3
SUPPORTED_STATE_SCHEMA_VERSION_V2 = 2
SUPPORTED_REVISION_METADATA_SCHEMA_VERSION = 1
SUPPORTED_GROUP_METADATA_SCHEMA_VERSION = 1
SUPPORTED_TRANSACTION_MANIFEST_SCHEMA_VERSION = 1
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_STALE_AFTER = timedelta(minutes=15)
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


class ChannelWorkflowWriteError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error(code: str, message: str, status: int = 400) -> ChannelWorkflowWriteError:
    return ChannelWorkflowWriteError(code, message, status)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _validate_digest(value: Any, *, field_name: str, code: str) -> str:
    if not isinstance(value, str) or len(value.strip()) != 64:
        raise _error(code, f"{field_name} must be a 64-character SHA-256 hex digest.")
    digest = value.strip().upper()
    if any(ch not in "0123456789ABCDEF" for ch in digest):
        raise _error(code, f"{field_name} must be a valid SHA-256 hex digest.")
    return digest


def _ensure_iso_timestamp(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name} must be a timezone-aware ISO timestamp.", 409)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name} must be timezone-aware.", 409)


def _safe_relative_path(value: str, *, field_name: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise _error("REVISION_STORAGE_INVALID", f"{field_name} must be a non-empty relative path.", 409)
    if "\\" in value:
        raise _error("REVISION_STORAGE_INVALID", f"{field_name} must use forward slashes only.", 409)
    pure = PurePosixPath(value)
    if pure.is_absolute() or "." in pure.parts or ".." in pure.parts:
        raise _error("REVISION_STORAGE_INVALID", f"{field_name} must remain under workflow/.", 409)
    return pure


def _validate_windows_safe_components(pure: PurePosixPath, *, code: str, field_name: str) -> None:
    lowered_seen: set[str] = set()
    for part in pure.parts:
        lowered = part.lower()
        if lowered in lowered_seen:
            raise _error(code, f"{field_name} contains a case-insensitive duplicate path component.", 409)
        lowered_seen.add(lowered)
        if lowered in WINDOWS_RESERVED_NAMES:
            raise _error(code, f"{field_name} contains a Windows reserved name.", 409)
        if part.rstrip(" .") != part:
            raise _error(code, f"{field_name} contains a trailing dot or space component.", 409)


def _safe_join(root: Path, relative_path: str, *, field_name: str) -> Path:
    pure = _safe_relative_path(relative_path, field_name=field_name)
    _validate_windows_safe_components(pure, code="REVISION_STORAGE_INVALID", field_name=field_name)
    resolved_root = root.resolve()
    resolved = (resolved_root / pure).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise _error("REVISION_STORAGE_INVALID", f"{field_name} escapes the workflow root.", 409) from exc
    return resolved


@dataclass(frozen=True)
class WorkflowWritePaths:
    workflow_dir: Path
    workflow_state_json: Path
    transactions_dir: Path
    lock_file: Path
    revisions_dir: Path
    groups_dir: Path
    artifacts_dir: Path
    decisions_dir: Path


def workflow_write_paths(project_dir: Path) -> WorkflowWritePaths:
    workflow_dir = (project_dir / "workflow").resolve()
    return WorkflowWritePaths(
        workflow_dir=workflow_dir,
        workflow_state_json=workflow_dir / "workflow_state.json",
        transactions_dir=workflow_dir / "_transactions",
        lock_file=workflow_dir / "_transactions" / ".lock",
        revisions_dir=workflow_dir / "revisions",
        groups_dir=workflow_dir / "revisions" / "groups",
        artifacts_dir=workflow_dir / "revisions" / "artifacts",
        decisions_dir=workflow_dir / "revisions" / "decisions",
    )


def _artifact_output_exists(project_dir: Path, artifact: dict[str, Any], *, binding: dict[str, Any], definition: dict[str, Any]) -> bool:
    from scripts import channel_prompt_bundle

    return channel_prompt_bundle._workflow_managed_artifact_is_trusted(  # type: ignore[attr-defined]
        project_dir=project_dir,
        artifact=artifact,
        binding=binding,
        definition=definition,
    )


def _derive_workflow_progress(project: dict[str, Any], project_dir: Path, definition: dict[str, Any]) -> dict[str, Any]:
    from scripts import channel_workflow

    steps = list(definition["steps"])
    ready = channel_workflow._is_project_workflow_input_ready(project)  # type: ignore[attr-defined]
    first_step = steps[0]
    if not ready:
        return {
            "current_lifecycle_state": None,
            "current_step_id": first_step["step_id"],
            "next_step_id": steps[1]["step_id"] if len(steps) > 1 else None,
            "base_status": "BLOCKED",
            "blocking_reason": "WORKFLOW_INPUT_NOT_READY",
        }

    previous_lifecycle_state = definition["entry_lifecycle_state"]
    for index, step in enumerate(steps):
        binding = project.get("workflow_binding")
        if not isinstance(binding, dict):
            raise _error("WORKFLOW_STATE_INVALID", "Project workflow binding is missing for workflow-managed artifact trust checks.", 409)
        outputs_ready = all(
            _artifact_output_exists(
                project_dir,
                next(artifact for artifact in definition["artifacts"] if artifact["artifact_id"] == artifact_id),
                binding=binding,
                definition=definition,
            )
            for artifact_id in step["output_artifact_ids"]
        )
        if not outputs_ready:
            return {
                "current_lifecycle_state": previous_lifecycle_state,
                "current_step_id": step["step_id"],
                "next_step_id": steps[index + 1]["step_id"] if index + 1 < len(steps) else None,
                "base_status": "READY",
                "blocking_reason": None,
            }
        previous_lifecycle_state = step["resulting_lifecycle_state"]

    last_step = steps[-1]
    return {
        "current_lifecycle_state": definition["terminal_lifecycle_state"],
        "current_step_id": last_step["step_id"],
        "next_step_id": None,
        "base_status": "APPROVED",
        "blocking_reason": None,
    }


def _empty_v2_state(binding: dict[str, Any], definition: dict[str, Any], *, created_at: str | None = None) -> dict[str, Any]:
    timestamp = created_at or utc_now_iso()
    return {
        "schema_version": SUPPORTED_STATE_SCHEMA_VERSION_V2,
        "workflow_id": binding["workflow_id"],
        "workflow_version": binding["workflow_version"],
        "workflow_definition_sha256": binding["workflow_definition_sha256"],
        "state_revision": 0,
        "step_states": {},
        "artifact_heads": {},
        "counters": {
            "next_group_number": 1,
            "next_revision_number_by_artifact": {
                artifact["artifact_id"]: 1 for artifact in definition["artifacts"] if artifact["artifact_role"] in {"GENERATED", "FINAL"}
            },
        },
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _empty_v3_state(binding: dict[str, Any], definition: dict[str, Any], *, created_at: str | None = None) -> dict[str, Any]:
    payload = _empty_v2_state(binding, definition, created_at=created_at)
    payload["schema_version"] = SUPPORTED_STATE_SCHEMA_VERSION
    return payload


def _step_inputs_are_trusted(
    *,
    project_dir: Path,
    step: dict[str, Any],
    binding: dict[str, Any],
    definition: dict[str, Any],
) -> bool:
    artifact_map = {artifact["artifact_id"]: artifact for artifact in definition["artifacts"]}
    return all(
        _artifact_output_exists(project_dir, artifact_map[artifact_id], binding=binding, definition=definition)
        for artifact_id in step["input_artifact_ids"]
    )


def _validate_stale_reason(value: Any, *, field_name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name} must be an object or null.", 409)
    required = {
        "upstream_artifact_ids",
        "caused_by_step_ids",
        "caused_by_group_ids",
        "caused_by_state_revision",
        "invalidated_at",
    }
    if set(value) != required:
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name} has invalid fields.", 409)
    upstream_artifact_ids = value["upstream_artifact_ids"]
    caused_by_step_ids = value["caused_by_step_ids"]
    caused_by_group_ids = value["caused_by_group_ids"]
    caused_by_state_revision = value["caused_by_state_revision"]
    invalidated_at = value["invalidated_at"]
    if not isinstance(upstream_artifact_ids, list) or not upstream_artifact_ids or any(not isinstance(item, str) or not item for item in upstream_artifact_ids):
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name}.upstream_artifact_ids must be a non-empty string list.", 409)
    if not isinstance(caused_by_step_ids, list) or not caused_by_step_ids or any(not isinstance(item, str) or not item for item in caused_by_step_ids):
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name}.caused_by_step_ids must be a non-empty string list.", 409)
    if not isinstance(caused_by_group_ids, list) or not caused_by_group_ids or any(not isinstance(item, str) or not item.startswith('grp_') for item in caused_by_group_ids):
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name}.caused_by_group_ids must be a non-empty group-id list.", 409)
    if not isinstance(caused_by_state_revision, int) or caused_by_state_revision < 0:
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name}.caused_by_state_revision must be a non-negative integer.", 409)
    _ensure_iso_timestamp(invalidated_at, f"{field_name}.invalidated_at")
    return {
        "upstream_artifact_ids": list(upstream_artifact_ids),
        "caused_by_step_ids": list(caused_by_step_ids),
        "caused_by_group_ids": list(caused_by_group_ids),
        "caused_by_state_revision": caused_by_state_revision,
        "invalidated_at": invalidated_at,
    }


def validate_workflow_state_v2(
    payload: Any,
    *,
    binding: dict[str, Any],
    definition: dict[str, Any],
    project_dir: Path,
    require_persisted_targets: bool = True,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.json must be a JSON object.", 409)
    required = {
        "schema_version",
        "workflow_id",
        "workflow_version",
        "workflow_definition_sha256",
        "state_revision",
        "step_states",
        "artifact_heads",
        "counters",
        "created_at",
        "updated_at",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state.json is missing fields: {', '.join(missing)}", 409)
    unknown = set(payload) - required
    if unknown:
        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state.json contains unknown fields: {', '.join(sorted(unknown))}", 409)
    if payload["schema_version"] != SUPPORTED_STATE_SCHEMA_VERSION_V2:
        raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "Unsupported workflow_state schema_version for write operations.", 409)
    if payload["workflow_id"] != binding["workflow_id"] or payload["workflow_version"] != binding["workflow_version"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state binding does not match the project workflow binding.", 409)
    digest = _validate_digest(
        payload["workflow_definition_sha256"],
        field_name="workflow_state.workflow_definition_sha256",
        code="WORKFLOW_STATE_INVALID",
    )
    if digest != binding["workflow_definition_sha256"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state definition digest does not match the project binding.", 409)
    if not isinstance(payload["state_revision"], int) or payload["state_revision"] < 0:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.state_revision must be a non-negative integer.", 409)
    _ensure_iso_timestamp(payload["created_at"], "created_at")
    _ensure_iso_timestamp(payload["updated_at"], "updated_at")

    step_ids = {step["step_id"] for step in definition["steps"]}
    step_states = payload["step_states"]
    if not isinstance(step_states, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.step_states must be an object.", 409)
    normalized_step_states: dict[str, Any] = {}
    for step_id, step_state in step_states.items():
        if step_id not in step_ids:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references unknown step_id {step_id}.", 409)
        if not isinstance(step_state, dict):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} must be an object.", 409)
        required_step_fields = {
            "status",
            "candidate_group_id",
            "approved_group_id",
            "candidate_idempotency_sha256",
            "updated_at",
        }
        missing_step = sorted(required_step_fields - set(step_state))
        unknown_step = set(step_state) - required_step_fields
        if missing_step or unknown_step:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} has invalid fields.", 409)
        status = step_state["status"]
        if status not in {"READY", "CANDIDATE", "APPROVED"}:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} has an unsupported v2 status.", 409)
        candidate_group_id = step_state["candidate_group_id"]
        approved_group_id = step_state["approved_group_id"]
        candidate_digest = step_state["candidate_idempotency_sha256"]
        if status == "READY":
            if candidate_group_id is not None or approved_group_id is not None or candidate_digest is not None:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state READY step {step_id} must not retain candidate or approved references.", 409)
            step_digest = None
        elif status == "CANDIDATE":
            if not isinstance(candidate_group_id, str) or not candidate_group_id.startswith("grp_"):
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} is missing a valid candidate_group_id.", 409)
            if approved_group_id is not None:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} must not define approved_group_id while candidate is active.", 409)
            step_digest = _validate_digest(
                candidate_digest,
                field_name=f"workflow_state.step_states.{step_id}.candidate_idempotency_sha256",
                code="WORKFLOW_STATE_INVALID",
            )
        else:
            if candidate_group_id is not None or candidate_digest is not None:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state APPROVED step {step_id} must not retain candidate references.", 409)
            if not isinstance(approved_group_id, str) or not approved_group_id.startswith("grp_"):
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state APPROVED step {step_id} must define a valid approved_group_id.", 409)
            step_digest = None
        _ensure_iso_timestamp(step_state["updated_at"], f"workflow_state.step_states.{step_id}.updated_at")
        normalized_step_states[step_id] = {
            "status": status,
            "candidate_group_id": candidate_group_id,
            "approved_group_id": approved_group_id,
            "candidate_idempotency_sha256": step_digest,
            "updated_at": step_state["updated_at"],
        }

    artifact_map = {artifact["artifact_id"]: artifact for artifact in definition["artifacts"]}
    artifact_heads = payload["artifact_heads"]
    if not isinstance(artifact_heads, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.artifact_heads must be an object.", 409)
    normalized_heads: dict[str, Any] = {}
    lowered_ids: set[str] = set()
    for artifact_id, head in artifact_heads.items():
        if artifact_id not in artifact_map:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references unknown artifact_id {artifact_id}.", 409)
        lowered = artifact_id.lower()
        if lowered in lowered_ids:
            raise _error("WORKFLOW_STATE_INVALID", "workflow_state contains a case-insensitive artifact collision.", 409)
        lowered_ids.add(lowered)
        if not isinstance(head, dict):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state artifact head for {artifact_id} must be an object.", 409)
        required_head_fields = {"candidate_revision_id", "approved_revision_id"}
        if set(head) != required_head_fields:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state artifact head for {artifact_id} has invalid fields.", 409)
        candidate_revision_id = head["candidate_revision_id"]
        if candidate_revision_id is not None and (not isinstance(candidate_revision_id, str) or not candidate_revision_id.startswith("rev_")):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state artifact head for {artifact_id} has an invalid candidate revision id.", 409)
        approved_revision_id = head["approved_revision_id"]
        if approved_revision_id is not None and (not isinstance(approved_revision_id, str) or not approved_revision_id.startswith("rev_")):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state artifact head for {artifact_id} has an invalid approved revision id.", 409)
        normalized_heads[artifact_id] = {
            "candidate_revision_id": candidate_revision_id,
            "approved_revision_id": approved_revision_id,
        }

    counters = payload["counters"]
    if not isinstance(counters, dict) or set(counters) != {"next_group_number", "next_revision_number_by_artifact"}:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.counters is malformed.", 409)
    if not isinstance(counters["next_group_number"], int) or counters["next_group_number"] < 1:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.counters.next_group_number must be a positive integer.", 409)
    next_revision_number_by_artifact = counters["next_revision_number_by_artifact"]
    if not isinstance(next_revision_number_by_artifact, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.counters.next_revision_number_by_artifact must be an object.", 409)
    normalized_revision_counters: dict[str, int] = {}
    generated_or_final = {artifact["artifact_id"] for artifact in definition["artifacts"] if artifact["artifact_role"] in {"GENERATED", "FINAL"}}
    if set(next_revision_number_by_artifact) != generated_or_final:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state revision counters must exist for every generated/final artifact.", 409)
    for artifact_id, number in next_revision_number_by_artifact.items():
        if not isinstance(number, int) or number < 1:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision counter for {artifact_id} must be a positive integer.", 409)
        normalized_revision_counters[artifact_id] = number

    revision_group_by_artifact_head: dict[tuple[str, str], str] = {}
    for artifact_id, head in normalized_heads.items():
        for head_field in ("candidate_revision_id", "approved_revision_id"):
            revision_id = head[head_field]
            if revision_id is None:
                continue
            revision_dir = workflow_write_paths(project_dir).artifacts_dir / artifact_id / revision_id
            if not revision_dir.exists():
                if not require_persisted_targets:
                    continue
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references missing revision {revision_id}.", 409)
            actual_files = {item.name for item in revision_dir.iterdir()}
            if actual_files != {"content.md", "metadata.json"}:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references an invalid revision directory for {revision_id}.", 409)
            metadata_path = revision_dir / "metadata.json"
            metadata = _load_json_file(metadata_path, code="WORKFLOW_STATE_INVALID", message=f"workflow_state references malformed revision metadata for {revision_id}.")
            _validate_revision_metadata(
                metadata,
                artifact_id=artifact_id,
                revision_id=revision_id,
                group_id=metadata.get("revision_group_id"),
                binding=binding,
            )
            revision_group_by_artifact_head[(artifact_id, revision_id)] = metadata["revision_group_id"]

    candidate_group_dir_map: dict[str, dict[str, Any]] = {}
    approved_group_dir_map: dict[str, dict[str, Any]] = {}
    step_output_map = {step["step_id"]: set(step["output_artifact_ids"]) for step in definition["steps"]}
    for step_id, step_state in normalized_step_states.items():
        for group_field, target_map in (("candidate_group_id", candidate_group_dir_map), ("approved_group_id", approved_group_dir_map)):
            group_id = step_state[group_field]
            if group_id is None:
                continue
            group_dir = _candidate_group_dir(workflow_write_paths(project_dir), group_id)
            metadata_path = group_dir / "metadata.json"
            if not metadata_path.exists():
                if not require_persisted_targets:
                    continue
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references missing candidate group {group_id}.", 409)
            actual_group_files = {item.name for item in group_dir.iterdir()}
            if actual_group_files != {"metadata.json"}:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references an invalid candidate group directory for {group_id}.", 409)
            group_payload = _load_json_file(metadata_path, code="WORKFLOW_STATE_INVALID", message=f"workflow_state references malformed candidate group metadata for {group_id}.")
            artifact_revision_ids = _validate_group_metadata_for_step(
                group_payload,
                group_id=group_id,
                step_id=step_id,
                binding=binding,
                definition=definition,
            )
            if set(artifact_revision_ids) != step_output_map[step_id]:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state candidate group {group_id} does not match the workflow step output contract.", 409)
            target_map[group_id] = artifact_revision_ids

    if require_persisted_targets:
        candidate_artifacts = {
            artifact_id
            for artifact_revision_ids in candidate_group_dir_map.values()
            for artifact_id in artifact_revision_ids
        }
        approved_artifacts = {
            artifact_id
            for artifact_revision_ids in approved_group_dir_map.values()
            for artifact_id in artifact_revision_ids
        }
        candidate_head_artifacts = {artifact_id for artifact_id, head in normalized_heads.items() if head["candidate_revision_id"] is not None}
        approved_head_artifacts = {artifact_id for artifact_id, head in normalized_heads.items() if head["approved_revision_id"] is not None}
        if candidate_head_artifacts != candidate_artifacts:
            raise _error("WORKFLOW_STATE_INVALID", "workflow_state candidate heads do not match the candidate group artifact set.", 409)
        if approved_head_artifacts != approved_artifacts:
            raise _error("WORKFLOW_STATE_INVALID", "workflow_state approved heads do not match the approved group artifact set.", 409)
        for artifact_id, head in normalized_heads.items():
            if head["candidate_revision_id"] is not None:
                matching_groups = [
                    group_id
                    for group_id, mapping in candidate_group_dir_map.items()
                    if mapping.get(artifact_id) == head["candidate_revision_id"]
                ]
                if len(matching_groups) != 1:
                    raise _error("WORKFLOW_STATE_INVALID", f"workflow_state candidate head for {artifact_id} does not match a unique candidate group revision.", 409)
            if head["approved_revision_id"] is not None:
                matching_groups = [
                    group_id
                    for group_id, mapping in approved_group_dir_map.items()
                    if mapping.get(artifact_id) == head["approved_revision_id"]
                ]
                if len(matching_groups) != 1:
                    raise _error("WORKFLOW_STATE_INVALID", f"workflow_state approved head for {artifact_id} does not match a unique approved group revision.", 409)

    max_group_number = 0
    group_ids_for_counter = (
        [*candidate_group_dir_map.keys(), *approved_group_dir_map.keys()]
        if require_persisted_targets
        else [
            group_id
            for step_state in normalized_step_states.values()
            for group_id in (step_state["candidate_group_id"], step_state["approved_group_id"])
            if group_id is not None
        ]
    )
    for group_id in group_ids_for_counter:
        try:
            max_group_number = max(max_group_number, int(group_id.split("_", 1)[1]))
        except Exception as exc:
            raise _error("WORKFLOW_STATE_INVALID", "workflow_state candidate group id is malformed.", 409) from exc
    if counters["next_group_number"] <= max_group_number:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state next_group_number must be greater than all allocated group ids.", 409)
    for artifact_id, number in normalized_revision_counters.items():
        max_revision_number = 0
        if require_persisted_targets:
            revision_dirs = workflow_write_paths(project_dir).artifacts_dir / artifact_id
            if revision_dirs.exists():
                for child in revision_dirs.iterdir():
                    if not child.is_dir():
                        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision storage for {artifact_id} is invalid.", 409)
                    try:
                        max_revision_number = max(max_revision_number, int(child.name.split("_", 1)[1]))
                    except Exception as exc:
                        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision id for {artifact_id} is malformed.", 409) from exc
        else:
            head = normalized_heads.get(
                artifact_id,
                {"candidate_revision_id": None, "approved_revision_id": None},
            )
            for revision_id in (
                head["candidate_revision_id"],
                head["approved_revision_id"],
            ):
                if revision_id is None:
                    continue
                try:
                    max_revision_number = max(max_revision_number, int(revision_id.split("_", 1)[1]))
                except Exception as exc:
                    raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision id for {artifact_id} is malformed.", 409) from exc
        if number <= max_revision_number:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision counter for {artifact_id} must be greater than all allocated revision ids.", 409)

    return {
        "schema_version": SUPPORTED_STATE_SCHEMA_VERSION_V2,
        "workflow_id": binding["workflow_id"],
        "workflow_version": binding["workflow_version"],
        "workflow_definition_sha256": binding["workflow_definition_sha256"],
        "state_revision": payload["state_revision"],
        "step_states": normalized_step_states,
        "artifact_heads": normalized_heads,
        "counters": {
            "next_group_number": counters["next_group_number"],
            "next_revision_number_by_artifact": normalized_revision_counters,
        },
        "created_at": payload["created_at"],
        "updated_at": payload["updated_at"],
    }


def validate_workflow_state_v3(
    payload: Any,
    *,
    binding: dict[str, Any],
    definition: dict[str, Any],
    project_dir: Path,
    require_persisted_targets: bool = True,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.json must be a JSON object.", 409)
    required = {
        "schema_version",
        "workflow_id",
        "workflow_version",
        "workflow_definition_sha256",
        "state_revision",
        "step_states",
        "artifact_heads",
        "counters",
        "created_at",
        "updated_at",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state.json is missing fields: {', '.join(missing)}", 409)
    unknown = set(payload) - required
    if unknown:
        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state.json contains unknown fields: {', '.join(sorted(unknown))}", 409)
    if payload["schema_version"] != SUPPORTED_STATE_SCHEMA_VERSION:
        raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "Unsupported workflow_state schema_version for write operations.", 409)
    if payload["workflow_id"] != binding["workflow_id"] or payload["workflow_version"] != binding["workflow_version"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state binding does not match the project workflow binding.", 409)
    digest = _validate_digest(
        payload["workflow_definition_sha256"],
        field_name="workflow_state.workflow_definition_sha256",
        code="WORKFLOW_STATE_INVALID",
    )
    if digest != binding["workflow_definition_sha256"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state definition digest does not match the project binding.", 409)
    if not isinstance(payload["state_revision"], int) or payload["state_revision"] < 0:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.state_revision must be a non-negative integer.", 409)
    _ensure_iso_timestamp(payload["created_at"], "created_at")
    _ensure_iso_timestamp(payload["updated_at"], "updated_at")

    step_ids = {step["step_id"] for step in definition["steps"]}
    step_states = payload["step_states"]
    if not isinstance(step_states, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.step_states must be an object.", 409)
    normalized_step_states: dict[str, Any] = {}
    for step_id, step_state in step_states.items():
        if step_id not in step_ids:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references unknown step_id {step_id}.", 409)
        if not isinstance(step_state, dict):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} must be an object.", 409)
        required_step_fields = {
            "status",
            "candidate_group_id",
            "approved_group_id",
            "candidate_idempotency_sha256",
            "stale_reason",
            "invalidated_candidate_group_id",
            "updated_at",
        }
        missing_step = sorted(required_step_fields - set(step_state))
        unknown_step = set(step_state) - required_step_fields
        if missing_step or unknown_step:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} has invalid fields.", 409)
        status = step_state["status"]
        if status not in {"READY", "CANDIDATE", "APPROVED"}:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} has an unsupported v3 status.", 409)
        candidate_group_id = step_state["candidate_group_id"]
        approved_group_id = step_state["approved_group_id"]
        candidate_digest = step_state["candidate_idempotency_sha256"]
        invalidated_candidate_group_id = step_state["invalidated_candidate_group_id"]
        if invalidated_candidate_group_id is not None and (not isinstance(invalidated_candidate_group_id, str) or not invalidated_candidate_group_id.startswith("grp_")):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} has an invalid invalidated_candidate_group_id.", 409)
        stale_reason = _validate_stale_reason(step_state["stale_reason"], field_name=f"workflow_state.step_states.{step_id}.stale_reason")
        if status == "READY":
            if candidate_group_id is not None or approved_group_id is not None or candidate_digest is not None:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state READY step {step_id} must not retain candidate or approved references.", 409)
            if stale_reason is not None:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state READY step {step_id} must not define stale_reason.", 409)
            step_digest = None
        elif status == "CANDIDATE":
            if not isinstance(candidate_group_id, str) or not candidate_group_id.startswith("grp_"):
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} is missing a valid candidate_group_id.", 409)
            if approved_group_id is not None:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state CANDIDATE step {step_id} must not define approved_group_id.", 409)
            if stale_reason is not None:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state CANDIDATE step {step_id} must not define stale_reason.", 409)
            step_digest = _validate_digest(
                candidate_digest,
                field_name=f"workflow_state.step_states.{step_id}.candidate_idempotency_sha256",
                code="WORKFLOW_STATE_INVALID",
            )
        else:
            if not isinstance(approved_group_id, str) or not approved_group_id.startswith("grp_"):
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state APPROVED step {step_id} must define a valid approved_group_id.", 409)
            if candidate_group_id is None:
                if candidate_digest is not None:
                    raise _error("WORKFLOW_STATE_INVALID", f"workflow_state APPROVED step {step_id} must not retain candidate digest without a candidate group.", 409)
                step_digest = None
            else:
                if not isinstance(candidate_group_id, str) or not candidate_group_id.startswith("grp_"):
                    raise _error("WORKFLOW_STATE_INVALID", f"workflow_state APPROVED step {step_id} candidate_group_id is invalid.", 409)
                step_digest = _validate_digest(
                    candidate_digest,
                    field_name=f"workflow_state.step_states.{step_id}.candidate_idempotency_sha256",
                    code="WORKFLOW_STATE_INVALID",
                )
        _ensure_iso_timestamp(step_state["updated_at"], f"workflow_state.step_states.{step_id}.updated_at")
        normalized_step_states[step_id] = {
            "status": status,
            "candidate_group_id": candidate_group_id,
            "approved_group_id": approved_group_id,
            "candidate_idempotency_sha256": step_digest,
            "stale_reason": stale_reason,
            "invalidated_candidate_group_id": invalidated_candidate_group_id,
            "updated_at": step_state["updated_at"],
        }

    artifact_map = {artifact["artifact_id"]: artifact for artifact in definition["artifacts"]}
    artifact_heads = payload["artifact_heads"]
    if not isinstance(artifact_heads, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.artifact_heads must be an object.", 409)
    normalized_heads: dict[str, Any] = {}
    lowered_ids: set[str] = set()
    for artifact_id, head in artifact_heads.items():
        if artifact_id not in artifact_map:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references unknown artifact_id {artifact_id}.", 409)
        lowered = artifact_id.lower()
        if lowered in lowered_ids:
            raise _error("WORKFLOW_STATE_INVALID", "workflow_state contains a case-insensitive artifact collision.", 409)
        lowered_ids.add(lowered)
        if not isinstance(head, dict):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state artifact head for {artifact_id} must be an object.", 409)
        if set(head) != {"candidate_revision_id", "approved_revision_id"}:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state artifact head for {artifact_id} has invalid fields.", 409)
        candidate_revision_id = head["candidate_revision_id"]
        approved_revision_id = head["approved_revision_id"]
        if candidate_revision_id is not None and (not isinstance(candidate_revision_id, str) or not candidate_revision_id.startswith("rev_")):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state artifact head for {artifact_id} has an invalid candidate revision id.", 409)
        if approved_revision_id is not None and (not isinstance(approved_revision_id, str) or not approved_revision_id.startswith("rev_")):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state artifact head for {artifact_id} has an invalid approved revision id.", 409)
        normalized_heads[artifact_id] = {
            "candidate_revision_id": candidate_revision_id,
            "approved_revision_id": approved_revision_id,
        }

    counters = payload["counters"]
    if not isinstance(counters, dict) or set(counters) != {"next_group_number", "next_revision_number_by_artifact"}:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.counters is malformed.", 409)
    if not isinstance(counters["next_group_number"], int) or counters["next_group_number"] < 1:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.counters.next_group_number must be a positive integer.", 409)
    next_revision_number_by_artifact = counters["next_revision_number_by_artifact"]
    if not isinstance(next_revision_number_by_artifact, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.counters.next_revision_number_by_artifact must be an object.", 409)
    normalized_revision_counters: dict[str, int] = {}
    generated_or_final = {artifact["artifact_id"] for artifact in definition["artifacts"] if artifact["artifact_role"] in {"GENERATED", "FINAL"}}
    if set(next_revision_number_by_artifact) != generated_or_final:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state revision counters must exist for every generated/final artifact.", 409)
    for artifact_id, number in next_revision_number_by_artifact.items():
        if not isinstance(number, int) or number < 1:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision counter for {artifact_id} must be a positive integer.", 409)
        normalized_revision_counters[artifact_id] = number

    revision_group_by_artifact_head: dict[tuple[str, str], str] = {}
    paths = workflow_write_paths(project_dir)
    for artifact_id, head in normalized_heads.items():
        for head_field in ("candidate_revision_id", "approved_revision_id"):
            revision_id = head[head_field]
            if revision_id is None:
                continue
            revision_dir = paths.artifacts_dir / artifact_id / revision_id
            if not revision_dir.exists():
                if not require_persisted_targets:
                    continue
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references missing revision {revision_id}.", 409)
            actual_files = {item.name for item in revision_dir.iterdir()}
            if actual_files != {"content.md", "metadata.json"}:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references an invalid revision directory for {revision_id}.", 409)
            metadata_path = revision_dir / "metadata.json"
            metadata = _load_json_file(metadata_path, code="WORKFLOW_STATE_INVALID", message=f"workflow_state references malformed revision metadata for {revision_id}.")
            _validate_revision_metadata(
                metadata,
                artifact_id=artifact_id,
                revision_id=revision_id,
                group_id=metadata.get("revision_group_id"),
                binding=binding,
            )
            revision_group_by_artifact_head[(artifact_id, revision_id)] = metadata["revision_group_id"]

    candidate_group_dir_map: dict[str, dict[str, Any]] = {}
    approved_group_dir_map: dict[str, dict[str, Any]] = {}
    step_output_map = {step["step_id"]: set(step["output_artifact_ids"]) for step in definition["steps"]}
    for step_id, step_state in normalized_step_states.items():
        for group_field, target_map in (("candidate_group_id", candidate_group_dir_map), ("approved_group_id", approved_group_dir_map)):
            group_id = step_state[group_field]
            if group_id is None:
                continue
            group_dir = _candidate_group_dir(paths, group_id)
            metadata_path = group_dir / "metadata.json"
            if not metadata_path.exists():
                if not require_persisted_targets:
                    continue
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references missing candidate group {group_id}.", 409)
            actual_group_files = {item.name for item in group_dir.iterdir()}
            if actual_group_files != {"metadata.json"}:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references an invalid candidate group directory for {group_id}.", 409)
            group_payload = _load_json_file(metadata_path, code="WORKFLOW_STATE_INVALID", message=f"workflow_state references malformed candidate group metadata for {group_id}.")
            artifact_revision_ids = _validate_group_metadata_for_step(
                group_payload,
                group_id=group_id,
                step_id=step_id,
                binding=binding,
                definition=definition,
            )
            if set(artifact_revision_ids) != step_output_map[step_id]:
                raise _error("WORKFLOW_STATE_INVALID", f"workflow_state candidate group {group_id} does not match the workflow step output contract.", 409)
            target_map[group_id] = artifact_revision_ids

    if require_persisted_targets:
        candidate_artifacts = {
            artifact_id
            for artifact_revision_ids in candidate_group_dir_map.values()
            for artifact_id in artifact_revision_ids
        }
        approved_artifacts = {
            artifact_id
            for artifact_revision_ids in approved_group_dir_map.values()
            for artifact_id in artifact_revision_ids
        }
        candidate_head_artifacts = {artifact_id for artifact_id, head in normalized_heads.items() if head["candidate_revision_id"] is not None}
        approved_head_artifacts = {artifact_id for artifact_id, head in normalized_heads.items() if head["approved_revision_id"] is not None}
        if candidate_head_artifacts != candidate_artifacts:
            raise _error("WORKFLOW_STATE_INVALID", "workflow_state candidate heads do not match the candidate group artifact set.", 409)
        if approved_head_artifacts != approved_artifacts:
            raise _error("WORKFLOW_STATE_INVALID", "workflow_state approved heads do not match the approved group artifact set.", 409)
        for artifact_id, head in normalized_heads.items():
            if head["candidate_revision_id"] is not None:
                matching_groups = [
                    group_id
                    for group_id, mapping in candidate_group_dir_map.items()
                    if mapping.get(artifact_id) == head["candidate_revision_id"]
                ]
                if len(matching_groups) != 1:
                    raise _error("WORKFLOW_STATE_INVALID", f"workflow_state candidate head for {artifact_id} does not match a unique candidate group revision.", 409)
            if head["approved_revision_id"] is not None:
                matching_groups = [
                    group_id
                    for group_id, mapping in approved_group_dir_map.items()
                    if mapping.get(artifact_id) == head["approved_revision_id"]
                ]
                if len(matching_groups) != 1:
                    raise _error("WORKFLOW_STATE_INVALID", f"workflow_state approved head for {artifact_id} does not match a unique approved group revision.", 409)

    max_group_number = 0
    group_ids_for_counter = (
        [*candidate_group_dir_map.keys(), *approved_group_dir_map.keys()]
        if require_persisted_targets
        else [
            group_id
            for step_state in normalized_step_states.values()
            for group_id in (step_state["candidate_group_id"], step_state["approved_group_id"], step_state["invalidated_candidate_group_id"])
            if group_id is not None
        ]
    )
    for group_id in group_ids_for_counter:
        try:
            max_group_number = max(max_group_number, int(group_id.split("_", 1)[1]))
        except Exception as exc:
            raise _error("WORKFLOW_STATE_INVALID", "workflow_state candidate group id is malformed.", 409) from exc
    if counters["next_group_number"] <= max_group_number:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state next_group_number must be greater than all allocated group ids.", 409)
    for artifact_id, number in normalized_revision_counters.items():
        max_revision_number = 0
        if require_persisted_targets:
            revision_dirs = paths.artifacts_dir / artifact_id
            if revision_dirs.exists():
                for child in revision_dirs.iterdir():
                    if not child.is_dir():
                        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision storage for {artifact_id} is invalid.", 409)
                    try:
                        max_revision_number = max(max_revision_number, int(child.name.split("_", 1)[1]))
                    except Exception as exc:
                        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision id for {artifact_id} is malformed.", 409) from exc
        else:
            head = normalized_heads.get(
                artifact_id,
                {"candidate_revision_id": None, "approved_revision_id": None},
            )
            for revision_id in (
                head["candidate_revision_id"],
                head["approved_revision_id"],
            ):
                if revision_id is None:
                    continue
                try:
                    max_revision_number = max(max_revision_number, int(revision_id.split("_", 1)[1]))
                except Exception as exc:
                    raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision id for {artifact_id} is malformed.", 409) from exc
        if number <= max_revision_number:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state revision counter for {artifact_id} must be greater than all allocated revision ids.", 409)

    return {
        "schema_version": SUPPORTED_STATE_SCHEMA_VERSION,
        "workflow_id": binding["workflow_id"],
        "workflow_version": binding["workflow_version"],
        "workflow_definition_sha256": binding["workflow_definition_sha256"],
        "state_revision": payload["state_revision"],
        "step_states": normalized_step_states,
        "artifact_heads": normalized_heads,
        "counters": {
            "next_group_number": counters["next_group_number"],
            "next_revision_number_by_artifact": normalized_revision_counters,
        },
        "created_at": payload["created_at"],
        "updated_at": payload["updated_at"],
    }


def validate_workflow_state_v1(
    payload: Any,
    *,
    binding: dict[str, Any],
    definition: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.json must be a JSON object.", 409)
    required = {
        "schema_version",
        "workflow_id",
        "workflow_version",
        "workflow_definition_sha256",
        "current_step_id",
        "current_lifecycle_state",
        "step_states",
        "created_at",
        "updated_at",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state.json is missing fields: {', '.join(missing)}", 409)
    if payload["schema_version"] != 1:
        raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "Unsupported workflow_state schema_version.", 409)
    if payload["workflow_id"] != binding["workflow_id"] or payload["workflow_version"] != binding["workflow_version"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state workflow id/version does not match the project binding.", 409)
    digest = _validate_digest(
        payload["workflow_definition_sha256"],
        field_name="workflow_state.workflow_definition_sha256",
        code="WORKFLOW_STATE_INVALID",
    )
    if digest != binding["workflow_definition_sha256"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state definition digest does not match the project binding.", 409)
    current_lifecycle_state = payload["current_lifecycle_state"]
    if current_lifecycle_state is not None and current_lifecycle_state not in definition["lifecycle_states"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state current_lifecycle_state is not part of the definition.", 409)
    step_ids = [step["step_id"] for step in definition["steps"]]
    if payload["current_step_id"] not in step_ids:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state current_step_id is not present in the definition.", 409)
    step_states = payload["step_states"]
    if not isinstance(step_states, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state step_states must be an object.", 409)
    for step_id, step_state in step_states.items():
        if step_id not in step_ids:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references unknown step_id {step_id}.", 409)
        if not isinstance(step_state, dict):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} must be an object.", 409)
        status = step_state.get("status")
        if status not in {"BLOCKED", "READY", "CANDIDATE", "IN_PROGRESS", "AWAITING_APPROVAL", "APPROVED", "REJECTED", "STALE"}:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} has an unsupported status.", 409)
    _ensure_iso_timestamp(payload["created_at"], "created_at")
    _ensure_iso_timestamp(payload["updated_at"], "updated_at")
    current_step_state = step_states.get(payload["current_step_id"], {})
    current_step_status = current_step_state.get("status")
    if current_step_status not in {"BLOCKED", "READY", "CANDIDATE", "IN_PROGRESS", "AWAITING_APPROVAL", "APPROVED", "REJECTED", "STALE"}:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state current step is missing a supported status.", 409)
    blocking_reason = payload.get("blocking_reason")
    if blocking_reason is not None and not isinstance(blocking_reason, str):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state blocking_reason must be a string or null.", 409)
    current_index = step_ids.index(payload["current_step_id"])
    return {
        "schema_version": 1,
        "current_lifecycle_state": current_lifecycle_state,
        "current_step_id": payload["current_step_id"],
        "current_step_status": current_step_status,
        "next_step_id": step_ids[current_index + 1] if current_index + 1 < len(step_ids) else None,
        "blocking_reason": blocking_reason,
    }


def build_read_state_model(
    *,
    project: dict[str, Any],
    project_dir: Path,
    binding: dict[str, Any],
    definition: dict[str, Any],
    state_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    progress = _derive_workflow_progress(project, project_dir, definition)
    steps = definition["steps"]
    step_states_for_view: dict[str, Any] = {}
    artifact_heads_for_view: dict[str, Any] = {}
    state_revision = 0
    state_persisted = False
    state_source = "SYNTHESIZED"
    schema_version = None

    if state_payload is not None and state_payload.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION:
        validated = validate_workflow_state_v3(state_payload, binding=binding, definition=definition, project_dir=project_dir)
        schema_version = SUPPORTED_STATE_SCHEMA_VERSION
        state_revision = validated["state_revision"]
        state_persisted = True
        state_source = "FILE"
        step_states_for_view = validated["step_states"]
        artifact_heads_for_view = validated["artifact_heads"]
    elif state_payload is not None and state_payload.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION_V2:
        validated = validate_workflow_state_v2(state_payload, binding=binding, definition=definition, project_dir=project_dir)
        schema_version = SUPPORTED_STATE_SCHEMA_VERSION_V2
        state_revision = validated["state_revision"]
        state_persisted = True
        state_source = "FILE"
        step_states_for_view = validated["step_states"]
        artifact_heads_for_view = validated["artifact_heads"]
    elif state_payload is not None and state_payload.get("schema_version") == 1:
        validated_v1 = validate_workflow_state_v1(state_payload, binding=binding, definition=definition)
        schema_version = 1
        state_revision = 0
        state_persisted = True
        state_source = "FILE"
        return {
            "initialized": True,
            "state_source": "FILE",
            "schema_version": 1,
            "state_revision": 0,
            "state_persisted": True,
            "current_lifecycle_state": validated_v1["current_lifecycle_state"],
            "current_step_id": validated_v1["current_step_id"],
            "current_step_status": validated_v1["current_step_status"],
            "next_step_id": validated_v1["next_step_id"],
            "blocking_reason": validated_v1["blocking_reason"],
            "step_states": {},
            "artifact_heads": {},
            "available_actions": {
                step["step_id"]: {
                    "save_candidate": step["step_id"] == validated_v1["current_step_id"] and validated_v1["current_step_status"] == "READY",
                    "approve_candidate": False,
                    "reject_candidate": False,
                }
                for step in steps
            },
        }
    elif state_payload is not None:
        raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "Unsupported workflow_state schema_version.", 409)

    current_step_status = progress["base_status"]
    current_step_state = step_states_for_view.get(progress["current_step_id"])
    if current_step_state and current_step_state.get("status") == "CANDIDATE":
        current_step_status = "CANDIDATE"

    step_summaries: dict[str, Any] = {}
    for step in steps:
        step_state = step_states_for_view.get(step["step_id"], {})
        candidate_group_summary = None
        approved_group_summary = None
        if isinstance(step_state, dict) and step_state.get("candidate_group_id"):
            candidate_group_summary = _load_group_summary(workflow_write_paths(project_dir), step_state["candidate_group_id"])
        if isinstance(step_state, dict) and step_state.get("approved_group_id"):
            approved_group_summary = _load_group_summary(workflow_write_paths(project_dir), step_state["approved_group_id"])
        if step_state.get("status") == "APPROVED":
            step_status = "APPROVED"
        elif step_state.get("status") == "CANDIDATE":
            step_status = "CANDIDATE"
        elif step_state.get("status") == "READY":
            step_status = "READY"
        elif progress["current_step_id"] == step["step_id"]:
            step_status = current_step_status
        else:
            all_outputs_ready = all(
                _artifact_output_exists(
                    project_dir,
                    next(artifact for artifact in definition["artifacts"] if artifact["artifact_id"] == artifact_id),
                    binding=binding,
                    definition=definition,
                )
                for artifact_id in step["output_artifact_ids"]
            )
            step_status = "APPROVED" if all_outputs_ready else "BLOCKED"
        step_summaries[step["step_id"]] = {
            "step_id": step["step_id"],
            "status": step_status,
            "candidate_group_id": step_state.get("candidate_group_id") if isinstance(step_state, dict) else None,
            "approved_group_id": step_state.get("approved_group_id") if isinstance(step_state, dict) else None,
            "candidate_group": candidate_group_summary,
            "approved_group": approved_group_summary,
            "candidate_idempotency_sha256": step_state.get("candidate_idempotency_sha256") if isinstance(step_state, dict) else None,
            "stale_reason": step_state.get("stale_reason") if isinstance(step_state, dict) else None,
            "invalidated_candidate_group_id": step_state.get("invalidated_candidate_group_id") if isinstance(step_state, dict) else None,
            "replacement_candidate": bool(
                isinstance(step_state, dict)
                and step_state.get("status") == "APPROVED"
                and step_state.get("candidate_group_id")
            ),
        }

    available_actions: dict[str, Any] = {}
    for step in steps:
        step_id = step["step_id"]
        candidate = step_states_for_view.get(step_id)
        candidate_status = candidate.get("status") if isinstance(candidate, dict) else None
        replacement_save = (
            candidate_status == "APPROVED"
            and candidate.get("candidate_group_id") is None
            and _step_inputs_are_trusted(
                project_dir=project_dir,
                step=step,
                binding=binding,
                definition=definition,
            )
        )
        first_save = (
            progress["current_step_id"] == step_id
            and current_step_status == "READY"
            and not (candidate and candidate.get("status") == "CANDIDATE")
            and not (candidate and candidate.get("status") == "APPROVED")
        )
        save_candidate = first_save or replacement_save
        has_active_candidate = bool(isinstance(candidate, dict) and candidate.get("candidate_group_id"))
        available_actions[step_id] = {
            "save_candidate": bool(save_candidate),
            "approve_candidate": bool(has_active_candidate),
            "reject_candidate": bool(has_active_candidate),
        }

    return {
        "initialized": state_persisted,
        "state_source": state_source,
        "schema_version": schema_version,
        "state_revision": state_revision,
        "state_persisted": state_persisted,
        "current_lifecycle_state": progress["current_lifecycle_state"],
        "current_step_id": progress["current_step_id"],
        "current_step_status": current_step_status,
        "next_step_id": progress["next_step_id"],
        "blocking_reason": progress["blocking_reason"],
        "step_states": step_summaries,
        "artifact_heads": artifact_heads_for_view,
        "available_actions": available_actions,
    }


def load_workflow_state_for_read(
    *,
    project: dict[str, Any],
    project_dir: Path,
    binding: dict[str, Any],
    definition: dict[str, Any],
) -> dict[str, Any]:
    paths = workflow_write_paths(project_dir)
    assert_no_pending_read_transaction(project_dir=project_dir)
    if not paths.workflow_state_json.exists():
        return build_read_state_model(
            project=project,
            project_dir=project_dir,
            binding=binding,
            definition=definition,
            state_payload=None,
        )
    try:
        payload = json.loads(paths.workflow_state_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.json is malformed JSON.", 409) from exc
    return build_read_state_model(
        project=project,
        project_dir=project_dir,
        binding=binding,
        definition=definition,
        state_payload=payload,
    )


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
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    _write_bytes_atomic(path, payload.encode("utf-8"))


def _write_staged_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _canonical_idempotency_sha256(
    *,
    channel_slug: str,
    project_slug: str,
    workflow_id: str,
    workflow_version: str,
    step_id: str,
    bundle_sha256: str,
    raw_output_sha256: str,
    current_approved_group_id: str | None = None,
) -> str:
    payload = {
        "bundle_sha256": bundle_sha256,
        "channel_slug": channel_slug,
        "current_approved_group_id": current_approved_group_id,
        "project_slug": project_slug,
        "raw_output_sha256": raw_output_sha256,
        "step_id": step_id,
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
    }
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def _validate_expected_state_revision(value: Any) -> int:
    if not isinstance(value, int) or value < 0:
        raise _error("INVALID_REQUEST", "expected_state_revision must be a non-negative integer.", 400)
    return value


def _validate_group_id(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("grp_"):
        raise _error("CANDIDATE_NOT_FOUND", "candidate_group_id must be a valid group id.", 400)
    return value


def _validate_output_artifact_storage(output_artifact_ids: list[str]) -> None:
    lowered: set[str] = set()
    for artifact_id in output_artifact_ids:
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise _error("REVISION_STORAGE_INVALID", "Output artifact id is invalid.", 409)
        lowered_id = artifact_id.lower()
        if lowered_id in lowered:
            raise _error("REVISION_STORAGE_INVALID", "Output artifact ids collide on a case-insensitive filesystem.", 409)
        lowered.add(lowered_id)
        if lowered_id in WINDOWS_RESERVED_NAMES:
            raise _error("REVISION_STORAGE_INVALID", f"Output artifact id {artifact_id} is not Windows-safe.", 409)


def _validate_stable_artifact_target_paths(
    *,
    project_dir: Path,
    definition: dict[str, Any],
    artifact_ids: list[str],
) -> dict[str, Path]:
    artifact_map = {artifact["artifact_id"]: artifact for artifact in definition["artifacts"]}
    final_paths: dict[str, Path] = {}
    lowered_paths: set[str] = set()
    for artifact_id in artifact_ids:
        artifact = artifact_map.get(artifact_id)
        if artifact is None:
            raise _error("STABLE_ARTIFACT_PATH_INVALID", f"Artifact {artifact_id} is not part of the workflow definition.", 409)
        pure = _safe_relative_path(artifact["relative_path"], field_name=f"artifacts.{artifact_id}.relative_path")
        _validate_windows_safe_components(pure, code="STABLE_ARTIFACT_PATH_INVALID", field_name=f"artifacts.{artifact_id}.relative_path")
        lowered_path = pure.as_posix().lower()
        if lowered_path in lowered_paths:
            raise _error("STABLE_ARTIFACT_PATH_INVALID", "Stable artifact paths collide on a case-insensitive filesystem.", 409)
        lowered_paths.add(lowered_path)
        final_path = _safe_join(project_dir, pure.as_posix(), field_name=f"artifacts.{artifact_id}.relative_path")
        final_paths[artifact_id] = final_path
    return final_paths


@dataclass(frozen=True)
class LockHandle:
    path: Path
    owner_token: str


def _acquire_lock(lock_path: Path, *, transaction_id: str, operation: str) -> LockHandle:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    created_at = utc_now_iso()
    owner_token = _sha256_text(
        json.dumps(
            {
                "transaction_id": transaction_id,
                "created_at": created_at,
                "process_id": os.getpid(),
                "operation": operation,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    payload = {
        "transaction_id": transaction_id,
        "created_at": created_at,
        "process_id": os.getpid(),
        "operation": operation,
        "owner_token": owner_token,
    }
    encoded = _json_bytes(payload)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, encoded)
            os.fsync(fd)
        finally:
            os.close(fd)
        return LockHandle(lock_path, owner_token)
    except FileExistsError:
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(existing["created_at"])
        except Exception as exc:
            raise _error("PROJECT_WORKFLOW_LOCK_STALE", "The project workflow lock is stale or unreadable.", 409) from exc
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise _error("PROJECT_WORKFLOW_LOCK_STALE", "The project workflow lock is stale or unreadable.", 409)
        if datetime.now(timezone.utc) - created_at >= LOCK_STALE_AFTER:
            raise _error("PROJECT_WORKFLOW_LOCK_STALE", "The project workflow lock is stale and requires manual cleanup.", 409)
        raise _error("PROJECT_WORKFLOW_BUSY", "Another workflow save is already in progress for this project.", 409)


def _release_lock(handle: LockHandle | None) -> None:
    if handle is None:
        return
    try:
        if not handle.path.exists():
            return
        payload = json.loads(handle.path.read_text(encoding="utf-8"))
        if payload.get("owner_token") != handle.owner_token:
            return
        handle.path.unlink(missing_ok=True)
    except Exception:
        pass


def _expected_relative_files_for_target(target: dict[str, Any]) -> set[str]:
    relative_path = PurePosixPath(target["relative_path"])
    if target["kind"] == "ARTIFACT_REVISION_CONTENT":
        return {"content.md", "metadata.json"}
    if target["kind"] == "ARTIFACT_REVISION_METADATA":
        return {"content.md", "metadata.json"}
    if target["kind"] == "REVISION_GROUP_METADATA":
        return {"metadata.json"}
    if target["kind"] == "DECISION_RECORD":
        return {relative_path.name}
    if target["kind"] == "STABLE_ARTIFACT":
        return {relative_path.name}
    raise _error("WORKFLOW_RECOVERY_REQUIRED", "Transaction manifest target kind is unsupported.", 409)


def _validate_immutable_target_directory(final_path: Path, target: dict[str, Any]) -> None:
    if target["kind"] not in {"ARTIFACT_REVISION_CONTENT", "ARTIFACT_REVISION_METADATA", "REVISION_GROUP_METADATA"}:
        return
    target_dir = final_path.parent
    if not target_dir.exists():
        return
    if not target_dir.is_dir():
        raise _error("WORKFLOW_RECOVERY_REQUIRED", "Immutable workflow target directory is invalid.", 409)
    expected = _expected_relative_files_for_target(target)
    actual = {child.name for child in target_dir.iterdir()}
    if actual != expected:
        raise _error("WORKFLOW_RECOVERY_REQUIRED", "Immutable workflow target directory contains unexpected files.", 409)


def _load_json_file(path: Path, *, code: str, message: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _error(code, message, 409) from exc
    if not isinstance(payload, dict):
        raise _error(code, message, 409)
    return payload


def _validate_group_metadata_for_step(
    group_payload: dict[str, Any],
    *,
    group_id: str,
    step_id: str,
    binding: dict[str, Any],
    definition: dict[str, Any],
) -> dict[str, str]:
    if group_payload.get("schema_version") != SUPPORTED_GROUP_METADATA_SCHEMA_VERSION:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group metadata schema is unsupported.", 409)
    if group_payload.get("revision_group_id") != group_id:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group id is inconsistent.", 409)
    if group_payload.get("step_id") != step_id:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group step does not match workflow state.", 409)
    if group_payload.get("workflow_id") != binding["workflow_id"] or group_payload.get("workflow_version") != binding["workflow_version"]:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group binding does not match the project binding.", 409)
    if group_payload.get("workflow_definition_sha256") != binding["workflow_definition_sha256"]:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group definition digest is inconsistent.", 409)
    artifact_revision_ids = group_payload.get("artifact_revision_ids")
    if not isinstance(artifact_revision_ids, dict) or not artifact_revision_ids:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group artifact map is invalid.", 409)
    step = next(item for item in definition["steps"] if item["step_id"] == step_id)
    if set(artifact_revision_ids) != set(step["output_artifact_ids"]):
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group artifacts do not match the workflow step output contract.", 409)
    return artifact_revision_ids


def _validate_decision_record(
    payload: dict[str, Any],
    *,
    group_id: str,
    step_id: str,
    action: str | None = None,
    binding: dict[str, Any],
    definition: dict[str, Any],
) -> dict[str, Any]:
    required = {
        "schema_version",
        "decision_id",
        "revision_group_id",
        "step_id",
        "action",
        "workflow_id",
        "workflow_version",
        "workflow_definition_sha256",
        "artifact_revision_ids",
        "base_state_revision",
        "target_state_revision",
        "decided_at",
        "decided_by",
    }
    allowed = set(required) | {"replaces_approved_group_id"}
    if required - set(payload) or set(payload) - allowed:
        raise _error("WORKFLOW_STATE_INVALID", "Decision record fields are invalid.", 409)
    if payload["schema_version"] != 1:
        raise _error("WORKFLOW_STATE_INVALID", "Decision record schema_version is unsupported.", 409)
    if payload["decision_id"] != f"decision_{group_id}":
        raise _error("WORKFLOW_STATE_INVALID", "Decision record id is inconsistent.", 409)
    if payload["revision_group_id"] != group_id or payload["step_id"] != step_id:
        raise _error("WORKFLOW_STATE_INVALID", "Decision record does not match the workflow step candidate group.", 409)
    if payload["action"] not in {"APPROVE", "REJECT"}:
        raise _error("WORKFLOW_STATE_INVALID", "Decision record action is unsupported.", 409)
    replaces_approved_group_id = payload.get("replaces_approved_group_id")
    if replaces_approved_group_id is not None and (not isinstance(replaces_approved_group_id, str) or not replaces_approved_group_id.startswith("grp_")):
        raise _error("WORKFLOW_STATE_INVALID", "Decision record replacement group is invalid.", 409)
    if action is not None and payload["action"] != action:
        raise _error("CANDIDATE_DECISION_CONFLICT", "The candidate group already has the opposite final decision.", 409)
    if payload["workflow_id"] != binding["workflow_id"] or payload["workflow_version"] != binding["workflow_version"]:
        raise _error("WORKFLOW_STATE_INVALID", "Decision record workflow binding does not match the project binding.", 409)
    if payload["workflow_definition_sha256"] != binding["workflow_definition_sha256"]:
        raise _error("WORKFLOW_STATE_INVALID", "Decision record workflow digest does not match the project binding.", 409)
    if not isinstance(payload["artifact_revision_ids"], dict) or not payload["artifact_revision_ids"]:
        raise _error("WORKFLOW_STATE_INVALID", "Decision record artifact revision map is invalid.", 409)
    expected_artifacts = next(step for step in definition["steps"] if step["step_id"] == step_id)["output_artifact_ids"]
    if set(payload["artifact_revision_ids"]) != set(expected_artifacts):
        raise _error("WORKFLOW_STATE_INVALID", "Decision record artifact map does not match the workflow step output contract.", 409)
    if not isinstance(payload["base_state_revision"], int) or payload["base_state_revision"] < 0:
        raise _error("WORKFLOW_STATE_INVALID", "Decision record base_state_revision is invalid.", 409)
    if not isinstance(payload["target_state_revision"], int) or payload["target_state_revision"] < payload["base_state_revision"]:
        raise _error("WORKFLOW_STATE_INVALID", "Decision record target_state_revision is invalid.", 409)
    _ensure_iso_timestamp(payload["decided_at"], "decision_record.decided_at")
    if not isinstance(payload["decided_by"], str) or not payload["decided_by"].strip():
        raise _error("WORKFLOW_STATE_INVALID", "Decision record decided_by is required.", 409)
    return payload


def _validate_revision_metadata(
    metadata: dict[str, Any],
    *,
    artifact_id: str,
    revision_id: str,
    group_id: str,
    binding: dict[str, Any],
) -> None:
    if metadata.get("schema_version") != SUPPORTED_REVISION_METADATA_SCHEMA_VERSION:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate revision metadata schema is unsupported.", 409)
    if metadata.get("artifact_id") != artifact_id or metadata.get("revision_id") != revision_id:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate revision metadata is inconsistent.", 409)
    if metadata.get("revision_group_id") != group_id:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate revision group reference is inconsistent.", 409)
    if metadata.get("workflow_id") != binding["workflow_id"] or metadata.get("workflow_version") != binding["workflow_version"]:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate revision binding does not match the project binding.", 409)
    if metadata.get("workflow_definition_sha256") != binding["workflow_definition_sha256"]:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate revision definition digest is inconsistent.", 409)
    if metadata.get("created_status") != "CANDIDATE":
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate revision status is unsupported in Phase 7C2C1.", 409)


def _published_target_state(
    *,
    paths: WorkflowWritePaths,
    project_dir: Path,
    txn_dir: Path,
    target: dict[str, Any],
) -> str:
    final_path = _transaction_target_final_path(paths=paths, project_dir=project_dir, target=target)
    staged_path = txn_dir / "staged" / PurePosixPath(target["relative_path"])
    expected_hash = target.get("target_sha256") or target["sha256"]
    previous_hash = target.get("previous_sha256")
    if final_path.exists():
        _validate_immutable_target_directory(final_path, target)
        final_hash = _sha256_bytes(final_path.read_bytes())
        if final_hash == expected_hash:
            return "FINAL"
        if previous_hash is not None and final_hash == previous_hash:
            return "PREVIOUS_FINAL"
        if final_hash != expected_hash:
            raise _error("WORKFLOW_RECOVERY_REQUIRED", "Published workflow transaction target hash mismatch.", 409)
    if staged_path.exists():
        if _sha256_bytes(staged_path.read_bytes()) != expected_hash:
            raise _error("WORKFLOW_RECOVERY_REQUIRED", "Staged workflow transaction target hash mismatch.", 409)
        return "STAGED"
    return "MISSING"


def classify_transaction_state(
    *,
    paths: WorkflowWritePaths,
    txn_dir: Path,
    binding: dict[str, Any],
    definition: dict[str, Any],
    project_dir: Path,
) -> str:
    manifest_path = txn_dir / "manifest.json"
    if not manifest_path.exists():
        staged_root = txn_dir / "staged"
        if staged_root.exists() or (txn_dir / "next_workflow_state.json").exists():
            return "STAGING_INCOMPLETE"
        return "AMBIGUOUS"
    manifest = _validate_transaction_manifest(
        _load_json_file(manifest_path, code="WORKFLOW_RECOVERY_REQUIRED", message="Transaction manifest is malformed."),
        paths=paths,
        project_dir=project_dir,
    )
    next_state_path = txn_dir / "next_workflow_state.json"
    if not next_state_path.exists():
        return "STAGING_INCOMPLETE"
    next_state_bytes = next_state_path.read_bytes()
    if _sha256_bytes(next_state_bytes) != manifest["next_state_sha256"]:
        raise _error("WORKFLOW_RECOVERY_REQUIRED", "Staged workflow state hash mismatch during recovery.", 409)
    next_state_payload = json.loads(next_state_bytes.decode("utf-8"))
    if next_state_payload.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION:
        validate_workflow_state_v3(
            next_state_payload,
            binding=binding,
            definition=definition,
            project_dir=project_dir,
            require_persisted_targets=False,
        )
    else:
        validate_workflow_state_v2(
            next_state_payload,
            binding=binding,
            definition=definition,
            project_dir=project_dir,
            require_persisted_targets=False,
        )
    target_states = [
        _published_target_state(paths=paths, project_dir=project_dir, txn_dir=txn_dir, target=target)
        for target in manifest["targets"]
    ]
    state_payload = _load_state_payload_for_write(paths)
    current_revision = 0
    if state_payload is not None and state_payload.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION:
        current_revision = validate_workflow_state_v3(
            state_payload,
            binding=binding,
            definition=definition,
            project_dir=project_dir,
            require_persisted_targets=False,
        )["state_revision"]
    elif state_payload is not None and state_payload.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION_V2:
        current_revision = validate_workflow_state_v2(
            state_payload,
            binding=binding,
            definition=definition,
            project_dir=project_dir,
            require_persisted_targets=False,
        )["state_revision"]
    elif state_payload is not None and state_payload.get("schema_version") == 1:
        current_revision = 0
    if all(item == "STAGED" for item in target_states):
        return "STAGED_COMPLETE"
    if "MISSING" in target_states and "FINAL" not in target_states and "PREVIOUS_FINAL" not in target_states:
        return "STAGING_INCOMPLETE"
    if ("FINAL" in target_states or "PREVIOUS_FINAL" in target_states) and "MISSING" in target_states:
        return "PARTIALLY_PUBLISHED"
    if all(item == "FINAL" for item in target_states):
        if current_revision >= manifest["target_state_revision"]:
            return "STATE_COMMITTED_CLEANUP_PENDING"
        return "OBJECTS_PUBLISHED_STATE_PENDING"
    if all(item in {"FINAL", "PREVIOUS_FINAL"} for item in target_states):
        if current_revision >= manifest["target_state_revision"]:
            return "STATE_COMMITTED_CLEANUP_PENDING"
        return "OBJECTS_PUBLISHED_STATE_PENDING"
    if any(item in {"FINAL", "PREVIOUS_FINAL"} for item in target_states) and any(item == "STAGED" for item in target_states):
        return "PARTIALLY_PUBLISHED"
    return "AMBIGUOUS"


def assert_no_pending_read_transaction(
    *,
    project_dir: Path,
) -> None:
    paths = workflow_write_paths(project_dir)
    if not paths.transactions_dir.exists():
        return
    pending = [item for item in sorted(paths.transactions_dir.glob("txn_*")) if item.is_dir()]
    if pending:
        raise _error("WORKFLOW_RECOVERY_REQUIRED", "An incomplete workflow transaction requires review before continuing.", 409)


def _candidate_group_dir(paths: WorkflowWritePaths, group_id: str) -> Path:
    return paths.groups_dir / group_id


def _candidate_revision_dir(paths: WorkflowWritePaths, artifact_id: str, revision_id: str) -> Path:
    return paths.artifacts_dir / artifact_id / revision_id


def _load_group_summary(paths: WorkflowWritePaths, group_id: str) -> dict[str, Any]:
    metadata_path = _candidate_group_dir(paths, group_id) / "metadata.json"
    if not metadata_path.exists():
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group metadata is missing.", 409)
    group_dir = metadata_path.parent
    if {child.name for child in group_dir.iterdir()} != {"metadata.json"}:
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group directory is invalid.", 409)
    payload = _load_json_file(metadata_path, code="WORKFLOW_STATE_INVALID", message="The saved candidate group metadata is malformed.")
    artifacts = []
    artifact_revision_ids = payload.get("artifact_revision_ids", {})
    if not isinstance(artifact_revision_ids, dict):
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group metadata is malformed.", 409)
    for artifact_id, revision_id in artifact_revision_ids.items():
        metadata_path = _candidate_revision_dir(paths, artifact_id, revision_id) / "metadata.json"
        if not metadata_path.exists():
            raise _error("WORKFLOW_STATE_INVALID", "The saved candidate revision metadata is missing.", 409)
        revision_dir = metadata_path.parent
        if {child.name for child in revision_dir.iterdir()} != {"content.md", "metadata.json"}:
            raise _error("WORKFLOW_STATE_INVALID", "The saved candidate revision directory is invalid.", 409)
        metadata = _load_json_file(metadata_path, code="WORKFLOW_STATE_INVALID", message="The saved candidate revision metadata is malformed.")
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "revision_id": revision_id,
                "content_sha256": metadata["content_sha256"],
                "character_count": metadata["character_count"],
            }
        )
    return {
        "revision_group_id": payload["revision_group_id"],
        "bundle_sha256": payload["bundle_sha256"],
        "raw_output_sha256": payload["raw_output_sha256"],
        "artifacts": artifacts,
    }


def _load_group_artifact_revision_ids(
    paths: WorkflowWritePaths,
    *,
    group_id: str,
    step_id: str,
    binding: dict[str, Any],
    definition: dict[str, Any],
) -> dict[str, str]:
    group_path = _candidate_group_dir(paths, group_id) / "metadata.json"
    if not group_path.exists():
        raise _error("WORKFLOW_STATE_INVALID", "The saved candidate group metadata is missing.", 409)
    group_payload = _load_json_file(group_path, code="WORKFLOW_STATE_INVALID", message="The saved candidate group metadata is malformed.")
    return _validate_group_metadata_for_step(
        group_payload,
        group_id=group_id,
        step_id=step_id,
        binding=binding,
        definition=definition,
    )


def _approved_group_matches_stable_files(
    *,
    paths: WorkflowWritePaths,
    project_dir: Path,
    definition: dict[str, Any],
    binding: dict[str, Any],
    step_id: str,
    approved_group_id: str,
) -> dict[str, str]:
    artifact_revision_ids = _load_group_artifact_revision_ids(
        paths,
        group_id=approved_group_id,
        step_id=step_id,
        binding=binding,
        definition=definition,
    )
    artifacts_by_id = {artifact["artifact_id"]: artifact for artifact in definition["artifacts"]}
    for artifact_id, revision_id in artifact_revision_ids.items():
        artifact = artifacts_by_id[artifact_id]
        revision_dir = _candidate_revision_dir(paths, artifact_id, revision_id)
        metadata_path = revision_dir / "metadata.json"
        content_path = revision_dir / "content.md"
        metadata = _load_json_file(metadata_path, code="WORKFLOW_STATE_INVALID", message="Approved revision metadata is malformed.")
        stable_path = project_dir / PurePosixPath(artifact["relative_path"])
        if not stable_path.exists() or not stable_path.is_file():
            raise _error("STABLE_ARTIFACT_CONFLICT", "Current stable workflow output does not match the approved revision state.", 409)
        stable_bytes = stable_path.read_bytes()
        revision_bytes = content_path.read_bytes()
        if stable_bytes != revision_bytes or metadata.get("content_sha256") != _sha256_bytes(stable_bytes):
            raise _error("STABLE_ARTIFACT_CONFLICT", "Current stable workflow output does not match the approved revision state.", 409)
    return artifact_revision_ids


def _decision_record_path(paths: WorkflowWritePaths, group_id: str) -> Path:
    return paths.decisions_dir / f"{group_id}.json"


def _load_decision_record(
    paths: WorkflowWritePaths,
    *,
    group_id: str,
    step_id: str,
    action: str | None,
    binding: dict[str, Any],
    definition: dict[str, Any],
) -> dict[str, Any] | None:
    decision_path = _decision_record_path(paths, group_id)
    if not decision_path.exists():
        return None
    payload = _load_json_file(decision_path, code="WORKFLOW_STATE_INVALID", message="The saved decision record is malformed.")
    return _validate_decision_record(payload, group_id=group_id, step_id=step_id, action=action, binding=binding, definition=definition)


def _build_candidate_response(
    *,
    channel_slug: str,
    project_slug: str,
    binding: dict[str, Any],
    step_id: str,
    state_revision: int,
    group_summary: dict[str, Any],
    status: str,
    idempotent_replay: bool,
) -> dict[str, Any]:
    return {
        "status": status,
        "idempotent_replay": idempotent_replay,
        "identity": {
            "channel_slug": channel_slug,
            "project_slug": project_slug,
            "workflow_id": binding["workflow_id"],
            "workflow_version": binding["workflow_version"],
            "step_id": step_id,
        },
        "state_revision": state_revision,
        "revision_group": group_summary,
    }


def _build_decision_response(
    *,
    status: str,
    idempotent_replay: bool,
    state_revision: int,
    group_id: str,
    artifacts: list[dict[str, Any]] | None = None,
    replacement: bool | None = None,
    replaces_approved_group_id: str | None = None,
    changed_artifact_ids: list[str] | None = None,
    stale_step_ids: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "idempotent_replay": idempotent_replay,
        "state_revision": state_revision,
        "revision_group_id": group_id,
    }
    if artifacts is not None:
        payload["artifacts"] = artifacts
    if replacement is not None:
        payload["replacement"] = replacement
    if replaces_approved_group_id is not None:
        payload["replaces_approved_group_id"] = replaces_approved_group_id
    if changed_artifact_ids is not None:
        payload["changed_artifact_ids"] = changed_artifact_ids
    if stale_step_ids is not None:
        payload["stale_step_ids"] = stale_step_ids
    return payload


def _build_dependency_maps(definition: dict[str, Any]) -> tuple[dict[str, str], dict[str, list[str]]]:
    artifact_ids = {artifact["artifact_id"] for artifact in definition["artifacts"]}
    producer_by_artifact: dict[str, str] = {}
    consumers_by_artifact: dict[str, list[str]] = {}
    for step in definition["steps"]:
        for artifact_id in step["output_artifact_ids"]:
            if artifact_id not in artifact_ids:
                raise _error("WORKFLOW_DEFINITION_INVALID", "Workflow output references an unknown artifact id.", 409)
            if artifact_id.lower() in {key.lower() for key in producer_by_artifact}:
                raise _error("WORKFLOW_DEFINITION_INVALID", "Workflow output artifact producers are not unique.", 409)
            if artifact_id in producer_by_artifact:
                raise _error("WORKFLOW_DEFINITION_INVALID", "Workflow output artifact producers are not unique.", 409)
            producer_by_artifact[artifact_id] = step["step_id"]
        for artifact_id in step["input_artifact_ids"]:
            if artifact_id not in artifact_ids:
                raise _error("WORKFLOW_DEFINITION_INVALID", "Workflow input references an unknown artifact id.", 409)
            consumers_by_artifact.setdefault(artifact_id, []).append(step["step_id"])

    step_edges: dict[str, set[str]] = {step["step_id"]: set() for step in definition["steps"]}
    for artifact_id, producer_step_id in producer_by_artifact.items():
        for consumer_step_id in consumers_by_artifact.get(artifact_id, []):
            step_edges[producer_step_id].add(consumer_step_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            raise _error("WORKFLOW_DEFINITION_INVALID", "Workflow dependency cycle is not supported.", 409)
        visiting.add(step_id)
        for downstream in step_edges.get(step_id, set()):
            visit(downstream)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in step_edges:
        visit(step_id)
    return producer_by_artifact, consumers_by_artifact


def _clear_candidate_group_from_state(
    *,
    next_state: dict[str, Any],
    definition: dict[str, Any],
    step_id: str,
    invalidated_group_id: str,
) -> None:
    step = next(item for item in definition["steps"] if item["step_id"] == step_id)
    step_state = next_state["step_states"].get(step_id, {})
    for artifact_id in step["output_artifact_ids"]:
        head = next_state["artifact_heads"].get(artifact_id)
        if head is None:
            continue
        if head.get("approved_revision_id") is None:
            next_state["artifact_heads"].pop(artifact_id, None)
        else:
            head["candidate_revision_id"] = None
    step_state["candidate_group_id"] = None
    step_state["candidate_idempotency_sha256"] = None
    step_state["invalidated_candidate_group_id"] = invalidated_group_id


def _propagate_stale_state(
    *,
    next_state: dict[str, Any],
    definition: dict[str, Any],
    source_step_id: str,
    source_group_id: str,
    changed_artifact_ids: list[str],
    target_state_revision: int,
    invalidated_at: str,
) -> list[str]:
    if not changed_artifact_ids:
        return []
    _, consumers_by_artifact = _build_dependency_maps(definition)
    stale_step_ids: list[str] = []
    processed_pairs: set[tuple[str, str]] = set()
    queue: list[tuple[str, str]] = [(artifact_id, source_step_id) for artifact_id in changed_artifact_ids]
    while queue:
        artifact_id, producer_step_id = queue.pop(0)
        for consumer_step_id in consumers_by_artifact.get(artifact_id, []):
            pair = (artifact_id, consumer_step_id)
            if pair in processed_pairs:
                continue
            processed_pairs.add(pair)
            step_state = next_state["step_states"].get(consumer_step_id)
            if not isinstance(step_state, dict):
                continue
            if step_state.get("status") == "APPROVED":
                stale_reason = step_state.get("stale_reason") or {
                    "upstream_artifact_ids": [],
                    "caused_by_step_ids": [],
                    "caused_by_group_ids": [],
                    "caused_by_state_revision": target_state_revision,
                    "invalidated_at": invalidated_at,
                }
                stale_reason["upstream_artifact_ids"] = sorted(set([*stale_reason["upstream_artifact_ids"], artifact_id]))
                stale_reason["caused_by_step_ids"] = sorted(set([*stale_reason["caused_by_step_ids"], producer_step_id]))
                stale_reason["caused_by_group_ids"] = sorted(set([*stale_reason["caused_by_group_ids"], source_group_id]))
                stale_reason["caused_by_state_revision"] = target_state_revision
                stale_reason["invalidated_at"] = invalidated_at
                step_state["stale_reason"] = stale_reason
                if step_state.get("candidate_group_id"):
                    _clear_candidate_group_from_state(
                        next_state=next_state,
                        definition=definition,
                        step_id=consumer_step_id,
                        invalidated_group_id=step_state["candidate_group_id"],
                    )
                if consumer_step_id not in stale_step_ids:
                    stale_step_ids.append(consumer_step_id)
                consumer_step = next(item for item in definition["steps"] if item["step_id"] == consumer_step_id)
                for downstream_artifact_id in consumer_step["output_artifact_ids"]:
                    queue.append((downstream_artifact_id, consumer_step_id))
            elif step_state.get("status") == "CANDIDATE":
                candidate_group_id = step_state.get("candidate_group_id")
                if candidate_group_id:
                    _clear_candidate_group_from_state(
                        next_state=next_state,
                        definition=definition,
                        step_id=consumer_step_id,
                        invalidated_group_id=candidate_group_id,
                    )
                    step_state["status"] = "READY"
                    step_state["approved_group_id"] = None
                    step_state["stale_reason"] = None
                    if consumer_step_id not in stale_step_ids:
                        stale_step_ids.append(consumer_step_id)
    return stale_step_ids


def _load_state_payload_for_write(paths: WorkflowWritePaths) -> dict[str, Any] | None:
    if not paths.workflow_state_json.exists():
        return None
    try:
        payload = json.loads(paths.workflow_state_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.json is malformed JSON.", 409) from exc
    if not isinstance(payload, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.json must be a JSON object.", 409)
    return payload


def _load_state_for_write(
    *,
    paths: WorkflowWritePaths,
    binding: dict[str, Any],
    definition: dict[str, Any],
    project_dir: Path,
) -> tuple[dict[str, Any], int]:
    payload = _load_state_payload_for_write(paths)
    if payload is None:
        return _empty_v2_state(binding, definition), 0
    schema_version = payload.get("schema_version")
    if schema_version == SUPPORTED_STATE_SCHEMA_VERSION:
        validated = validate_workflow_state_v3(payload, binding=binding, definition=definition, project_dir=project_dir)
        return validated, validated["state_revision"]
    if schema_version == SUPPORTED_STATE_SCHEMA_VERSION_V2:
        validated = validate_workflow_state_v2(payload, binding=binding, definition=definition, project_dir=project_dir)
        return validated, validated["state_revision"]
    if schema_version == 1:
        validated_v1 = validate_workflow_state_v1(payload, binding=binding, definition=definition)
        created_at = payload.get("created_at") if isinstance(payload.get("created_at"), str) else utc_now_iso()
        _ensure_iso_timestamp(created_at, "created_at")
        current_step_id = validated_v1["current_step_id"]
        if validated_v1["current_step_status"] != "READY":
            raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "The saved schema-v1 workflow state cannot be converted safely unless the current step is READY.", 409)
        converted = _empty_v2_state(binding, definition, created_at=created_at)
        for artifact_id in converted["counters"]["next_revision_number_by_artifact"]:
            artifact_dir = paths.artifacts_dir / artifact_id
            max_revision_number = 0
            if artifact_dir.exists():
                for child in artifact_dir.iterdir():
                    if not child.is_dir() or not child.name.startswith("rev_"):
                        raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "The saved schema-v1 workflow state has incompatible revision storage.", 409)
                    try:
                        max_revision_number = max(max_revision_number, int(child.name.split("_", 1)[1]))
                    except Exception as exc:
                        raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "The saved schema-v1 workflow state has malformed revision storage.", 409) from exc
            converted["counters"]["next_revision_number_by_artifact"][artifact_id] = max_revision_number + 1
        max_group_number = 0
        if paths.groups_dir.exists():
            for child in paths.groups_dir.iterdir():
                if not child.is_dir() or not child.name.startswith("grp_"):
                    raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "The saved schema-v1 workflow state has incompatible group storage.", 409)
                try:
                    max_group_number = max(max_group_number, int(child.name.split("_", 1)[1]))
                except Exception as exc:
                    raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "The saved schema-v1 workflow state has malformed group storage.", 409) from exc
        converted["counters"]["next_group_number"] = max_group_number + 1
        converted["updated_at"] = payload.get("updated_at", created_at)
        _ensure_iso_timestamp(converted["updated_at"], "updated_at")
        if current_step_id not in {step["step_id"] for step in definition["steps"]}:
            raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "The saved schema-v1 workflow state cannot be converted safely.", 409)
        return converted, 0
    raise _error("WORKFLOW_STATE_VERSION_UNSUPPORTED", "The saved workflow_state version cannot be written safely.", 409)


def _convert_v2_state_to_v3(state_v2: dict[str, Any]) -> dict[str, Any]:
    converted = json.loads(json.dumps(state_v2))
    converted["schema_version"] = SUPPORTED_STATE_SCHEMA_VERSION
    for step_state in converted["step_states"].values():
        step_state["stale_reason"] = None
        step_state["invalidated_candidate_group_id"] = None
    return converted


def _validate_step_writable(
    *,
    project: dict[str, Any],
    project_dir: Path,
    binding: dict[str, Any],
    definition: dict[str, Any],
    step_id: str,
    state_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    state_view = build_read_state_model(
        project=project,
        project_dir=project_dir,
        binding=binding,
        definition=definition,
        state_payload=state_payload,
    )
    if not state_view["available_actions"].get(step_id, {}).get("save_candidate"):
        current_step_state = state_view["step_states"].get(step_id)
        if current_step_state and current_step_state.get("candidate_group_id"):
            raise _error("CANDIDATE_EXISTS", "A candidate already exists for this workflow step.", 409)
        raise _error("WORKFLOW_STEP_NOT_WRITABLE", "The selected workflow step is not writable for candidate save.", 409)
    return state_view


def _load_decidable_step_context(
    *,
    paths: WorkflowWritePaths,
    binding: dict[str, Any],
    definition: dict[str, Any],
    step_id: str,
    state_payload: dict[str, Any] | None,
    state_view: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    step_state = state_view["step_states"].get(step_id)
    if not isinstance(step_state, dict):
        raise _error("WORKFLOW_STEP_NOT_DECIDABLE", "The selected workflow step is not currently decidable.", 409)
    group_id = step_state.get("candidate_group_id")
    if group_id is None and step_state.get("status") == "CANDIDATE":
        group_id = step_state.get("candidate_group_id")
    if group_id is None:
        raise _error("WORKFLOW_STEP_NOT_DECIDABLE", "The selected workflow step is not currently decidable.", 409)
    if not isinstance(group_id, str) or not group_id.startswith("grp_"):
        raise _error("CANDIDATE_NOT_FOUND", "The selected workflow step has no valid candidate group.", 409)
    group_path = _candidate_group_dir(paths, group_id) / "metadata.json"
    if not group_path.exists():
        raise _error("CANDIDATE_NOT_FOUND", "The selected candidate group could not be found.", 409)
    group_payload = _load_json_file(group_path, code="WORKFLOW_STATE_INVALID", message="The candidate group metadata is malformed.")
    artifact_revision_ids = _validate_group_metadata_for_step(
        group_payload,
        group_id=group_id,
        step_id=step_id,
        binding=binding,
        definition=definition,
    )
    for artifact_id, revision_id in artifact_revision_ids.items():
        metadata_path = _candidate_revision_dir(paths, artifact_id, revision_id) / "metadata.json"
        content_path = _candidate_revision_dir(paths, artifact_id, revision_id) / "content.md"
        if not metadata_path.exists() or not content_path.exists():
            raise _error("CANDIDATE_NOT_FOUND", "The selected candidate revision could not be found.", 409)
        metadata = _load_json_file(metadata_path, code="WORKFLOW_STATE_INVALID", message="The candidate revision metadata is malformed.")
        _validate_revision_metadata(
            metadata,
            artifact_id=artifact_id,
            revision_id=revision_id,
            group_id=group_id,
            binding=binding,
        )
        if _sha256_bytes(content_path.read_bytes()) != metadata["content_sha256"]:
            raise _error("WORKFLOW_STATE_INVALID", "The candidate revision content hash does not match its metadata.", 409)
    return step_state, group_payload, artifact_revision_ids


def _maybe_fail(stage: str, fail_stage: str | None) -> None:
    if fail_stage == stage:
        raise _error("WORKFLOW_WRITE_FAILED", f"Injected failure at stage: {stage}", 500)


def _validate_transaction_manifest(
    manifest: dict[str, Any],
    *,
    paths: WorkflowWritePaths,
    project_dir: Path,
) -> dict[str, Any]:
    required = {"schema_version", "transaction_id", "operation", "base_state_revision", "target_state_revision", "revision_group_id", "targets", "next_state_sha256", "created_at"}
    if not isinstance(manifest, dict) or required - set(manifest):
        raise _error("WORKFLOW_RECOVERY_REQUIRED", "Transaction manifest is malformed.", 409)
    if manifest["schema_version"] != SUPPORTED_TRANSACTION_MANIFEST_SCHEMA_VERSION:
        raise _error("WORKFLOW_RECOVERY_REQUIRED", "Transaction manifest version is unsupported.", 409)
    _validate_digest(manifest["next_state_sha256"], field_name="transaction_manifest.next_state_sha256", code="WORKFLOW_RECOVERY_REQUIRED")
    _ensure_iso_timestamp(manifest["created_at"], "transaction_manifest.created_at")
    if not isinstance(manifest["targets"], list) or not manifest["targets"]:
        raise _error("WORKFLOW_RECOVERY_REQUIRED", "Transaction manifest targets are missing.", 409)
    for index, item in enumerate(manifest["targets"]):
        if not isinstance(item, dict):
            raise _error("WORKFLOW_RECOVERY_REQUIRED", "Transaction manifest target is malformed.", 409)
        if not isinstance(item.get("kind"), str):
            raise _error("WORKFLOW_RECOVERY_REQUIRED", "Transaction manifest target kind is missing.", 409)
        relative_path = item.get("relative_path")
        if not isinstance(relative_path, str):
            raise _error("WORKFLOW_RECOVERY_REQUIRED", "Transaction manifest target path is missing.", 409)
        _transaction_target_final_path(paths=paths, project_dir=project_dir, target=item)
        _validate_digest(item.get("sha256"), field_name=f"transaction_manifest.targets[{index}].sha256", code="WORKFLOW_RECOVERY_REQUIRED")
        if item.get("kind") == "STABLE_ARTIFACT":
            if item.get("previous_sha256") is not None:
                _validate_digest(item.get("previous_sha256"), field_name=f"transaction_manifest.targets[{index}].previous_sha256", code="WORKFLOW_RECOVERY_REQUIRED")
            if item.get("target_sha256") is not None:
                _validate_digest(item.get("target_sha256"), field_name=f"transaction_manifest.targets[{index}].target_sha256", code="WORKFLOW_RECOVERY_REQUIRED")
    return manifest


def _transaction_target_final_path(
    *,
    paths: WorkflowWritePaths,
    project_dir: Path,
    target: dict[str, Any],
) -> Path:
    relative_path = target["relative_path"]
    if target.get("kind") == "STABLE_ARTIFACT":
        return _safe_join(project_dir, relative_path, field_name="transaction_manifest.targets[].relative_path")
    return _safe_join(paths.workflow_dir, relative_path, field_name="transaction_manifest.targets[].relative_path")


def _copy_staged_file_to_final(
    staged_path: Path,
    final_path: Path,
    *,
    existing_code: str = "REVISION_ID_CONFLICT",
    expected_existing_sha256: str | None = None,
) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if final_path.exists():
        if expected_existing_sha256 is not None and final_path.is_file() and _sha256_bytes(final_path.read_bytes()) == expected_existing_sha256:
            final_path.unlink()
        else:
            message = "A stable artifact already exists for this workflow output." if existing_code == "STABLE_ARTIFACT_CONFLICT" else "Immutable revision target already exists."
            raise _error(existing_code, message, 409)
    os.replace(staged_path, final_path)


def _recover_transactions(
    *,
    paths: WorkflowWritePaths,
    binding: dict[str, Any],
    definition: dict[str, Any],
    project_dir: Path,
) -> None:
    paths.transactions_dir.mkdir(parents=True, exist_ok=True)
    for txn_dir in sorted(paths.transactions_dir.glob("txn_*")):
        if not txn_dir.is_dir():
            continue
        transaction_state = classify_transaction_state(
            paths=paths,
            txn_dir=txn_dir,
            binding=binding,
            definition=definition,
            project_dir=project_dir,
        )
        if transaction_state in {"AMBIGUOUS", "STAGING_INCOMPLETE"}:
            raise _error("WORKFLOW_RECOVERY_REQUIRED", "An incomplete workflow transaction cannot be recovered safely.", 409)

        manifest = _validate_transaction_manifest(
            _load_json_file(txn_dir / "manifest.json", code="WORKFLOW_RECOVERY_REQUIRED", message="Transaction manifest is malformed."),
            paths=paths,
            project_dir=project_dir,
        )
        state_payload = _load_state_payload_for_write(paths)
        current_revision = 0
        if state_payload is not None:
            schema_version = state_payload.get("schema_version")
            if schema_version == SUPPORTED_STATE_SCHEMA_VERSION:
                current_revision = validate_workflow_state_v3(
                    state_payload,
                    binding=binding,
                    definition=definition,
                    project_dir=project_dir,
                    require_persisted_targets=False,
                )["state_revision"]
            elif schema_version == SUPPORTED_STATE_SCHEMA_VERSION_V2:
                current_revision = validate_workflow_state_v2(
                    state_payload,
                    binding=binding,
                    definition=definition,
                    project_dir=project_dir,
                    require_persisted_targets=False,
                )["state_revision"]
            elif schema_version == 1:
                current_revision = 0
        target_group_id = manifest["revision_group_id"]
        if transaction_state == "STATE_COMMITTED_CLEANUP_PENDING" or current_revision >= manifest["target_state_revision"]:
            group_summary = _load_group_summary(paths, target_group_id)
            if group_summary["revision_group_id"] != target_group_id:
                raise _error("WORKFLOW_RECOVERY_REQUIRED", "Completed workflow transaction cannot be verified safely.", 409)
            shutil.rmtree(txn_dir, ignore_errors=True)
            continue

        next_state_path = txn_dir / "next_workflow_state.json"
        next_state_bytes = next_state_path.read_bytes()
        next_state_payload = json.loads(next_state_bytes.decode("utf-8"))
        if next_state_payload.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION:
            validate_workflow_state_v3(
                next_state_payload,
                binding=binding,
                definition=definition,
                project_dir=project_dir,
                require_persisted_targets=False,
            )
        else:
            validate_workflow_state_v2(
                next_state_payload,
                binding=binding,
                definition=definition,
                project_dir=project_dir,
                require_persisted_targets=False,
            )

        for target in manifest["targets"]:
            final_path = _transaction_target_final_path(paths=paths, project_dir=project_dir, target=target)
            published_state = _published_target_state(paths=paths, project_dir=project_dir, txn_dir=txn_dir, target=target)
            if published_state == "FINAL":
                continue
            staged_path = txn_dir / "staged" / PurePosixPath(target["relative_path"])
            if final_path.exists() and published_state == "PREVIOUS_FINAL":
                final_path.unlink()
            _copy_staged_file_to_final(staged_path, final_path, existing_code="STABLE_ARTIFACT_CONFLICT")

        _write_bytes_atomic(paths.workflow_state_json, next_state_bytes)
        shutil.rmtree(txn_dir, ignore_errors=True)


def save_candidate(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    step_id: str,
    bundle_sha256: Any,
    output_text: Any,
    expected_state_revision: Any,
    *,
    fail_stage: str | None = None,
    publish_log: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    from scripts import channel_output_parser, channel_projects, channel_prompt_bundle, channel_workflow

    provided_bundle_sha256 = _validate_digest(bundle_sha256, field_name="bundle_sha256", code="BUNDLE_IDENTITY_MISMATCH")
    expected_revision = _validate_expected_state_revision(expected_state_revision)
    if not isinstance(output_text, str) or not output_text.strip():
        raise _error("OUTPUT_TEXT_REQUIRED", "Pasted AI output is required.", 400)

    project = channel_projects.load_channel_project(root, channel_slug, project_slug)
    project_dir = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug
    binding = channel_workflow.resolve_project_workflow_binding(root, channel_slug, project)
    definition = channel_workflow.load_workflow_definition(root, binding["workflow_id"], binding["workflow_version"])
    step = next((item for item in definition["steps"] if item["step_id"] == step_id), None)
    if step is None:
        raise _error("WORKFLOW_STEP_NOT_FOUND", "The selected workflow step was not found for this project binding.", 404)
    prompt_set = definition["prompt_set"]
    if prompt_set.get("status") != "AVAILABLE" or not prompt_set.get("bundle_available"):
        raise _error("PROMPT_SET_UNAVAILABLE", "The pinned workflow version does not expose an available prompt set.", 409)
    _validate_output_artifact_storage(list(step["output_artifact_ids"]))

    raw_output_sha256 = _sha256_text(output_text)
    lock_identity_sha = _canonical_idempotency_sha256(
        channel_slug=channel_slug,
        project_slug=project_slug,
        workflow_id=binding["workflow_id"],
        workflow_version=binding["workflow_version"],
        step_id=step_id,
        bundle_sha256=provided_bundle_sha256,
        raw_output_sha256=raw_output_sha256,
    )
    transaction_id = f"txn_{lock_identity_sha[:16].lower()}"
    paths = workflow_write_paths(project_dir)
    lock_handle: LockHandle | None = None
    try:
        lock_handle = _acquire_lock(paths.lock_file, transaction_id=transaction_id, operation="SAVE_CANDIDATE")
        _recover_transactions(paths=paths, binding=binding, definition=definition, project_dir=project_dir)

        state_payload = _load_state_payload_for_write(paths)
        state_for_write, current_state_revision = _load_state_for_write(
            paths=paths,
            binding=binding,
            definition=definition,
            project_dir=project_dir,
        )
        existing_step_state = state_for_write["step_states"].get(step_id)
        current_approved_group_id = existing_step_state.get("approved_group_id") if isinstance(existing_step_state, dict) else None
        replacement_mode = bool(
            isinstance(existing_step_state, dict)
            and existing_step_state.get("status") == "APPROVED"
            and current_approved_group_id
        )
        idempotency_sha256 = _canonical_idempotency_sha256(
            channel_slug=channel_slug,
            project_slug=project_slug,
            workflow_id=binding["workflow_id"],
            workflow_version=binding["workflow_version"],
            step_id=step_id,
            bundle_sha256=provided_bundle_sha256,
            raw_output_sha256=raw_output_sha256,
            current_approved_group_id=current_approved_group_id if isinstance(current_approved_group_id, str) else None,
        )
        transaction_id = f"txn_{idempotency_sha256[:16].lower()}"
        if existing_step_state is not None and existing_step_state.get("candidate_group_id"):
            if existing_step_state.get("candidate_idempotency_sha256") == idempotency_sha256:
                group_summary = _load_group_summary(paths, existing_step_state["candidate_group_id"])
                return 200, _build_candidate_response(
                    channel_slug=channel_slug,
                    project_slug=project_slug,
                    binding=binding,
                    step_id=step_id,
                    state_revision=current_state_revision,
                    group_summary=group_summary,
                    status="CANDIDATE_ALREADY_SAVED",
                    idempotent_replay=True,
                )
            raise _error("CANDIDATE_EXISTS", "A different candidate already exists for this workflow step.", 409)
        if expected_revision != current_state_revision:
            raise _error("STATE_REVISION_CONFLICT", "The workflow state changed before the candidate save completed.", 409)
        _validate_step_writable(
            project=project,
            project_dir=project_dir,
            binding=binding,
            definition=definition,
            step_id=step_id,
            state_payload=state_payload,
        )
        if replacement_mode:
            if state_payload is not None and state_payload.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION_V2:
                state_for_write = _convert_v2_state_to_v3(state_for_write)
            approved_group_id = existing_step_state.get("approved_group_id")
            if not isinstance(approved_group_id, str) or not approved_group_id.startswith("grp_"):
                raise _error("WORKFLOW_STATE_INVALID", "Approved workflow step is missing its approved group id.", 409)
            _approved_group_matches_stable_files(
                paths=paths,
                project_dir=project_dir,
                definition=definition,
                binding=binding,
                step_id=step_id,
                approved_group_id=approved_group_id,
            )

        bundle = channel_prompt_bundle.build_prompt_bundle(root, channel_slug, project_slug, step_id, project, project_dir)
        if bundle["bundle_sha256"] != provided_bundle_sha256:
            raise _error("BUNDLE_IDENTITY_MISMATCH", "The pasted AI output does not match the currently loaded workflow bundle.", 409)

        parsed_output = channel_output_parser.parse_channel_output(
            root,
            channel_slug,
            project_slug,
            step_id,
            provided_bundle_sha256,
            output_text,
            project,
            project_dir,
        )
        if parsed_output["status"] != "VALID":
            raise _error("PROMPT_OUTPUT_INVALID", "The pasted AI output did not satisfy the workflow output contract.", 409)
        parsed_artifacts = parsed_output["artifacts"]
        parsed_artifact_ids = [item["artifact_id"] for item in parsed_artifacts]
        if parsed_artifact_ids != list(step["output_artifact_ids"]):
            raise _error("OUTPUT_CONTRACT_INVALID", "The parsed output artifacts do not match the workflow step output contract.", 409)

        group_number = state_for_write["counters"]["next_group_number"]
        group_id = f"grp_{group_number:06d}"
        artifact_revision_map: dict[str, str] = {}
        artifact_revision_targets: list[dict[str, Any]] = []
        now = utc_now_iso()

        transaction_dir = paths.transactions_dir / transaction_id
        if transaction_dir.exists():
            shutil.rmtree(transaction_dir, ignore_errors=True)
        transaction_dir.mkdir(parents=True, exist_ok=False)
        staged_root = transaction_dir / "staged"

        for artifact in parsed_artifacts:
            artifact_id = artifact["artifact_id"]
            revision_number = state_for_write["counters"]["next_revision_number_by_artifact"][artifact_id]
            revision_id = f"rev_{revision_number:06d}"
            artifact_revision_map[artifact_id] = revision_id
            final_content_rel = f"revisions/artifacts/{artifact_id}/{revision_id}/content.md"
            final_metadata_rel = f"revisions/artifacts/{artifact_id}/{revision_id}/metadata.json"
            revision_content_bytes = artifact["content"].encode("utf-8")
            revision_metadata = {
                "schema_version": SUPPORTED_REVISION_METADATA_SCHEMA_VERSION,
                "revision_id": revision_id,
                "artifact_id": artifact_id,
                "stored_filename": "content.md",
                "content_sha256": artifact["sha256"],
                "character_count": artifact["character_count"],
                "created_at": now,
                "created_by": "ui_save_candidate",
                "source_step_id": step_id,
                "workflow_id": binding["workflow_id"],
                "workflow_version": binding["workflow_version"],
                "workflow_definition_sha256": binding["workflow_definition_sha256"],
                "prompt_set_id": prompt_set["prompt_set_id"],
                "prompt_set_version": prompt_set["version"],
                "bundle_sha256": bundle["bundle_sha256"],
                "raw_output_sha256": raw_output_sha256,
                "parse_status": "VALID",
                "revision_group_id": group_id,
                "created_status": "CANDIDATE",
            }
            _write_staged_file(staged_root / PurePosixPath(final_content_rel), revision_content_bytes)
            _write_staged_file(staged_root / PurePosixPath(final_metadata_rel), _json_bytes(revision_metadata))
            artifact_revision_targets.append({"kind": "ARTIFACT_REVISION_CONTENT", "relative_path": final_content_rel, "sha256": _sha256_bytes(revision_content_bytes)})
            artifact_revision_targets.append({"kind": "ARTIFACT_REVISION_METADATA", "relative_path": final_metadata_rel, "sha256": _sha256_bytes(_json_bytes(revision_metadata))})

        _maybe_fail("before_staging_complete", fail_stage)

        group_metadata = {
            "schema_version": SUPPORTED_GROUP_METADATA_SCHEMA_VERSION,
            "revision_group_id": group_id,
            "step_id": step_id,
            "workflow_id": binding["workflow_id"],
            "workflow_version": binding["workflow_version"],
            "workflow_definition_sha256": binding["workflow_definition_sha256"],
            "prompt_set_id": prompt_set["prompt_set_id"],
            "prompt_set_version": prompt_set["version"],
            "bundle_sha256": bundle["bundle_sha256"],
            "raw_output_sha256": raw_output_sha256,
            "idempotency_sha256": idempotency_sha256,
            "artifact_revision_ids": artifact_revision_map,
            "created_at": now,
            "created_by": "ui_save_candidate",
            "created_status": "CANDIDATE",
        }
        group_metadata_rel = f"revisions/groups/{group_id}/metadata.json"
        _write_staged_file(staged_root / PurePosixPath(group_metadata_rel), _json_bytes(group_metadata))
        group_target = {"kind": "REVISION_GROUP_METADATA", "relative_path": group_metadata_rel, "sha256": _sha256_bytes(_json_bytes(group_metadata))}

        next_state = json.loads(json.dumps(state_for_write))
        next_state["state_revision"] = current_state_revision + 1
        next_state["updated_at"] = now
        next_state["counters"]["next_group_number"] = group_number + 1
        use_v3_state = replacement_mode or state_for_write.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION
        if replacement_mode:
            next_state["step_states"][step_id] = {
                "status": "APPROVED",
                "candidate_group_id": group_id,
                "approved_group_id": current_approved_group_id,
                "candidate_idempotency_sha256": idempotency_sha256,
                "stale_reason": existing_step_state.get("stale_reason"),
                "invalidated_candidate_group_id": None,
                "updated_at": now,
            }
        else:
            next_step_state = {
                "status": "CANDIDATE",
                "candidate_group_id": group_id,
                "approved_group_id": None,
                "candidate_idempotency_sha256": idempotency_sha256,
                "updated_at": now,
            }
            if use_v3_state:
                next_step_state["stale_reason"] = None
                next_step_state["invalidated_candidate_group_id"] = None
            next_state["step_states"][step_id] = next_step_state
        for artifact_id, revision_id in artifact_revision_map.items():
            previous_approved_revision_id = None
            if replacement_mode:
                previous_approved_revision_id = (
                    existing_step_state
                    and state_for_write["artifact_heads"].get(artifact_id, {}).get("approved_revision_id")
                )
            next_state["artifact_heads"][artifact_id] = {
                "candidate_revision_id": revision_id,
                "approved_revision_id": previous_approved_revision_id,
            }
            next_state["counters"]["next_revision_number_by_artifact"][artifact_id] += 1
        if use_v3_state:
            validate_workflow_state_v3(
                next_state,
                binding=binding,
                definition=definition,
                project_dir=project_dir,
                require_persisted_targets=False,
            )
        else:
            validate_workflow_state_v2(
                next_state,
                binding=binding,
                definition=definition,
                project_dir=project_dir,
                require_persisted_targets=False,
            )
        next_state_bytes = _json_bytes(next_state)
        next_state_path = transaction_dir / "next_workflow_state.json"
        _write_staged_file(next_state_path, next_state_bytes)

        manifest = {
            "schema_version": SUPPORTED_TRANSACTION_MANIFEST_SCHEMA_VERSION,
            "transaction_id": transaction_id,
            "operation": "SAVE_CANDIDATE",
            "base_state_revision": current_state_revision,
            "target_state_revision": next_state["state_revision"],
            "revision_group_id": group_id,
            "targets": [*artifact_revision_targets, group_target],
            "next_state_sha256": _sha256_bytes(next_state_bytes),
            "created_at": now,
        }
        _write_staged_file(transaction_dir / "manifest.json", _json_bytes(manifest))

        published_artifact_count = 0
        for target in artifact_revision_targets:
            final_path = paths.workflow_dir / PurePosixPath(target["relative_path"])
            staged_path = staged_root / PurePosixPath(target["relative_path"])
            _copy_staged_file_to_final(staged_path, final_path, existing_code="STABLE_ARTIFACT_CONFLICT")
            if publish_log is not None:
                publish_log.append(f"artifact:{target['relative_path']}")
            if target["kind"] == "ARTIFACT_REVISION_METADATA":
                published_artifact_count += 1
                if published_artifact_count == 1:
                    _maybe_fail("after_one_artifact_revision_published", fail_stage)

        _maybe_fail("after_all_artifact_revisions_before_group", fail_stage)
        final_group_path = paths.workflow_dir / PurePosixPath(group_target["relative_path"])
        staged_group_path = staged_root / PurePosixPath(group_target["relative_path"])
        _copy_staged_file_to_final(staged_group_path, final_group_path)
        if publish_log is not None:
            publish_log.append(f"group:{group_target['relative_path']}")
        _maybe_fail("after_group_publication_before_state", fail_stage)
        _write_bytes_atomic(paths.workflow_state_json, next_state_bytes)
        if publish_log is not None:
            publish_log.append("state:workflow/workflow_state.json")
        _maybe_fail("after_state_replacement_before_cleanup", fail_stage)
        shutil.rmtree(transaction_dir, ignore_errors=True)
        if publish_log is not None:
            publish_log.append("cleanup:workflow/_transactions")

        group_summary = _load_group_summary(paths, group_id)
        return 201, _build_candidate_response(
            channel_slug=channel_slug,
            project_slug=project_slug,
            binding=binding,
            step_id=step_id,
            state_revision=next_state["state_revision"],
            group_summary=group_summary,
            status="CANDIDATE_SAVED",
            idempotent_replay=False,
        )
    except ChannelWorkflowWriteError:
        raise
    except channel_projects.ChannelProjectError as exc:
        message = str(exc)
        if "project.json does not exist" in message:
            raise _error("PROJECT_NOT_FOUND", "Selected project was not found.", 404) from exc
        raise _error("INVALID_REQUEST", message, 400) from exc
    except channel_prompt_bundle.PromptBundleError as exc:
        raise _error(exc.code, exc.message, exc.status) from exc
    except channel_output_parser.ChannelOutputParserError as exc:
        raise _error(exc.code, exc.message, exc.status) from exc
    except channel_workflow.ChannelWorkflowError as exc:
        raise _error(exc.code, exc.message, exc.status) from exc
    except Exception as exc:
        raise _error("WORKFLOW_WRITE_FAILED", "The candidate workflow write could not be completed safely.", 500) from exc
    finally:
        _release_lock(lock_handle)


def _stable_publication_targets(
    *,
    project_dir: Path,
    definition: dict[str, Any],
    artifact_revision_ids: dict[str, str],
    paths: WorkflowWritePaths,
    allow_existing_exact: bool,
    current_approved_artifact_revision_ids: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    final_paths = _validate_stable_artifact_target_paths(project_dir=project_dir, definition=definition, artifact_ids=list(artifact_revision_ids))
    targets: list[dict[str, Any]] = []
    artifact_summaries: list[dict[str, Any]] = []
    for artifact_id, revision_id in artifact_revision_ids.items():
        revision_dir = _candidate_revision_dir(paths, artifact_id, revision_id)
        content_path = revision_dir / "content.md"
        metadata_path = revision_dir / "metadata.json"
        metadata = _load_json_file(metadata_path, code="WORKFLOW_STATE_INVALID", message="Candidate revision metadata is malformed.")
        content_bytes = content_path.read_bytes()
        final_path = final_paths[artifact_id]
        previous_sha256 = None
        if current_approved_artifact_revision_ids is not None:
            current_revision_id = current_approved_artifact_revision_ids.get(artifact_id)
            if not isinstance(current_revision_id, str) or not current_revision_id.startswith("rev_"):
                raise _error("WORKFLOW_STATE_INVALID", "Approved artifact heads are inconsistent for replacement publication.", 409)
            approved_revision_dir = _candidate_revision_dir(paths, artifact_id, current_revision_id)
            approved_content_path = approved_revision_dir / "content.md"
            approved_metadata_path = approved_revision_dir / "metadata.json"
            if not approved_content_path.exists() or not approved_metadata_path.exists():
                raise _error("WORKFLOW_STATE_INVALID", "Approved revision storage is incomplete for replacement publication.", 409)
            approved_bytes = approved_content_path.read_bytes()
            previous_sha256 = _sha256_bytes(approved_bytes)
            if not final_path.exists() or not final_path.is_file():
                raise _error("STABLE_ARTIFACT_CONFLICT", "A stable artifact already exists for this workflow output.", 409)
            if _sha256_bytes(final_path.read_bytes()) != previous_sha256:
                raise _error("STABLE_ARTIFACT_CONFLICT", "A stable artifact already exists for this workflow output.", 409)
        elif final_path.exists() and not allow_existing_exact:
            raise _error("STABLE_ARTIFACT_CONFLICT", "A stable artifact already exists for this workflow output.", 409)
        targets.append(
            {
                "kind": "STABLE_ARTIFACT",
                "relative_path": str(final_path.relative_to(project_dir)).replace("\\", "/"),
                "sha256": _sha256_bytes(content_bytes),
                "previous_sha256": previous_sha256,
                "target_sha256": _sha256_bytes(content_bytes),
                "source_revision_path": revision_dir / "content.md",
            }
        )
        artifact_summaries.append(
            {
                "artifact_id": artifact_id,
                "revision_id": revision_id,
                "content_sha256": metadata["content_sha256"],
                "character_count": metadata["character_count"],
            }
        )
    return targets, artifact_summaries


def _decision_response_status(action: str, *, replay: bool) -> str:
    if action == "APPROVE":
        return "CANDIDATE_ALREADY_APPROVED" if replay else "CANDIDATE_APPROVED"
    return "CANDIDATE_ALREADY_REJECTED" if replay else "CANDIDATE_REJECTED"


def decide_candidate(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    step_id: str,
    candidate_group_id: Any,
    expected_state_revision: Any,
    *,
    action: str,
    fail_stage: str | None = None,
    publish_log: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    from scripts import channel_projects, channel_workflow

    if action not in {"APPROVE", "REJECT"}:
        raise _error("INVALID_REQUEST", "Unsupported decision action.", 400)
    requested_group_id = _validate_group_id(candidate_group_id)
    expected_revision = _validate_expected_state_revision(expected_state_revision)
    project = channel_projects.load_channel_project(root, channel_slug, project_slug)
    project_dir = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug
    binding = channel_workflow.resolve_project_workflow_binding(root, channel_slug, project)
    definition = channel_workflow.load_workflow_definition(root, binding["workflow_id"], binding["workflow_version"])
    step = next((item for item in definition["steps"] if item["step_id"] == step_id), None)
    if step is None:
        raise _error("WORKFLOW_STEP_NOT_FOUND", "The selected workflow step was not found for this project binding.", 404)
    prompt_set = definition["prompt_set"]
    if prompt_set.get("status") != "AVAILABLE" or not prompt_set.get("bundle_available"):
        raise _error("PROMPT_SET_UNAVAILABLE", "The pinned workflow version does not expose an available prompt set.", 409)

    paths = workflow_write_paths(project_dir)
    transaction_id = f"txn_{_sha256_text(json.dumps({'action': action, 'channel_slug': channel_slug, 'project_slug': project_slug, 'step_id': step_id, 'candidate_group_id': requested_group_id}, sort_keys=True, separators=(',', ':')))[:16].lower()}"
    lock_handle: LockHandle | None = None
    try:
        lock_handle = _acquire_lock(paths.lock_file, transaction_id=transaction_id, operation=f"{action}_CANDIDATE")
        _recover_transactions(paths=paths, binding=binding, definition=definition, project_dir=project_dir)

        state_payload = _load_state_payload_for_write(paths)
        state_for_write, current_state_revision = _load_state_for_write(
            paths=paths,
            binding=binding,
            definition=definition,
            project_dir=project_dir,
        )
        state_view = build_read_state_model(
            project=project,
            project_dir=project_dir,
            binding=binding,
            definition=definition,
            state_payload=state_payload,
        )

        existing_decision = _load_decision_record(
            paths,
            group_id=requested_group_id,
            step_id=step_id,
            action=None,
            binding=binding,
            definition=definition,
        )
        if existing_decision is not None:
            if existing_decision["action"] != action:
                raise _error("CANDIDATE_DECISION_CONFLICT", "The candidate group already has the opposite final decision.", 409)
            return 200, _build_decision_response(
                status=_decision_response_status(action, replay=True),
                idempotent_replay=True,
                state_revision=current_state_revision,
                group_id=requested_group_id,
                artifacts=None if action == "REJECT" else _load_group_summary(paths, requested_group_id)["artifacts"],
                replacement=bool(existing_decision.get("replaces_approved_group_id")),
                replaces_approved_group_id=existing_decision.get("replaces_approved_group_id"),
            )

        if expected_revision != current_state_revision:
            raise _error("STATE_REVISION_CONFLICT", "The workflow state changed before the candidate decision completed.", 409)

        step_state, group_payload, artifact_revision_ids = _load_decidable_step_context(
            paths=paths,
            binding=binding,
            definition=definition,
            step_id=step_id,
            state_payload=state_payload,
            state_view=state_view,
        )
        if step_state.get("candidate_group_id") != requested_group_id:
            raise _error("CANDIDATE_GROUP_MISMATCH", "The requested candidate group is not the current candidate for this workflow step.", 409)
        replacement = bool(step_state.get("status") == "APPROVED" and step_state.get("approved_group_id"))
        approved_group_id = step_state.get("approved_group_id") if replacement else None
        current_approved_artifact_revision_ids: dict[str, str] | None = None
        if replacement:
            if state_payload is not None and state_payload.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION_V2:
                state_for_write = _convert_v2_state_to_v3(state_for_write)
            if not isinstance(approved_group_id, str) or not approved_group_id.startswith("grp_"):
                raise _error("WORKFLOW_STATE_INVALID", "Approved workflow step is missing its approved group id.", 409)
            current_approved_artifact_revision_ids = _approved_group_matches_stable_files(
                paths=paths,
                project_dir=project_dir,
                definition=definition,
                binding=binding,
                step_id=step_id,
                approved_group_id=approved_group_id,
            )
            existing_approve = _load_decision_record(
                paths,
                group_id=approved_group_id,
                step_id=step_id,
                action="APPROVE",
                binding=binding,
                definition=definition,
            )
            if existing_approve is None:
                raise _error("WORKFLOW_STATE_INVALID", "The current approved group has no immutable approval decision.", 409)
        elif step_state.get("status") != "CANDIDATE":
            raise _error("WORKFLOW_STEP_NOT_DECIDABLE", "The selected workflow step is not currently in candidate state.", 409)
        elif any(head.get("approved_revision_id") is not None for artifact_id, head in state_for_write["artifact_heads"].items() if artifact_id in artifact_revision_ids):
            raise _error("CANDIDATE_ALREADY_DECIDED", "This workflow step already has approved artifact heads.", 409)

        now = utc_now_iso()
        decision_record = {
            "schema_version": 1,
            "decision_id": f"decision_{requested_group_id}",
            "revision_group_id": requested_group_id,
            "step_id": step_id,
            "action": action,
            "replaces_approved_group_id": approved_group_id if replacement else None,
            "workflow_id": binding["workflow_id"],
            "workflow_version": binding["workflow_version"],
            "workflow_definition_sha256": binding["workflow_definition_sha256"],
            "artifact_revision_ids": artifact_revision_ids,
            "base_state_revision": current_state_revision,
            "target_state_revision": current_state_revision + 1,
            "decided_at": now,
            "decided_by": "ui_approve_candidate" if action == "APPROVE" else "ui_reject_candidate",
        }
        decision_rel = f"revisions/decisions/{requested_group_id}.json"

        next_state = json.loads(json.dumps(state_for_write))
        next_state["state_revision"] = current_state_revision + 1
        next_state["updated_at"] = now

        stable_targets: list[dict[str, Any]] = []
        artifact_summaries: list[dict[str, Any]] | None = None
        changed_artifact_ids: list[str] = []
        stale_step_ids: list[str] = []
        if action == "APPROVE":
            stable_targets, artifact_summaries = _stable_publication_targets(
                project_dir=project_dir,
                definition=definition,
                artifact_revision_ids=artifact_revision_ids,
                paths=paths,
                allow_existing_exact=not replacement,
                current_approved_artifact_revision_ids=current_approved_artifact_revision_ids,
            )
            if replacement:
                for artifact_id, revision_id in artifact_revision_ids.items():
                    old_revision_id = current_approved_artifact_revision_ids[artifact_id]
                    old_metadata = _load_json_file(
                        _candidate_revision_dir(paths, artifact_id, old_revision_id) / "metadata.json",
                        code="WORKFLOW_STATE_INVALID",
                        message="Approved revision metadata is malformed.",
                    )
                    new_metadata = _load_json_file(
                        _candidate_revision_dir(paths, artifact_id, revision_id) / "metadata.json",
                        code="WORKFLOW_STATE_INVALID",
                        message="Candidate revision metadata is malformed.",
                    )
                    if old_metadata["content_sha256"] != new_metadata["content_sha256"]:
                        changed_artifact_ids.append(artifact_id)
            next_step_state = {
                "status": "APPROVED",
                "candidate_group_id": None,
                "approved_group_id": requested_group_id,
                "candidate_idempotency_sha256": None,
                "updated_at": now,
            }
            if replacement or state_for_write.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION:
                next_step_state["stale_reason"] = None
                next_step_state["invalidated_candidate_group_id"] = None
            next_state["step_states"][step_id] = next_step_state
            for artifact_id, revision_id in artifact_revision_ids.items():
                next_state["artifact_heads"][artifact_id] = {
                    "candidate_revision_id": None,
                    "approved_revision_id": revision_id,
                }
            if replacement and changed_artifact_ids:
                stale_step_ids = _propagate_stale_state(
                    next_state=next_state,
                    definition=definition,
                    source_step_id=step_id,
                    source_group_id=requested_group_id,
                    changed_artifact_ids=changed_artifact_ids,
                    target_state_revision=next_state["state_revision"],
                    invalidated_at=now,
                )
        else:
            if replacement:
                next_state["step_states"][step_id] = {
                    "status": "APPROVED",
                    "candidate_group_id": None,
                    "approved_group_id": approved_group_id,
                    "candidate_idempotency_sha256": None,
                    "stale_reason": step_state.get("stale_reason"),
                    "invalidated_candidate_group_id": None,
                    "updated_at": now,
                }
                for artifact_id in artifact_revision_ids:
                    head = next_state["artifact_heads"].get(artifact_id)
                    if head is not None:
                        head["candidate_revision_id"] = None
            else:
                next_step_state = {
                    "status": "READY",
                    "candidate_group_id": None,
                    "approved_group_id": None,
                    "candidate_idempotency_sha256": None,
                    "updated_at": now,
                }
                if state_for_write.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION:
                    next_step_state["stale_reason"] = None
                    next_step_state["invalidated_candidate_group_id"] = None
                next_state["step_states"][step_id] = next_step_state
                for artifact_id in artifact_revision_ids:
                    next_state["artifact_heads"].pop(artifact_id, None)

        if replacement or state_for_write.get("schema_version") == SUPPORTED_STATE_SCHEMA_VERSION:
            validate_workflow_state_v3(next_state, binding=binding, definition=definition, project_dir=project_dir, require_persisted_targets=False)
        else:
            validate_workflow_state_v2(next_state, binding=binding, definition=definition, project_dir=project_dir, require_persisted_targets=False)
        next_state_bytes = _json_bytes(next_state)

        transaction_dir = paths.transactions_dir / transaction_id
        if transaction_dir.exists():
            shutil.rmtree(transaction_dir, ignore_errors=True)
        transaction_dir.mkdir(parents=True, exist_ok=False)
        staged_root = transaction_dir / "staged"

        _maybe_fail("before_decision_staging_complete", fail_stage)
        for target in stable_targets:
            source_path = target["source_revision_path"]
            _write_staged_file(staged_root / PurePosixPath(target["relative_path"]), source_path.read_bytes())
        _write_staged_file(staged_root / PurePosixPath(decision_rel), _json_bytes(decision_record))
        _write_staged_file(transaction_dir / "next_workflow_state.json", next_state_bytes)
        manifest = {
            "schema_version": SUPPORTED_TRANSACTION_MANIFEST_SCHEMA_VERSION,
            "transaction_id": transaction_id,
            "operation": f"{action}_CANDIDATE",
            "base_state_revision": current_state_revision,
            "target_state_revision": next_state["state_revision"],
            "revision_group_id": requested_group_id,
            "targets": [
                *[
                    {
                        "kind": "STABLE_ARTIFACT",
                        "relative_path": target["relative_path"],
                        "sha256": target["sha256"],
                        "previous_sha256": target.get("previous_sha256"),
                        "target_sha256": target.get("target_sha256"),
                    }
                    for target in stable_targets
                ],
                {"kind": "DECISION_RECORD", "relative_path": decision_rel, "sha256": _sha256_bytes(_json_bytes(decision_record))},
            ],
            "next_state_sha256": _sha256_bytes(next_state_bytes),
            "created_at": now,
        }
        _write_staged_file(transaction_dir / "manifest.json", _json_bytes(manifest))

        published_stable_count = 0
        for target in stable_targets:
            final_path = project_dir / PurePosixPath(target["relative_path"])
            staged_path = staged_root / PurePosixPath(target["relative_path"])
            try:
                _copy_staged_file_to_final(
                    staged_path,
                    final_path,
                    existing_code="STABLE_ARTIFACT_CONFLICT",
                    expected_existing_sha256=target.get("previous_sha256"),
                )
            except ChannelWorkflowWriteError as exc:
                if exc.code == "STABLE_ARTIFACT_CONFLICT":
                    shutil.rmtree(transaction_dir, ignore_errors=True)
                raise
            published_stable_count += 1
            if publish_log is not None:
                publish_log.append(f"stable:{target['relative_path']}")
            if published_stable_count == 1:
                _maybe_fail("after_one_stable_artifact_published", fail_stage)
        if action == "APPROVE":
            _maybe_fail("after_all_stable_artifacts_before_decision", fail_stage)
        decision_final_path = paths.workflow_dir / PurePosixPath(decision_rel)
        decision_staged_path = staged_root / PurePosixPath(decision_rel)
        _copy_staged_file_to_final(decision_staged_path, decision_final_path)
        if publish_log is not None:
            publish_log.append(f"decision:{decision_rel}")
        _maybe_fail("after_decision_before_state", fail_stage)
        _write_bytes_atomic(paths.workflow_state_json, next_state_bytes)
        if publish_log is not None:
            publish_log.append("state:workflow/workflow_state.json")
        _maybe_fail("after_state_before_cleanup", fail_stage)
        shutil.rmtree(transaction_dir, ignore_errors=True)
        if publish_log is not None:
            publish_log.append("cleanup:workflow/_transactions")
        return 200, _build_decision_response(
            status=_decision_response_status(action, replay=False),
            idempotent_replay=False,
            state_revision=next_state["state_revision"],
            group_id=requested_group_id,
            artifacts=artifact_summaries,
            replacement=replacement,
            replaces_approved_group_id=approved_group_id if replacement else None,
            changed_artifact_ids=changed_artifact_ids if action == "APPROVE" and replacement else [],
            stale_step_ids=stale_step_ids if action == "APPROVE" and replacement else [],
        )
    finally:
        _release_lock(lock_handle)


def approve_candidate(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    step_id: str,
    candidate_group_id: Any,
    expected_state_revision: Any,
    *,
    fail_stage: str | None = None,
    publish_log: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    return decide_candidate(
        root,
        channel_slug,
        project_slug,
        step_id,
        candidate_group_id,
        expected_state_revision,
        action="APPROVE",
        fail_stage=fail_stage,
        publish_log=publish_log,
    )


def reject_candidate(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    step_id: str,
    candidate_group_id: Any,
    expected_state_revision: Any,
    *,
    fail_stage: str | None = None,
    publish_log: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    return decide_candidate(
        root,
        channel_slug,
        project_slug,
        step_id,
        candidate_group_id,
        expected_state_revision,
        action="REJECT",
        fail_stage=fail_stage,
        publish_log=publish_log,
    )
