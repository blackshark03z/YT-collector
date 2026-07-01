from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from scripts import channel_projects, channel_workflow


SUPPORTED_PROMPT_MANIFEST_SCHEMA_VERSION = 1
SUPPORTED_RESPONSE_MODES = {
    "SINGLE_ARTIFACT",
    "MULTI_ARTIFACT_TOOL_ENVELOPE",
    "MULTI_ARTIFACT_PROMPT_NATIVE",
}
TOOL_DELIVERY_CONTRACT_VERSION = "1"
WORKFLOW_PLACEHOLDER_SENTINEL = "TODO: Fill manually during Workflow V2."


class PromptBundleError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error(code: str, message: str, status: int = 400) -> PromptBundleError:
    return PromptBundleError(code, message, status)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _validate_digest(value: Any, *, field_name: str, code: str) -> str:
    if not isinstance(value, str) or len(value.strip()) != 64:
        raise _error(code, f"{field_name} must be a 64-character SHA-256 hex digest.")
    digest = value.strip().upper()
    if any(ch not in "0123456789ABCDEF" for ch in digest):
        raise _error(code, f"{field_name} must be a valid SHA-256 hex digest.")
    return digest


def _safe_relative_path(value: Any, *, field_name: str, code: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise _error(code, f"{field_name} must be a non-empty relative path.")
    raw = value.strip()
    if "\\" in raw:
        raise _error(code, f"{field_name} must use forward slashes only.")
    if PureWindowsPath(raw).drive:
        raise _error(code, f"{field_name} must not contain a drive prefix.")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or "." in pure.parts or ".." in pure.parts:
        raise _error(code, f"{field_name} must stay within the workflow version directory.")
    return pure


def _safe_resolve(base_dir: Path, relative_path: str, *, field_name: str, code: str) -> Path:
    safe = _safe_relative_path(relative_path, field_name=field_name, code=code)
    resolved_base = base_dir.resolve()
    resolved = (resolved_base / safe).resolve()
    try:
        resolved.relative_to(resolved_base)
    except ValueError as exc:
        raise _error(code, f"{field_name} escapes the workflow version directory.") from exc
    return resolved


def _artifact_map(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {artifact["artifact_id"]: artifact for artifact in definition["artifacts"]}


def _step_map(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["step_id"]: step for step in definition["steps"]}


def _step_ref_map(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for step in definition["steps"]:
        ref = step["prompt_source_ref"]
        if not isinstance(ref, str) or not ref.strip():
            raise _error("PROMPT_SET_UNAVAILABLE", "The workflow does not expose prompt bundle metadata for every step.", 409)
        refs[ref.strip()] = step
    return refs


def _format_constraint_summary(constraints: list[dict[str, Any]]) -> list[str]:
    if not constraints:
        return []
    summaries = []
    for constraint in constraints:
        constraint_type = constraint.get("type", "")
        group_id = constraint.get("group_id")
        if group_id:
            summaries.append(f"{constraint_type} ({group_id})")
        else:
            summaries.append(str(constraint_type))
    return summaries


def _derive_project_topic(project: dict[str, Any]) -> str:
    slug = project.get("project_slug", "").strip()
    if len(slug) > 9 and slug[:8].isdigit() and slug[8] == "_":
        slug = slug[9:]
    return slug.replace("-", " ").strip() or project.get("project_slug", "").strip()


def _load_competitor_video_metadata(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "input" / "_raw" / "competitor_video.json"
    if not path.exists() or not path.is_file():
        raise _error("BUNDLE_PROJECT_CONTEXT_MISSING", "Canonical competitor metadata is missing for required project context.", 409)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("BUNDLE_PROJECT_CONTEXT_MISSING", "Canonical competitor metadata is unreadable for required project context.", 409) from exc
    if not isinstance(payload, dict):
        raise _error("BUNDLE_PROJECT_CONTEXT_MISSING", "Canonical competitor metadata is malformed for required project context.", 409)
    return payload


def _context_value(project: dict[str, Any], project_dir: Path, item: dict[str, Any]) -> tuple[str, str]:
    source = item["source"]
    if source == "project_slug":
        return project["project_slug"], "project.json:project_slug"
    if source == "source_video_id":
        return project["source_video_id"], "project.json:source_video_id"
    if source == "source_video_url":
        return project["source_video_url"], "project.json:source_video_url"
    if source == "source_metadata_title":
        metadata = _load_competitor_video_metadata(project_dir)
        title = metadata.get("title")
        if not isinstance(title, str) or not title.strip():
            raise _error("BUNDLE_PROJECT_CONTEXT_MISSING", "Canonical competitor metadata does not contain a usable title for Topic.", 409)
        return title.strip(), "input/_raw/competitor_video.json:title"
    if source == "unavailable":
        return "NOT PROVIDED IN CANONICAL PROJECT", "UNAVAILABLE"
    raise _error("PROMPT_MANIFEST_INVALID", f"Unsupported context source {source}.", 409)


def _required_text_list(value: Any, *, field_name: str, code: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise _error(code, f"{field_name} must be a non-empty list of strings.")
    return [item.strip() for item in value]


def _validate_output_contract(
    step: dict[str, Any],
    output_contract: Any,
    prompt_text: str,
    *,
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(output_contract, dict):
        raise _error("PROMPT_MANIFEST_INVALID", f"{field_name} must be an object.", 409)
    response_mode = output_contract.get("response_mode")
    if response_mode not in SUPPORTED_RESPONSE_MODES:
        raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}.response_mode is unsupported.", 409)
    artifacts = output_contract.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}.artifacts must be a non-empty list.", 409)
    workflow_outputs = list(step["output_artifact_ids"])
    normalized_artifacts: list[dict[str, Any]] = []
    seen_artifact_ids: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}.artifacts[{index}] must be an object.", 409)
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str) or artifact_id not in workflow_outputs:
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}.artifacts[{index}].artifact_id is inconsistent with workflow outputs.", 409)
        if artifact_id in seen_artifact_ids:
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name} contains duplicate output artifact {artifact_id}.", 409)
        seen_artifact_ids.add(artifact_id)
        normalized = {"artifact_id": artifact_id}
        if response_mode == "SINGLE_ARTIFACT":
            normalized["required_headings"] = _required_text_list(
                artifact.get("required_headings"),
                field_name=f"{field_name}.artifacts[{index}].required_headings",
                code="PROMPT_MANIFEST_INVALID",
            )
        elif response_mode == "MULTI_ARTIFACT_TOOL_ENVELOPE":
            delivery_marker = artifact.get("delivery_marker")
            if not isinstance(delivery_marker, str) or not delivery_marker.strip():
                raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}.artifacts[{index}].delivery_marker is required.", 409)
            normalized["delivery_marker"] = delivery_marker.strip()
            normalized["required_headings"] = _required_text_list(
                artifact.get("required_headings"),
                field_name=f"{field_name}.artifacts[{index}].required_headings",
                code="PROMPT_MANIFEST_INVALID",
            )
            if normalized["delivery_marker"] in prompt_text:
                raise _error("PROMPT_MANIFEST_INVALID", "Tool-owned delivery markers must not already exist in the canonical prompt text.", 409)
        else:
            native_marker = artifact.get("native_marker")
            if not isinstance(native_marker, str) or not native_marker.strip():
                raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}.artifacts[{index}].native_marker is required.", 409)
            normalized["native_marker"] = native_marker.strip()
            if normalized["native_marker"] not in prompt_text:
                raise _error("PROMPT_MANIFEST_INVALID", "A prompt-native marker declared in the manifest is missing from the canonical prompt file.", 409)
        normalized_artifacts.append(normalized)

    if set(seen_artifact_ids) != set(workflow_outputs):
        raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}.artifacts must match workflow outputs exactly.", 409)
    if response_mode == "SINGLE_ARTIFACT" and len(normalized_artifacts) != 1:
        raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}.artifacts must contain exactly one artifact for SINGLE_ARTIFACT mode.", 409)
    return {"response_mode": response_mode, "artifacts": normalized_artifacts}


