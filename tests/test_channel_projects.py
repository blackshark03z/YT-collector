import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_projects, channel_workspace
from tests.runtime_isolation_helpers import snapshot_runtime_state


def make_channel(root: Path, slug: str, channel_id: str) -> None:
    channel_workspace.create_channel_workspace(root, slug, slug.replace("_", " ").title(), channel_id, "@" + slug)
    paths = channel_workspace.canonical_channel_paths(root, slug)
    paths.channel_learnings_master.write_text(
        f"# {slug}\n\nApproved learnings only.\n", encoding="utf-8", newline="\n"
    )
    paths.channel_metrics_csv.parent.mkdir(parents=True, exist_ok=True)
    paths.channel_metrics_csv.write_text(
        "video,video_id,published,impressions,ctr,views,avd,apv\nA,vid1,2026-07-01,PENDING,PENDING,100,10,50\n",
        encoding="utf-8",
        newline="\n",
    )


def source_metadata(title="Why Rome Executed Jesus", channel="Competitor Channel"):
    return {
        "title": title,
        "channelTitle": channel,
        "channelId": "UC_COMP",
        "publishedAt": "2026-06-30T00:00:00+00:00",
        "duration": "PT12M",
        "description": "Public description",
        "tags": ["rome", "history"],
        "viewCount": "1234",
        "likeCount": "55",
        "commentCount": "8",
        "thumbnailUrl": "https://i.ytimg.com/example.jpg",
    }


