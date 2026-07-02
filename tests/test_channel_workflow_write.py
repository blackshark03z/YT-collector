import json
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_projects, channel_workflow, channel_workflow_write, channel_workspace, ui_server
from tests.runtime_isolation_helpers import snapshot_runtime_state
from tests.test_channel_output_parser import build_generic_three_artifact_fixture
from tests.test_channel_prompt_bundle import copy_workflows, create_project, make_channel, prepare_step2_inputs


def make_v2_project(root: Path, *, channel_slug: str = "mist_of_ages", video_id: str = "VIDEO12345A") -> tuple[dict, Path]:
    copy_workflows(root)
    registry_path = root / "workflows" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "2"
    registry["channel_defaults"][channel_slug] = {"workflow_id": "mist_of_ages_assisted_content"}
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8", newline="\n")
    make_channel(root, channel_slug, "UC123")
    project = create_project(root, channel_slug, video_id)
    project_dir = channel_workspace.canonical_channel_paths(root, channel_slug).projects_dir / project["project_slug"]
    return project, project_dir


def build_prompt1_output() -> str:
    return (
        "## Subject\nRome\n"
        "## Competitor Promise\nPromise\n"
        "## Narrative Map\nMap\n"
        "## Strong Idea-Level Elements\nStrong\n"
        "## Weak or Removable Elements\nWeak\n"
        "## Claims Requiring Verification\nClaims\n"
        "## Originality Risks\nRisks\n"
        "## Neutral Research Questions\nQuestions\n"
    )


