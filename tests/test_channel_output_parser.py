import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_output_parser, channel_projects, channel_workspace
from tests.test_channel_prompt_bundle import (
    copy_workflows,
    make_channel,
    create_project,
    prepare_step2_inputs,
    prepare_prompt7_inputs,
)
from tests.runtime_isolation_helpers import snapshot_runtime_state


def make_v2_project(root: Path, channel_slug: str = "mist_of_ages", video_id: str = "VIDEO12345A") -> tuple[dict, Path]:
    copy_workflows(root)
    make_channel(root, channel_slug, "UC123")
    registry = root / "workflows" / "registry.json"
    payload = registry.read_text(encoding="utf-8")
    payload = payload.replace('"default_version": "1"', '"default_version": "2"', 1)
    registry.write_text(payload, encoding="utf-8", newline="\n")
    project = create_project(root, channel_slug, video_id)
    project_dir = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project["project_slug"]
    return project, project_dir


def parse_for_step(
    root: Path,
    project: dict,
    project_dir: Path,
    step_id: str,
    output_text: str,
    *,
    channel_slug: str = "mist_of_ages",
) -> dict:
    bundle = __import__("scripts.channel_prompt_bundle", fromlist=[""]).build_prompt_bundle(
        root,
        channel_slug,
        project["project_slug"],
        step_id,
        channel_projects.load_channel_project(root, channel_slug, project["project_slug"]),
        project_dir,
    )
    project_data = channel_projects.load_channel_project(root, channel_slug, project["project_slug"])
    return channel_output_parser.parse_channel_output(
        root,
        channel_slug,
        project["project_slug"],
        step_id,
        bundle["bundle_sha256"],
        output_text,
        project_data,
        project_dir,
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def build_generic_three_artifact_fixture(root: Path) -> tuple[dict, Path]:
    copy_workflows(root)
    make_channel(root, "mist_of_ages", "UC123")
    v3_dir = root / "workflows" / "mist_of_ages_assisted_content" / "v3"
    prompt_dir = v3_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": 1,
        "prompt_set_id": "parser_fixture",
        "prompt_set_version": "3",
        "source_document": {"filename": "fixture.docx", "sha256": "A" * 64},
        "prompts": {
            "alpha_single_custom": {
                "relative_path": "alpha.md",
                "sha256": "",
                "output_contract": {
                    "response_mode": "SINGLE_ARTIFACT",
                    "artifacts": [
                        {"artifact_id": "alpha_notes_custom", "required_headings": ["# Alpha", "## Beta"]}
                    ],
                },
            },
            "beta_envelope_custom": {
                "relative_path": "beta.md",
                "sha256": "",
                "output_contract": {
                    "response_mode": "MULTI_ARTIFACT_TOOL_ENVELOPE",
                    "artifacts": [
                        {"artifact_id": "brief_custom", "delivery_marker": "=== FILE 1: brief.custom ===", "required_headings": ["# Brief"]},
                        {"artifact_id": "facts_custom", "delivery_marker": "=== FILE 2: facts.custom ===", "required_headings": ["# Facts"]},
                        {"artifact_id": "notes_custom", "delivery_marker": "=== FILE 3: notes.custom ===", "required_headings": ["# Notes"]},
                    ],
                },
            },
            "gamma_native_custom": {
                "relative_path": "gamma.md",
                "sha256": "",
                "output_contract": {
                    "response_mode": "MULTI_ARTIFACT_PROMPT_NATIVE",
                    "artifacts": [
                        {"artifact_id": "story_custom", "native_marker": "=== FILE 1: story.custom ===", "required_headings": ["# Story"]},
                        {"artifact_id": "package_custom", "native_marker": "=== FILE 2: package.custom ===", "required_headings": ["# Package"]},
                        {"artifact_id": "summary_custom", "native_marker": "=== FILE 3: summary.custom ===", "required_headings": ["# Summary"]},
                    ],
                },
            },
        },
    }
    prompt_files = {
        "alpha.md": "ALPHA\n",
        "beta.md": "BETA\n",
        "gamma.md": "GAMMA\n=== FILE 1: story.custom ===\n[story]\n=== FILE 2: package.custom ===\n[package]\n=== FILE 3: summary.custom ===\n[summary]\n",
    }
    for filename, text in prompt_files.items():
        path = prompt_dir / filename
        path.write_text(text, encoding="utf-8", newline="\n")
        for prompt in manifest["prompts"].values():
            if prompt["relative_path"] == filename:
                prompt["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    write_json(prompt_dir / "manifest.json", manifest)

    workflow = {
        "schema_version": 1,
        "workflow_id": "mist_of_ages_assisted_content",
        "workflow_version": "3",
        "display_name": "Parser Fixture",
        "execution_mode": "LINEAR",
        "entry_lifecycle_state": "INPUT_READY",
        "terminal_lifecycle_state": "DONE",
        "lifecycle_states": ["INPUT_READY", "ALPHA_READY", "BETA_READY", "DONE"],
        "prompt_set": {
            "status": "AVAILABLE",
            "prompt_set_id": "parser_fixture",
            "version": "3",
            "manifest_path": "prompts/manifest.json",
            "manifest_sha256": hashlib.sha256((prompt_dir / "manifest.json").read_bytes()).hexdigest().upper(),
            "bundle_available": True,
        },
        "artifacts": [
            {"artifact_id": "competitor_transcript", "display_name": "Competitor Transcript", "relative_path": "research/competitor_transcript.md", "artifact_role": "INPUT", "required": True, "media_type": "text/markdown"},
            {"artifact_id": "alpha_notes_custom", "display_name": "Alpha Notes", "relative_path": "workflow/alpha_notes_custom.md", "artifact_role": "GENERATED", "required": True, "media_type": "text/markdown"},
            {"artifact_id": "brief_custom", "display_name": "Brief", "relative_path": "workflow/brief_custom.md", "artifact_role": "GENERATED", "required": True, "media_type": "text/markdown"},
            {"artifact_id": "facts_custom", "display_name": "Facts", "relative_path": "workflow/facts_custom.md", "artifact_role": "GENERATED", "required": True, "media_type": "text/markdown"},
            {"artifact_id": "notes_custom", "display_name": "Notes", "relative_path": "workflow/notes_custom.md", "artifact_role": "GENERATED", "required": True, "media_type": "text/markdown"},
            {"artifact_id": "story_custom", "display_name": "Story", "relative_path": "workflow/story_custom.md", "artifact_role": "FINAL", "required": True, "media_type": "text/markdown"},
            {"artifact_id": "package_custom", "display_name": "Package", "relative_path": "workflow/package_custom.md", "artifact_role": "FINAL", "required": True, "media_type": "text/markdown"},
            {"artifact_id": "summary_custom", "display_name": "Summary", "relative_path": "workflow/summary_custom.md", "artifact_role": "FINAL", "required": True, "media_type": "text/markdown"},
        ],
        "steps": [
            {"step_id": "alpha_single_custom", "order": 1, "display_name": "Alpha", "required_model": "Model A", "input_artifact_ids": ["competitor_transcript"], "optional_input_artifact_ids": [], "output_artifact_ids": ["alpha_notes_custom"], "resulting_lifecycle_state": "ALPHA_READY", "constraints": [], "prompt_source_ref": "alpha_single_custom"},
            {"step_id": "beta_envelope_custom", "order": 2, "display_name": "Beta", "required_model": "Model B", "input_artifact_ids": ["alpha_notes_custom"], "optional_input_artifact_ids": [], "output_artifact_ids": ["brief_custom", "facts_custom", "notes_custom"], "resulting_lifecycle_state": "BETA_READY", "constraints": [], "prompt_source_ref": "beta_envelope_custom"},
            {"step_id": "gamma_native_custom", "order": 3, "display_name": "Gamma", "required_model": "Model C", "input_artifact_ids": ["brief_custom", "facts_custom", "notes_custom"], "optional_input_artifact_ids": [], "output_artifact_ids": ["story_custom", "package_custom", "summary_custom"], "resulting_lifecycle_state": "DONE", "constraints": [], "prompt_source_ref": "gamma_native_custom"},
        ],
    }
    write_json(v3_dir / "workflow.json", workflow)
    registry_path = root / "workflows" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["workflows"]["mist_of_ages_assisted_content"]["versions"]["3"] = {
        "status": "ACTIVE",
        "definition_path": "mist_of_ages_assisted_content/v3/workflow.json",
        "definition_sha256": hashlib.sha256((v3_dir / "workflow.json").read_bytes()).hexdigest().upper(),
    }
    registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "3"
    registry["channel_defaults"]["mist_of_ages"] = {"workflow_id": "mist_of_ages_assisted_content"}
    write_json(registry_path, registry)

    project = create_project(root, "mist_of_ages", "VIDEO12345Z")
    channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
    project_dir = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project["project_slug"]
    (project_dir / "workflow" / "alpha_notes_custom.md").write_text("# Alpha\n## Beta\n", encoding="utf-8", newline="\n")
    (project_dir / "workflow" / "brief_custom.md").write_text("# Brief\n", encoding="utf-8", newline="\n")
    (project_dir / "workflow" / "facts_custom.md").write_text("# Facts\n", encoding="utf-8", newline="\n")
    (project_dir / "workflow" / "notes_custom.md").write_text("# Notes\n", encoding="utf-8", newline="\n")
    return project, project_dir


class ChannelOutputParserTests(unittest.TestCase):
    def test_single_artifact_output_parses_and_preserves_exact_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            output_text = (
                "## Subject\nRome\n"
                "## Competitor Promise\nPromise\n"
                "## Narrative Map\nMap\n"
                "## Strong Idea-Level Elements\nStrong\n"
                "## Weak or Removable Elements\nWeak\n"
                "## Claims Requiring Verification\nClaims\n"
                "## Originality Risks\nRisks\n"
                "## Neutral Research Questions\nQuestions\n"
            )
            parsed = parse_for_step(root, project, project_dir, "prompt_1_transcript_analysis", output_text)
            self.assertEqual(parsed["status"], "VALID")
            self.assertEqual(parsed["raw_output"]["character_count"], len(output_text))
            self.assertEqual(parsed["artifacts"][0]["content"], output_text)
            self.assertEqual(parsed["artifacts"][0]["validation"]["status"], "VALID")

    def test_single_artifact_missing_heading_returns_invalid_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            output_text = "## Subject\nRome\n## Competitor Promise\nPromise\n"
            parsed = parse_for_step(root, project, project_dir, "prompt_1_transcript_analysis", output_text)
            self.assertEqual(parsed["status"], "INVALID")
            self.assertTrue(parsed["validation"]["errors"])
            self.assertIn("Missing required heading", parsed["validation"]["errors"][0])

    def test_tool_envelope_output_parses_into_two_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            output_text = (
                "=== FILE 1: research_pack.md ===\n"
                "## Topic Overview\nOverview\n"
                "## Reliable Timeline\nTimeline\n"
                "## Key People and Roles\nPeople\n"
                "## Anchor Facts\nFacts\n"
                "## Human Details and Human Cost\nCost\n"
                "## Myths, Disputes, and Later Accounts\nMyths\n"
                "## Facts That Contradict the Competitor\nContradictions\n"
                "## Possible Evidence-Based Contradictions\nEvidence\n"
                "## Documented Visual Details\nVisuals\n"
                "## Source Notes\nSources\n"
                "=== FILE 2: evidence_ledger.md ===\n"
                "CLAIM:\nFact\nSOURCE:\nBook\nSTATUS:\nVERIFIED\nALLOWED WORDING:\nOkay.\nNOTES:\nNone.\n"
            )
            parsed = parse_for_step(root, project, project_dir, "prompt_2_historical_research", output_text)
            self.assertEqual(parsed["status"], "VALID")
            self.assertEqual([item["artifact_id"] for item in parsed["artifacts"]], ["research_pack", "evidence_ledger"])
            self.assertTrue(parsed["artifacts"][0]["content"].startswith("## Topic Overview"))
            self.assertTrue(parsed["artifacts"][1]["content"].startswith("CLAIM:"))

    def test_prompt_native_output_parses_in_memory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            prepare_prompt7_inputs(root, "mist_of_ages", project["project_slug"])
            output_text = (
                "=== FILE 1: content.md ===\n"
                "# Title\nBody\n"
                "=== FILE 2: publishing_package.md ===\n"
                "# Package\nTags\n"
            )
            before = sorted(path.relative_to(project_dir).as_posix() for path in project_dir.rglob("*"))
            parsed = parse_for_step(root, project, project_dir, "prompt_7_final_content", output_text)
            after = sorted(path.relative_to(project_dir).as_posix() for path in project_dir.rglob("*"))
            self.assertEqual(parsed["status"], "VALID")
            self.assertEqual([item["filename"] for item in parsed["artifacts"]], ["content.md", "publishing_package.md"])
            self.assertEqual(before, after)

    def test_marker_errors_are_reported_without_throwing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            output_text = (
                "Unexpected prefix\n"
                "=== FILE 2: evidence_ledger.md ===\n"
                "CLAIM:\nFact\nSOURCE:\nBook\nSTATUS:\nVERIFIED\nALLOWED WORDING:\nOkay.\nNOTES:\nNone.\n"
            )
            parsed = parse_for_step(root, project, project_dir, "prompt_2_historical_research", output_text)
            self.assertEqual(parsed["status"], "INVALID")
            self.assertEqual(parsed["artifacts"], [])
            self.assertTrue(any("Missing required marker" in item for item in parsed["validation"]["errors"]))

    def test_bundle_identity_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            project_data = channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])
            with self.assertRaises(channel_output_parser.ChannelOutputParserError) as ctx:
                channel_output_parser.parse_channel_output(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    "A" * 64,
                    "## Subject\nRome\n",
                    project_data,
                    project_dir,
                )
            self.assertEqual(ctx.exception.code, "BUNDLE_IDENTITY_MISMATCH")

    def test_real_repository_runtime_state_is_unchanged(self):
        before = snapshot_runtime_state(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            parse_for_step(
                root,
                project,
                project_dir,
                "prompt_1_transcript_analysis",
                "## Subject\nRome\n## Competitor Promise\nPromise\n## Narrative Map\nMap\n## Strong Idea-Level Elements\nStrong\n## Weak or Removable Elements\nWeak\n## Claims Requiring Verification\nClaims\n## Originality Risks\nRisks\n## Neutral Research Questions\nQuestions\n",
            )
        after = snapshot_runtime_state(ROOT)
        self.assertEqual(before, after)

    def test_single_artifact_preserves_crlf_whitespace_and_unicode_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            output_text = (
                "\r\n"
                "## Subject\r\nXin chào\r\n"
                "## Competitor Promise\r\n Promise \r\n"
                "## Narrative Map\r\nMap\r\n"
                "## Strong Idea-Level Elements\r\nStrong\r\n"
                "## Weak or Removable Elements\r\nWeak\r\n"
                "## Claims Requiring Verification\r\nClaims\r\n"
                "## Originality Risks\r\nRisks\r\n"
                "## Neutral Research Questions\r\nQuestions\r\n\r\n"
            )
            parsed = parse_for_step(root, project, project_dir, "prompt_1_transcript_analysis", output_text)
            self.assertEqual(parsed["artifacts"][0]["content"], output_text)
            self.assertEqual(parsed["raw_output"]["sha256"], hashlib.sha256(output_text.encode("utf-8")).hexdigest().upper())
            self.assertEqual(parsed["raw_output"]["character_count"], len(output_text))

    def test_single_artifact_duplicate_and_out_of_order_headings_are_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            output_text = (
                "## Competitor Promise\nPromise\n"
                "## Subject\nRome\n"
                "## Narrative Map\nMap\n"
                "## Strong Idea-Level Elements\nStrong\n"
                "## Weak or Removable Elements\nWeak\n"
                "## Claims Requiring Verification\nClaims\n"
                "## Originality Risks\nRisks\n"
                "## Neutral Research Questions\nQuestions\n"
                "## Subject\nDuplicate\n"
            )
            parsed = parse_for_step(root, project, project_dir, "prompt_1_transcript_analysis", output_text)
            self.assertEqual(parsed["status"], "INVALID")
            self.assertTrue(any("Duplicate required heading" in item for item in parsed["validation"]["errors"]))
            self.assertTrue(any("out of order" in item for item in parsed["validation"]["errors"]))

    def test_single_artifact_heading_like_sentence_does_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            output_text = (
                "Before text mentioning ## Subject inside a sentence.\n"
                "## Competitor Promise\nPromise\n"
                "## Narrative Map\nMap\n"
                "## Strong Idea-Level Elements\nStrong\n"
                "## Weak or Removable Elements\nWeak\n"
                "## Claims Requiring Verification\nClaims\n"
                "## Originality Risks\nRisks\n"
                "## Neutral Research Questions\nQuestions\n"
            )
            parsed = parse_for_step(root, project, project_dir, "prompt_1_transcript_analysis", output_text)
            self.assertEqual(parsed["status"], "INVALID")
            self.assertTrue(any(item.startswith("Missing required heading: ## Subject") for item in parsed["validation"]["errors"]))

    def test_single_artifact_heading_with_surrounding_whitespace_does_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            output_text = (
                " ## Subject \nRome\n"
                "## Competitor Promise\nPromise\n"
                "## Narrative Map\nMap\n"
                "## Strong Idea-Level Elements\nStrong\n"
                "## Weak or Removable Elements\nWeak\n"
                "## Claims Requiring Verification\nClaims\n"
                "## Originality Risks\nRisks\n"
                "## Neutral Research Questions\nQuestions\n"
            )
            parsed = parse_for_step(root, project, project_dir, "prompt_1_transcript_analysis", output_text)
            self.assertEqual(parsed["status"], "INVALID")
            self.assertTrue(any(item.startswith("Missing required heading: ## Subject") for item in parsed["validation"]["errors"]))

    def test_single_artifact_whitespace_only_and_empty_output_are_rejected_before_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            project_data = channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])
            for text in ("", "   \r\n\t"):
                with self.assertRaises(channel_output_parser.ChannelOutputParserError) as ctx:
                    channel_output_parser.parse_channel_output(
                        root,
                        "mist_of_ages",
                        project["project_slug"],
                        "prompt_1_transcript_analysis",
                        "A" * 64,
                        text,
                        project_data,
                        project_dir,
                    )
                self.assertEqual(ctx.exception.code, "OUTPUT_TEXT_REQUIRED")

    def test_multi_artifact_crlf_markers_and_three_artifact_generic_parsing_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = build_generic_three_artifact_fixture(root)
            parsed = parse_for_step(
                root,
                project,
                project_dir,
                "beta_envelope_custom",
                "=== FILE 1: brief.custom ===\r\n# Brief\r\nA\r\n=== FILE 2: facts.custom ===\r\n# Facts\r\nB\r\n=== FILE 3: notes.custom ===\r\n# Notes\r\nC\r\n",
            )
            self.assertEqual(parsed["status"], "VALID")
            self.assertEqual([item["artifact_id"] for item in parsed["artifacts"]], ["brief_custom", "facts_custom", "notes_custom"])
            self.assertEqual(parsed["artifacts"][0]["content"], "# Brief\r\nA\r\n")
            self.assertEqual(parsed["artifacts"][2]["filename"], "notes_custom.md")

    def test_multi_artifact_whitespace_prefix_allowed_but_non_whitespace_prefix_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = build_generic_three_artifact_fixture(root)
            valid = parse_for_step(
                root,
                project,
                project_dir,
                "beta_envelope_custom",
                "\r\n\r\n=== FILE 1: brief.custom ===\n# Brief\nA\n=== FILE 2: facts.custom ===\n# Facts\nB\n=== FILE 3: notes.custom ===\n# Notes\nC\n",
            )
            self.assertEqual(valid["status"], "VALID")
            invalid = parse_for_step(
                root,
                project,
                project_dir,
                "beta_envelope_custom",
                "prefix\n=== FILE 1: brief.custom ===\n# Brief\nA\n=== FILE 2: facts.custom ===\n# Facts\nB\n=== FILE 3: notes.custom ===\n# Notes\nC\n",
            )
            self.assertEqual(invalid["status"], "INVALID")
            self.assertTrue(any("Non-whitespace content appears before the first required marker." == item for item in invalid["validation"]["errors"]))

    def test_multi_artifact_removes_only_structural_newline_after_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = build_generic_three_artifact_fixture(root)
            parsed_lf = parse_for_step(
                root,
                project,
                project_dir,
                "beta_envelope_custom",
                "=== FILE 1: brief.custom ===\n\n# Brief\nA\n=== FILE 2: facts.custom ===\n# Facts\nB\n=== FILE 3: notes.custom ===\n# Notes\nC\n",
            )
            self.assertEqual(parsed_lf["artifacts"][0]["content"], "\n# Brief\nA\n")
            parsed_crlf = parse_for_step(
                root,
                project,
                project_dir,
                "beta_envelope_custom",
                "=== FILE 1: brief.custom ===\r\n\r\n# Brief\r\nA\r\n=== FILE 2: facts.custom ===\r\n# Facts\r\nB\r\n=== FILE 3: notes.custom ===\r\n# Notes\r\nC\r\n",
            )
            self.assertEqual(parsed_crlf["artifacts"][0]["content"], "\r\n# Brief\r\nA\r\n")

    def test_multi_artifact_duplicate_unknown_and_out_of_order_markers_are_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = build_generic_three_artifact_fixture(root)
            parsed = parse_for_step(
                root,
                project,
                project_dir,
                "beta_envelope_custom",
                "=== FILE 2: facts.custom ===\n# Facts\nB\n=== FILE 1: brief.custom ===\n# Brief\nA\n=== FILE 2: facts.custom ===\n# Facts\nB2\n=== FILE X: rogue.custom ===\n# Rogue\n=== FILE 3: notes.custom ===\n# Notes\nC\n",
            )
            self.assertEqual(parsed["status"], "INVALID")
            self.assertEqual(parsed["artifacts"], [])
            self.assertTrue(any("Unknown output marker line" in item for item in parsed["validation"]["errors"]))
            self.assertTrue(any("Duplicate required marker" in item for item in parsed["validation"]["errors"]))

    def test_multi_artifact_marker_like_body_line_is_treated_as_ambiguous_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = build_generic_three_artifact_fixture(root)
            parsed = parse_for_step(
                root,
                project,
                project_dir,
                "gamma_native_custom",
                "=== FILE 1: story.custom ===\n# Story\n=== FILE 9: confusing.custom ===\n=== FILE 2: package.custom ===\n# Package\n=== FILE 3: summary.custom ===\n# Summary\n",
            )
            self.assertEqual(parsed["status"], "INVALID")
            self.assertEqual(parsed["artifacts"], [])

    def test_prompt_native_three_artifact_contract_parses_generically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = build_generic_three_artifact_fixture(root)
            parsed = parse_for_step(
                root,
                project,
                project_dir,
                "gamma_native_custom",
                "=== FILE 1: story.custom ===\n# Story\nOne\n=== FILE 2: package.custom ===\n# Package\nTwo\n=== FILE 3: summary.custom ===\n# Summary\nThree",
            )
            self.assertEqual(parsed["status"], "VALID")
            self.assertEqual([item["artifact_id"] for item in parsed["artifacts"]], ["story_custom", "package_custom", "summary_custom"])
            self.assertEqual(parsed["artifacts"][2]["content"], "# Summary\nThree")

    def test_multi_artifact_empty_middle_body_and_per_artifact_heading_validation_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = build_generic_three_artifact_fixture(root)
            parsed = parse_for_step(
                root,
                project,
                project_dir,
                "beta_envelope_custom",
                "=== FILE 1: brief.custom ===\n# Brief\nA\n=== FILE 2: facts.custom ===\n=== FILE 3: notes.custom ===\n# Notes\n# Brief\n",
            )
            self.assertEqual(parsed["status"], "INVALID")
            self.assertEqual(len(parsed["artifacts"]), 3)
            facts = next(item for item in parsed["artifacts"] if item["artifact_id"] == "facts_custom")
            notes = next(item for item in parsed["artifacts"] if item["artifact_id"] == "notes_custom")
            self.assertEqual(facts["validation"]["status"], "INVALID")
            self.assertTrue(any("empty" in item.lower() for item in facts["validation"]["errors"]))
            self.assertEqual(notes["validation"]["status"], "VALID")

    def test_required_heading_validation_is_scoped_per_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = build_generic_three_artifact_fixture(root)
            parsed = parse_for_step(
                root,
                project,
                project_dir,
                "beta_envelope_custom",
                "=== FILE 1: brief.custom ===\n# Facts\nWrong place\n=== FILE 2: facts.custom ===\n# Facts\nOkay\n=== FILE 3: notes.custom ===\n# Notes\nOkay\n",
            )
            self.assertEqual(parsed["status"], "INVALID")
            brief = next(item for item in parsed["artifacts"] if item["artifact_id"] == "brief_custom")
            facts = next(item for item in parsed["artifacts"] if item["artifact_id"] == "facts_custom")
            self.assertEqual(brief["validation"]["status"], "INVALID")
            self.assertEqual(facts["validation"]["status"], "VALID")

    def test_bundle_identity_accepts_lowercase_hex_and_rejects_malformed_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            bundle = __import__("scripts.channel_prompt_bundle", fromlist=[""]).build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            project_data = channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])
            parsed = channel_output_parser.parse_channel_output(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                bundle["bundle_sha256"].lower(),
                "## Subject\nRome\n## Competitor Promise\nPromise\n## Narrative Map\nMap\n## Strong Idea-Level Elements\nStrong\n## Weak or Removable Elements\nWeak\n## Claims Requiring Verification\nClaims\n## Originality Risks\nRisks\n## Neutral Research Questions\nQuestions\n",
                project_data,
                project_dir,
            )
            self.assertEqual(parsed["status"], "VALID")
            with self.assertRaises(channel_output_parser.ChannelOutputParserError) as ctx:
                channel_output_parser.parse_channel_output(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    "not-a-digest",
                    "x",
                    project_data,
                    project_dir,
                )
            self.assertEqual(ctx.exception.code, "BUNDLE_IDENTITY_MISMATCH")

    def test_changed_required_input_invalidates_old_bundle_digest_before_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            project_data = channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])
            bundle = __import__("scripts.channel_prompt_bundle", fromlist=[""]).build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                project_data,
                project_dir,
            )
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "changed transcript " * 12, overwrite=True)
            with self.assertRaises(channel_output_parser.ChannelOutputParserError) as ctx:
                channel_output_parser.parse_channel_output(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    "## Subject\nRome\n## Competitor Promise\nPromise\n## Narrative Map\nMap\n## Strong Idea-Level Elements\nStrong\n## Weak or Removable Elements\nWeak\n## Claims Requiring Verification\nClaims\n## Originality Risks\nRisks\n## Neutral Research Questions\nQuestions\n",
                    channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                    project_dir,
                )
            self.assertEqual(ctx.exception.code, "BUNDLE_IDENTITY_MISMATCH")


if __name__ == "__main__":
    unittest.main()
