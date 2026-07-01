import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import legacy_migration


FIXED_TIME = "2026-07-01T12:00:00+00:00"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, payload) -> None:
    write_text(path, json.dumps(payload, indent=2) + "\n")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk_strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)
    elif isinstance(value, str):
        yield value


class LegacyMigrationTests(unittest.TestCase):
    def make_repo(
        self,
        *,
        identity=True,
        identity_payload=None,
        learnings="# Approved learnings\n\nKeep this tight.\n",
        token_payload=None,
        token_raw=None,
        projects=None,
        jesus_exists=True,
        canonical_workspace=False,
        canonical_workspace_partial=False,
        canonical_token=False,
        channel_unknown=None,
    ):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        if identity:
            payload = identity_payload or {
                "id": "UC123",
                "title": "Mist of Ages",
                "customUrl": "@mistofages",
                "uploads": "UU123",
                "connected_at": "2026-07-01T00:39:50+00:00",
            }
            write_json(root / ".local" / "mist_of_ages_channel.json", payload)
        channel_dir = root / "channel" / "mist_of_ages"
        if learnings is not None:
            write_text(channel_dir / "channel_learnings_master.md", learnings)
        if channel_unknown:
            for name in channel_unknown:
                write_text(channel_dir / name, "unknown\n")
        if token_raw is not None:
            write_text(root / "youtube_oauth_token.json", token_raw)
        else:
            payload = token_payload
            if payload is None:
                payload = {
                    "access_token": "ACCESS_SECRET_VALUE",
                    "refresh_token": "REFRESH_SECRET_VALUE",
                }
            if payload is not False:
                write_json(root / "youtube_oauth_token.json", payload)
        projects = projects or []
        for project in projects:
            project_dir = root / "projects" / project["name"]
            if project.get("project_json", True):
                project_payload = project.get(
                    "project_payload",
                    {
                        "schema_version": project.get("schema_version", 1),
                        "source_video_id": project.get("source_video_id", "abc123"),
                    },
                )
                write_json(project_dir / "project.json", project_payload)
            if project.get("transcript"):
                write_text(project_dir / "research" / "competitor_transcript.md", "manual transcript\n")
            if project.get("workflow_files"):
                for index in range(project["workflow_files"]):
                    write_text(project_dir / "workflow" / f"step_{index}.md", "workflow\n")
            if project.get("content"):
                write_text(project_dir / "content.md", "final content\n")
            if project.get("publishing"):
                write_text(project_dir / "publishing_package.md", "publishing package\n")
            for name, content in project.get("unknown_files", []):
                write_text(project_dir / name, content)
        if jesus_exists:
            (root / "jesus").mkdir(parents=True, exist_ok=True)
        if canonical_workspace:
            write_text(root / "channels" / "mist_of_ages" / "channel.json", "{}\n")
            write_text(root / "channels" / "mist_of_ages" / "channel_profile.md", "# profile\n")
            write_text(root / "channels" / "mist_of_ages" / "channel_learnings_master.md", "# learnings\n")
            (root / "channels" / "mist_of_ages" / "metrics").mkdir(parents=True, exist_ok=True)
            (root / "channels" / "mist_of_ages" / "projects").mkdir(parents=True, exist_ok=True)
        if canonical_workspace_partial:
            write_text(root / "channels" / "mist_of_ages" / "channel.json", "{}\n")
        if canonical_token:
            write_text(root / "secrets" / "youtube" / "mist_of_ages_oauth_token.json", "{}\n")
        return tmp, root

    def build_plan(self, root: Path):
        return legacy_migration.build_legacy_migration_plan(root, planned_at=FIXED_TIME)

    def expected_hashes(self, root: Path):
        return {
            ".local/mist_of_ages_channel.json": file_hash(root / ".local" / "mist_of_ages_channel.json"),
            "channel/mist_of_ages/channel_learnings_master.md": file_hash(
                root / "channel" / "mist_of_ages" / "channel_learnings_master.md"
            ),
            "youtube_oauth_token.json": file_hash(root / "youtube_oauth_token.json"),
        }

    def test_module_import_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            __import__("scripts.legacy_migration")
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(before, after)

    def test_dry_run_creates_no_canonical_workspace_or_token_destination(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        legacy_migration.run_dry_run(root, planned_at=FIXED_TIME)
        self.assertFalse((root / "channels" / "mist_of_ages").exists())
        self.assertFalse((root / "secrets" / "youtube" / "mist_of_ages_oauth_token.json").exists())

    def test_dry_run_does_not_modify_legacy_files(self):
        projects = [{"name": "alpha", "transcript": True, "workflow_files": 2, "content": True, "publishing": True}]
        tmp, root = self.make_repo(projects=projects)
        self.addCleanup(tmp.cleanup)
        paths = [
            root / ".local" / "mist_of_ages_channel.json",
            root / "channel" / "mist_of_ages" / "channel_learnings_master.md",
            root / "youtube_oauth_token.json",
            root / "projects" / "alpha" / "project.json",
            root / "projects" / "alpha" / "research" / "competitor_transcript.md",
            root / "projects" / "alpha" / "workflow" / "step_0.md",
            root / "projects" / "alpha" / "content.md",
            root / "projects" / "alpha" / "publishing_package.md",
        ]
        before = {str(path): file_hash(path) for path in paths}
        legacy_migration.run_dry_run(root, planned_at=FIXED_TIME)
        after = {str(path): file_hash(path) for path in paths}
        self.assertEqual(before, after)

    def test_correct_legacy_channel_identity_mapping(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        identity = plan["legacy"]["channel_identity"]
        self.assertEqual(identity["youtube_channel_id"], "UC123")
        self.assertEqual(identity["display_name"], "Mist of Ages")
        self.assertEqual(identity["youtube_handle"], "@mistofages")
        self.assertEqual(identity["last_connected_at"], "2026-07-01T00:39:50+00:00")

    def test_missing_channel_identity_file_is_blocked(self):
        tmp, root = self.make_repo(identity=False)
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        self.assertEqual(plan["result"], legacy_migration.RESULT_BLOCKED)
        self.assertIn("Legacy channel identity file is missing.", plan["blockers"])

    def test_malformed_channel_identity_is_blocked(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        write_text(root / ".local" / "mist_of_ages_channel.json", "{bad json")
        plan = self.build_plan(root)
        self.assertEqual(plan["result"], legacy_migration.RESULT_BLOCKED)
        self.assertIn("Legacy channel identity file is malformed.", plan["blockers"])

    def test_missing_channel_id_is_blocked(self):
        tmp, root = self.make_repo(identity_payload={"title": "Mist"})
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        self.assertIn("Legacy channel identity is missing a valid channel ID.", plan["blockers"])

    def test_learnings_existence_detected_and_empty_learnings_blocked(self):
        tmp, root = self.make_repo(learnings="")
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        self.assertTrue(plan["legacy"]["learnings"]["exists"])
        self.assertFalse(plan["legacy"]["learnings"]["non_empty"])
        self.assertIn("Legacy channel learnings file is empty.", plan["blockers"])

    def test_learnings_contents_never_appear_in_report(self):
        secret_text = "TOP SECRET LEARNING SENTENCE"
        tmp, root = self.make_repo(learnings=secret_text + "\n")
        self.addCleanup(tmp.cleanup)
        report = legacy_migration.render_migration_report(self.build_plan(root))
        self.assertNotIn(secret_text, report)

    def test_token_presence_and_valid_structure_are_classified_safely(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        token = self.build_plan(root)["legacy"]["oauth_token"]
        self.assertTrue(token["TOKEN_PRESENT"])
        self.assertTrue(token["TOKEN_VALID_STRUCTURE"])
        self.assertTrue(token["REFRESH_TOKEN_PRESENT"])
        self.assertFalse(token["RECONNECT_REQUIRED"])

    def test_missing_refresh_token_produces_reconnect_required_state(self):
        tmp, root = self.make_repo(token_payload={"access_token": "ACCESS_SECRET_VALUE"})
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        token = plan["legacy"]["oauth_token"]
        self.assertTrue(token["TOKEN_VALID_STRUCTURE"])
        self.assertFalse(token["REFRESH_TOKEN_PRESENT"])
        self.assertTrue(token["RECONNECT_REQUIRED"])
        self.assertEqual(plan["canonical"]["channel_json"]["status"], "NEEDS_RECONNECT")

    def test_malformed_token_does_not_leak_contents(self):
        tmp, root = self.make_repo(token_raw='{"access_token":"VERY_SECRET"')
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        payload = json.dumps(plan)
        self.assertNotIn("VERY_SECRET", payload)
        report = legacy_migration.render_migration_report(plan)
        self.assertNotIn("VERY_SECRET", report)

    def test_token_values_never_appear_in_plan_or_exceptions(self):
        tmp, root = self.make_repo(token_payload={"access_token": "ACCESS_SECRET_VALUE", "refresh_token": "REFRESH_SECRET_VALUE"})
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        payload = json.dumps(plan)
        self.assertNotIn("ACCESS_SECRET_VALUE", payload)
        self.assertNotIn("REFRESH_SECRET_VALUE", payload)
        with self.assertRaises(legacy_migration.LegacyMigrationError) as ctx:
            legacy_migration.run_dry_run(root, report_path="../outside.md", planned_at=FIXED_TIME)
        self.assertNotIn("ACCESS_SECRET_VALUE", str(ctx.exception))
        self.assertNotIn("REFRESH_SECRET_VALUE", str(ctx.exception))

    def test_empty_legacy_projects_directory_is_accepted(self):
        tmp, root = self.make_repo(projects=[])
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        self.assertEqual(plan["legacy"]["project_count"], 0)
        self.assertEqual(plan["result"], legacy_migration.RESULT_READY)

    def test_legacy_projects_are_enumerated_deterministically(self):
        projects = [{"name": "b_project"}, {"name": "a_project"}]
        tmp, root = self.make_repo(projects=projects)
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        names = [project["legacy_folder_name"] for project in plan["legacy"]["projects"]]
        self.assertEqual(names, ["a_project", "b_project"])

    def test_project_schema_transcript_workflow_and_final_outputs_are_detected(self):
        projects = [
            {"name": "alpha", "schema_version": 1, "transcript": True, "workflow_files": 3, "content": True, "publishing": True}
        ]
        tmp, root = self.make_repo(projects=projects)
        self.addCleanup(tmp.cleanup)
        project = self.build_plan(root)["legacy"]["projects"][0]
        self.assertEqual(project["current_project_schema"], 1)
        self.assertTrue(project["manual_transcript_present"])
        self.assertEqual(project["workflow_artifact_count"], 3)
        self.assertTrue(project["content_md_present"])
        self.assertTrue(project["publishing_package_md_present"])
        self.assertTrue(project["metadata_conversion_required"])

    def test_protected_project_files_are_not_modified(self):
        projects = [{"name": "alpha", "transcript": True, "workflow_files": 1, "content": True, "publishing": True}]
        tmp, root = self.make_repo(projects=projects)
        self.addCleanup(tmp.cleanup)
        protected = [
            root / "projects" / "alpha" / "research" / "competitor_transcript.md",
            root / "projects" / "alpha" / "workflow" / "step_0.md",
            root / "projects" / "alpha" / "content.md",
            root / "projects" / "alpha" / "publishing_package.md",
        ]
        before = {str(path): file_hash(path) for path in protected}
        legacy_migration.run_dry_run(root, planned_at=FIXED_TIME)
        after = {str(path): file_hash(path) for path in protected}
        self.assertEqual(before, after)

    def test_destination_collisions_and_partial_workspace_are_detected(self):
        projects = [{"name": "alpha"}]
        tmp, root = self.make_repo(projects=projects, canonical_workspace_partial=True)
        self.addCleanup(tmp.cleanup)
        write_text(root / "channels" / "mist_of_ages" / "projects" / "alpha" / "project.json", "{}\n")
        plan = self.build_plan(root)
        self.assertEqual(plan["canonical"]["channel_workspace"]["state"], "DESTINATION_PARTIAL")
        self.assertIn("Canonical channel workspace already exists in a partial state.", plan["blockers"])
        self.assertIn("Canonical project destination already exists for projects/alpha.", plan["blockers"])

    def test_canonical_token_collision_is_detected(self):
        tmp, root = self.make_repo(canonical_token=True)
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        self.assertEqual(plan["canonical"]["token_destination"]["state"], "DESTINATION_CONFLICT")
        self.assertIn("Canonical token destination already exists and requires review before migration.", plan["blockers"])

    def test_same_project_folder_collision_is_not_assumed_safe(self):
        projects = [{"name": "alpha"}]
        tmp, root = self.make_repo(projects=projects)
        self.addCleanup(tmp.cleanup)
        write_text(root / "channels" / "mist_of_ages" / "projects" / "alpha" / "project.json", "{}\n")
        plan = self.build_plan(root)
        self.assertEqual(plan["legacy"]["projects"][0]["collision_state"], "DESTINATION_PARTIAL")
        self.assertEqual(plan["legacy"]["projects"][0]["classification"], "BLOCKED_DESTINATION_COLLISION")

    def test_unknown_legacy_files_are_classified(self):
        projects = [{"name": "alpha", "unknown_files": [("notes.txt", "note\n")]}]
        tmp, root = self.make_repo(projects=projects, channel_unknown=["rogue.md"])
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        self.assertIn("channel/mist_of_ages/rogue.md", plan["legacy"]["unclassified_files"])
        self.assertIn("projects/alpha/notes.txt", plan["legacy"]["unclassified_files"])

    def test_jesus_is_reported_but_not_recursively_inspected(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        write_text(root / "jesus" / "nested.txt", "do not open\n")
        report = legacy_migration.render_migration_report(self.build_plan(root))
        self.assertIn("jesus: PROTECTED_EXCLUDED_FROM_MIGRATION", report)
        self.assertNotIn("nested.txt", report)

    def test_jesus_files_are_never_opened(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        write_text(root / "jesus" / "nested.txt", "do not open\n")
        original_read_text = Path.read_text
        original_read_bytes = Path.read_bytes
        original_iterdir = Path.iterdir

        def guard_read_text(path_obj, *args, **kwargs):
            if path_obj.resolve().is_relative_to((root / "jesus").resolve()):
                raise AssertionError("jesus file was read")
            return original_read_text(path_obj, *args, **kwargs)

        def guard_read_bytes(path_obj, *args, **kwargs):
            if path_obj.resolve().is_relative_to((root / "jesus").resolve()):
                raise AssertionError("jesus file was read")
            return original_read_bytes(path_obj, *args, **kwargs)

        def guard_iterdir(path_obj):
            if path_obj.resolve() == (root / "jesus").resolve():
                raise AssertionError("jesus directory was enumerated")
            return original_iterdir(path_obj)

        with mock.patch("pathlib.Path.read_text", guard_read_text), mock.patch(
            "pathlib.Path.read_bytes", guard_read_bytes
        ), mock.patch("pathlib.Path.iterdir", guard_iterdir):
            plan = self.build_plan(root)
        self.assertEqual(plan["legacy"]["protected_paths"][0]["classification"], "PROTECTED_EXCLUDED_FROM_MIGRATION")

    def test_relative_paths_only_appear_in_plan_and_absolute_paths_do_not_appear_in_report(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        plan = self.build_plan(root)
        for value in walk_strings(plan):
            if "/" in value or "\\" in value:
                self.assertFalse(Path(value).is_absolute(), value)
        report = legacy_migration.render_migration_report(plan)
        self.assertNotIn(str(root), report)

    def test_report_contains_required_sections_and_is_newline_terminated_utf8(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        result = legacy_migration.run_dry_run(root, report_path="migration_dry_run.md", planned_at=FIXED_TIME)
        report_path = root / result["report_path"]
        text = report_path.read_text(encoding="utf-8")
        self.assertIn("# Mist of Ages Legacy Migration Dry Run", text)
        self.assertIn("## Result", text)
        self.assertIn("## Legacy Sources", text)
        self.assertIn("## Canonical Destination State", text)
        self.assertIn("## Approval Gate", text)
        self.assertTrue(report_path.read_bytes().endswith(b"\n"))

    def test_report_path_traversal_and_forbidden_roots_are_rejected(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(legacy_migration.LegacyMigrationError):
            legacy_migration.run_dry_run(root, report_path="../migration_dry_run.md", planned_at=FIXED_TIME)
        with self.assertRaises(legacy_migration.LegacyMigrationError):
            legacy_migration.run_dry_run(root, report_path="secrets/report.md", planned_at=FIXED_TIME)
        with self.assertRaises(legacy_migration.LegacyMigrationError):
            legacy_migration.run_dry_run(root, report_path="channels/report.md", planned_at=FIXED_TIME)

    def test_dry_run_output_is_deterministic(self):
        projects = [{"name": "b_project"}, {"name": "a_project", "workflow_files": 1}]
        tmp, root = self.make_repo(projects=projects)
        self.addCleanup(tmp.cleanup)
        first = legacy_migration.run_dry_run(root, planned_at=FIXED_TIME)
        second = legacy_migration.run_dry_run(root, planned_at=FIXED_TIME)
        self.assertEqual(first["plan"], second["plan"])
        self.assertEqual(first["report"], second["report"])

    def test_cli_requires_dry_run_and_has_no_apply_mode(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        script = ROOT / "scripts" / "legacy_migration.py"
        result = subprocess.run([sys.executable, str(script), "--root", str(root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Choose exactly one mode", result.stdout)
        both_result = subprocess.run(
            [sys.executable, str(script), "--root", str(root), "--dry-run", "--apply"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(both_result.returncode, 2)
        self.assertIn("Choose exactly one mode", both_result.stdout)

    def test_cli_exit_codes_for_ready_and_blocked_plans(self):
        script = ROOT / "scripts" / "legacy_migration.py"

        ready_tmp, ready_root = self.make_repo()
        self.addCleanup(ready_tmp.cleanup)
        ready = subprocess.run(
            [sys.executable, str(script), "--root", str(ready_root), "--channel-slug", "mist_of_ages", "--dry-run"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(ready.returncode, 0)
        self.assertIn("READY_FOR_REAL_MIGRATION", ready.stdout)

        blocked_tmp, blocked_root = self.make_repo(identity=False)
        self.addCleanup(blocked_tmp.cleanup)
        blocked = subprocess.run(
            [sys.executable, str(script), "--root", str(blocked_root), "--channel-slug", "mist_of_ages", "--dry-run"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("BLOCKED", blocked.stdout)

    def test_successful_apply_creates_exact_canonical_file_set(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        result = legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=self.expected_hashes(root))
        workspace = root / "channels" / "mist_of_ages"
        token = root / "secrets" / "youtube" / "mist_of_ages_oauth_token.json"
        self.assertEqual(result["status"], "CONNECTED")
        self.assertEqual(
            sorted(path.relative_to(root).as_posix() for path in workspace.rglob("*") if path.is_file()) + [token.relative_to(root).as_posix()],
            [
                "channels/mist_of_ages/channel.json",
                "channels/mist_of_ages/channel_learnings_master.md",
                "channels/mist_of_ages/channel_profile.md",
                "secrets/youtube/mist_of_ages_oauth_token.json",
            ],
        )
        self.assertFalse((workspace / "metrics").exists())
        self.assertFalse((workspace / "projects").exists())

    def test_apply_refuses_overwrite_and_second_apply(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=self.expected_hashes(root))
        with self.assertRaises(legacy_migration.LegacyMigrationError) as ctx:
            legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=self.expected_hashes(root))
        self.assertIn("refuses", str(ctx.exception))

    def test_apply_source_hash_precondition_failure(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        bad_hashes = dict(self.expected_hashes(root))
        bad_hashes["youtube_oauth_token.json"] = "0" * 64
        with self.assertRaises(legacy_migration.LegacyMigrationError) as ctx:
            legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=bad_hashes)
        self.assertIn("hash mismatch", str(ctx.exception).lower())
        self.assertFalse((root / "channels" / "mist_of_ages").exists())

    def test_apply_invalid_identity_source_is_rejected(self):
        tmp, root = self.make_repo(identity_payload={"id": "UC123"})
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(legacy_migration.LegacyMigrationError):
            legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=self.expected_hashes(root))

    def test_apply_invalid_token_source_is_rejected(self):
        tmp, root = self.make_repo(token_payload={"access_token": "ACCESS_SECRET_VALUE"})
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(legacy_migration.LegacyMigrationError) as ctx:
            legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes={
                ".local/mist_of_ages_channel.json": file_hash(root / ".local" / "mist_of_ages_channel.json"),
                "channel/mist_of_ages/channel_learnings_master.md": file_hash(root / "channel" / "mist_of_ages" / "channel_learnings_master.md"),
                "youtube_oauth_token.json": file_hash(root / "youtube_oauth_token.json"),
            })
        self.assertNotIn("ACCESS_SECRET_VALUE", str(ctx.exception))

    def test_apply_atomic_write_failure_rolls_back(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        calls = {"count": 0}

        def flaky_writer(path, data):
            calls["count"] += 1
            if calls["count"] == 3:
                raise OSError("boom")
            legacy_migration._write_bytes_atomic(path, data)

        with self.assertRaises(legacy_migration.LegacyMigrationError):
            legacy_migration.apply_legacy_migration(
                root,
                planned_at=FIXED_TIME,
                expected_source_hashes=self.expected_hashes(root),
                write_bytes_atomic=flaky_writer,
            )
        self.assertFalse((root / "channels" / "mist_of_ages").exists())
        self.assertFalse((root / "secrets").exists())

    def test_apply_partial_operation_rollback_removes_created_files_only(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        preexisting = root / "secrets"
        preexisting.mkdir()
        calls = {"count": 0}

        def flaky_writer(path, data):
            calls["count"] += 1
            if calls["count"] == 4:
                raise OSError("boom")
            legacy_migration._write_bytes_atomic(path, data)

        with self.assertRaises(legacy_migration.LegacyMigrationError):
            legacy_migration.apply_legacy_migration(
                root,
                planned_at=FIXED_TIME,
                expected_source_hashes=self.expected_hashes(root),
                write_bytes_atomic=flaky_writer,
            )
        self.assertTrue(preexisting.exists())
        self.assertFalse((root / "channels" / "mist_of_ages").exists())
        self.assertFalse((root / "secrets" / "youtube").exists())

    def test_apply_preserves_legacy_sources(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        before = {
            "identity": file_hash(root / ".local" / "mist_of_ages_channel.json"),
            "learnings": file_hash(root / "channel" / "mist_of_ages" / "channel_learnings_master.md"),
            "token": file_hash(root / "youtube_oauth_token.json"),
        }
        legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=self.expected_hashes(root))
        after = {
            "identity": file_hash(root / ".local" / "mist_of_ages_channel.json"),
            "learnings": file_hash(root / "channel" / "mist_of_ages" / "channel_learnings_master.md"),
            "token": file_hash(root / "youtube_oauth_token.json"),
        }
        self.assertEqual(before, after)

    def test_apply_protected_path_exclusion(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        write_text(root / "jesus" / "nested.txt", "do not inspect\n")
        original_iterdir = Path.iterdir

        def guard_iterdir(path_obj):
            if path_obj.resolve() == (root / "jesus").resolve():
                raise AssertionError("jesus directory was enumerated")
            return original_iterdir(path_obj)

        with mock.patch("pathlib.Path.iterdir", guard_iterdir):
            legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=self.expected_hashes(root))

    def test_apply_token_secrecy_in_cli_output_and_files(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        script = ROOT / "scripts" / "legacy_migration.py"
        hashes = self.expected_hashes(root)
        hash_args = []
        for rel_path, value in hashes.items():
            hash_args.extend(["--expected-source-hash", f"{rel_path}={value}"])
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(root), "--channel-slug", "mist_of_ages", "--apply", *hash_args],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("ACCESS_SECRET_VALUE", result.stdout)
        self.assertNotIn("REFRESH_SECRET_VALUE", result.stdout)
        payload = (root / "secrets" / "youtube" / "mist_of_ages_oauth_token.json").read_text(encoding="utf-8")
        self.assertIn("ACCESS_SECRET_VALUE", payload)

    def test_apply_no_project_creation_for_empty_inventory(self):
        tmp, root = self.make_repo(projects=[])
        self.addCleanup(tmp.cleanup)
        legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=self.expected_hashes(root))
        self.assertFalse((root / "channels" / "mist_of_ages" / "projects").exists())

    def test_apply_channel_json_and_profile_are_valid(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=self.expected_hashes(root))
        channel_json = json.loads((root / "channels" / "mist_of_ages" / "channel.json").read_text(encoding="utf-8"))
        self.assertEqual(channel_json["youtube_channel_id"], "UC123")
        self.assertEqual(channel_json["display_name"], "Mist of Ages")
        self.assertEqual(channel_json["youtube_handle"], "@mistofages")
        self.assertEqual(channel_json["status"], "CONNECTED")
        profile = (root / "channels" / "mist_of_ages" / "channel_profile.md").read_text(encoding="utf-8")
        self.assertIn("Mist of Ages", profile)
        self.assertIn("@mistofages", profile)

    def test_apply_learnings_and_token_preserve_source_bytes(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        source_learnings = (root / "channel" / "mist_of_ages" / "channel_learnings_master.md").read_bytes()
        source_token = (root / "youtube_oauth_token.json").read_bytes()
        legacy_migration.apply_legacy_migration(root, planned_at=FIXED_TIME, expected_source_hashes=self.expected_hashes(root))
        self.assertEqual(source_learnings, (root / "channels" / "mist_of_ages" / "channel_learnings_master.md").read_bytes())
        self.assertEqual(source_token, (root / "secrets" / "youtube" / "mist_of_ages_oauth_token.json").read_bytes())

    def test_no_runtime_paths_are_touched_in_temp_repo(self):
        tmp, root = self.make_repo()
        self.addCleanup(tmp.cleanup)
        legacy_migration.run_dry_run(root, report_path="migration_dry_run.md", planned_at=FIXED_TIME)
        self.assertFalse((root / "channels" / "mist_of_ages").exists())
        self.assertFalse((root / "secrets").exists())
        self.assertTrue((root / "migration_dry_run.md").exists())


if __name__ == "__main__":
    unittest.main()
