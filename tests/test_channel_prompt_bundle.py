import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from xml.sax.saxutils import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_projects, channel_prompt_bundle, channel_workflow, channel_workspace, prompt_source_ingest, ui_server
from tests.runtime_isolation_helpers import snapshot_runtime_state


SOURCE_DOC_ENV_VAR = "MIST_OF_AGES_PROMPT_SOURCE_DOCX"
PRODUCTION_V1_DIGEST = "BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E"


def optional_source_docx_path() -> Path | None:
    value = os.environ.get(SOURCE_DOC_ENV_VAR, "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.exists():
        return None
    return path


def write_docx_paragraph_fixture(path: Path, paragraphs: list[str]) -> None:
    document_lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
        "<w:body>",
    ]
    for paragraph in paragraphs:
        document_lines.append(f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>")
    document_lines.extend(["<w:sectPr/>", "</w:body>", "</w:document>"])
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", "\n".join(document_lines))


def make_prompt_source_fixture_docx(path: Path) -> None:
    paragraphs = ["Cover Page", "Internal notes"]
    for title, step_id in prompt_source_ingest.PROMPT_TITLE_TO_STEP_ID.items():
        paragraphs.extend(
            [
                title,
                "Mục",
                "Nội dung",
                "Model duy nhất",
                "Model Label",
                "Input",
                "Input Summary",
                "Output",
                "Output Summary",
                f"Authoritative body for {step_id}.",
            ]
        )
    paragraphs.extend(["Checklist bàn giao", "Tail"])
    write_docx_paragraph_fixture(path, paragraphs)


def make_channel(root: Path, slug: str, channel_id: str, *, with_metrics: bool = True) -> None:
    channel_workspace.create_channel_workspace(root, slug, slug.replace("_", " ").title(), channel_id, "@" + slug)
    paths = channel_workspace.canonical_channel_paths(root, slug)
    paths.channel_learnings_master.write_text("# Learnings\n\nApproved.\n", encoding="utf-8", newline="\n")
    registry_path = root / "workflows" / "registry.json"
    if registry_path.exists():
        registry = read_json(registry_path)
        registry["channel_defaults"][slug] = {"workflow_id": "mist_of_ages_assisted_content"}
        write_json(registry_path, registry)
    if with_metrics:
        paths.channel_metrics_csv.parent.mkdir(parents=True, exist_ok=True)
        paths.channel_metrics_csv.write_text(
            "video_id,title,published_at,views,estimated_minutes_watched,average_view_duration_seconds,average_view_percentage,likes,comments,thumbnail_impressions,thumbnail_ctr,data_status\n"
            "vid-a,A,2026-07-01,10,20,30,40,1,2,,,PENDING_REACH\n",
            encoding="utf-8",
            newline="\n",
        )


def source_metadata() -> dict:
    return {
        "title": "Why Rome Executed Jesus",
        "channelTitle": "Competitor",
        "channelId": "UC_COMP",
        "publishedAt": "2026-07-01T00:00:00+00:00",
        "duration": "PT10M",
        "description": "desc",
        "tags": ["rome"],
        "viewCount": "123",
        "likeCount": "4",
        "commentCount": "5",
        "thumbnailUrl": "https://example.com/thumb.jpg",
    }


def copy_workflows(root: Path) -> None:
    shutil.copytree(ROOT / "workflows", root / "workflows", dirs_exist_ok=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def sha(path: Path) -> str:
    return channel_workflow._sha256_file(path)


def file_tree_snapshot(root: Path) -> dict[str, tuple[str, int]]:
    snapshot: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        snapshot[rel] = ("dir", 0) if path.is_dir() else ("file", path.stat().st_size)
    return snapshot


def set_default_workflow_version(root: Path, version: str) -> None:
    registry_path = root / "workflows" / "registry.json"
    registry = read_json(registry_path)
    registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = version
    write_json(registry_path, registry)


def create_project(root: Path, channel_slug: str, video_id: str = "VIDEO12345A") -> dict:
    return channel_projects.create_channel_project(
        root,
        channel_slug,
        video_id,
        f"https://youtube.com/watch?v={video_id}",
        source_metadata(),
        created_at="2026-07-01T00:00:00+00:00",
    )


def write_project_artifact(root: Path, channel_slug: str, project_slug: str, relative_path: str, text: str) -> None:
    path = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project_slug / Path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def make_v2_bound_project(root: Path, *, channel_slug: str = "mist_of_ages", video_id: str = "VIDEO12345A") -> dict:
    copy_workflows(root)
    set_default_workflow_version(root, "2")
    make_channel(root, channel_slug, "UC123")
    project = create_project(root, channel_slug, video_id)
    return project


def prepare_step2_inputs(root: Path, channel_slug: str, project_slug: str) -> None:
    channel_projects.save_project_transcript(root, channel_slug, project_slug, "real transcript " * 12)
    write_project_artifact(root, channel_slug, project_slug, "workflow/transcript_analysis.md", "## Subject\nRome\n")


def prepare_prompt7_inputs(root: Path, channel_slug: str, project_slug: str) -> None:
    write_project_artifact(root, channel_slug, project_slug, "workflow/narration_v1.md", "## Narration\nA real narration.\n")
    write_project_artifact(root, channel_slug, project_slug, "workflow/red_team_report.md", "## Overall Verdict\nPASS\n## Must Fix — Narration\nNone.\n## Must Fix — Publishing Package\nNone.\n## Optional Improvements\nNone.\n## Passed Checks\nAll.\n")
    write_project_artifact(root, channel_slug, project_slug, "workflow/locked_creative_package.md", "# Locked Creative Package\n## Topic Verdict\nPRODUCE\n")
    write_project_artifact(root, channel_slug, project_slug, "workflow/evidence_ledger.md", "CLAIM:\nFact\nSOURCE:\nBook\nSTATUS:\nVERIFIED\nALLOWED WORDING:\nOkay.\nNOTES:\nNone.\n")


class PromptBundleTests(unittest.TestCase):
    def test_docx_fixture_paragraph_reader_and_raw_prompt_extraction_are_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "fixture.docx"
            make_prompt_source_fixture_docx(docx_path)
            paragraphs = prompt_source_ingest._docx_paragraphs(docx_path)
            self.assertIn("Cover Page", paragraphs)
            self.assertIn("Prompt 1 — Transcript Analyst", paragraphs)
            raw = prompt_source_ingest.extract_raw_prompt_bodies(docx_path)
            self.assertEqual(len(raw), 7)
            self.assertEqual(raw["prompt_1_transcript_analysis"], "Authoritative body for prompt_1_transcript_analysis.")
            self.assertEqual(raw["prompt_7_final_content"], "Authoritative body for prompt_7_final_content.")

    def test_committed_prompt_files_are_present_and_non_empty(self):
        prompt_dir = ROOT / "workflows" / "mist_of_ages_assisted_content" / "v2" / "prompts"
        file_map = {
            "prompt_1_transcript_analysis": "prompt_01_transcript_analyst.md",
            "prompt_2_historical_research": "prompt_02_historical_researcher.md",
            "prompt_3_creative_package": "prompt_03_creative_strategist.md",
            "prompt_4_retention_outline": "prompt_04_retention_architect.md",
            "prompt_5_narration_v1": "prompt_05_main_writer.md",
            "prompt_6_red_team": "prompt_06_red_team.md",
            "prompt_7_final_content": "prompt_07_finalizer.md",
        }
        self.assertEqual(len(list(prompt_dir.glob("prompt_*.md"))), 7)
        for filename in file_map.values():
            committed = (prompt_dir / filename).read_text(encoding="utf-8")
            self.assertTrue(committed.strip())

    def test_prompt_files_exclude_wrapper_metadata_and_preserve_marker_rules(self):
        prompt_dir = ROOT / "workflows" / "mist_of_ages_assisted_content" / "v2" / "prompts"
        files = sorted(path for path in prompt_dir.glob("prompt_*.md"))
        self.assertEqual(len(files), 7)
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertFalse(text.endswith("\n\n"))
            self.assertNotIn("Mục", text)
            self.assertNotIn("Nội dung", text)
            self.assertNotIn("Checklist bàn giao", text)
            self.assertNotIn("Model duy nhất", text)
            self.assertNotIn("Output Summary", text)
            self.assertNotIn("TODO: Fill manually during Workflow V2.", text)
            for line in text.splitlines():
                self.assertEqual(line, line.rstrip())
        prompt2 = (prompt_dir / "prompt_02_historical_researcher.md").read_text(encoding="utf-8")
        self.assertNotIn("=== FILE 1: research_pack.md ===", prompt2)
        self.assertNotIn("=== FILE 2: evidence_ledger.md ===", prompt2)
        self.assertIn("OUTPUT A", prompt2)
        self.assertIn("OUTPUT B", prompt2)
        prompt5 = (prompt_dir / "prompt_05_main_writer.md").read_text(encoding="utf-8")
        self.assertIn("Optional Pronunciation Notes", prompt5)
        prompt7 = (prompt_dir / "prompt_07_finalizer.md").read_text(encoding="utf-8")
        self.assertEqual(prompt7.count("=== FILE 1: content.md ==="), 1)
        self.assertEqual(prompt7.count("=== FILE 2: publishing_package.md ==="), 1)

    def test_manifest_loads_and_records_source_digest(self):
        definition = channel_workflow.load_workflow_definition(ROOT, "mist_of_ages_assisted_content", "2")
        manifest = channel_prompt_bundle.load_prompt_manifest(ROOT, "mist_of_ages_assisted_content", "2", definition)
        self.assertEqual(manifest["prompt_set_id"], "mist_of_ages_package_first")
        self.assertEqual(manifest["source_document"]["sha256"], prompt_source_ingest.EXPECTED_SOURCE_SHA256)
        self.assertEqual(len(manifest["prompts"]), 7)

    def test_manifest_rejects_unsafe_prompt_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_workflows(root)
            manifest_path = root / "workflows" / "mist_of_ages_assisted_content" / "v2" / "prompts" / "manifest.json"
            manifest = read_json(manifest_path)
            manifest["prompts"]["prompt_1_transcript_analysis"]["relative_path"] = "../escape.md"
            write_json(manifest_path, manifest)
            with self.assertRaises(channel_prompt_bundle.PromptBundleError) as ctx:
                channel_prompt_bundle.load_prompt_manifest(root, "mist_of_ages_assisted_content", "2")
            self.assertEqual(ctx.exception.code, "PROMPT_MANIFEST_INVALID")

    def test_manifest_rejects_one_byte_prompt_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_workflows(root)
            prompt_path = root / "workflows" / "mist_of_ages_assisted_content" / "v2" / "prompts" / "prompt_01_transcript_analyst.md"
            original = prompt_path.read_bytes()
            prompt_path.write_bytes(original + b"\n")
            with self.assertRaises(channel_prompt_bundle.PromptBundleError) as ctx:
                channel_prompt_bundle.load_prompt_manifest(root, "mist_of_ages_assisted_content", "2")
            self.assertEqual(ctx.exception.code, "PROMPT_FILE_DIGEST_MISMATCH")

    def test_manifest_missing_or_extra_entries_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_workflows(root)
            manifest_path = root / "workflows" / "mist_of_ages_assisted_content" / "v2" / "prompts" / "manifest.json"
            manifest = read_json(manifest_path)
            del manifest["prompts"]["prompt_7_final_content"]
            write_json(manifest_path, manifest)
            with self.assertRaises(channel_prompt_bundle.PromptBundleError):
                channel_prompt_bundle.load_prompt_manifest(root, "mist_of_ages_assisted_content", "2")

            copy_workflows(root)
            manifest = read_json(manifest_path)
            manifest["prompts"]["prompt_extra"] = dict(manifest["prompts"]["prompt_1_transcript_analysis"])
            write_json(manifest_path, manifest)
            with self.assertRaises(channel_prompt_bundle.PromptBundleError):
                channel_prompt_bundle.load_prompt_manifest(root, "mist_of_ages_assisted_content", "2")

    def test_manifest_invalid_output_contract_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_workflows(root)
            manifest_path = root / "workflows" / "mist_of_ages_assisted_content" / "v2" / "prompts" / "manifest.json"
            manifest = read_json(manifest_path)
            manifest["prompts"]["prompt_1_transcript_analysis"]["output_contract"]["artifacts"][0]["artifact_id"] = "unknown_artifact"
            write_json(manifest_path, manifest)
            with self.assertRaises(channel_prompt_bundle.PromptBundleError) as ctx:
                channel_prompt_bundle.load_prompt_manifest(root, "mist_of_ages_assisted_content", "2")
            self.assertEqual(ctx.exception.code, "PROMPT_MANIFEST_INVALID")

    def test_v1_digest_unchanged_and_v2_loads_without_becoming_default(self):
        self.assertEqual(sha(ROOT / "workflows" / "mist_of_ages_assisted_content" / "v1" / "workflow.json"), PRODUCTION_V1_DIGEST)
        registry = channel_workflow.load_workflow_registry(ROOT)
        self.assertEqual(registry["workflows"]["mist_of_ages_assisted_content"]["default_version"], "1")
        self.assertEqual(registry["workflows"]["mist_of_ages_assisted_content"]["legacy_unpinned_version"], "1")
        definition = channel_workflow.load_workflow_definition(ROOT, "mist_of_ages_assisted_content", "2")
        self.assertEqual(len(definition["steps"]), 7)
        self.assertEqual(definition["steps"][0]["required_model"], "Gemini 3.1 Pro")
        self.assertEqual(definition["steps"][4]["required_model"], "Claude Sonnet 4.6 — High")
        self.assertIn("competitor_transcript", definition["steps"][4]["input_artifact_ids"])
        self.assertIn("retention_outline", definition["steps"][5]["input_artifact_ids"])
        self.assertEqual(definition["prompt_set"]["status"], "AVAILABLE")

    def test_bundle_builder_generates_step1_bundle_and_reports_optional_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_v2_bound_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            learnings = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project["project_slug"] / "input" / "channel_learnings.md"
            learnings.unlink()
            project_dir = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project["project_slug"]
            bundle = channel_prompt_bundle.build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            self.assertIn("=== AUTHORITATIVE PROMPT ===", bundle["bundle"])
            self.assertEqual(bundle["bundle"].count("You are the Transcript Analyst for Mist of Ages"), 1)
            self.assertLess(bundle["bundle"].find("competitor_reference.md"), bundle["bundle"].find("competitor_transcript.md"))
            self.assertIn("channel_learnings", bundle["missing_optional_inputs"])
            self.assertNotIn(str(root), bundle["bundle"])

    def test_bundle_builder_prompt2_tool_envelope_and_digest_changes_with_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_v2_bound_project(root)
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            project_dir = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project["project_slug"]
            project_data = channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])
            first = channel_prompt_bundle.build_prompt_bundle(root, "mist_of_ages", project["project_slug"], "prompt_2_historical_research", project_data, project_dir)
            second = channel_prompt_bundle.build_prompt_bundle(root, "mist_of_ages", project["project_slug"], "prompt_2_historical_research", project_data, project_dir)
            self.assertEqual(first["bundle_sha256"], second["bundle_sha256"])
            self.assertEqual(first["output_contract"]["response_mode"], "MULTI_ARTIFACT_TOOL_ENVELOPE")
            self.assertEqual(first["bundle"].count("=== FILE 1: research_pack.md ==="), 1)
            self.assertEqual(first["bundle"].count("=== FILE 2: evidence_ledger.md ==="), 1)
            self.assertEqual(first["project_context"]["topic"]["value"], "Why Rome Executed Jesus")
            self.assertEqual(first["project_context"]["topic"]["source_field"], "input/_raw/competitor_video.json:title")
            self.assertIn("Source: input/_raw/competitor_video.json:title", first["bundle"])
            write_project_artifact(root, "mist_of_ages", project["project_slug"], "workflow/transcript_analysis.md", "## Subject\nChanged\n")
            changed = channel_prompt_bundle.build_prompt_bundle(root, "mist_of_ages", project["project_slug"], "prompt_2_historical_research", project_data, project_dir)
            self.assertNotEqual(first["bundle_sha256"], changed["bundle_sha256"])

    def test_bundle_builder_prompt2_topic_does_not_fall_back_to_slug_and_missing_title_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_v2_bound_project(root, channel_slug="mist_of_ages", video_id="VIDEO12345A")
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            project_dir = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project["project_slug"]
            raw_path = project_dir / "input" / "_raw" / "competitor_video.json"
            raw_payload = read_json(raw_path)
            raw_payload["title"] = "Actual Human Topic"
            write_json(raw_path, raw_payload)
            project_data = channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])
            bundle = channel_prompt_bundle.build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_2_historical_research",
                project_data,
                project_dir,
            )
            self.assertEqual(bundle["project_context"]["topic"]["value"], "Actual Human Topic")
            self.assertNotEqual(bundle["project_context"]["topic"]["value"], project["project_slug"])

            raw_payload.pop("title", None)
            write_json(raw_path, raw_payload)
            with self.assertRaises(channel_prompt_bundle.PromptBundleError) as ctx:
                channel_prompt_bundle.build_prompt_bundle(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_2_historical_research",
                    project_data,
                    project_dir,
                )
            self.assertEqual(ctx.exception.code, "BUNDLE_PROJECT_CONTEXT_MISSING")

    def test_bundle_builder_missing_required_artifact_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_v2_bound_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            project_dir = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project["project_slug"]
            with self.assertRaises(channel_prompt_bundle.PromptBundleError) as ctx:
                channel_prompt_bundle.build_prompt_bundle(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_2_historical_research",
                    channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                    project_dir,
                )
            self.assertEqual(ctx.exception.code, "BUNDLE_REQUIRED_INPUT_MISSING")

    def test_prompt7_bundle_does_not_duplicate_native_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_v2_bound_project(root)
            prepare_prompt7_inputs(root, "mist_of_ages", project["project_slug"])
            project_dir = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project["project_slug"]
            bundle = channel_prompt_bundle.build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_7_final_content",
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            self.assertEqual(bundle["output_contract"]["response_mode"], "MULTI_ARTIFACT_PROMPT_NATIVE")
            self.assertEqual(bundle["bundle"].count("=== FILE 1: content.md ==="), 1)
            self.assertEqual(bundle["bundle"].count("=== FILE 2: publishing_package.md ==="), 1)
            self.assertNotIn("=== TOOL OUTPUT DELIVERY CONTRACT ===", bundle["bundle"])

    def test_alternate_temporary_prompt_set_works_without_business_logic_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_workflows(root)
            make_channel(root, "mist_of_ages", "UC123")

            v3_dir = root / "workflows" / "mist_of_ages_assisted_content" / "v3"
            prompt_dir = v3_dir / "prompts"
            prompt_dir.mkdir(parents=True, exist_ok=True)

            alpha_prompt = prompt_dir / "alpha_prompt.md"
            beta_prompt = prompt_dir / "beta_prompt.md"
            gamma_prompt = prompt_dir / "gamma_prompt.md"
            alpha_prompt.write_text("ALPHA SINGLE\n", encoding="utf-8", newline="\n")
            beta_prompt.write_text("BETA ENVELOPE\n", encoding="utf-8", newline="\n")
            gamma_prompt.write_text(
                "GAMMA NATIVE\n=== FILE 1: story.custom ===\n[story]\n=== FILE 2: package.custom ===\n[package]\n",
                encoding="utf-8",
                newline="\n",
            )

            manifest = {
                "schema_version": 1,
                "prompt_set_id": "alternate_bundle_fixture",
                "prompt_set_version": "3",
                "source_document": {
                    "filename": "fixture.docx",
                    "sha256": "A" * 64,
                },
                "prompts": {
                    "alpha_single": {
                        "relative_path": "alpha_prompt.md",
                        "sha256": sha(alpha_prompt),
                        "output_contract": {
                            "response_mode": "SINGLE_ARTIFACT",
                            "artifacts": [
                                {
                                    "artifact_id": "alpha_notes",
                                    "required_headings": ["# Alpha Notes"],
                                }
                            ],
                        },
                    },
                    "beta_bundle": {
                        "relative_path": "beta_prompt.md",
                        "sha256": sha(beta_prompt),
                        "output_contract": {
                            "response_mode": "MULTI_ARTIFACT_TOOL_ENVELOPE",
                            "artifacts": [
                                {
                                    "artifact_id": "beta_brief",
                                    "delivery_marker": "=== FILE 1: beta_brief.custom ===",
                                    "required_headings": ["# Beta Brief"],
                                },
                                {
                                    "artifact_id": "beta_facts",
                                    "delivery_marker": "=== FILE 2: beta_facts.custom ===",
                                    "required_headings": ["# Beta Facts"],
                                },
                            ],
                        },
                    },
                    "gamma_native": {
                        "relative_path": "gamma_prompt.md",
                        "sha256": sha(gamma_prompt),
                        "output_contract": {
                            "response_mode": "MULTI_ARTIFACT_PROMPT_NATIVE",
                            "artifacts": [
                                {"artifact_id": "story_output", "native_marker": "=== FILE 1: story.custom ==="},
                                {"artifact_id": "package_output", "native_marker": "=== FILE 2: package.custom ==="},
                            ],
                        },
                    },
                },
            }
            write_json(prompt_dir / "manifest.json", manifest)

            workflow = {
                "schema_version": 1,
                "workflow_id": "mist_of_ages_assisted_content",
                "workflow_version": "3",
                "display_name": "Alternate Bundle Fixture",
                "execution_mode": "LINEAR",
                "entry_lifecycle_state": "INPUT_READY",
                "terminal_lifecycle_state": "DONE",
                "lifecycle_states": ["INPUT_READY", "ALPHA_READY", "BETA_READY", "DONE"],
                "prompt_set": {
                    "status": "AVAILABLE",
                    "prompt_set_id": "alternate_bundle_fixture",
                    "version": "3",
                    "manifest_path": "prompts/manifest.json",
                    "manifest_sha256": sha(prompt_dir / "manifest.json"),
                    "bundle_available": True,
                },
                "artifacts": [
                    {"artifact_id": "competitor_transcript", "display_name": "Competitor Transcript", "relative_path": "research/competitor_transcript.md", "artifact_role": "INPUT", "required": True, "media_type": "text/markdown"},
                    {"artifact_id": "alpha_notes", "display_name": "Alpha Notes", "relative_path": "workflow/alpha_notes.md", "artifact_role": "GENERATED", "required": True, "media_type": "text/markdown"},
                    {"artifact_id": "beta_brief", "display_name": "Beta Brief", "relative_path": "workflow/beta_brief.md", "artifact_role": "GENERATED", "required": True, "media_type": "text/markdown"},
                    {"artifact_id": "beta_facts", "display_name": "Beta Facts", "relative_path": "workflow/beta_facts.md", "artifact_role": "GENERATED", "required": True, "media_type": "text/markdown"},
                    {"artifact_id": "story_output", "display_name": "Story Output", "relative_path": "workflow/story_output.md", "artifact_role": "FINAL", "required": True, "media_type": "text/markdown"},
                    {"artifact_id": "package_output", "display_name": "Package Output", "relative_path": "workflow/package_output.md", "artifact_role": "FINAL", "required": True, "media_type": "text/markdown"},
                ],
                "steps": [
                    {"step_id": "alpha_single", "order": 1, "display_name": "Alpha", "required_model": "Model A", "input_artifact_ids": ["competitor_transcript"], "optional_input_artifact_ids": [], "output_artifact_ids": ["alpha_notes"], "resulting_lifecycle_state": "ALPHA_READY", "constraints": [], "prompt_source_ref": "alpha_single"},
                    {"step_id": "beta_bundle", "order": 2, "display_name": "Beta", "required_model": "Model B", "input_artifact_ids": ["alpha_notes"], "optional_input_artifact_ids": [], "output_artifact_ids": ["beta_brief", "beta_facts"], "resulting_lifecycle_state": "BETA_READY", "constraints": [], "prompt_source_ref": "beta_bundle"},
                    {"step_id": "gamma_native", "order": 3, "display_name": "Gamma", "required_model": "Model C", "input_artifact_ids": ["beta_brief", "beta_facts"], "optional_input_artifact_ids": [], "output_artifact_ids": ["story_output", "package_output"], "resulting_lifecycle_state": "DONE", "constraints": [], "prompt_source_ref": "gamma_native"},
                ],
            }
            write_json(v3_dir / "workflow.json", workflow)
            registry = read_json(root / "workflows" / "registry.json")
            registry["workflows"]["mist_of_ages_assisted_content"]["versions"]["3"] = {
                "status": "ACTIVE",
                "definition_path": "mist_of_ages_assisted_content/v3/workflow.json",
                "definition_sha256": sha(v3_dir / "workflow.json"),
            }
            registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "3"
            write_json(root / "workflows" / "registry.json", registry)

            project_v3 = create_project(root, "mist_of_ages", "VIDEO12345B")
            channel_projects.save_project_transcript(root, "mist_of_ages", project_v3["project_slug"], "real transcript " * 12)
            project_data = channel_projects.load_channel_project(root, "mist_of_ages", project_v3["project_slug"])
            project_dir = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project_v3["project_slug"]

            alpha_bundle = channel_prompt_bundle.build_prompt_bundle(root, "mist_of_ages", project_v3["project_slug"], "alpha_single", project_data, project_dir)
            self.assertIn("ALPHA SINGLE", alpha_bundle["bundle"])
            self.assertEqual(alpha_bundle["output_contract"]["response_mode"], "SINGLE_ARTIFACT")

            write_project_artifact(root, "mist_of_ages", project_v3["project_slug"], "workflow/alpha_notes.md", "# Alpha Notes\nReady\n")
            beta_bundle = channel_prompt_bundle.build_prompt_bundle(root, "mist_of_ages", project_v3["project_slug"], "beta_bundle", project_data, project_dir)
            self.assertIn("BETA ENVELOPE", beta_bundle["bundle"])
            self.assertEqual(beta_bundle["output_contract"]["response_mode"], "MULTI_ARTIFACT_TOOL_ENVELOPE")
            self.assertIn("=== FILE 1: beta_brief.custom ===", beta_bundle["bundle"])
            self.assertIn("=== FILE 2: beta_facts.custom ===", beta_bundle["bundle"])

            write_project_artifact(root, "mist_of_ages", project_v3["project_slug"], "workflow/beta_brief.md", "# Beta Brief\nReady\n")
            write_project_artifact(root, "mist_of_ages", project_v3["project_slug"], "workflow/beta_facts.md", "# Beta Facts\nReady\n")
            gamma_bundle = channel_prompt_bundle.build_prompt_bundle(root, "mist_of_ages", project_v3["project_slug"], "gamma_native", project_data, project_dir)
            self.assertIn("GAMMA NATIVE", gamma_bundle["bundle"])
            self.assertEqual(gamma_bundle["output_contract"]["response_mode"], "MULTI_ARTIFACT_PROMPT_NATIVE")
            self.assertEqual(gamma_bundle["bundle"].count("=== FILE 1: story.custom ==="), 1)
            self.assertEqual(gamma_bundle["bundle"].count("=== FILE 2: package.custom ==="), 1)
            self.assertEqual(gamma_bundle["binding"]["workflow_version"], "3")

    def test_api_bundle_success_and_v1_prompt_set_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            v2_project = make_v2_bound_project(root, channel_slug="channel_a")
            prepare_step2_inputs(root, "channel_a", v2_project["project_slug"])
            ctx = ui_server.build_app_context(root=root)
            status, data = ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/channel_a/projects/{v2_project['project_slug']}/workflow/steps/prompt_2_historical_research/bundle",
                context=ctx,
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["binding"]["workflow_version"], "2")

            copy_workflows(root)
            make_channel(root, "channel_b", "UC2")
            v1_project = create_project(root, "channel_b", "VIDEO12345C")
            channel_projects.save_project_transcript(root, "channel_b", v1_project["project_slug"], "real transcript " * 12)
            with self.assertRaises(ui_server.V2Error) as v1_ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/channel_b/projects/{v1_project['project_slug']}/workflow/steps/prompt_1_transcript_analysis/bundle",
                    context=ctx,
                )
            self.assertEqual(v1_ctx.exception.code, "PROMPT_SET_UNAVAILABLE")

            legacy_path = channel_workspace.canonical_channel_paths(root, "channel_b").projects_dir / v1_project["project_slug"] / "project.json"
            legacy = read_json(legacy_path)
            legacy.pop("workflow_binding", None)
            write_json(legacy_path, legacy)
            with self.assertRaises(ui_server.V2Error) as legacy_ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/channel_b/projects/{v1_project['project_slug']}/workflow/steps/prompt_1_transcript_analysis/bundle",
                    context=ctx,
                )
            self.assertEqual(legacy_ctx.exception.code, "PROMPT_SET_UNAVAILABLE")

    def test_api_bundle_unknown_step_cross_channel_invalid_slug_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_v2_bound_project(root, channel_slug="channel_a")
            prepare_step2_inputs(root, "channel_a", project["project_slug"])
            make_channel(root, "channel_b", "UC2")
            ctx = ui_server.build_app_context(root=root)
            project_dir = channel_workspace.canonical_channel_paths(root, "channel_a").projects_dir / project["project_slug"]
            before = file_tree_snapshot(project_dir)
            with self.assertRaises(ui_server.V2Error) as unknown_ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/channel_a/projects/{project['project_slug']}/workflow/steps/missing/bundle",
                    context=ctx,
                )
            self.assertEqual(unknown_ctx.exception.code, "WORKFLOW_STEP_NOT_FOUND")
            with self.assertRaises(ui_server.V2Error):
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/channel_b/projects/{project['project_slug']}/workflow/steps/prompt_2_historical_research/bundle",
                    context=ctx,
                )
            with self.assertRaises(ui_server.V2Error) as invalid_ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/Bad-Slug/projects/{project['project_slug']}/workflow/steps/prompt_2_historical_research/bundle",
                    context=ctx,
                )
            self.assertEqual(invalid_ctx.exception.code, "INVALID_CHANNEL_SLUG")
            after = file_tree_snapshot(project_dir)
            self.assertEqual(before, after)

    def test_existing_workflow_and_project_detail_endpoints_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_v2_bound_project(root, channel_slug="channel_a")
            prepare_step2_inputs(root, "channel_a", project["project_slug"])
            ctx = ui_server.build_app_context(root=root)
            workflow_status, workflow_data = ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/channel_a/projects/{project['project_slug']}/workflow",
                context=ctx,
            )
            detail_status, detail_data = ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/channel_a/projects/{project['project_slug']}",
                context=ctx,
            )
            self.assertEqual(workflow_status, 200)
            self.assertEqual(workflow_data["binding"]["workflow_version"], "2")
            self.assertEqual(detail_status, 200)
            self.assertEqual(
                set(detail_data["project"].keys()),
                {
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
                    "has_content",
                    "has_publishing_package",
                },
            )

    def test_temp_root_work_never_mutates_real_runtime(self):
        before = snapshot_runtime_state(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_v2_bound_project(root)
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            channel_prompt_bundle.build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_2_historical_research",
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project["project_slug"],
            )
        after = snapshot_runtime_state(ROOT)
        self.assertEqual(before, after)


