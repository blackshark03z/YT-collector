import csv
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_metrics, channel_oauth, channel_workspace


def make_channel(root: Path, slug: str, channel_id: str) -> None:
    channel_workspace.create_channel_workspace(root, slug, slug.replace("_", " ").title(), channel_id, "@" + slug)


def recent_payload() -> dict:
    return {
        "items": [
            {"id": "vid-a", "snippet": {"title": "A", "publishedAt": "2026-07-01T00:00:00+00:00"}, "statistics": {"viewCount": "10", "likeCount": "2", "commentCount": "1"}},
            {"id": "vid-b", "snippet": {"title": "B", "publishedAt": "2026-07-02T00:00:00+00:00"}, "statistics": {"viewCount": "0", "likeCount": "0", "commentCount": "0"}},
        ]
    }


def analytics_payload() -> dict:
    return {
        "columnHeaders": [
            {"name": "video"},
            {"name": "views"},
            {"name": "estimatedMinutesWatched"},
            {"name": "averageViewDuration"},
            {"name": "averageViewPercentage"},
            {"name": "access_token_debug"},
        ],
        "rows": [
            ["vid-a", 10, 50, 30, 60, "secret-a"],
            ["vid-b", 0, 0, 0, 0, "secret-b"],
        ],
    }


def pending_reach_payload() -> dict:
    return {
        "status": "PENDING",
        "report_type": "channel_reach_basic_a1",
        "message": "Pending",
        "available_metrics": [],
        "pending_metrics": ["thumbnail_impressions", "thumbnail_ctr"],
        "rows": [],
        "authorization": "secret",
    }


def complete_reach_payload() -> dict:
    return {
        "status": "COMPLETE",
        "report_type": "channel_reach_basic_a1",
        "message": "Ready",
        "available_metrics": ["thumbnail_impressions", "thumbnail_ctr"],
        "pending_metrics": [],
        "rows": [
            {"video_id": "vid-a", "thumbnail_impressions": 100, "thumbnail_ctr": 4.5},
            {"video_id": "vid-b", "thumbnail_impressions": 0, "thumbnail_ctr": 0},
        ],
        "access_token_note": "secret",
    }