def _validate_project_context_items(value: Any, *, field_name: str) -> list[dict[str, Any]]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise _error("PROMPT_MANIFEST_INVALID", f"{field_name} must be a list when provided.", 409)
    normalized = []
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}[{index}] must be an object.", 409)
        context_id = item.get("context_id")
        label = item.get("label")
        source = item.get("source")
        required = item.get("required")
        if not isinstance(context_id, str) or not context_id.strip():
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}[{index}].context_id is required.", 409)
        if context_id in seen_ids:
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name} contains duplicate context_id {context_id}.", 409)
        seen_ids.add(context_id)
        if not isinstance(label, str) or not label.strip():
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}[{index}].label is required.", 409)
        if source not in {"project_slug", "source_video_id", "source_video_url", "source_metadata_title", "unavailable"}:
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}[{index}].source is unsupported.", 409)
        if not isinstance(required, bool):
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}[{index}].required must be boolean.", 409)
        note = item.get("note")
        if note is not None and (not isinstance(note, str) or not note.strip()):
            raise _error("PROMPT_MANIFEST_INVALID", f"{field_name}[{index}].note must be a non-empty string when provided.", 409)
        normalized.append(
            {
                "context_id": context_id.strip(),
                "label": label.strip(),
                "source": source,
                "required": required,
                "note": note.strip() if isinstance(note, str) else None,
            }
        )
    return normalized