source_docx_path = optional_source_docx_path()


if source_docx_path is not None:
    class OperatorSourceAuditTests(unittest.TestCase):
        def test_authoritative_source_doc_hash_matches_and_committed_prompt_files_match_extraction(self):
            source = source_docx_path
            self.assertEqual(prompt_source_ingest.verify_source_document(source), prompt_source_ingest.EXPECTED_SOURCE_SHA256)
            extracted = prompt_source_ingest.extract_formatted_prompts(source)
            prompt_dir = ROOT / "workflows" / "mist_of_ages_assisted_content" / "v2" / "prompts"
            file_map = {
                "prompt_1_transcript_analysis": "prompt_01_transcript_analyst.md",
                "prompt_2_historical_research": "prompt_02_historical_researcher.md",
                "prompt_3_creative_package": "prompt_03_creative_strategist.md",
                "prompt_4_retention_outline": "prompt_04_retention_architect.md",
                "prompt_5_narration_v1": "prompt_05_main_writer.md",
                "prompt_6_red_team": "prompt_06_red_team.md",
                "prompt_7_final_content": "prompt_07_finalizer.md",
            }
            self.assertEqual(set(extracted), set(file_map))
            for step_id, filename in file_map.items():
                committed = (prompt_dir / filename).read_text(encoding="utf-8")
                self.assertEqual(committed, extracted[step_id])


if __name__ == "__main__":
    unittest.main()