class ChannelMetricsTests(unittest.TestCase):
    def test_module_import_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            importlib.reload(channel_metrics)
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(before, after)

    def test_sync_channel_a_writes_only_a_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            make_channel(root, "channel_b", "UC2")
            channel_metrics.sync_channel_metrics(
                root,
                "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            self.assertTrue((root / "channels" / "channel_a" / "metrics" / "channel_metrics.csv").exists())
            self.assertFalse((root / "channels" / "channel_b" / "metrics" / "channel_metrics.csv").exists())

    def test_sync_a_does_not_modify_b(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            make_channel(root, "channel_b", "UC2")
            b_paths = channel_workspace.canonical_channel_paths(root, "channel_b")
            b_paths.channel_metrics_csv.parent.mkdir(parents=True, exist_ok=True)
            b_paths.channel_metrics_csv.write_text("old\n", encoding="utf-8")
            before = b_paths.channel_metrics_csv.read_bytes()
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            self.assertEqual(b_paths.channel_metrics_csv.read_bytes(), before)

    def test_correct_csv_columns_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            with (root / "channels" / "channel_a" / "metrics" / "channel_metrics.csv").open(encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader)
            self.assertEqual(header, channel_metrics.CSV_COLUMNS)

    def test_zero_values_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            with (root / "channels" / "channel_a" / "metrics" / "channel_metrics.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[1]["views"], "0")
            self.assertEqual(rows[1]["thumbnail_impressions"], "0")
            self.assertEqual(rows[1]["thumbnail_ctr"], "0")

    def test_missing_reach_fields_remain_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            with (root / "channels" / "channel_a" / "metrics" / "channel_metrics.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[0]["thumbnail_impressions"], "")
            self.assertEqual(rows[0]["thumbnail_ctr"], "")

    def test_reach_pending_produces_pending_reach(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            result = channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            self.assertEqual(result["metrics_status"], "PENDING_REACH")

    def test_reach_pending_does_not_fail_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            result = channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            self.assertEqual(result["reporting_state"]["status"], "PENDING")

    def test_complete_reach_produces_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            result = channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            self.assertEqual(result["metrics_status"], "COMPLETE")
            self.assertEqual(result["reporting_state"]["status"], "COMPLETE")

    def test_raw_analytics_json_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            raw = (root / "channels" / "channel_a" / "metrics" / "_raw" / "channel_analytics.json").read_text(encoding="utf-8").lower()
            self.assertNotIn("access_token", raw)

    def test_raw_recent_videos_json_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            payload = recent_payload()
            payload["authorization"] = "secret"
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: payload,
                reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            raw = (root / "channels" / "channel_a" / "metrics" / "_raw" / "recent_channel_videos.json").read_text(encoding="utf-8").lower()
            self.assertNotIn("authorization", raw)

    def test_reporting_state_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            payload = json.loads((root / "channels" / "channel_a" / "metrics" / "reporting_state.json").read_text(encoding="utf-8"))
            dumped = json.dumps(payload).lower()
            self.assertNotIn("access_token", dumped)
            self.assertNotIn("refresh_token", dumped)

    def test_no_secret_markers_in_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            for path in (root / "channels" / "channel_a" / "metrics").rglob("*"):
                if path.is_file():
                    text = path.read_text(encoding="utf-8", errors="ignore").lower()
                    self.assertNotIn("access_token", text)
                    self.assertNotIn("refresh_token", text)
                    self.assertNotIn("client_secret", text)

    def test_total_failure_preserves_previous_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            paths = channel_workspace.canonical_channel_paths(root, "channel_a")
            paths.channel_metrics_csv.parent.mkdir(parents=True, exist_ok=True)
            paths.channel_metrics_csv.write_bytes(b"old-csv\n")
            paths.reporting_state_json.write_bytes(b'{"old":true}\n')
            before_csv = paths.channel_metrics_csv.read_bytes()
            before_state = paths.reporting_state_json.read_bytes()
            with self.assertRaises(channel_metrics.ChannelMetricsError):
                channel_metrics.sync_channel_metrics(
                    root, "channel_a",
                    analytics_fetcher=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
                    recent_videos_fetcher=lambda **kwargs: recent_payload(),
                    reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                    token_provider=lambda root, slug: "token-a",
                )
            self.assertEqual(paths.channel_metrics_csv.read_bytes(), before_csv)
            self.assertEqual(paths.reporting_state_json.read_bytes(), before_state)

    def test_partial_reach_failure_preserves_valid_analytics_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            result = channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("pending")),
                token_provider=lambda root, slug: "token-a",
            )
            self.assertTrue((root / "channels" / "channel_a" / "metrics" / "channel_metrics.csv").exists())
            self.assertEqual(result["reporting_state"]["status"], "PENDING")

    def test_atomic_csv_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            leftovers = [path for path in (root / "channels" / "channel_a" / "metrics").iterdir() if path.suffix == ".tmp"]
            self.assertEqual(leftovers, [])

    def test_atomic_json_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            leftovers = [path for path in (root / "channels" / "channel_a").rglob("*.tmp")]
            self.assertEqual(leftovers, [])

    def test_newline_termination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            self.assertTrue((root / "channels" / "channel_a" / "metrics" / "channel_metrics.csv").read_text(encoding="utf-8").endswith("\n"))
            self.assertTrue((root / "channels" / "channel_a" / "metrics" / "reporting_state.json").read_text(encoding="utf-8").endswith("\n"))

    def test_timezone_aware_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            result = channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            self.assertIn("+00:00", result["reporting_state"]["last_checked_at"])

    def test_last_metrics_sync_at_updates_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            before = channel_workspace.load_channel(root, "channel_a")["last_metrics_sync_at"]
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            after = channel_workspace.load_channel(root, "channel_a")["last_metrics_sync_at"]
            self.assertIsNone(before)
            self.assertIsNotNone(after)

    def test_metadata_unchanged_on_total_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            before = channel_workspace.load_channel(root, "channel_a")
            with self.assertRaises(channel_metrics.ChannelMetricsError):
                channel_metrics.sync_channel_metrics(
                    root, "channel_a",
                    analytics_fetcher=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
                    recent_videos_fetcher=lambda **kwargs: recent_payload(),
                    reporting_fetcher=lambda **kwargs: pending_reach_payload(),
                    token_provider=lambda root, slug: "token-a",
                )
            after = channel_workspace.load_channel(root, "channel_a")
            self.assertEqual(after["last_metrics_sync_at"], before["last_metrics_sync_at"])
            self.assertEqual(after["status"], before["status"])

    def test_channel_identity_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            loaded = channel_workspace.load_channel(root, "channel_a")
            self.assertEqual(loaded["youtube_channel_id"], "UC1")

    def test_missing_channel_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                channel_metrics.sync_channel_metrics(
                    tmp, "missing",
                    analytics_fetcher=lambda **kwargs: analytics_payload(),
                    recent_videos_fetcher=lambda **kwargs: recent_payload(),
                    reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                    token_provider=lambda root, slug: "token-a",
                )

    def test_missing_token_reconnect_error_is_classified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            with self.assertRaises(channel_metrics.ChannelMetricsReconnectRequiredError):
                channel_metrics.sync_channel_metrics(
                    root, "channel_a",
                    analytics_fetcher=lambda **kwargs: analytics_payload(),
                    recent_videos_fetcher=lambda **kwargs: recent_payload(),
                    reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                    token_provider=lambda root, slug: (_ for _ in ()).throw(channel_oauth.TokenMissingError("missing")),
                )

    def test_no_real_repository_path_is_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            channel_metrics.sync_channel_metrics(
                root, "channel_a",
                analytics_fetcher=lambda **kwargs: analytics_payload(),
                recent_videos_fetcher=lambda **kwargs: recent_payload(),
                reporting_fetcher=lambda **kwargs: complete_reach_payload(),
                token_provider=lambda root, slug: "token-a",
            )
            self.assertFalse((ROOT / "channels").exists())


if __name__ == "__main__":
    unittest.main()
