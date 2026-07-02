from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

from scripts import channel_prompt_bundle, channel_workflow


SUPPORTED_RESPONSE_MODES = {
    "SINGLE_ARTIFACT",
    "MULTI_ARTIFACT_TOOL_ENVELOPE",
    "MULTI_ARTIFACT_PROMPT_NATIVE",
}


class ChannelOutputParserError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error(code: str, message: str, status: int = 400) -> ChannelOutputParserError:
    return ChannelOutputParserError(code, message, status)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _validate_digest(value: Any, *, field_name: str, code: str) -> str:
    if not isinstance(value, str) or len(value.strip()) != 64:
        raise _error(code, f"{field_name} must be a 64-character SHA-256 hex digest.")
    digest = value.strip().upper()
    if any(ch not in "0123456789ABCDEF" for ch in digest):
        raise _error(code, f"{field_name} must be a valid SHA-256 hex digest.")
    return digest


def _step_map(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["step_id"]: step for step in definition["steps"]}


def _artifact_map(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {artifact["artifact_id"]: artifact for artifact in definition["artifacts"]}


def _contract_artifact_filename(definition_artifact: dict[str, Any]) -> str:
    return PurePosixPath(definition_artifact["relative_path"]).name


def _heading_occurrences(text: str, heading: str) -> list[int]:
    lines = text.splitlines()
    return [index for index, line in enumerate(lines) if line == heading]


def _validate_required_headings(text: str, required_headings: list[str]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    heading_results: list[dict[str, Any]] = []
    first_positions: list[int] = []
    ordered_heading_positions: list[tuple[str, int]] = []

    for heading in required_headings:
        positions = _heading_occurrences(text, heading)
        heading_errors: list[str] = []
        if not positions:
            heading_errors.append("MISSING")
            errors.append(f"Missing required heading: {heading}")
        if len(positions) > 1:
            heading_errors.append("DUPLICATE")
            errors.append(f"Duplicate required heading: {heading}")
        if positions:
            first_positions.append(positions[0])
            ordered_heading_positions.append((heading, positions[0]))
        heading_results.append(
            {
                "heading": heading,
                "status": "VALID" if not heading_errors else "INVALID",
                "occurrences": len(positions),
                "errors": heading_errors,
            }
        )

    if len(first_positions) >= 2:
        for index in range(1, len(ordered_heading_positions)):
            previous_heading, previous_pos = ordered_heading_positions[index - 1]
            current_heading, current_pos = ordered_heading_positions[index]
            if current_pos < previous_pos:
                errors.append(f"Required heading out of order: {current_heading} appears before {previous_heading}.")
                for result in heading_results:
                    if result["heading"] == current_heading and "OUT_OF_ORDER" not in result["errors"]:
                        result["errors"].append("OUT_OF_ORDER")
                        result["status"] = "INVALID"
                        break

    return {
        "status": "VALID" if not errors else "INVALID",
        "errors": errors,
        "warnings": warnings,
        "heading_results": heading_results,
    }


def _single_artifact_parse(
    output_text: str,
    artifact_contract: dict[str, Any],
    definition_artifact: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validation = _validate_required_headings(output_text, list(artifact_contract.get("required_headings", [])))
    artifact_validation_errors = list(validation["errors"])
    if not output_text:
        artifact_validation_errors.append("Artifact content is empty.")
    artifact_validation = {
        "status": "VALID" if not artifact_validation_errors else "INVALID",
        "errors": artifact_validation_errors,
        "warnings": list(validation["warnings"]),
        "heading_results": validation["heading_results"],
    }
    artifact = {
        "artifact_id": artifact_contract["artifact_id"],
        "display_name": definition_artifact["display_name"],
        "filename": _contract_artifact_filename(definition_artifact),
        "content": output_text,
        "sha256": _sha256_bytes(output_text.encode("utf-8")),
        "character_count": len(output_text),
        "validation": artifact_validation,
    }
    top_level_errors = list(artifact_validation_errors)
    return [artifact], {"errors": top_level_errors, "warnings": []}


def _marker_pattern(marker: str) -> re.Pattern[str]:
    return re.compile(rf"(?m)^(?P<marker>{re.escape(marker)})(?P<line_ending>\r\n|\n|\r)?")


def _scan_known_marker_occurrences(output_text: str, markers: list[str]) -> dict[str, list[re.Match[str]]]:
    return {marker: list(_marker_pattern(marker).finditer(output_text)) for marker in markers}


def _scan_unknown_marker_lines(output_text: str, known_markers: set[str]) -> list[str]:
    unknown: list[str] = []
    generic_pattern = re.compile(r"(?m)^(?P<marker>=== FILE .+ ===)(?:\r\n|\n|\r)?")
    for match in generic_pattern.finditer(output_text):
        marker = match.group("marker")
        if marker not in known_markers:
            unknown.append(marker)
    return unknown


def _parse_multi_artifact_output(
    output_text: str,
    response_mode: str,
    contract_artifacts: list[dict[str, Any]],
    definition_artifacts_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    marker_field = "delivery_marker" if response_mode == "MULTI_ARTIFACT_TOOL_ENVELOPE" else "native_marker"
    markers = [artifact[marker_field] for artifact in contract_artifacts]
    known_markers = set(markers)
    marker_occurrences = _scan_known_marker_occurrences(output_text, markers)
    unknown_marker_lines = _scan_unknown_marker_lines(output_text, known_markers)

    errors: list[str] = []
    warnings: list[str] = []
    if unknown_marker_lines:
        for marker in unknown_marker_lines:
            errors.append(f"Unknown output marker line: {marker}")

    ordered_occurrences: list[tuple[int, int, dict[str, Any]]] = []
    for contract_artifact in contract_artifacts:
        marker = contract_artifact[marker_field]
        matches = marker_occurrences[marker]
        if not matches:
            errors.append(f"Missing required marker: {marker}")
            continue
        if len(matches) > 1:
            errors.append(f"Duplicate required marker: {marker}")
            continue
        match = matches[0]
        ordered_occurrences.append((match.start(), match.end(), contract_artifact))

    ordered_occurrences.sort(key=lambda item: item[0])
    if ordered_occurrences:
        prefix = output_text[: ordered_occurrences[0][0]]
        if prefix.strip():
            errors.append("Non-whitespace content appears before the first required marker.")

    expected_marker_order = [artifact[marker_field] for artifact in contract_artifacts]
    actual_marker_order = [artifact[marker_field] for _, _, artifact in ordered_occurrences]
    if len(actual_marker_order) == len(expected_marker_order) and actual_marker_order != expected_marker_order:
        errors.append("Required markers are out of order.")

    if errors:
        return [], {"errors": errors, "warnings": warnings}

    parsed_artifacts: list[dict[str, Any]] = []
    top_level_errors: list[str] = []
    for index, (_, marker_end, contract_artifact) in enumerate(ordered_occurrences):
        next_start = ordered_occurrences[index + 1][0] if index + 1 < len(ordered_occurrences) else len(output_text)
        body = output_text[marker_end:next_start]
        definition_artifact = definition_artifacts_by_id[contract_artifact["artifact_id"]]
        required_headings = list(contract_artifact.get("required_headings", []))
        heading_validation = _validate_required_headings(body, required_headings) if required_headings else {
            "status": "VALID",
            "errors": [],
            "warnings": [],
            "heading_results": [],
        }
        artifact_errors = list(heading_validation["errors"])
        if not body:
            artifact_errors.append(f"Parsed artifact {contract_artifact['artifact_id']} is empty.")
        parsed_artifacts.append(
            {
                "artifact_id": contract_artifact["artifact_id"],
                "display_name": definition_artifact["display_name"],
                "filename": _contract_artifact_filename(definition_artifact),
                "content": body,
                "sha256": _sha256_bytes(body.encode("utf-8")),
                "character_count": len(body),
                "validation": {
                    "status": "VALID" if not artifact_errors else "INVALID",
                    "errors": artifact_errors,
                    "warnings": list(heading_validation["warnings"]),
                    "heading_results": heading_validation["heading_results"],
                },
            }
        )
        top_level_errors.extend(artifact_errors)

    return parsed_artifacts, {"errors": top_level_errors, "warnings": warnings}


def _parse_output_against_contract(
    output_text: str,
    output_contract: dict[str, Any],
    definition: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    response_mode = output_contract.get("response_mode")
    if response_mode not in SUPPORTED_RESPONSE_MODES:
        raise _error("OUTPUT_CONTRACT_INVALID", "The selected workflow step has an unsupported output contract.", 409)
    contract_artifacts = output_contract.get("artifacts")
    if not isinstance(contract_artifacts, list) or not contract_artifacts:
        raise _error("OUTPUT_CONTRACT_INVALID", "The selected workflow step has an invalid output contract.", 409)

    definition_artifacts_by_id = _artifact_map(definition)
    for contract_artifact in contract_artifacts:
        artifact_id = contract_artifact.get("artifact_id")
        if artifact_id not in definition_artifacts_by_id:
            raise _error("OUTPUT_CONTRACT_INVALID", "The selected workflow step output contract is inconsistent with workflow artifacts.", 409)

    if response_mode == "SINGLE_ARTIFACT":
        if len(contract_artifacts) != 1:
            raise _error("OUTPUT_CONTRACT_INVALID", "SINGLE_ARTIFACT mode must declare exactly one artifact.", 409)
        contract_artifact = contract_artifacts[0]
        return _single_artifact_parse(output_text, contract_artifact, definition_artifacts_by_id[contract_artifact["artifact_id"]])

    return _parse_multi_artifact_output(output_text, response_mode, contract_artifacts, definition_artifacts_by_id)


def parse_channel_output(
    root: Path | str,
    channel_slug: str,
    project_slug: str,
    step_id: str,
    bundle_sha256: Any,
    output_text: Any,
    project: dict[str, Any],
    project_dir: Path,
) -> dict[str, Any]:
    provided_bundle_sha256 = _validate_digest(
        bundle_sha256,
        field_name="bundle_sha256",
        code="BUNDLE_IDENTITY_MISMATCH",
    )
    if not isinstance(output_text, str) or not output_text.strip():
        raise _error("OUTPUT_TEXT_REQUIRED", "Pasted AI output is required.", 400)

    binding = channel_workflow.resolve_project_workflow_binding(root, channel_slug, project)
    definition = channel_workflow.load_workflow_definition(root, binding["workflow_id"], binding["workflow_version"])
    steps = _step_map(definition)
    step = steps.get(step_id)
    if step is None:
        raise _error("WORKFLOW_STEP_NOT_FOUND", "The selected workflow step was not found for this project binding.", 404)

    bundle = channel_prompt_bundle.build_prompt_bundle(
        root,
        channel_slug,
        project_slug,
        step_id,
        project,
        project_dir,
    )
    if bundle["bundle_sha256"] != provided_bundle_sha256:
        raise _error("BUNDLE_IDENTITY_MISMATCH", "The pasted AI output does not match the currently loaded workflow bundle.", 409)

    output_contract = bundle.get("output_contract")
    if not isinstance(output_contract, dict):
        raise _error("OUTPUT_CONTRACT_INVALID", "The selected workflow step does not expose a valid output contract.", 409)

    artifacts, validation = _parse_output_against_contract(output_text, output_contract, definition)
    status = "VALID" if not validation["errors"] and all(item["validation"]["status"] == "VALID" for item in artifacts) else "INVALID"
    return {
        "identity": {
            "channel_slug": channel_slug,
            "project_slug": project_slug,
            "workflow_id": binding["workflow_id"],
            "workflow_version": binding["workflow_version"],
            "step_id": step_id,
            "bundle_sha256": bundle["bundle_sha256"],
        },
        "raw_output": {
            "sha256": _sha256_bytes(output_text.encode("utf-8")),
            "character_count": len(output_text),
        },
        "contract": {
            "response_mode": output_contract["response_mode"],
        },
        "status": status,
        "artifacts": artifacts,
        "validation": {
            "errors": list(validation["errors"]),
            "warnings": list(validation["warnings"]),
        },
    }