def build_prompt2_output() -> str:
    return (
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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def build_bundle(root: Path, project_slug: str, step_id: str, project_dir: Path) -> dict:
    return __import__("scripts.channel_prompt_bundle", fromlist=[""]).build_prompt_bundle(
        root,
        "mist_of_ages",
        project_slug,
        step_id,
        channel_projects.load_channel_project(root, "mist_of_ages", project_slug),
        project_dir,
    )


def tree_hashes(root: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            entries[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    return entries


class ChannelWorkflowWriteTests(unittest.TestCase):
    def test_absent_state_synthesizes_revision_zero_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            model = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            self.assertEqual(model["state"]["state_revision"], 0)
            self.assertFalse(model["state"]["state_persisted"])
            self.assertFalse((project_dir / "workflow" / "workflow_state.json").exists())

    def test_first_candidate_save_persists_schema_v2_and_keeps_stable_artifact_untouched(self):
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
            status, data = channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                bundle["bundle_sha256"],
                build_prompt1_output(),
                0,
            )
            self.assertEqual(status, 201)
            self.assertEqual(data["status"], "CANDIDATE_SAVED")
            state_path = project_dir / "workflow" / "workflow_state.json"
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["state_revision"], 1)
            self.assertEqual(payload["step_states"]["prompt_1_transcript_analysis"]["status"], "CANDIDATE")
            candidate_revision = payload["artifact_heads"]["transcript_analysis"]["candidate_revision_id"]
            self.assertTrue((project_dir / "workflow" / "revisions" / "artifacts" / "transcript_analysis" / candidate_revision / "content.md").exists())
            self.assertIn("TODO: Fill manually during Workflow V2.", (project_dir / "workflow" / "transcript_analysis.md").read_text(encoding="utf-8"))

    def test_save_candidate_route_returns_idempotent_replay_without_new_files(self):
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
            first_status, first = ui_server.dispatch_v2_request(
                "POST",
                f"/api/v2/channels/mist_of_ages/projects/{project['project_slug']}/workflow/steps/prompt_1_transcript_analysis/revisions",
                {
                    "bundle_sha256": bundle["bundle_sha256"],
                    "output_text": build_prompt1_output(),
                    "expected_state_revision": 0,
                },
                context=ui_server.build_app_context(root=root),
            )
            before = sorted(path.relative_to(project_dir).as_posix() for path in project_dir.rglob("*"))
            second_status, second = ui_server.dispatch_v2_request(
                "POST",
                f"/api/v2/channels/mist_of_ages/projects/{project['project_slug']}/workflow/steps/prompt_1_transcript_analysis/revisions",
                {
                    "bundle_sha256": bundle["bundle_sha256"],
                    "output_text": build_prompt1_output(),
                    "expected_state_revision": 1,
                },
                context=ui_server.build_app_context(root=root),
            )
            after = sorted(path.relative_to(project_dir).as_posix() for path in project_dir.rglob("*"))
            self.assertEqual(first_status, 201)
            self.assertEqual(second_status, 200)
            self.assertEqual(second["status"], "CANDIDATE_ALREADY_SAVED")
            self.assertTrue(second["idempotent_replay"])
            self.assertEqual(first["revision_group"]["revision_group_id"], second["revision_group"]["revision_group_id"])
            self.assertEqual(before, after)

    def test_different_output_conflicts_when_candidate_exists(self):
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
            channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                bundle["bundle_sha256"],
                build_prompt1_output(),
                0,
            )
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError) as ctx:
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output() + "\nextra",
                    1,
                )
            self.assertEqual(ctx.exception.code, "CANDIDATE_EXISTS")

    def test_multi_artifact_candidate_save_is_atomic_and_does_not_unlock_next_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            project_data = channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])
            bundle = __import__("scripts.channel_prompt_bundle", fromlist=[""]).build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_2_historical_research",
                project_data,
                project_dir,
            )
            status, data = channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_2_historical_research",
                bundle["bundle_sha256"],
                build_prompt2_output(),
                0,
            )
            self.assertEqual(status, 201)
            self.assertEqual(len(data["revision_group"]["artifacts"]), 2)
            state = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )["state"]
            self.assertEqual(state["current_step_id"], "prompt_2_historical_research")
            self.assertEqual(state["current_step_status"], "CANDIDATE")
            self.assertEqual(state["next_step_id"], "prompt_3_creative_package")
            self.assertIn("TODO: Fill manually during Workflow V2.", (project_dir / "workflow" / "research_pack.md").read_text(encoding="utf-8"))
            self.assertIn("TODO: Fill manually during Workflow V2.", (project_dir / "workflow" / "evidence_ledger.md").read_text(encoding="utf-8"))

    def test_schema_v1_state_converts_only_on_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            state_path = project_dir / "workflow" / "workflow_state.json"
            write_json(
                state_path,
                {
                    "schema_version": 1,
                    "workflow_id": "mist_of_ages_assisted_content",
                    "workflow_version": "2",
                    "workflow_definition_sha256": "5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606",
                    "current_step_id": "prompt_1_transcript_analysis",
                    "current_lifecycle_state": "INPUT_READY",
                    "step_states": {"prompt_1_transcript_analysis": {"status": "READY"}},
                    "created_at": "2026-07-01T00:00:00+00:00",
                    "updated_at": "2026-07-01T00:00:00+00:00",
                },
            )
            read_model = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            self.assertEqual(read_model["state"]["schema_version"], 1)
            bundle = __import__("scripts.channel_prompt_bundle", fromlist=[""]).build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                bundle["bundle_sha256"],
                build_prompt1_output(),
                0,
            )
            upgraded = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(upgraded["schema_version"], 2)

    def test_state_revision_conflict_writes_nothing(self):
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
            before = sorted(path.relative_to(project_dir).as_posix() for path in project_dir.rglob("*"))
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError) as ctx:
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output(),
                    7,
                )
            after = sorted(path.relative_to(project_dir).as_posix() for path in project_dir.rglob("*"))
            self.assertEqual(ctx.exception.code, "STATE_REVISION_CONFLICT")
            self.assertFalse((project_dir / "workflow" / "workflow_state.json").exists())
            self.assertEqual([item for item in after if not item.startswith("workflow/_transactions")], before)
            self.assertEqual([item.name for item in (project_dir / "workflow" / "_transactions").iterdir() if item.name.startswith("txn_")], [])

    def test_active_and_stale_lock_are_reported(self):
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
            lock_path = project_dir / "workflow" / "_transactions" / ".lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(lock_path, {"transaction_id": "txn_demo", "created_at": "2099-01-01T00:00:00+00:00", "process_id": 1, "operation": "SAVE_CANDIDATE"})
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError) as busy_ctx:
                channel_workflow_write.save_candidate(root, "mist_of_ages", project["project_slug"], "prompt_1_transcript_analysis", bundle["bundle_sha256"], build_prompt1_output(), 0)
            self.assertEqual(busy_ctx.exception.code, "PROJECT_WORKFLOW_BUSY")
            write_json(lock_path, {"transaction_id": "txn_demo", "created_at": "2000-01-01T00:00:00+00:00", "process_id": 1, "operation": "SAVE_CANDIDATE"})
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError) as stale_ctx:
                channel_workflow_write.save_candidate(root, "mist_of_ages", project["project_slug"], "prompt_1_transcript_analysis", bundle["bundle_sha256"], build_prompt1_output(), 0)
            self.assertEqual(stale_ctx.exception.code, "PROJECT_WORKFLOW_LOCK_STALE")

    def test_recovery_completes_after_partial_revision_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            project_data = channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])
            bundle = __import__("scripts.channel_prompt_bundle", fromlist=[""]).build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_2_historical_research",
                project_data,
                project_dir,
            )
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError):
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_2_historical_research",
                    bundle["bundle_sha256"],
                    build_prompt2_output(),
                    0,
                    fail_stage="after_one_artifact_revision_published",
                )
            status, replay = channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_2_historical_research",
                bundle["bundle_sha256"],
                build_prompt2_output(),
                1,
            )
            self.assertEqual(status, 200)
            self.assertEqual(replay["status"], "CANDIDATE_ALREADY_SAVED")
            self.assertFalse((project_dir / "workflow" / "_transactions" / f"txn_{replay['revision_group']['raw_output_sha256'][:16].lower()}").exists())

    def test_recovery_cleans_completed_transaction_after_state_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            bundle = build_bundle(root, project["project_slug"], "prompt_1_transcript_analysis", project_dir)
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError):
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output(),
                    0,
                    fail_stage="after_state_replacement_before_cleanup",
                )
            status, replay = channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                bundle["bundle_sha256"],
                build_prompt1_output(),
                1,
            )
            self.assertEqual(status, 200)
            self.assertEqual(replay["status"], "CANDIDATE_ALREADY_SAVED")
            leftovers = [item.name for item in (project_dir / "workflow" / "_transactions").iterdir() if item.name.startswith("txn_")]
            self.assertEqual(leftovers, [])

    def test_failure_before_staging_complete_requires_recovery_and_leaves_state_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            bundle = build_bundle(root, project["project_slug"], "prompt_1_transcript_analysis", project_dir)
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError) as ctx:
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output(),
                    0,
                    fail_stage="before_staging_complete",
                )
            self.assertEqual(ctx.exception.code, "WORKFLOW_WRITE_FAILED")
            self.assertFalse((project_dir / "workflow" / "workflow_state.json").exists())
            self.assertEqual(
                channel_workflow_write.classify_transaction_state(
                    paths=channel_workflow_write.workflow_write_paths(project_dir),
                    txn_dir=channel_workflow_write.workflow_write_paths(project_dir).transactions_dir / f"txn_{channel_workflow_write._canonical_idempotency_sha256(channel_slug='mist_of_ages', project_slug=project['project_slug'], workflow_id='mist_of_ages_assisted_content', workflow_version='2', step_id='prompt_1_transcript_analysis', bundle_sha256=bundle['bundle_sha256'], raw_output_sha256=channel_workflow_write._sha256_text(build_prompt1_output()))[:16].lower()}",
                    binding=channel_workflow.resolve_project_workflow_binding(root, "mist_of_ages", channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])),
                    definition=channel_workflow.load_workflow_definition(root, "mist_of_ages_assisted_content", "2"),
                    project_dir=project_dir,
                ),
                "STAGING_INCOMPLETE",
            )
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError) as retry_ctx:
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output(),
                    0,
                )
            self.assertEqual(retry_ctx.exception.code, "WORKFLOW_RECOVERY_REQUIRED")
            self.assertFalse((project_dir / "workflow" / "workflow_state.json").exists())

    def test_recovery_after_all_artifact_revisions_before_group_reuses_original_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            bundle = build_bundle(root, project["project_slug"], "prompt_2_historical_research", project_dir)
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError):
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_2_historical_research",
                    bundle["bundle_sha256"],
                    build_prompt2_output(),
                    0,
                    fail_stage="after_all_artifact_revisions_before_group",
                )
            paths = channel_workflow_write.workflow_write_paths(project_dir)
            txn_dir = next(item for item in paths.transactions_dir.iterdir() if item.name.startswith("txn_"))
            self.assertEqual(
                channel_workflow_write.classify_transaction_state(
                    paths=paths,
                    txn_dir=txn_dir,
                    binding=channel_workflow.resolve_project_workflow_binding(root, "mist_of_ages", channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])),
                    definition=channel_workflow.load_workflow_definition(root, "mist_of_ages_assisted_content", "2"),
                    project_dir=project_dir,
                ),
                "PARTIALLY_PUBLISHED",
            )
            status, replay = channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_2_historical_research",
                bundle["bundle_sha256"],
                build_prompt2_output(),
                1,
            )
            self.assertEqual(status, 200)
            self.assertEqual(replay["status"], "CANDIDATE_ALREADY_SAVED")
            revision_ids = {item["artifact_id"]: item["revision_id"] for item in replay["revision_group"]["artifacts"]}
            self.assertEqual(set(revision_ids), {"research_pack", "evidence_ledger"})
            self.assertEqual(set(revision_ids.values()), {"rev_000001"})

    def test_recovery_after_group_publication_before_state_reuses_original_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            bundle = build_bundle(root, project["project_slug"], "prompt_1_transcript_analysis", project_dir)
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError):
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output(),
                    0,
                    fail_stage="after_group_publication_before_state",
                )
            status, replay = channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                bundle["bundle_sha256"],
                build_prompt1_output(),
                1,
            )
            self.assertEqual(status, 200)
            self.assertEqual(replay["revision_group"]["revision_group_id"], "grp_000001")
            self.assertEqual(replay["revision_group"]["artifacts"][0]["revision_id"], "rev_000001")

    def test_recovery_refuses_corrupted_final_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            bundle = build_bundle(root, project["project_slug"], "prompt_1_transcript_analysis", project_dir)
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError):
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output(),
                    0,
                    fail_stage="after_group_publication_before_state",
                )
            revision_content = project_dir / "workflow" / "revisions" / "artifacts" / "transcript_analysis" / "rev_000001" / "content.md"
            revision_content.write_text("corrupted", encoding="utf-8", newline="\n")
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError) as ctx:
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output(),
                    1,
                )
            self.assertEqual(ctx.exception.code, "WORKFLOW_RECOVERY_REQUIRED")

    def test_recovery_refuses_corrupted_staged_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            bundle = build_bundle(root, project["project_slug"], "prompt_1_transcript_analysis", project_dir)
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError):
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output(),
                    0,
                    fail_stage="after_state_replacement_before_cleanup",
                )
            state_path = project_dir / "workflow" / "workflow_state.json"
            state_path.unlink()
            staged_state_path = next((project_dir / "workflow" / "_transactions").glob("txn_*/next_workflow_state.json"))
            staged_state_path.write_text("{}", encoding="utf-8", newline="\n")
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError) as ctx:
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_1_transcript_analysis",
                    bundle["bundle_sha256"],
                    build_prompt1_output(),
                    1,
                )
            self.assertEqual(ctx.exception.code, "WORKFLOW_RECOVERY_REQUIRED")

    def test_existing_exact_final_targets_are_reused_during_recovery_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            bundle = build_bundle(root, project["project_slug"], "prompt_2_historical_research", project_dir)
            with self.assertRaises(channel_workflow_write.ChannelWorkflowWriteError):
                channel_workflow_write.save_candidate(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    "prompt_2_historical_research",
                    bundle["bundle_sha256"],
                    build_prompt2_output(),
                    0,
                    fail_stage="after_all_artifact_revisions_before_group",
                )
            before_hashes = tree_hashes(project_dir / "workflow" / "revisions")
            status, _ = channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_2_historical_research",
                bundle["bundle_sha256"],
                build_prompt2_output(),
                1,
            )
            after_hashes = tree_hashes(project_dir / "workflow" / "revisions")
            self.assertEqual(status, 200)
            for path, digest in before_hashes.items():
                self.assertEqual(after_hashes.get(path), digest)

    def test_unknown_extra_file_in_revision_directory_fails_state_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            bundle = build_bundle(root, project["project_slug"], "prompt_1_transcript_analysis", project_dir)
            channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                bundle["bundle_sha256"],
                build_prompt1_output(),
                0,
            )
            extra_path = project_dir / "workflow" / "revisions" / "artifacts" / "transcript_analysis" / "rev_000001" / "extra.txt"
            extra_path.write_text("unexpected", encoding="utf-8", newline="\n")
            with self.assertRaises(channel_workflow.ChannelWorkflowError) as ctx:
                channel_workflow.build_workflow_read_model(
                    root,
                    "mist_of_ages",
                    project["project_slug"],
                    channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                    project_dir,
                )
            self.assertEqual(ctx.exception.code, "WORKFLOW_STATE_INVALID")

    def test_lock_cleanup_does_not_remove_replaced_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            paths = channel_workflow_write.workflow_write_paths(project_dir)
            handle = channel_workflow_write._acquire_lock(paths.lock_file, transaction_id="txn_a", operation="SAVE_CANDIDATE")
            write_json(
                paths.lock_file,
                {
                    "transaction_id": "txn_b",
                    "created_at": "2099-01-01T00:00:00+00:00",
                    "process_id": 999,
                    "operation": "SAVE_CANDIDATE",
                    "owner_token": "replacement",
                },
            )
            channel_workflow_write._release_lock(handle)
            self.assertTrue(paths.lock_file.exists())

    def test_schema_v1_read_does_not_migrate_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            state_path = project_dir / "workflow" / "workflow_state.json"
            original_payload = {
                "schema_version": 1,
                "workflow_id": "mist_of_ages_assisted_content",
                "workflow_version": "2",
                "workflow_definition_sha256": "5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606",
                "current_step_id": "prompt_1_transcript_analysis",
                "current_lifecycle_state": "INPUT_READY",
                "step_states": {"prompt_1_transcript_analysis": {"status": "READY"}},
                "created_at": "2026-07-01T00:00:00+00:00",
                "updated_at": "2026-07-01T00:00:00+00:00",
            }
            write_json(state_path, original_payload)
            before = state_path.read_bytes()
            model = channel_workflow.build_workflow_read_model(
                root,
                "mist_of_ages",
                project["project_slug"],
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            after = state_path.read_bytes()
            self.assertEqual(model["state"]["schema_version"], 1)
            self.assertEqual(before, after)

    def test_schema_v1_conversion_initializes_counters_from_existing_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 12)
            revision_dir = project_dir / "workflow" / "revisions" / "artifacts" / "transcript_analysis" / "rev_000003"
            revision_dir.mkdir(parents=True, exist_ok=True)
            (revision_dir / "content.md").write_text("old", encoding="utf-8", newline="\n")
            write_json(
                revision_dir / "metadata.json",
                {
                    "schema_version": 1,
                    "revision_id": "rev_000003",
                    "artifact_id": "transcript_analysis",
                    "revision_group_id": "grp_000004",
                    "workflow_id": "mist_of_ages_assisted_content",
                    "workflow_version": "2",
                    "workflow_definition_sha256": "5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606",
                    "created_status": "CANDIDATE",
                },
            )
            state_path = project_dir / "workflow" / "workflow_state.json"
            write_json(
                state_path,
                {
                    "schema_version": 1,
                    "workflow_id": "mist_of_ages_assisted_content",
                    "workflow_version": "2",
                    "workflow_definition_sha256": "5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606",
                    "current_step_id": "prompt_1_transcript_analysis",
                    "current_lifecycle_state": "INPUT_READY",
                    "step_states": {"prompt_1_transcript_analysis": {"status": "READY"}},
                    "created_at": "2026-07-01T00:00:00+00:00",
                    "updated_at": "2026-07-01T00:00:00+00:00",
                },
            )
            bundle = build_bundle(root, project["project_slug"], "prompt_1_transcript_analysis", project_dir)
            channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                bundle["bundle_sha256"],
                build_prompt1_output(),
                0,
            )
            upgraded = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(upgraded["counters"]["next_revision_number_by_artifact"]["transcript_analysis"], 5)

    def test_publish_order_is_state_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_v2_project(root)
            prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
            bundle = build_bundle(root, project["project_slug"], "prompt_2_historical_research", project_dir)
            publish_log: list[str] = []
            channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_2_historical_research",
                bundle["bundle_sha256"],
                build_prompt2_output(),
                0,
                publish_log=publish_log,
            )
            self.assertTrue(all(not item.startswith("stable:") for item in publish_log))
            self.assertTrue(publish_log[-2].startswith("state:"))
            self.assertEqual(publish_log[-1], "cleanup:workflow/_transactions")
            group_index = next(index for index, item in enumerate(publish_log) if item.startswith("group:"))
            state_index = next(index for index, item in enumerate(publish_log) if item.startswith("state:"))
            self.assertLess(group_index, state_index)
            self.assertTrue(all(index < group_index for index, item in enumerate(publish_log) if item.startswith("artifact:")))

    def test_three_artifact_generic_fixture_saves_one_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = build_generic_three_artifact_fixture(root)
            bundle = __import__("scripts.channel_prompt_bundle", fromlist=[""]).build_prompt_bundle(
                root,
                "mist_of_ages",
                project["project_slug"],
                "gamma_native_custom",
                channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"]),
                project_dir,
            )
            output_text = (
                "=== FILE 1: story.custom ===\n# Story\nBody\n"
                "=== FILE 2: package.custom ===\n# Package\nBody\n"
                "=== FILE 3: summary.custom ===\n# Summary\nBody\n"
            )
            status, data = channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "gamma_native_custom",
                bundle["bundle_sha256"],
                output_text,
                0,
            )
            self.assertEqual(status, 201)
            self.assertEqual(len(data["revision_group"]["artifacts"]), 3)

    def test_no_real_repository_runtime_path_is_touched(self):
        before = snapshot_runtime_state(ROOT)
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
            channel_workflow_write.save_candidate(
                root,
                "mist_of_ages",
                project["project_slug"],
                "prompt_1_transcript_analysis",
                bundle["bundle_sha256"],
                build_prompt1_output(),
                0,
            )
        after = snapshot_runtime_state(ROOT)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
