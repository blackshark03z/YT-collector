import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_projects, channel_workflow, channel_workspace, ui_server
from tests.runtime_isolation_helpers import snapshot_runtime_state


def make_channel(root: Path, slug: str, channel_id: str, *, with_metrics: bool = True) -> None:
    channel_workspace.create_channel_workspace(root, slug, slug.replace("_", " ").title(), channel_id, "@" + slug)
    paths = channel_workspace.canonical_channel_paths(root, slug)
    paths.channel_learnings_master.write_text("# Learnings\n\nApproved.\n", encoding="utf-8", newline="\n")
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


def copy_production_workflows(root: Path) -> None:
    shutil.copytree(ROOT / "workflows", root / "workflows")


def create_project(root: Path, channel_slug: str, video_id: str = "VIDEO12345A") -> dict:
    return channel_projects.create_channel_project(
        root,
        channel_slug,
        video_id,
        f"https://youtube.com/watch?v={video_id}",
        source_metadata(),
        created_at="2026-07-01T00:00:00+00:00",
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def snapshot_tree(root: Path) -> dict[str, tuple[str, int]]:
    items: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            items[rel] = ("dir", 0)
        else:
            items[rel] = ("file", path.stat().st_size)
    return items


def map_channel_to_workflow(root: Path, channel_slug: str, workflow_id: str = "mist_of_ages_assisted_content") -> None:
    registry_path = root / "workflows" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["channel_defaults"][channel_slug] = {"workflow_id": workflow_id}
    write_json(registry_path, registry)


def add_temp_v2_definition(root: Path) -> str:
    v1_path = root / "workflows" / "mist_of_ages_assisted_content" / "v1" / "workflow.json"
    definition = json.loads(v1_path.read_text(encoding="utf-8"))
    definition["workflow_version"] = "2"
    definition["lifecycle_states"].insert(2, "EDITOR_NOTES_READY")
    definition["artifacts"].append(
        {
            "artifact_id": "editor_notes",
            "display_name": "Editor Notes",
            "relative_path": "workflow/editor_notes.md",
            "artifact_role": "GENERATED",
            "required": True,
            "media_type": "text/markdown",
        }
    )
    definition["steps"][2]["required_model"] = "Claude"
    inserted_step = {
        "step_id": "prompt_2b_editor_notes",
        "order": 3,
        "display_name": "Prompt 2B - Editor Notes",
        "required_model": "GPT",
        "input_artifact_ids": ["research_pack", "evidence_ledger"],
        "optional_input_artifact_ids": [],
        "output_artifact_ids": ["editor_notes"],
        "resulting_lifecycle_state": "EDITOR_NOTES_READY",
        "constraints": [],
        "prompt_source_ref": None,
    }
    definition["steps"].insert(2, inserted_step)
    for index, step in enumerate(definition["steps"], start=1):
        step["order"] = index
    v2_path = root / "workflows" / "mist_of_ages_assisted_content" / "v2" / "workflow.json"
    write_json(v2_path, definition)
    return channel_workflow._sha256_file(v2_path)


class ChannelWorkflowTests(unittest.TestCase):
    def test_production_registry_loads_and_channel_default_resolves(self):
        registry = channel_workflow.load_workflow_registry(ROOT)
        self.assertEqual(registry["schema_version"], 1)
        self.assertEqual(
            channel_workflow.get_channel_default_workflow(ROOT, "mist_of_ages"),
            {
                "workflow_id": "mist_of_ages_assisted_content",
                "workflow_version": "1",
                "workflow_definition_sha256": "BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E",
            },
        )
        self.assertIsNone(channel_workflow.get_channel_default_workflow(ROOT, "channel_without_mapping"))

    def test_registry_rejects_missing_default_legacy_and_unsafe_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "workflows" / "registry.json",
                {
                    "schema_version": 1,
                    "channel_defaults": {"mist_of_ages": {"workflow_id": "wf"}},
                    "workflows": {
                        "wf": {
                            "display_name": "WF",
                            "default_version": "2",
                            "legacy_unpinned_version": "1",
                            "versions": {
                                "1": {
                                    "status": "ACTIVE",
                                    "definition_path": "../outside.json",
                                    "definition_sha256": "A" * 64,
                                }
                            },
                        }
                    },
                },
            )
            with self.assertRaises(channel_workflow.ChannelWorkflowError) as ctx:
                channel_workflow.load_workflow_registry(root)
            self.assertEqual(ctx.exception.code, "WORKFLOW_REGISTRY_INVALID")

    def test_registry_rejects_missing_and_incorrect_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            registry_path = root / "workflows" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            del registry["workflows"]["mist_of_ages_assisted_content"]["versions"]["1"]["definition_sha256"]
            write_json(registry_path, registry)
            with self.assertRaises(channel_workflow.ChannelWorkflowError) as missing_ctx:
                channel_workflow.load_workflow_registry(root)
            self.assertEqual(missing_ctx.exception.code, "WORKFLOW_REGISTRY_INVALID")

            shutil.rmtree(root / "workflows")
            copy_production_workflows(root)
            registry = json.loads((root / "workflows" / "registry.json").read_text(encoding="utf-8"))
            registry["workflows"]["mist_of_ages_assisted_content"]["versions"]["1"]["definition_sha256"] = "0" * 64
            write_json(root / "workflows" / "registry.json", registry)
            with self.assertRaises(channel_workflow.ChannelWorkflowError) as bad_ctx:
                channel_workflow.load_workflow_definition(root, "mist_of_ages_assisted_content", "1")
            self.assertEqual(bad_ctx.exception.code, "WORKFLOW_DEFINITION_DIGEST_MISMATCH")

    def test_loader_is_independent_of_process_cwd(self):
        original_cwd = Path.cwd()
        tmp = tempfile.mkdtemp()
        try:
            os.chdir(tmp)
            definition = channel_workflow.load_workflow_definition(ROOT, "mist_of_ages_assisted_content", "1")
            self.assertEqual(definition["workflow_version"], "1")
            self.assertEqual(definition["steps"][0]["step_id"], "prompt_1_transcript_analysis")
        finally:
            os.chdir(original_cwd)
            shutil.rmtree(tmp)

    def test_definition_path_escape_is_rejected_after_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            safe_path = root / "workflows" / "mist_of_ages_assisted_content" / "v1" / "workflow.json"
            outside_path = root / "outside.json"
            outside_path.write_text(safe_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            safe_path.unlink()
            try:
                safe_path.symlink_to(outside_path)
            except (NotImplementedError, OSError):
                self.skipTest("Symlink creation is not supported in this environment.")
            with self.assertRaises(channel_workflow.ChannelWorkflowError) as ctx:
                channel_workflow.load_workflow_definition(root, "mist_of_ages_assisted_content", "1")
            self.assertEqual(ctx.exception.code, "WORKFLOW_DEFINITION_INVALID")

    def test_production_definition_loads_from_json_data(self):
        definition = channel_workflow.load_workflow_definition(ROOT, "mist_of_ages_assisted_content", "1")
        self.assertEqual(len(definition["steps"]), 7)
        self.assertEqual(len(definition["lifecycle_states"]), 9)
        self.assertEqual(definition["prompt_set"]["status"], "MISSING")
        self.assertFalse(definition["prompt_set"]["bundle_available"])
        self.assertEqual(definition["steps"][0]["step_id"], "prompt_1_transcript_analysis")
        self.assertEqual(definition["steps"][4]["required_model"], "Claude")
        self.assertEqual(definition["steps"][6]["constraints"][0]["group_id"], "claude_narration_and_final")
        self.assertEqual(definition["artifacts"][0]["relative_path"], "input/competitor_reference.md")

    def test_production_definition_digest_matches_exact_bytes_and_one_byte_change_breaks_it(self):
        production_path = ROOT / "workflows" / "mist_of_ages_assisted_content" / "v1" / "workflow.json"
        self.assertEqual(
            channel_workflow._sha256_file(production_path),
            "BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            definition_path = root / "workflows" / "mist_of_ages_assisted_content" / "v1" / "workflow.json"
            original = definition_path.read_bytes()
            mutated = original[:-1] + (b"\n" if original[-1:] != b"\n" else b" ")
            definition_path.write_bytes(mutated)
            with self.assertRaises(channel_workflow.ChannelWorkflowError) as ctx:
                channel_workflow.load_workflow_definition(root, "mist_of_ages_assisted_content", "1")
            self.assertEqual(ctx.exception.code, "WORKFLOW_DEFINITION_DIGEST_MISMATCH")

    def test_definition_rejects_duplicate_step_and_unsafe_artifact_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {
                "schema_version": 1,
                "workflow_id": "wf",
                "workflow_version": "1",
                "display_name": "WF",
                "execution_mode": "LINEAR",
                "entry_lifecycle_state": "A",
                "terminal_lifecycle_state": "B",
                "lifecycle_states": ["A", "B"],
                "prompt_set": {"status": "MISSING", "version": None, "bundle_available": False},
                "artifacts": [
                    {
                        "artifact_id": "bad",
                        "display_name": "Bad",
                        "relative_path": "../escape.md",
                        "artifact_role": "INPUT",
                        "required": True,
                        "media_type": "text/markdown",
                    }
                ],
                "steps": [
                    {
                        "step_id": "s1",
                        "order": 1,
                        "display_name": "S1",
                        "required_model": "GPT",
                        "input_artifact_ids": ["bad"],
                        "optional_input_artifact_ids": [],
                        "output_artifact_ids": [],
                        "resulting_lifecycle_state": "B",
                        "constraints": [],
                        "prompt_source_ref": None,
                    },
                    {
                        "step_id": "s1",
                        "order": 2,
                        "display_name": "S2",
                        "required_model": "GPT",
                        "input_artifact_ids": ["bad"],
                        "optional_input_artifact_ids": [],
                        "output_artifact_ids": [],
                        "resulting_lifecycle_state": "B",
                        "constraints": [],
                        "prompt_source_ref": None,
                    },
                ],
            }
            write_json(root / "workflows" / "wf" / "v1" / "workflow.json", payload)
            write_json(
                root / "workflows" / "registry.json",
                {
                    "schema_version": 1,
                    "channel_defaults": {"mist_of_ages": {"workflow_id": "wf"}},
                    "workflows": {
                        "wf": {
                            "display_name": "WF",
                            "default_version": "1",
                            "legacy_unpinned_version": "1",
                            "versions": {
                                "1": {
                                    "status": "ACTIVE",
                                    "definition_path": "wf/v1/workflow.json",
                                    "definition_sha256": channel_workflow._sha256_file(root / "workflows" / "wf" / "v1" / "workflow.json"),
                                }
                            },
                        }
                    },
                },
            )
            with self.assertRaises(channel_workflow.ChannelWorkflowError) as ctx:
                channel_workflow.load_workflow_definition(root, "wf", "1")
            self.assertEqual(ctx.exception.code, "WORKFLOW_DEFINITION_INVALID")

    def test_new_project_gets_immutable_binding_and_legacy_project_stays_unbound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            make_channel(root, "mist_of_ages", "UC123")
            bound_project = create_project(root, "mist_of_ages")
            payload = json.loads(
                (root / "channels" / "mist_of_ages" / "projects" / bound_project["project_slug"] / "project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["workflow_binding"]["workflow_version"], "1")
            self.assertEqual(
                payload["workflow_binding"]["workflow_definition_sha256"],
                "BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E",
            )

            legacy_project = create_project(root, "mist_of_ages", "VIDEO12345B")
            legacy_path = root / "channels" / "mist_of_ages" / "projects" / legacy_project["project_slug"] / "project.json"
            legacy_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
            del legacy_payload["workflow_binding"]
            write_json(legacy_path, legacy_payload)
            before = legacy_path.read_text(encoding="utf-8")
            model = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                legacy_project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", legacy_project["project_slug"]),
                root / "channels" / "mist_of_ages" / "projects" / legacy_project["project_slug"],
            )
            after = legacy_path.read_text(encoding="utf-8")
            self.assertEqual(model["binding"]["binding_source"], "LEGACY_SYNTHESIZED")
            self.assertEqual(before, after)

    def test_default_change_affects_only_new_project_binding_and_legacy_unbound_stays_on_legacy_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            make_channel(root, "mist_of_ages", "UC123")
            first = create_project(root, "mist_of_ages", "VIDEO12345A")
            first_payload = json.loads(
                (root / "channels" / "mist_of_ages" / "projects" / first["project_slug"] / "project.json").read_text(encoding="utf-8")
            )
            legacy_project = create_project(root, "mist_of_ages", "VIDEO12345L")
            legacy_path = root / "channels" / "mist_of_ages" / "projects" / legacy_project["project_slug"] / "project.json"
            legacy_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
            del legacy_payload["workflow_binding"]
            write_json(legacy_path, legacy_payload)
            v2_digest = add_temp_v2_definition(root)
            registry_path = root / "workflows" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "2"
            registry["workflows"]["mist_of_ages_assisted_content"]["versions"]["2"] = {
                "status": "ACTIVE",
                "definition_path": "mist_of_ages_assisted_content/v2/workflow.json",
                "definition_sha256": v2_digest,
            }
            write_json(registry_path, registry)

            second = create_project(root, "mist_of_ages", "VIDEO12345B")
            second_payload = json.loads(
                (root / "channels" / "mist_of_ages" / "projects" / second["project_slug"] / "project.json").read_text(encoding="utf-8")
            )
            legacy_model = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                legacy_project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", legacy_project["project_slug"]),
                root / "channels" / "mist_of_ages" / "projects" / legacy_project["project_slug"],
            )
            self.assertEqual(first_payload["workflow_binding"]["workflow_version"], "1")
            self.assertEqual(second_payload["workflow_binding"]["workflow_version"], "2")
            self.assertEqual(legacy_model["binding"]["workflow_version"], "1")
            self.assertEqual(legacy_model["binding"]["binding_source"], "LEGACY_SYNTHESIZED")
            self.assertEqual(first_payload["workflow_binding"]["workflow_definition_sha256"], "BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E")
            self.assertEqual(second_payload["workflow_binding"]["workflow_definition_sha256"], v2_digest)
            self.assertEqual(
                legacy_model["binding"]["workflow_definition_sha256"],
                "BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E",
            )

            project_dir = root / "channels" / "mist_of_ages" / "projects" / second["project_slug"]
            state_path = project_dir / "workflow" / "workflow_state.json"
            write_json(
                state_path,
                {
                    "schema_version": 1,
                    "workflow_id": "mist_of_ages_assisted_content",
                    "workflow_version": "2",
                    "workflow_definition_sha256": v2_digest,
                    "current_step_id": "prompt_2_historical_research",
                    "current_lifecycle_state": "RESEARCH_READY",
                    "step_states": {"prompt_2_historical_research": {"status": "READY"}},
                    "created_at": "2026-07-01T00:00:00+00:00",
                    "updated_at": "2026-07-01T00:00:00+00:00",
                },
            )
            model = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                second["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", second["project_slug"]),
                project_dir,
            )
            self.assertEqual(len(model["definition"]["steps"]), 8)
            self.assertEqual(model["definition"]["steps"][2]["step_id"], "prompt_2b_editor_notes")
            self.assertEqual(model["definition"]["steps"][3]["required_model"], "Claude")
            self.assertTrue(any(item["artifact_id"] == "editor_notes" for item in model["artifacts"]))
            self.assertEqual(model["state"]["next_step_id"], "prompt_2b_editor_notes")

    def test_channel_without_configured_workflow_remains_creatable_without_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            make_channel(root, "tam_builds", "UC999")
            project = create_project(root, "tam_builds")
            payload = json.loads(
                (root / "channels" / "tam_builds" / "projects" / project["project_slug"] / "project.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("workflow_binding", payload)

    def test_missing_state_is_synthesized_and_get_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            make_channel(root, "mist_of_ages", "UC123")
            project = create_project(root, "mist_of_ages")
            project_dir = root / "channels" / "mist_of_ages" / "projects" / project["project_slug"]
            state_path = project_dir / "workflow" / "workflow_state.json"
            self.assertFalse(state_path.exists())

            ready_model = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            self.assertFalse(ready_model["state"]["initialized"])
            self.assertEqual(ready_model["state"]["current_step_id"], "prompt_1_transcript_analysis")
            self.assertEqual(ready_model["state"]["current_step_status"], "BLOCKED")
            self.assertEqual(ready_model["state"]["blocking_reason"], "WORKFLOW_INPUT_NOT_READY")
            self.assertFalse(state_path.exists())

            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 10)
            ready_model = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            self.assertEqual(ready_model["state"]["current_lifecycle_state"], "INPUT_READY")
            self.assertEqual(ready_model["state"]["current_step_status"], "READY")
            self.assertEqual(ready_model["state"]["next_step_id"], "prompt_2_historical_research")
            self.assertFalse(state_path.exists())

    def test_valid_and_invalid_state_file_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            make_channel(root, "mist_of_ages", "UC123")
            project = create_project(root, "mist_of_ages")
            project_dir = root / "channels" / "mist_of_ages" / "projects" / project["project_slug"]
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 10)
            state_path = project_dir / "workflow" / "workflow_state.json"
            payload = {
                "schema_version": 1,
                "workflow_id": "mist_of_ages_assisted_content",
                "workflow_version": "1",
                "workflow_definition_sha256": "BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E",
                "current_step_id": "prompt_1_transcript_analysis",
                "current_lifecycle_state": "INPUT_READY",
                "step_states": {"prompt_1_transcript_analysis": {"status": "READY"}},
                "created_at": "2026-07-01T00:00:00+00:00",
                "updated_at": "2026-07-01T00:00:00+00:00",
            }
            write_json(state_path, payload)
            before = state_path.read_text(encoding="utf-8")
            model = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            self.assertTrue(model["state"]["initialized"])
            self.assertEqual(before, state_path.read_text(encoding="utf-8"))

            payload["workflow_definition_sha256"] = "0" * 64
            write_json(state_path, payload)
            with self.assertRaises(channel_workflow.ChannelWorkflowError) as mismatch_ctx:
                channel_workflow.build_workflow_read_model(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                    project_dir,
                )
            self.assertEqual(mismatch_ctx.exception.code, "WORKFLOW_STATE_INVALID")

            state_path.write_text("{", encoding="utf-8")
            with self.assertRaises(channel_workflow.ChannelWorkflowError) as bad_ctx:
                channel_workflow.build_workflow_read_model(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                    project_dir,
                )
            self.assertEqual(bad_ctx.exception.code, "WORKFLOW_STATE_INVALID")

    def test_workflow_api_is_channel_scoped_and_existing_project_detail_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            map_channel_to_workflow(root, "channel_a")
            make_channel(root, "channel_a", "UC1")
            make_channel(root, "channel_b", "UC2")
            project = create_project(root, "channel_a")
            channel_projects.save_project_transcript(root, "channel_a", project["project_slug"], "real transcript " * 10)
            ctx = ui_server.build_app_context(root=root)

            detail_status, detail_data = ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/channel_a/projects/{project['project_slug']}",
                context=ctx,
            )
            self.assertEqual(detail_status, 200)
            self.assertIn("has_content", detail_data["project"])
            self.assertNotIn("workflow_binding", detail_data["project"])

            status, data = ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/channel_a/projects/{project['project_slug']}/workflow",
                context=ctx,
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["channel_slug"], "channel_a")
            self.assertEqual(data["binding"]["workflow_version"], "1")

            with self.assertRaises(ui_server.V2Error) as missing_ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    "/api/v2/channels/channel_a/projects/missing/workflow",
                    context=ctx,
                )
            self.assertEqual(missing_ctx.exception.code, "PROJECT_NOT_FOUND")

            with self.assertRaises(ui_server.V2Error) as cross_ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/channel_b/projects/{project['project_slug']}/workflow",
                    context=ctx,
                )
            self.assertEqual(cross_ctx.exception.code, "PROJECT_NOT_FOUND")

            with self.assertRaises(ui_server.V2Error) as invalid_ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/Bad-Slug/projects/{project['project_slug']}/workflow",
                    context=ctx,
                )
            self.assertEqual(invalid_ctx.exception.code, "INVALID_CHANNEL_SLUG")

    def test_workflow_get_creates_no_file_or_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            map_channel_to_workflow(root, "channel_a")
            make_channel(root, "channel_a", "UC1")
            project = create_project(root, "channel_a")
            project_dir = root / "channels" / "channel_a" / "projects" / project["project_slug"]
            before_tree = snapshot_tree(project_dir)
            before_project_json = (project_dir / "project.json").read_text(encoding="utf-8")
            ctx = ui_server.build_app_context(root=root)
            status, payload = ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/channel_a/projects/{project['project_slug']}/workflow",
                context=ctx,
            )
            after_tree = snapshot_tree(project_dir)
            after_project_json = (project_dir / "project.json").read_text(encoding="utf-8")
            self.assertEqual(status, 200)
            self.assertEqual(payload["project_slug"], project["project_slug"])
            self.assertEqual(before_tree, after_tree)
            self.assertEqual(before_project_json, after_project_json)

    def test_unmapped_channel_workflow_endpoint_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            make_channel(root, "tam_builds", "UC9")
            project = create_project(root, "tam_builds")
            ctx = ui_server.build_app_context(root=root)
            with self.assertRaises(ui_server.V2Error) as err:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/tam_builds/projects/{project['project_slug']}/workflow",
                    context=ctx,
                )
            self.assertEqual(err.exception.code, "WORKFLOW_NOT_CONFIGURED")

    def test_temp_root_work_never_mutates_real_runtime(self):
        before = snapshot_runtime_state(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_production_workflows(root)
            make_channel(root, "mist_of_ages", "UC123")
            project = create_project(root, "mist_of_ages")
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 10)
            channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                root / "channels" / "mist_of_ages" / "projects" / project["project_slug"],
            )
        after = snapshot_runtime_state(ROOT)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