class ChannelProjectTests(unittest.TestCase):
    def test_module_import_creates_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            importlib.reload(channel_projects)
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(before, after)

    def test_create_project_under_channel_a(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(
                root, "mist_of_ages", "VIDEO12345A", "https://www.youtube.com/watch?v=VIDEO12345A", source_metadata()
            )
            self.assertEqual(project["channel_slug"], "mist_of_ages")

    def test_create_project_under_channel_b(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "tam_builds", "UC456")
            project = channel_projects.create_channel_project(
                root, "tam_builds", "VIDEO12345A", "https://www.youtube.com/watch?v=VIDEO12345A", source_metadata()
            )
            self.assertEqual(project["channel_slug"], "tam_builds")

    def test_same_source_video_allowed_across_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            make_channel(root, "tam_builds", "UC456")
            channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            channel_projects.create_channel_project(root, "tam_builds", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            self.assertEqual(len(channel_projects.list_channel_projects(root, "mist_of_ages")), 1)
            self.assertEqual(len(channel_projects.list_channel_projects(root, "tam_builds")), 1)

    def test_duplicate_source_video_rejected_within_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())

    def test_correct_canonical_project_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata(), created_at="2026-07-01T00:00:00+00:00")
            slug = project["project_slug"]
            self.assertTrue(slug.startswith("20260701_"))
            self.assertTrue((root / "channels" / "mist_of_ages" / "projects" / slug).exists())

    def test_safe_project_slug_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(
                root,
                "mist_of_ages",
                "VIDEO12345A",
                "https://youtube.com/watch?v=VIDEO12345A",
                source_metadata(title="Unsafe / Title: Here"),
                project_name="My Project / Name",
                created_at="2026-07-01T00:00:00+00:00",
            )
            self.assertEqual(project["project_slug"], "20260701_my-project-name")

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.load_channel_project(root, "mist_of_ages", "../evil")

    def test_missing_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                channel_projects.create_channel_project(tmp, "missing", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())

    def test_missing_learnings_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@mist")
            paths = channel_workspace.canonical_channel_paths(root, "mist_of_ages")
            paths.channel_learnings_master.unlink()
            paths.channel_metrics_csv.parent.mkdir(parents=True, exist_ok=True)
            paths.channel_metrics_csv.write_text("a,b\n1,2\n", encoding="utf-8")
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())

    def test_missing_metrics_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@mist")
            paths = channel_workspace.canonical_channel_paths(root, "mist_of_ages")
            paths.channel_learnings_master.write_text("# Learnings\n", encoding="utf-8")
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())

    def test_pending_metrics_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            metrics = (root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "input" / "channel_metrics.csv").read_text(encoding="utf-8")
            self.assertIn("PENDING", metrics)

    def test_learnings_snapshot_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            src = channel_workspace.canonical_channel_paths(root, "mist_of_ages").channel_learnings_master.read_bytes()
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            dst = (root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "input" / "channel_learnings.md").read_bytes()
            self.assertEqual(src, dst)

    def test_metrics_snapshot_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            src = channel_workspace.canonical_channel_paths(root, "mist_of_ages").channel_metrics_csv.read_bytes()
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            dst = (root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "input" / "channel_metrics.csv").read_bytes()
            self.assertEqual(src, dst)

    def test_snapshot_source_files_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            paths = channel_workspace.canonical_channel_paths(root, "mist_of_ages")
            before_learnings = paths.channel_learnings_master.read_bytes()
            before_metrics = paths.channel_metrics_csv.read_bytes()
            channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            self.assertEqual(paths.channel_learnings_master.read_bytes(), before_learnings)
            self.assertEqual(paths.channel_metrics_csv.read_bytes(), before_metrics)

    def test_project_creation_writes_all_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            base = root / "channels" / "mist_of_ages" / "projects" / project["project_slug"]
            required = [
                "project.json",
                "input/competitor_reference.md",
                "input/channel_learnings.md",
                "input/channel_metrics.csv",
                "input/_raw/competitor_video.json",
                "research/competitor_transcript.md",
            ] + [f"workflow/{name}" for name in channel_projects.WORKFLOW_PLACEHOLDERS]
            for rel in required:
                self.assertTrue((base / rel).exists(), rel)

    def test_project_creation_does_not_create_final_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            base = root / "channels" / "mist_of_ages" / "projects" / project["project_slug"]
            self.assertFalse((base / "content.md").exists())
            self.assertFalse((base / "publishing_package.md").exists())

    def test_raw_competitor_json_contains_no_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            raw = (root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "input" / "_raw" / "competitor_video.json").read_text(encoding="utf-8").lower()
            self.assertNotIn("access_token", raw)
            self.assertNotIn("refresh_token", raw)

    def test_thumbnail_written_only_when_supplied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            without_thumb = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            base = root / "channels" / "mist_of_ages" / "projects" / without_thumb["project_slug"] / "input" / "assets"
            self.assertEqual(list(base.iterdir()), [])
            with_thumb = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345B", "https://youtube.com/watch?v=VIDEO12345B", source_metadata(), thumbnail_bytes=b"img", thumbnail_extension=".jpg")
            assets = root / "channels" / "mist_of_ages" / "projects" / with_thumb["project_slug"] / "input" / "assets"
            self.assertTrue((assets / "competitor_thumbnail.jpg").exists())

    def test_thumbnail_extension_is_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata(), thumbnail_bytes=b"img", thumbnail_extension=".exe")

    def test_failed_creation_leaves_no_partial_final_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            bad = dict(source_metadata())
            bad["access_token"] = "secret"
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", bad)
            projects_dir = root / "channels" / "mist_of_ages" / "projects"
            self.assertEqual(list(projects_dir.iterdir()), [])

    def test_failed_creation_cleans_temporary_project_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.create_channel_project(root, "mist_of_ages", "", "https://youtube.com/watch?v=", source_metadata())
            projects_dir = root / "channels" / "mist_of_ages" / "projects"
            self.assertEqual([p for p in projects_dir.iterdir() if p.name.startswith(".tmp-")], [])

    def test_existing_project_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            first = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata(), created_at="2026-07-01T00:00:00+00:00")
            second = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345B", "https://youtube.com/watch?v=VIDEO12345B", source_metadata(), project_name="Why Rome Executed Jesus", created_at="2026-07-01T00:00:00+00:00")
            self.assertNotEqual(first["project_slug"], second["project_slug"])

    def test_project_json_schema_is_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            payload = json.loads((root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["project_type"], "youtube_research")
            self.assertEqual(payload["channel_slug"], "mist_of_ages")
            self.assertEqual(payload["youtube_channel_id"], "UC123")

    def test_project_json_ends_with_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            content = (root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "project.json").read_text(encoding="utf-8")
            self.assertTrue(content.endswith("\n"))

    def test_project_timestamps_are_timezone_aware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            payload = json.loads((root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "project.json").read_text(encoding="utf-8"))
            self.assertIn("+00:00", payload["created_at"])
            self.assertIn("+00:00", payload["updated_at"])

    def test_list_channel_returns_only_its_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            make_channel(root, "tam_builds", "UC456")
            channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            channel_projects.create_channel_project(root, "tam_builds", "VIDEO12345B", "https://youtube.com/watch?v=VIDEO12345B", source_metadata())
            listed = channel_projects.list_channel_projects(root, "mist_of_ages")
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["channel_slug"], "mist_of_ages")

    def test_listing_ignores_temporary_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            projects_dir = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir
            projects_dir.mkdir(parents=True, exist_ok=True)
            (projects_dir / ".tmp-test").mkdir()
            self.assertEqual(channel_projects.list_channel_projects(root, "mist_of_ages"), [])

    def test_cross_channel_load_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            make_channel(root, "tam_builds", "UC456")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.load_channel_project(root, "tam_builds", project["project_slug"])

    def test_cross_channel_transcript_save_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            make_channel(root, "tam_builds", "UC456")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.save_project_transcript(root, "tam_builds", project["project_slug"], "real transcript " * 10)

    def test_untouched_transcript_template_can_be_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            result = channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 10)
            self.assertTrue(result["checks"]["transcript_real_content"])

    def test_real_transcript_not_overwritten_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 10)
            path = root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "research" / "competitor_transcript.md"
            before = path.read_bytes()
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "other transcript " * 10)
            self.assertEqual(path.read_bytes(), before)

    def test_explicit_transcript_overwrite_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 10)
            channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "replacement transcript " * 10, overwrite=True)
            content = (root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "research" / "competitor_transcript.md").read_text(encoding="utf-8")
            self.assertIn("replacement transcript", content)

    def test_empty_transcript_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "   ")

    def test_validation_detects_untouched_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            result = channel_projects.validate_channel_project(root, "mist_of_ages", project["project_slug"])
            self.assertFalse(result["checks"]["transcript_real_content"])
            self.assertEqual(result["project"]["status"], "WAITING_FOR_TRANSCRIPT")

    def test_validation_becomes_ready_with_real_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            result = channel_projects.save_project_transcript(root, "mist_of_ages", project["project_slug"], "real transcript " * 10)
            self.assertEqual(result["project"]["status"], "READY_FOR_WORKFLOW")
            self.assertEqual(result["project"]["workflow_input_status"], "READY")
            self.assertTrue(result["project"]["runnable"])

    def test_validation_updates_only_allowed_status_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            base = root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "project.json"
            before = json.loads(base.read_text(encoding="utf-8"))
            channel_projects.validate_channel_project(root, "mist_of_ages", project["project_slug"])
            after = json.loads(base.read_text(encoding="utf-8"))
            for field in ("schema_version", "project_type", "project_slug", "channel_slug", "youtube_channel_id", "source_video_id", "source_video_url", "created_at", "channel_snapshot"):
                self.assertEqual(before[field], after[field])

    def test_validation_preserves_ownership_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            channel_projects.validate_channel_project(root, "mist_of_ages", project["project_slug"])
            loaded = channel_projects.load_channel_project(root, "mist_of_ages", project["project_slug"])
            self.assertEqual(loaded["channel_slug"], "mist_of_ages")
            self.assertEqual(loaded["youtube_channel_id"], "UC123")

    def test_validation_for_wrong_channel_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            make_channel(root, "tam_builds", "UC456")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            with self.assertRaises(channel_projects.ChannelProjectError):
                channel_projects.validate_channel_project(root, "tam_builds", project["project_slug"])

    def test_placeholder_files_are_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            workflow_dir = root / "channels" / "mist_of_ages" / "projects" / project["project_slug"] / "workflow"
            self.assertEqual(sorted(p.name for p in workflow_dir.iterdir()), sorted(channel_projects.WORKFLOW_PLACEHOLDERS))

    def test_content_and_publishing_package_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            project = channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            base = root / "channels" / "mist_of_ages" / "projects" / project["project_slug"]
            self.assertFalse((base / "content.md").exists())
            self.assertFalse((base / "publishing_package.md").exists())

    def test_channel_a_operations_do_not_modify_channel_b_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            make_channel(root, "tam_builds", "UC456")
            b_paths = channel_workspace.canonical_channel_paths(root, "tam_builds")
            before_learnings = b_paths.channel_learnings_master.read_bytes()
            before_metrics = b_paths.channel_metrics_csv.read_bytes()
            channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
            self.assertEqual(b_paths.channel_learnings_master.read_bytes(), before_learnings)
            self.assertEqual(b_paths.channel_metrics_csv.read_bytes(), before_metrics)

    def test_no_real_repository_runtime_folder_is_touched(self):
        before = snapshot_runtime_state(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "mist_of_ages", "UC123")
            channel_projects.create_channel_project(root, "mist_of_ages", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", source_metadata())
        after = snapshot_runtime_state(ROOT)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
