import importlib
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_workspace


class ChannelWorkspaceTests(unittest.TestCase):
    def test_create_one_channel_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = channel_workspace.create_channel_workspace(
                root=root,
                slug="mist_of_ages",
                display_name="Mist of Ages",
                youtube_channel_id="UC123",
                youtube_handle="@MistOfAges",
            )
            paths = channel_workspace.canonical_channel_paths(root, "mist_of_ages")
            self.assertEqual(data["channel_slug"], "mist_of_ages")
            self.assertTrue(paths.channel_json.exists())
            self.assertTrue(paths.channel_profile.exists())
            self.assertTrue(paths.channel_learnings_master.exists())
            self.assertTrue(paths.metrics_raw_dir.exists())
            self.assertTrue(paths.projects_dir.exists())
            self.assertTrue(paths.secrets_dir.exists())
            self.assertFalse(paths.oauth_token_file.exists())

    def test_create_and_list_two_channel_workspaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            channel_workspace.create_channel_workspace(root, "tam_builds", "Tam Builds", "UC456", "@TamBuilds")
            channels = channel_workspace.list_channels(root)
            self.assertEqual([item["channel_slug"] for item in channels], ["mist_of_ages", "tam_builds"])

    def test_load_and_validate_channel_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            data = channel_workspace.load_channel(root, "mist_of_ages")
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["oauth_token_ref"], "secrets/youtube/mist_of_ages_oauth_token.json")
            self.assertEqual(data["status"], "NOT_CONNECTED")

    def test_reject_duplicate_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages 2", "UC456", "@Mist2")

    def test_reject_duplicate_youtube_channel_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                channel_workspace.create_channel_workspace(root, "tam_builds", "Tam Builds", "UC123", "@TamBuilds")

    def test_reject_invalid_slug_categories(self):
        invalid_slugs = [
            "Mist_Of_Ages",
            "../evil",
            "a/b",
            "a\\b",
            "/absolute",
            ".",
            "..",
            "_empty",
            "empty_",
            "double__underscore",
            "has spaces",
            "mistoftuoié",
        ]
        for slug in invalid_slugs:
            with self.subTest(slug=slug):
                with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                    channel_workspace.validate_channel_slug(slug)

    def test_verify_canonical_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = channel_workspace.canonical_channel_paths(root, "mist_of_ages")
            self.assertEqual(paths.channel_json.relative_to(root).as_posix(), "channels/mist_of_ages/channel.json")
            self.assertEqual(paths.channel_profile.relative_to(root).as_posix(), "channels/mist_of_ages/channel_profile.md")
            self.assertEqual(
                paths.channel_learnings_master.relative_to(root).as_posix(),
                "channels/mist_of_ages/channel_learnings_master.md",
            )
            self.assertEqual(
                paths.channel_metrics_csv.relative_to(root).as_posix(),
                "channels/mist_of_ages/metrics/channel_metrics.csv",
            )
            self.assertEqual(
                paths.reporting_state_json.relative_to(root).as_posix(),
                "channels/mist_of_ages/metrics/reporting_state.json",
            )
            self.assertEqual(paths.metrics_raw_dir.relative_to(root).as_posix(), "channels/mist_of_ages/metrics/_raw")
            self.assertEqual(paths.projects_dir.relative_to(root).as_posix(), "channels/mist_of_ages/projects")
            self.assertEqual(paths.oauth_token_ref, "secrets/youtube/mist_of_ages_oauth_token.json")

    def test_different_channels_receive_different_token_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = channel_workspace.canonical_channel_paths(root, "mist_of_ages")
            second = channel_workspace.canonical_channel_paths(root, "tam_builds")
            self.assertNotEqual(first.oauth_token_ref, second.oauth_token_ref)

    def test_all_paths_stay_under_supplied_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = channel_workspace.canonical_channel_paths(root, "mist_of_ages")
            for value in paths.__dict__.values():
                if isinstance(value, Path):
                    value.resolve().relative_to(root.resolve())

    def test_channel_json_contains_no_secret_fields_or_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            payload = json.loads((root / "channels" / "mist_of_ages" / "channel.json").read_text(encoding="utf-8"))
            text = json.dumps(payload, ensure_ascii=False).lower()
            for field in ("access_token", "refresh_token", "client_secret"):
                self.assertNotIn(field, payload)
                self.assertNotIn(field, text)

    def test_create_does_not_overwrite_existing_channel_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            path = root / "channels" / "mist_of_ages" / "channel.json"
            original = path.read_text(encoding="utf-8")
            with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                channel_workspace.create_channel_workspace(root, "mist_of_ages", "Changed", "UC999", "@Changed")
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_starter_markdown_files_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            profile = root / "channels" / "mist_of_ages" / "channel_profile.md"
            learnings = root / "channels" / "mist_of_ages" / "channel_learnings_master.md"
            profile.write_text("manual profile", encoding="utf-8")
            learnings.write_text("manual learnings", encoding="utf-8")
            with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            self.assertEqual(profile.read_text(encoding="utf-8"), "manual profile")
            self.assertEqual(learnings.read_text(encoding="utf-8"), "manual learnings")

    def test_module_import_creates_no_folders_or_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            importlib.reload(channel_workspace)
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(before, after)

    def test_timestamps_are_timezone_aware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            created = datetime.fromisoformat(data["created_at"])
            self.assertIsNotNone(created.tzinfo)
            self.assertIsNotNone(created.utcoffset())

    def test_json_ends_with_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist of Ages", "UC123", "@MistOfAges")
            content = (root / "channels" / "mist_of_ages" / "channel.json").read_text(encoding="utf-8")
            self.assertTrue(content.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
