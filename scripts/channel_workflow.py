from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from scripts import channel_workspace


SUPPORTED_REGISTRY_SCHEMA_VERSION = 1
SUPPORTED_DEFINITION_SCHEMA_VERSION = 1
SUPPORTED_STATE_SCHEMA_VERSION = 1
SUPPORTED_EXECUTION_MODE = "LINEAR"
SUPPORTED_PROMPT_SET_STATUSES = {"MISSING", "AVAILABLE"}
SUPPORTED_VERSION_STATUSES = {"ACTIVE", "DEPRECATED"}
SUPPORTED_ARTIFACT_ROLES = {"INPUT", "OPTIONAL_INPUT", "GENERATED", "FINAL"}
SUPPORTED_STEP_STATUSES = {
    "BLOCKED",
    "READY",
    "IN_PROGRESS",
    "AWAITING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "STALE",
}


class ChannelWorkflowError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error(code: str, message: str, status: int = 400) -> ChannelWorkflowError:
    return ChannelWorkflowError(code, message, status)


def workflows_root(root: Path | str) -> Path:
    return Path(root).resolve() / "workflows"


def _ensure_iso_timestamp(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name} must be a timezone-aware ISO timestamp.")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error("WORKFLOW_STATE_INVALID", f"{field_name} must be timezone-aware.")


