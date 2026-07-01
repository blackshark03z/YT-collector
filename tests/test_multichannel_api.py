import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_projects, channel_workspace, ui_server


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
        paths.reporting_state_json.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "channel_slug": slug,
                    "youtube_channel_id": channel_id,
                    "status": "PENDING",
                    "report_type": None,
                    "last_checked_at": "2026-07-01T00:00:00+00:00",
                    "message": "Pending",
                    "available_metrics": [],
                    "pending_metrics": ["thumbnail_impressions", "thumbnail_ctr"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def fake_video(video_id: str) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": "Why Rome Executed Jesus",
            "channelTitle": "Competitor",
            "channelId": "UC_COMP",
            "publishedAt": "2026-07-01T00:00:00+00:00",
            "description": "desc",
            "tags": ["rome"],
            "thumbnails": {"high": {"url": "https://example.com/thumb.jpg"}},
        },
        "contentDetails": {"duration": "PT10M"},
        "statistics": {"viewCount": "123", "likeCount": "4", "commentCount": "5"},
    }


class MultiChannelApiTests(unittest.TestCase):
    def test_legacy_routes_remain_registered_unchanged(self):
        self.assertIn("Mist of Ages Research", ui_server.HTML_PAGE)
        self.assertEqual(ui_server.app_status()["oauth_client"] in {"FOUND", "MISSING"}, True)

    def test_list_channels_returns_sanitized_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            status, data = ui_server.dispatch_v2_request("GET", "/api/v2/channels", context=ui_server.build_app_context(root=root))
            self.assertEqual(status, 200)
            self.assertEqual(data["channels"][0]["channel_slug"], "channel_a")
            dumped = json.dumps(data)
            self.assertNotIn("token_path", dumped)
            self.assertNotIn("access_token", dumped)

    def test_channel_status_is_channel_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            status, data = ui_server.dispatch_v2_request("GET", "/api/v2/channels/channel_a", context=ui_server.build_app_context(root=root))
            self.assertEqual(status, 200)
            self.assertEqual(data["channel"]["channel_slug"], "channel_a")
            self.assertEqual(data["project_count"], 0)

    def test_invalid_slug_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ui_server.V2Error) as ctx:
                ui_server.dispatch_v2_request("GET", "/api/v2/channels/Bad-Slug", context=ui_server.build_app_context(root=tmp))
            self.assertEqual(ctx.exception.code, "INVALID_CHANNEL_SLUG")

    def test_missing_channel_returns_stable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ui_server.V2Error) as ctx:
                ui_server.dispatch_v2_request("GET", "/api/v2/channels/missing", context=ui_server.build_app_context(root=tmp))
            self.assertEqual(ctx.exception.code, "CHANNEL_NOT_FOUND")

    def test_project_list_returns_only_selected_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            make_channel(root, "channel_b", "UC2")
            channel_projects.create_channel_project(root, "channel_a", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", ui_server.normalize_competitor_metadata(fake_video("VIDEO12345A"), "https://youtube.com/watch?v=VIDEO12345A", "https://example.com/thumb.jpg"))
            channel_projects.create_channel_project(root, "channel_b", "VIDEO12345A", "https://youtube.com/watch?v=VIDEO12345A", ui_server.normalize_competitor_metadata(fake_video("VIDEO12345A"), "https://youtube.com/watch?v=VIDEO12345A", "https://example.com/thumb.jpg"))
            status, data = ui_server.dispatch_v2_request("GET", "/api/v2/channels/channel_a/projects", context=ui_server.build_app_context(root=root))
            self.assertEqual(status, 200)
            self.assertEqual(len(data["projects"]), 1)
            self.assertEqual(data["projects"][0]["channel_slug"], "channel_a")

    def test_sync_metrics_passes_selected_channel_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            called = {}

            def fake_sync(root, channel_slug, **kwargs):
                called["slug"] = channel_slug
                return {"channel_slug": channel_slug, "reporting_state": {"status": "PENDING"}}

            status, data = ui_server.dispatch_v2_request(
                "POST",
                "/api/v2/channels/channel_a/sync_metrics",
                {"window_days": 90, "recent_count": 12},
                context=ui_server.build_app_context(root=root, metrics_syncer=fake_sync),
            )
            self.assertEqual(status, 200)
            self.assertEqual(called["slug"], "channel_a")

    def test_sync_a_cannot_invoke_b_token_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            seen = {}

            def token_provider(root, slug):
                seen["slug"] = slug
                return "token"

            def fake_sync(root, channel_slug, **kwargs):
                kwargs["token_provider"](root, channel_slug)
                return {"channel_slug": channel_slug, "reporting_state": {"status": "PENDING"}}

            ui_server.dispatch_v2_request(
                "POST",
                "/api/v2/channels/channel_a/sync_metrics",
                {},
                context=ui_server.build_app_context(root=root, metrics_syncer=fake_sync, token_provider=token_provider),
            )
            self.assertEqual(seen["slug"], "channel_a")

    def test_create_project_fetches_public_competitor_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            seen = {}

            def fetcher(video_id):
                seen["video_id"] = video_id
                return fake_video(video_id)

            status, data = ui_server.dispatch_v2_request(
                "POST",
                "/api/v2/channels/channel_a/projects",
                {"url": "https://youtube.com/watch?v=VIDEO12345A"},
                context=ui_server.build_app_context(root=root, competitor_video_fetcher=fetcher, thumbnail_fetcher=lambda url: (b"img", ".jpg")),
            )
            self.assertEqual(status, 200)
            self.assertEqual(seen["video_id"], "VIDEO12345A")
            self.assertIn("project", data)

    def test_create_project_does_not_fetch_analytics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")

            def bad_sync(*args, **kwargs):
                raise AssertionError("metrics sync should not run")

            status, _ = ui_server.dispatch_v2_request(
                "POST",
                "/api/v2/channels/channel_a/projects",
                {"url": "https://youtube.com/watch?v=VIDEO12345A"},
                context=ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None), metrics_syncer=bad_sync),
            )
            self.assertEqual(status, 200)

    def test_create_project_fails_clearly_without_channel_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1", with_metrics=False)
            with self.assertRaises(ui_server.V2Error) as ctx:
                ui_server.dispatch_v2_request(
                    "POST",
                    "/api/v2/channels/channel_a/projects",
                    {"url": "https://youtube.com/watch?v=VIDEO12345A"},
                    context=ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None)),
                )
            self.assertEqual(ctx.exception.code, "CHANNEL_METRICS_NOT_READY")

    def test_same_competitor_url_may_create_one_project_per_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            make_channel(root, "channel_b", "UC2")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)
            ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_b/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)
            self.assertEqual(len(channel_projects.list_channel_projects(root, "channel_a")), 1)
            self.assertEqual(len(channel_projects.list_channel_projects(root, "channel_b")), 1)

    def test_duplicate_competitor_inside_one_channel_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)
            with self.assertRaises(ui_server.V2Error) as err:
                ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)
            self.assertEqual(err.exception.code, "SOURCE_VIDEO_ALREADY_EXISTS")

    def test_transcript_save_uses_selected_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            project = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            status, data = ui_server.dispatch_v2_request("POST", f"/api/v2/channels/channel_a/projects/{project['project_slug']}/transcript", {"transcript": "real transcript " * 10}, context=ctx)
            self.assertEqual(status, 200)
            self.assertTrue(data["checks"]["transcript_real_content"])

    def test_transcript_overwrite_requirement_maps_to_stable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            project = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            ui_server.dispatch_v2_request("POST", f"/api/v2/channels/channel_a/projects/{project['project_slug']}/transcript", {"transcript": "real transcript " * 10}, context=ctx)
            with self.assertRaises(ui_server.V2Error) as err:
                ui_server.dispatch_v2_request("POST", f"/api/v2/channels/channel_a/projects/{project['project_slug']}/transcript", {"transcript": "other transcript " * 10}, context=ctx)
            self.assertEqual(err.exception.code, "TRANSCRIPT_OVERWRITE_REQUIRED")

    def test_validate_uses_selected_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            project = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            status, data = ui_server.dispatch_v2_request("POST", f"/api/v2/channels/channel_a/projects/{project['project_slug']}/validate", {}, context=ctx)
            self.assertEqual(status, 200)
            self.assertEqual(data["project"]["channel_slug"], "channel_a")

    def test_cross_channel_project_access_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            make_channel(root, "channel_b", "UC2")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            project = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            with self.assertRaises(ui_server.V2Error):
                ui_server.dispatch_v2_request("POST", f"/api/v2/channels/channel_b/projects/{project['project_slug']}/validate", {}, context=ctx)

    def test_absolute_path_input_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            with self.assertRaises(ui_server.V2Error):
                ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects/C:\\evil\\validate", {}, context=ui_server.build_app_context(root=root))

    def test_errors_contain_no_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1", with_metrics=False)
            try:
                ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None)))
            except ui_server.V2Error as exc:
                self.assertNotIn("access_token", exc.message)
                self.assertNotIn("client_secret", exc.message)

    def test_responses_contain_no_token_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            status, data = ui_server.dispatch_v2_request("GET", "/api/v2/channels", context=ui_server.build_app_context(root=root))
            self.assertEqual(status, 200)
            dumped = json.dumps(data)
            self.assertNotIn("access_token", dumped)
            self.assertNotIn("refresh_token", dumped)

    def test_raw_google_payload_is_not_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            status, data = ui_server.dispatch_v2_request("GET", "/api/v2/channels/channel_a", context=ui_server.build_app_context(root=root))
            self.assertEqual(status, 200)
            dumped = json.dumps(data)
            self.assertNotIn("items", dumped)
            self.assertNotIn("columnHeaders", dumped)

    def test_v2_route_dispatch_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            status, _ = ui_server.dispatch_v2_request("GET", "/api/v2/channels", context=ui_server.build_app_context(root=root))
            self.assertEqual(status, 200)

    def test_existing_collector_behavior_remains_unchanged(self):
        self.assertIn("api_key", ui_server.app_status())
        self.assertTrue(callable(ui_server.create_project))

    def test_no_real_api_network_request_occurs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            called = {"video": 0}
            ctx = ui_server.build_app_context(
                root=root,
                competitor_video_fetcher=lambda video_id: called.__setitem__("video", called["video"] + 1) or fake_video(video_id),
                thumbnail_fetcher=lambda url: (None, None),
            )
            ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)
            self.assertEqual(called["video"], 1)

    def test_no_real_repository_runtime_data_is_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ui_server.dispatch_v2_request("GET", "/api/v2/channels", context=ui_server.build_app_context(root=root))
            self.assertFalse((ROOT / "channels").exists())


if __name__ == "__main__":
    unittest.main()