def load_prompt_manifest(
    root: Path | str,
    workflow_id: str,
    workflow_version: str,
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    definition = definition or channel_workflow.load_workflow_definition(root, workflow_id, workflow_version)
    prompt_set = definition["prompt_set"]
    if prompt_set.get("status") != "AVAILABLE" or not prompt_set.get("bundle_available"):
        raise _error("PROMPT_SET_UNAVAILABLE", "The pinned workflow version does not expose an available prompt set.", 409)

    version_dir = channel_workflow.resolve_workflow_definition_path(root, workflow_id, workflow_version).parent
    manifest_path = _safe_resolve(
        version_dir,
        prompt_set["manifest_path"],
        field_name="prompt_set.manifest_path",
        code="PROMPT_MANIFEST_INVALID",
    )
    if not manifest_path.exists():
        raise _error("PROMPT_MANIFEST_INVALID", "The prompt-set manifest file does not exist.", 409)
    manifest_bytes = manifest_path.read_bytes()
    manifest_digest = _sha256_bytes(manifest_bytes)
    if manifest_digest != prompt_set["manifest_sha256"]:
        raise _error("PROMPT_MANIFEST_INVALID", "The prompt-set manifest digest does not match the workflow definition.", 409)
    try:
        payload = json.loads(manifest_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise _error("PROMPT_MANIFEST_INVALID", "The prompt-set manifest is malformed JSON.") from exc
    if not isinstance(payload, dict):
        raise _error("PROMPT_MANIFEST_INVALID", "The prompt-set manifest must be a JSON object.", 409)
    if payload.get("schema_version") != SUPPORTED_PROMPT_MANIFEST_SCHEMA_VERSION:
        raise _error("PROMPT_MANIFEST_INVALID", "Unsupported prompt-set manifest schema_version.", 409)
    if payload.get("prompt_set_id") != prompt_set["prompt_set_id"]:
        raise _error("PROMPT_MANIFEST_INVALID", "prompt_set_id does not match the workflow definition.", 409)
    if payload.get("prompt_set_version") != prompt_set["version"]:
        raise _error("PROMPT_MANIFEST_INVALID", "prompt_set_version does not match the workflow definition.", 409)

    source_document = payload.get("source_document")
    if not isinstance(source_document, dict):
        raise _error("PROMPT_MANIFEST_INVALID", "source_document must be an object.", 409)
    filename = source_document.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        raise _error("PROMPT_MANIFEST_INVALID", "source_document.filename is required.", 409)
    source_digest = _validate_digest(
        source_document.get("sha256"),
        field_name="source_document.sha256",
        code="PROMPT_MANIFEST_INVALID",
    )

    prompts = payload.get("prompts")
    if not isinstance(prompts, dict) or not prompts:
        raise _error("PROMPT_MANIFEST_INVALID", "prompts must be a non-empty object.", 409)
    step_refs = _step_ref_map(definition)
    if set(prompts) != set(step_refs):
        raise _error("PROMPT_MANIFEST_INVALID", "The prompt-set manifest must contain exactly one entry for every executable workflow step.", 409)

    normalized_prompts: dict[str, Any] = {}
    for prompt_ref, entry in prompts.items():
        if not isinstance(entry, dict):
            raise _error("PROMPT_MANIFEST_INVALID", f"Prompt entry {prompt_ref} must be an object.", 409)
        relative_path = entry.get("relative_path")
        prompt_path = _safe_resolve(
            manifest_path.parent,
            relative_path,
            field_name=f"prompts.{prompt_ref}.relative_path",
            code="PROMPT_MANIFEST_INVALID",
        )
        try:
            prompt_path.relative_to(version_dir.resolve())
        except ValueError as exc:
            raise _error("PROMPT_MANIFEST_INVALID", f"prompts.{prompt_ref}.relative_path escapes the workflow version directory.") from exc
        if not prompt_path.exists():
            raise _error("PROMPT_FILE_NOT_FOUND", f"The canonical prompt file for {prompt_ref} does not exist.", 404)
        prompt_bytes = prompt_path.read_bytes()
        if not prompt_bytes.strip():
            raise _error("PROMPT_FILE_NOT_FOUND", f"The canonical prompt file for {prompt_ref} is empty.", 404)
        prompt_digest = _validate_digest(
            entry.get("sha256"),
            field_name=f"prompts.{prompt_ref}.sha256",
            code="PROMPT_MANIFEST_INVALID",
        )
        actual_prompt_digest = _sha256_bytes(prompt_bytes)
        if actual_prompt_digest != prompt_digest:
            raise _error("PROMPT_FILE_DIGEST_MISMATCH", f"The canonical prompt file digest for {prompt_ref} does not match the manifest.", 409)
        prompt_text = prompt_bytes.decode("utf-8")
        output_contract = _validate_output_contract(
            step_refs[prompt_ref],
            entry.get("output_contract"),
            prompt_text,
            field_name=f"prompts.{prompt_ref}.output_contract",
        )
        normalized_prompts[prompt_ref] = {
            "relative_path": _safe_relative_path(relative_path, field_name=f"prompts.{prompt_ref}.relative_path", code="PROMPT_MANIFEST_INVALID").as_posix(),
            "sha256": prompt_digest,
            "prompt_text": prompt_text,
            "output_contract": output_contract,
            "project_context": _validate_project_context_items(
                entry.get("project_context"),
                field_name=f"prompts.{prompt_ref}.project_context",
            ),
        }

    return {
        "schema_version": SUPPORTED_PROMPT_MANIFEST_SCHEMA_VERSION,
        "prompt_set_id": prompt_set["prompt_set_id"],
        "prompt_set_version": prompt_set["version"],
        "manifest_sha256": manifest_digest,
        "source_document": {"filename": filename.strip(), "sha256": source_digest},
        "prompts": normalized_prompts,
        "version_dir": version_dir,
        "manifest_path": manifest_path,
    }


def _artifact_usability_error(path: Path, artifact_id: str) -> bool:
    if not path.exists() or not path.is_file():
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return True
    if not text.strip():
        return True
    if WORKFLOW_PLACEHOLDER_SENTINEL in text:
        return True
    if artifact_id == "competitor_transcript" and channel_projects.is_transcript_template(path):
        return True
    return False


def _read_artifact(project_dir: Path, artifact: dict[str, Any]) -> tuple[Path, bytes, str]:
    artifact_path = project_dir / PurePosixPath(artifact["relative_path"])
    if _artifact_usability_error(artifact_path, artifact["artifact_id"]):
        raise _error("BUNDLE_REQUIRED_INPUT_MISSING", f"Required input artifact {artifact['artifact_id']} is missing or unusable.", 409)
    data = artifact_path.read_bytes()
    text = data.decode("utf-8")
    return artifact_path, data, text


def _build_tool_delivery_contract(output_contract: dict[str, Any]) -> str:
    lines = [
        "=== TOOL OUTPUT DELIVERY CONTRACT ===",
        "Tool-owned delivery envelope:",
        "Return the final response exactly in this file order:",
    ]
    for artifact in output_contract["artifacts"]:
        lines.append(artifact["delivery_marker"])
        lines.append(f"[{artifact['artifact_id']} contents]")
    lines.append("Do not add any text before the first file marker or after the final file marker.")
    lines.append(f"Delivery Contract Version: {TOOL_DELIVERY_CONTRACT_VERSION}")
    return "\n".join(lines)


def build_prompt_bundle(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    step_id: str,
    project: dict[str, Any],
    project_dir: Path,
) -> dict[str, Any]:
    binding = channel_workflow.resolve_project_workflow_binding(root, channel_slug, project)
    definition = channel_workflow.load_workflow_definition(root, binding["workflow_id"], binding["workflow_version"])
    manifest = load_prompt_manifest(root, binding["workflow_id"], binding["workflow_version"], definition)
    steps = _step_map(definition)
    step = steps.get(step_id)
    if step is None:
        raise _error("WORKFLOW_STEP_NOT_FOUND", "The selected workflow step was not found for this project binding.", 404)
    prompt_ref = step["prompt_source_ref"]
    prompt_entry = manifest["prompts"].get(prompt_ref)
    if prompt_entry is None:
        raise _error("PROMPT_MANIFEST_INVALID", "The prompt-set manifest does not define the selected workflow step.", 409)

    artifacts_by_id = _artifact_map(definition)
    required_blocks: list[str] = []
    required_artifact_ids: list[str] = []
    required_hashes: dict[str, str] = {}
    missing_required: list[str] = []
    for artifact_id in step["input_artifact_ids"]:
        artifact = artifacts_by_id[artifact_id]
        artifact_path = project_dir / PurePosixPath(artifact["relative_path"])
        if _artifact_usability_error(artifact_path, artifact_id):
            missing_required.append(artifact_id)
            continue
        data = artifact_path.read_bytes()
        required_hashes[artifact_id] = _sha256_bytes(data)
        required_artifact_ids.append(artifact_id)
        required_blocks.append(f"--- ARTIFACT: {PurePosixPath(artifact['relative_path']).name} ---\n{data.decode('utf-8').rstrip()}")
    if missing_required:
        raise _error(
            "BUNDLE_REQUIRED_INPUT_MISSING",
            f"Required input artifacts are missing or unusable: {', '.join(missing_required)}",
            409,
        )

    optional_blocks: list[str] = []
    missing_optional_inputs: list[str] = []
    for artifact_id in step["optional_input_artifact_ids"]:
        artifact = artifacts_by_id[artifact_id]
        artifact_path = project_dir / PurePosixPath(artifact["relative_path"])
        if _artifact_usability_error(artifact_path, artifact_id):
            missing_optional_inputs.append(artifact_id)
            optional_blocks.append(f"--- OPTIONAL ARTIFACT: {PurePosixPath(artifact['relative_path']).name} ---\nNOT PROVIDED")
            continue
        data = artifact_path.read_bytes()
        optional_blocks.append(f"--- OPTIONAL ARTIFACT: {PurePosixPath(artifact['relative_path']).name} ---\n{data.decode('utf-8').rstrip()}")

    project_context_lines: list[str] = []
    project_context_metadata: dict[str, dict[str, str]] = {}
    for item in prompt_entry["project_context"]:
        value, source_field = _context_value(project, project_dir, item)
        label = item["label"]
        project_context_metadata[item["context_id"]] = {
            "value": value,
            "source_field": source_field,
        }
        if item["note"]:
            project_context_lines.append(f"- {label}: {value}")
            project_context_lines.append(f"  Source: {source_field}")
            project_context_lines.append(f"  Note: {item['note']}")
        else:
            project_context_lines.append(f"- {label}: {value}")
            project_context_lines.append(f"  Source: {source_field}")

    bundle_sections = [
        "=== ASSISTED WORKFLOW CONTEXT ===",
        f"Workflow: {definition['workflow_id']}",
        f"Workflow Version: {definition['workflow_version']}",
        f"Prompt Set: {manifest['prompt_set_id']} v{manifest['prompt_set_version']}",
        f"Channel: {channel_slug}",
        f"Project: {project_slug}",
        f"Step: {step['step_id']}",
        f"Required Model: {step['required_model']}",
        "Conversation Requirement: " + (", ".join(_format_constraint_summary(step["constraints"])) or "NONE"),
        "",
        "=== AUTHORITATIVE PROMPT ===",
        prompt_entry["prompt_text"].rstrip(),
        "",
        "=== REQUIRED INPUT ARTIFACTS ===",
        "\n\n".join(required_blocks),
        "",
        "=== OPTIONAL INPUT ARTIFACTS ===",
        "\n\n".join(optional_blocks) if optional_blocks else "No optional input artifacts are defined for this step.",
        "",
        "=== PROJECT CONTEXT ===",
        "\n".join(project_context_lines) if project_context_lines else "No additional project context is defined for this step.",
    ]
    if prompt_entry["output_contract"]["response_mode"] == "MULTI_ARTIFACT_TOOL_ENVELOPE":
        bundle_sections.extend(["", _build_tool_delivery_contract(prompt_entry["output_contract"])])
    bundle = "\n".join(bundle_sections).rstrip() + "\n"
    return {
        "channel_slug": channel_slug,
        "project_slug": project_slug,
        "step_id": step["step_id"],
        "binding": {
            "workflow_id": binding["workflow_id"],
            "workflow_version": binding["workflow_version"],
            "workflow_definition_sha256": binding["workflow_definition_sha256"],
            "binding_source": binding["binding_source"],
        },
        "prompt_set": {
            "prompt_set_id": manifest["prompt_set_id"],
            "prompt_set_version": manifest["prompt_set_version"],
            "manifest_sha256": manifest["manifest_sha256"],
            "source_document": manifest["source_document"],
        },
        "bundle": bundle,
        "bundle_sha256": _sha256_bytes(bundle.encode("utf-8")),
        "bundle_character_count": len(bundle),
        "prompt_file_sha256": prompt_entry["sha256"],
        "input_artifact_ids": required_artifact_ids,
        "input_artifact_sha256": required_hashes,
        "missing_optional_inputs": missing_optional_inputs,
        "project_context": project_context_metadata,
        "required_model": step["required_model"],
        "conversation_constraints": list(step["constraints"]),
        "output_contract": prompt_entry["output_contract"],
    }