def _safe_relative_posix_path(value: Any, *, field_name: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise _error("WORKFLOW_DEFINITION_INVALID", f"{field_name} must be a non-empty relative path.")
    raw = value.strip()
    if "\\" in raw:
        raise _error("WORKFLOW_DEFINITION_INVALID", f"{field_name} must use forward slashes only.")
    if PureWindowsPath(raw).drive:
        raise _error("WORKFLOW_DEFINITION_INVALID", f"{field_name} must not contain a drive prefix.")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise _error("WORKFLOW_DEFINITION_INVALID", f"{field_name} must stay within the workflow/project root.")
    return pure


def _safe_relative_project_path(value: Any, *, field_name: str) -> str:
    return _safe_relative_posix_path(value, field_name=field_name).as_posix()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _validate_digest(value: Any, *, field_name: str, code: str) -> str:
    if not isinstance(value, str) or len(value.strip()) != 64:
        raise _error(code, f"{field_name} must be a 64-character SHA-256 hex digest.")
    digest = value.strip().upper()
    if any(ch not in "0123456789ABCDEF" for ch in digest):
        raise _error(code, f"{field_name} must be a valid SHA-256 hex digest.")
    return digest


def _validate_registry_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise _error("WORKFLOW_REGISTRY_INVALID", "Workflow registry must be a JSON object.")
    if data.get("schema_version") != SUPPORTED_REGISTRY_SCHEMA_VERSION:
        raise _error("WORKFLOW_REGISTRY_INVALID", "Unsupported workflow registry schema_version.")

    channel_defaults = data.get("channel_defaults")
    workflows = data.get("workflows")
    if not isinstance(channel_defaults, dict) or not isinstance(workflows, dict) or not workflows:
        raise _error("WORKFLOW_REGISTRY_INVALID", "Workflow registry must define channel_defaults and workflows.")

    validated_workflows: dict[str, Any] = {}
    for workflow_id, workflow in workflows.items():
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise _error("WORKFLOW_REGISTRY_INVALID", "Workflow ids must be non-empty strings.")
        if not isinstance(workflow, dict):
            raise _error("WORKFLOW_REGISTRY_INVALID", f"Workflow entry {workflow_id} must be an object.")
        default_version = workflow.get("default_version")
        legacy_unpinned_version = workflow.get("legacy_unpinned_version")
        versions = workflow.get("versions")
        display_name = workflow.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            raise _error("WORKFLOW_REGISTRY_INVALID", f"Workflow {workflow_id} is missing display_name.")
        if not isinstance(versions, dict) or not versions:
            raise _error("WORKFLOW_REGISTRY_INVALID", f"Workflow {workflow_id} must define versions.")
        if not isinstance(default_version, str) or default_version not in versions:
            raise _error("WORKFLOW_REGISTRY_INVALID", f"Workflow {workflow_id} default_version must exist.")
        if not isinstance(legacy_unpinned_version, str) or legacy_unpinned_version not in versions:
            raise _error("WORKFLOW_REGISTRY_INVALID", f"Workflow {workflow_id} legacy_unpinned_version must exist.")

        validated_versions: dict[str, Any] = {}
        for version, version_entry in versions.items():
            if not isinstance(version, str) or not version.strip():
                raise _error("WORKFLOW_REGISTRY_INVALID", f"Workflow {workflow_id} has an invalid version key.")
            if not isinstance(version_entry, dict):
                raise _error("WORKFLOW_REGISTRY_INVALID", f"Workflow {workflow_id} version {version} must be an object.")
            status = version_entry.get("status")
            if status not in SUPPORTED_VERSION_STATUSES:
                raise _error("WORKFLOW_REGISTRY_INVALID", f"Workflow {workflow_id} version {version} has an unsupported status.")
            definition_path = _safe_relative_posix_path(
                version_entry.get("definition_path"), field_name=f"workflows.{workflow_id}.versions.{version}.definition_path"
            ).as_posix()
            digest = _validate_digest(
                version_entry.get("definition_sha256"),
                field_name=f"workflows.{workflow_id}.versions.{version}.definition_sha256",
                code="WORKFLOW_REGISTRY_INVALID",
            )
            validated_versions[version] = {
                "status": status,
                "definition_path": definition_path,
                "definition_sha256": digest,
            }

        validated_workflows[workflow_id] = {
            "display_name": display_name.strip(),
            "default_version": default_version,
            "legacy_unpinned_version": legacy_unpinned_version,
            "versions": validated_versions,
        }

    validated_defaults: dict[str, Any] = {}
    for channel_slug, value in channel_defaults.items():
        slug = channel_workspace.validate_channel_slug(channel_slug)
        if not isinstance(value, dict):
            raise _error("WORKFLOW_REGISTRY_INVALID", f"Channel default for {slug} must be an object.")
        workflow_id = value.get("workflow_id")
        if not isinstance(workflow_id, str) or workflow_id not in validated_workflows:
            raise _error("WORKFLOW_REGISTRY_INVALID", f"Channel default for {slug} must reference an existing workflow.")
        validated_defaults[slug] = {"workflow_id": workflow_id}

    return {
        "schema_version": SUPPORTED_REGISTRY_SCHEMA_VERSION,
        "channel_defaults": validated_defaults,
        "workflows": validated_workflows,
    }


def load_workflow_registry(root: Path | str) -> dict[str, Any]:
    path = workflows_root(root) / "registry.json"
    if not path.exists():
        raise _error("WORKFLOW_NOT_CONFIGURED", "No workflow registry is configured for this repository.", 409)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _error("WORKFLOW_REGISTRY_INVALID", "Workflow registry is malformed JSON.") from exc
    return _validate_registry_payload(payload)


def _validate_definition_payload(definition: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(definition, dict):
        raise _error("WORKFLOW_DEFINITION_INVALID", "Workflow definition must be a JSON object.")
    required_top = {
        "schema_version",
        "workflow_id",
        "workflow_version",
        "display_name",
        "execution_mode",
        "entry_lifecycle_state",
        "terminal_lifecycle_state",
        "lifecycle_states",
        "prompt_set",
        "artifacts",
        "steps",
    }
    missing = sorted(required_top - set(definition))
    if missing:
        raise _error("WORKFLOW_DEFINITION_INVALID", f"Workflow definition is missing required fields: {', '.join(missing)}")
    if definition["schema_version"] != SUPPORTED_DEFINITION_SCHEMA_VERSION:
        raise _error("WORKFLOW_DEFINITION_INVALID", "Unsupported workflow definition schema_version.")
    if definition["execution_mode"] != SUPPORTED_EXECUTION_MODE:
        raise _error("WORKFLOW_DEFINITION_INVALID", "Unsupported workflow execution_mode.")

    workflow_id = definition["workflow_id"]
    workflow_version = definition["workflow_version"]
    display_name = definition["display_name"]
    if not isinstance(workflow_id, str) or not workflow_id.strip():
        raise _error("WORKFLOW_DEFINITION_INVALID", "workflow_id is required.")
    if not isinstance(workflow_version, str) or not workflow_version.strip():
        raise _error("WORKFLOW_DEFINITION_INVALID", "workflow_version is required.")
    if not isinstance(display_name, str) or not display_name.strip():
        raise _error("WORKFLOW_DEFINITION_INVALID", "display_name is required.")

    lifecycle_states = definition["lifecycle_states"]
    if not isinstance(lifecycle_states, list) or not lifecycle_states:
        raise _error("WORKFLOW_DEFINITION_INVALID", "lifecycle_states must be a non-empty list.")
    if any(not isinstance(item, str) or not item.strip() for item in lifecycle_states):
        raise _error("WORKFLOW_DEFINITION_INVALID", "lifecycle_states must contain non-empty strings.")
    if len(set(lifecycle_states)) != len(lifecycle_states):
        raise _error("WORKFLOW_DEFINITION_INVALID", "lifecycle_states must not contain duplicates.")
    entry_state = definition["entry_lifecycle_state"]
    terminal_state = definition["terminal_lifecycle_state"]
    if entry_state not in lifecycle_states or terminal_state not in lifecycle_states:
        raise _error("WORKFLOW_DEFINITION_INVALID", "entry or terminal lifecycle state is missing from lifecycle_states.")

    prompt_set = definition["prompt_set"]
    if not isinstance(prompt_set, dict):
        raise _error("WORKFLOW_DEFINITION_INVALID", "prompt_set must be an object.")
    status = prompt_set.get("status")
    if status not in SUPPORTED_PROMPT_SET_STATUSES:
        raise _error("WORKFLOW_DEFINITION_INVALID", "prompt_set.status is unsupported.")
    if not isinstance(prompt_set.get("bundle_available"), bool):
        raise _error("WORKFLOW_DEFINITION_INVALID", "prompt_set.bundle_available must be a boolean.")
    if status == "MISSING":
        if prompt_set.get("bundle_available"):
            raise _error("WORKFLOW_DEFINITION_INVALID", "Prompt bundle cannot be available when prompt_set.status is MISSING.")
        normalized_prompt_set = {
            "status": "MISSING",
            "version": prompt_set.get("version"),
            "bundle_available": False,
        }
    else:
        if not prompt_set.get("bundle_available"):
            raise _error("WORKFLOW_DEFINITION_INVALID", "prompt_set.bundle_available must be true when prompt_set.status is AVAILABLE.")
        prompt_set_id = prompt_set.get("prompt_set_id")
        prompt_set_version = prompt_set.get("version")
        manifest_path = prompt_set.get("manifest_path")
        if not isinstance(prompt_set_id, str) or not prompt_set_id.strip():
            raise _error("WORKFLOW_DEFINITION_INVALID", "prompt_set.prompt_set_id is required when the prompt set is available.")
        if not isinstance(prompt_set_version, str) or not prompt_set_version.strip():
            raise _error("WORKFLOW_DEFINITION_INVALID", "prompt_set.version is required when the prompt set is available.")
        normalized_prompt_set = {
            "status": "AVAILABLE",
            "prompt_set_id": prompt_set_id.strip(),
            "version": prompt_set_version.strip(),
            "manifest_path": _safe_relative_posix_path(manifest_path, field_name="prompt_set.manifest_path").as_posix(),
            "manifest_sha256": _validate_digest(
                prompt_set.get("manifest_sha256"),
                field_name="prompt_set.manifest_sha256",
                code="WORKFLOW_DEFINITION_INVALID",
            ),
            "bundle_available": True,
        }

    artifacts = definition["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise _error("WORKFLOW_DEFINITION_INVALID", "artifacts must be a non-empty list.")
    artifact_map: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise _error("WORKFLOW_DEFINITION_INVALID", "Each artifact definition must be an object.")
        for field in ("artifact_id", "display_name", "relative_path", "artifact_role", "required", "media_type"):
            if field not in artifact:
                raise _error("WORKFLOW_DEFINITION_INVALID", f"Artifact definition is missing {field}.")
        artifact_id = artifact["artifact_id"]
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise _error("WORKFLOW_DEFINITION_INVALID", "artifact_id must be a non-empty string.")
        if artifact_id in artifact_map:
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Duplicate artifact_id: {artifact_id}")
        role = artifact["artifact_role"]
        if role not in SUPPORTED_ARTIFACT_ROLES:
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Artifact {artifact_id} has an unsupported role.")
        if not isinstance(artifact["display_name"], str) or not artifact["display_name"].strip():
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Artifact {artifact_id} is missing display_name.")
        if not isinstance(artifact["required"], bool):
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Artifact {artifact_id} required must be boolean.")
        if not isinstance(artifact["media_type"], str) or not artifact["media_type"].strip():
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Artifact {artifact_id} is missing media_type.")
        relative_path = _safe_relative_project_path(artifact["relative_path"], field_name=f"artifacts.{artifact_id}.relative_path")
        artifact_map[artifact_id] = {
            "artifact_id": artifact_id,
            "display_name": artifact["display_name"].strip(),
            "relative_path": relative_path,
            "artifact_role": role,
            "required": artifact["required"],
            "media_type": artifact["media_type"].strip(),
        }

    steps = definition["steps"]
    if not isinstance(steps, list) or not steps:
        raise _error("WORKFLOW_DEFINITION_INVALID", "steps must be a non-empty list.")
    step_ids: set[str] = set()
    orders: set[int] = set()
    produced_artifacts: dict[str, str] = {}
    validated_steps: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            raise _error("WORKFLOW_DEFINITION_INVALID", "Each step definition must be an object.")
        for field in (
            "step_id",
            "order",
            "display_name",
            "required_model",
            "input_artifact_ids",
            "optional_input_artifact_ids",
            "output_artifact_ids",
            "resulting_lifecycle_state",
            "constraints",
            "prompt_source_ref",
        ):
            if field not in step:
                raise _error("WORKFLOW_DEFINITION_INVALID", f"Step definition is missing {field}.")
        step_id = step["step_id"]
        order = step["order"]
        if not isinstance(step_id, str) or not step_id.strip():
            raise _error("WORKFLOW_DEFINITION_INVALID", "step_id must be a non-empty string.")
        if step_id in step_ids:
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Duplicate step_id: {step_id}")
        step_ids.add(step_id)
        if not isinstance(order, int) or order < 1:
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Step {step_id} order must be a positive integer.")
        if order in orders:
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Duplicate step order: {order}")
        orders.add(order)
        if not isinstance(step["display_name"], str) or not step["display_name"].strip():
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Step {step_id} is missing display_name.")
        if not isinstance(step["required_model"], str) or not step["required_model"].strip():
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Step {step_id} is missing required_model.")
        if step["resulting_lifecycle_state"] not in lifecycle_states:
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Step {step_id} references an unknown resulting_lifecycle_state.")
        input_ids = step["input_artifact_ids"]
        optional_ids = step["optional_input_artifact_ids"]
        output_ids = step["output_artifact_ids"]
        if not isinstance(input_ids, list) or not isinstance(optional_ids, list) or not isinstance(output_ids, list):
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Step {step_id} artifact references must be lists.")
        for artifact_id in input_ids + optional_ids + output_ids:
            if artifact_id not in artifact_map:
                raise _error("WORKFLOW_DEFINITION_INVALID", f"Step {step_id} references unknown artifact {artifact_id}.")
        for artifact_id in output_ids:
            if artifact_id in produced_artifacts:
                raise _error(
                    "WORKFLOW_DEFINITION_INVALID",
                    f"Artifact {artifact_id} is produced by conflicting steps {produced_artifacts[artifact_id]} and {step_id}.",
                )
            produced_artifacts[artifact_id] = step_id
        constraints = step["constraints"]
        if not isinstance(constraints, list):
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Step {step_id} constraints must be a list.")
        for constraint in constraints:
            if not isinstance(constraint, dict) or not isinstance(constraint.get("type"), str) or not constraint["type"].strip():
                raise _error("WORKFLOW_DEFINITION_INVALID", f"Step {step_id} has an invalid constraint.")
        prompt_source_ref = step["prompt_source_ref"]
        if prompt_source_ref is not None and not isinstance(prompt_source_ref, str):
            raise _error("WORKFLOW_DEFINITION_INVALID", f"Step {step_id} prompt_source_ref must be a string or null.")
        validated_steps.append(
            {
                "step_id": step_id,
                "order": order,
                "display_name": step["display_name"].strip(),
                "required_model": step["required_model"].strip(),
                "input_artifact_ids": list(input_ids),
                "optional_input_artifact_ids": list(optional_ids),
                "output_artifact_ids": list(output_ids),
                "resulting_lifecycle_state": step["resulting_lifecycle_state"],
                "constraints": list(constraints),
                "prompt_source_ref": prompt_source_ref,
            }
        )

    expected_orders = list(range(1, len(validated_steps) + 1))
    if sorted(orders) != expected_orders:
        raise _error("WORKFLOW_DEFINITION_INVALID", "Step order must be contiguous starting at 1.")

    if prompt_set.get("bundle_available") and any(step["prompt_source_ref"] is None for step in validated_steps):
        raise _error("WORKFLOW_DEFINITION_INVALID", "Prompt bundle cannot be available while prompt_source_ref values are missing.")

    validated_steps.sort(key=lambda item: item["order"])
    return {
        "schema_version": SUPPORTED_DEFINITION_SCHEMA_VERSION,
        "workflow_id": workflow_id.strip(),
        "workflow_version": workflow_version.strip(),
        "display_name": display_name.strip(),
        "execution_mode": SUPPORTED_EXECUTION_MODE,
        "entry_lifecycle_state": entry_state,
        "terminal_lifecycle_state": terminal_state,
        "lifecycle_states": list(lifecycle_states),
        "prompt_set": normalized_prompt_set,
        "artifacts": list(artifact_map.values()),
        "steps": validated_steps,
    }


def resolve_workflow_definition_path(root: Path | str, workflow_id: str, workflow_version: str) -> Path:
    registry = load_workflow_registry(root)
    workflow_entry = registry["workflows"].get(workflow_id)
    if workflow_entry is None:
        raise _error("WORKFLOW_DEFINITION_NOT_FOUND", f"Workflow {workflow_id} is not registered.", 404)
    version_entry = workflow_entry["versions"].get(workflow_version)
    if version_entry is None:
        raise _error("WORKFLOW_DEFINITION_NOT_FOUND", f"Workflow {workflow_id} version {workflow_version} is not registered.", 404)
    workflow_root = workflows_root(root).resolve()
    definition_path = (workflow_root / version_entry["definition_path"]).resolve()
    try:
        definition_path.relative_to(workflow_root)
    except ValueError as exc:
        raise _error("WORKFLOW_DEFINITION_INVALID", "Workflow definition path escapes the workflow root.") from exc
    return definition_path


def load_workflow_definition(root: Path | str, workflow_id: str, workflow_version: str) -> dict[str, Any]:
    registry = load_workflow_registry(root)
    workflow_entry = registry["workflows"].get(workflow_id)
    if workflow_entry is None:
        raise _error("WORKFLOW_DEFINITION_NOT_FOUND", f"Workflow {workflow_id} is not registered.", 404)
    version_entry = workflow_entry["versions"].get(workflow_version)
    if version_entry is None:
        raise _error("WORKFLOW_DEFINITION_NOT_FOUND", f"Workflow {workflow_id} version {workflow_version} is not registered.", 404)
    definition_path = resolve_workflow_definition_path(root, workflow_id, workflow_version)
    if not definition_path.exists():
        raise _error("WORKFLOW_DEFINITION_NOT_FOUND", "Workflow definition file does not exist.", 404)
    digest = _sha256_file(definition_path)
    if digest != version_entry["definition_sha256"]:
        raise _error("WORKFLOW_DEFINITION_DIGEST_MISMATCH", "Workflow definition digest does not match the registry.", 409)
    try:
        payload = json.loads(definition_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _error("WORKFLOW_DEFINITION_INVALID", "Workflow definition is malformed JSON.") from exc
    validated = _validate_definition_payload(payload)
    if validated["workflow_id"] != workflow_id:
        raise _error("WORKFLOW_DEFINITION_INVALID", "Registry workflow id does not match definition workflow id.")
    if validated["workflow_version"] != workflow_version:
        raise _error("WORKFLOW_DEFINITION_INVALID", "Registry workflow version does not match definition workflow version.")
    return validated


def get_channel_default_workflow(root: Path | str, channel_slug: str) -> dict[str, str] | None:
    registry_path = workflows_root(root) / "registry.json"
    if not registry_path.exists():
        return None
    registry = load_workflow_registry(root)
    default = registry["channel_defaults"].get(channel_workspace.validate_channel_slug(channel_slug))
    if not default:
        return None
    workflow_entry = registry["workflows"][default["workflow_id"]]
    version = workflow_entry["default_version"]
    version_entry = workflow_entry["versions"][version]
    return {
        "workflow_id": default["workflow_id"],
        "workflow_version": version,
        "workflow_definition_sha256": version_entry["definition_sha256"],
    }


def validate_project_workflow_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _error("WORKFLOW_BINDING_INVALID", "workflow_binding must be an object.")
    required = {"workflow_id", "workflow_version", "workflow_definition_sha256"}
    missing = sorted(required - set(value))
    if missing:
        raise _error("WORKFLOW_BINDING_INVALID", f"workflow_binding is missing fields: {', '.join(missing)}")
    workflow_id = value["workflow_id"]
    workflow_version = value["workflow_version"]
    if not isinstance(workflow_id, str) or not workflow_id.strip():
        raise _error("WORKFLOW_BINDING_INVALID", "workflow_binding.workflow_id is required.")
    if not isinstance(workflow_version, str) or not workflow_version.strip():
        raise _error("WORKFLOW_BINDING_INVALID", "workflow_binding.workflow_version is required.")
    digest = _validate_digest(
        value["workflow_definition_sha256"],
        field_name="workflow_binding.workflow_definition_sha256",
        code="WORKFLOW_BINDING_INVALID",
    )
    return {
        "workflow_id": workflow_id.strip(),
        "workflow_version": workflow_version.strip(),
        "workflow_definition_sha256": digest,
    }


def resolve_project_workflow_binding(root: Path | str, channel_slug: str, project: dict[str, Any]) -> dict[str, Any]:
    registry = load_workflow_registry(root)
    channel_slug = channel_workspace.validate_channel_slug(channel_slug)
    workflow_binding = project.get("workflow_binding")
    if workflow_binding is None:
        default = registry["channel_defaults"].get(channel_slug)
        if not default:
            raise _error("WORKFLOW_NOT_CONFIGURED", "No workflow is configured for the selected channel.", 409)
        workflow_id = default["workflow_id"]
        workflow_entry = registry["workflows"][workflow_id]
        version = workflow_entry["legacy_unpinned_version"]
        version_entry = workflow_entry["versions"][version]
        return {
            "workflow_id": workflow_id,
            "workflow_version": version,
            "workflow_definition_sha256": version_entry["definition_sha256"],
            "binding_source": "LEGACY_SYNTHESIZED",
        }

    binding = validate_project_workflow_binding(workflow_binding)
    workflow_entry = registry["workflows"].get(binding["workflow_id"])
    if workflow_entry is None:
        raise _error("WORKFLOW_BINDING_INVALID", "Project workflow_binding references an unknown workflow.", 409)
    version_entry = workflow_entry["versions"].get(binding["workflow_version"])
    if version_entry is None:
        raise _error("WORKFLOW_BINDING_INVALID", "Project workflow_binding references an unknown workflow version.", 409)
    if binding["workflow_definition_sha256"] != version_entry["definition_sha256"]:
        raise _error("WORKFLOW_BINDING_INVALID", "Project workflow_binding digest does not match the registry.", 409)
    binding["binding_source"] = "PROJECT_METADATA"
    return binding


def workflow_state_path(project_dir: Path) -> Path:
    return project_dir / "workflow" / "workflow_state.json"


def _artifact_exists(project_dir: Path, relative_path: str) -> bool:
    return (project_dir / PurePosixPath(relative_path)).exists()


def _is_project_workflow_input_ready(project: dict[str, Any]) -> bool:
    return project.get("workflow_input_status") == "READY" or project.get("status") == "READY_FOR_WORKFLOW"


def _first_and_next_steps(definition: dict[str, Any], current_step_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    steps = sorted(definition["steps"], key=lambda item: item["order"])
    if not steps:
        raise _error("WORKFLOW_DEFINITION_INVALID", "Workflow definition has no steps.")
    if current_step_id is None:
        return steps[0], steps[1] if len(steps) > 1 else None
    for index, step in enumerate(steps):
        if step["step_id"] == current_step_id:
            return step, steps[index + 1] if index + 1 < len(steps) else None
    raise _error("WORKFLOW_STATE_INVALID", "workflow_state current_step_id is not present in the definition.")


def load_or_synthesize_workflow_state(
    root: Path | str,
    channel_slug: str,
    project: dict[str, Any],
    project_dir: Path,
    binding: dict[str, Any],
    definition: dict[str, Any],
) -> dict[str, Any]:
    state_file = workflow_state_path(project_dir)
    if not state_file.exists():
        current_step, next_step = _first_and_next_steps(definition)
        ready = _is_project_workflow_input_ready(project)
        return {
            "initialized": False,
            "state_source": "SYNTHESIZED",
            "current_lifecycle_state": definition["entry_lifecycle_state"] if ready else None,
            "current_step_id": current_step["step_id"],
            "current_step_status": "READY" if ready else "BLOCKED",
            "next_step_id": next_step["step_id"] if next_step else None,
            "blocking_reason": None if ready else "WORKFLOW_INPUT_NOT_READY",
        }

    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.json is malformed JSON.") from exc
    if not isinstance(payload, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state.json must be a JSON object.")
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
        raise _error("WORKFLOW_STATE_INVALID", f"workflow_state.json is missing fields: {', '.join(missing)}")
    if payload["schema_version"] != SUPPORTED_STATE_SCHEMA_VERSION:
        raise _error("WORKFLOW_STATE_INVALID", "Unsupported workflow_state schema_version.")
    if payload["workflow_id"] != binding["workflow_id"] or payload["workflow_version"] != binding["workflow_version"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state workflow id/version does not match the project binding.")
    digest = _validate_digest(
        payload["workflow_definition_sha256"],
        field_name="workflow_state.workflow_definition_sha256",
        code="WORKFLOW_STATE_INVALID",
    )
    if digest != binding["workflow_definition_sha256"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state definition digest does not match the project binding.")
    current_lifecycle_state = payload["current_lifecycle_state"]
    if current_lifecycle_state is not None and current_lifecycle_state not in definition["lifecycle_states"]:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state current_lifecycle_state is not part of the definition.")
    current_step, next_step = _first_and_next_steps(definition, payload["current_step_id"])
    step_states = payload["step_states"]
    if not isinstance(step_states, dict):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state step_states must be an object.")
    valid_step_ids = {step["step_id"] for step in definition["steps"]}
    for step_id, step_state in step_states.items():
        if step_id not in valid_step_ids:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state references unknown step_id {step_id}.")
        if not isinstance(step_state, dict):
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} must be an object.")
        status = step_state.get("status")
        if status not in SUPPORTED_STEP_STATUSES:
            raise _error("WORKFLOW_STATE_INVALID", f"workflow_state for step {step_id} has an unsupported status.")
    _ensure_iso_timestamp(payload["created_at"], "created_at")
    _ensure_iso_timestamp(payload["updated_at"], "updated_at")
    current_step_state = step_states.get(current_step["step_id"], {})
    current_step_status = current_step_state.get("status")
    if current_step_status not in SUPPORTED_STEP_STATUSES:
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state current step is missing a supported status.")
    blocking_reason = payload.get("blocking_reason")
    if blocking_reason is not None and not isinstance(blocking_reason, str):
        raise _error("WORKFLOW_STATE_INVALID", "workflow_state blocking_reason must be a string or null.")
    return {
        "initialized": True,
        "state_source": "FILE",
        "current_lifecycle_state": current_lifecycle_state,
        "current_step_id": current_step["step_id"],
        "current_step_status": current_step_status,
        "next_step_id": next_step["step_id"] if next_step else None,
        "blocking_reason": blocking_reason,
    }


def build_workflow_read_model(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    project: dict[str, Any],
    project_dir: Path,
) -> dict[str, Any]:
    binding = resolve_project_workflow_binding(root, channel_slug, project)
    definition = load_workflow_definition(root, binding["workflow_id"], binding["workflow_version"])
    state = load_or_synthesize_workflow_state(root, channel_slug, project, project_dir, binding, definition)
    artifacts = []
    for artifact in definition["artifacts"]:
        artifacts.append(
            {
                "artifact_id": artifact["artifact_id"],
                "display_name": artifact["display_name"],
                "relative_path": artifact["relative_path"],
                "artifact_role": artifact["artifact_role"],
                "required": artifact["required"],
                "exists": _artifact_exists(project_dir, artifact["relative_path"]),
            }
        )
    return {
        "channel_slug": channel_slug,
        "project_slug": project_slug,
        "binding": {
            "workflow_id": binding["workflow_id"],
            "workflow_version": binding["workflow_version"],
            "workflow_definition_sha256": binding["workflow_definition_sha256"],
            "binding_source": binding["binding_source"],
        },
        "definition": {
            "workflow_id": definition["workflow_id"],
            "workflow_version": definition["workflow_version"],
            "display_name": definition["display_name"],
            "execution_mode": definition["execution_mode"],
            "prompt_set": definition["prompt_set"],
            "entry_lifecycle_state": definition["entry_lifecycle_state"],
            "terminal_lifecycle_state": definition["terminal_lifecycle_state"],
            "lifecycle_states": list(definition["lifecycle_states"]),
            "steps": [
                {
                    "step_id": step["step_id"],
                    "order": step["order"],
                    "display_name": step["display_name"],
                    "required_model": step["required_model"],
                    "input_artifact_ids": list(step["input_artifact_ids"]),
                    "optional_input_artifact_ids": list(step["optional_input_artifact_ids"]),
                    "output_artifact_ids": list(step["output_artifact_ids"]),
                    "resulting_lifecycle_state": step["resulting_lifecycle_state"],
                    "constraints": list(step["constraints"]),
                    "prompt_source_ref": step["prompt_source_ref"],
                }
                for step in definition["steps"]
            ],
        },
        "state": state,
        "artifacts": artifacts,
    }
