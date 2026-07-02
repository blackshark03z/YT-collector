import http.client
import json
import threading
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_projects, channel_prompt_bundle, channel_workspace, ui_server
from tests.runtime_isolation_helpers import snapshot_runtime_state
from tests.test_channel_prompt_bundle import prepare_step2_inputs


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

    def test_project_list_returns_empty_array_when_channel_has_no_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            status, data = ui_server.dispatch_v2_request("GET", "/api/v2/channels/channel_a/projects", context=ui_server.build_app_context(root=root))
            self.assertEqual(status, 200)
            self.assertEqual(data["projects"], [])

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

    def test_default_recent_videos_fetcher_uses_bearer_auth_for_video_details(self):
        seen = []

        def fake_request_json(url, headers=None, data=None):
            seen.append({"url": url, "headers": headers or {}})
            if "/channels?" in url:
                return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UPLOADS123"}}}]}
            if "/playlistItems?" in url:
                return {"items": [{"contentDetails": {"videoId": "VIDEO12345A"}}]}
            if "/videos?" in url:
                return {"items": [{"id": "VIDEO12345A", "snippet": {}, "statistics": {}}]}
            raise AssertionError(url)

        with mock.patch("scripts.ui_server.request_json", side_effect=fake_request_json):
            payload = ui_server.default_recent_videos_fetcher(
                root=ROOT,
                channel_slug="mist_of_ages",
                access_token="token-a",
                recent_count=12,
                channel={"youtube_channel_id": "UC123"},
            )

        self.assertEqual([item["id"] for item in payload["items"]], ["VIDEO12345A"])
        self.assertEqual(len(seen), 3)
        self.assertTrue(all(call["headers"].get("Authorization") == "Bearer token-a" for call in seen))
        self.assertTrue(all("key=" not in call["url"] for call in seen))

    def test_default_recent_videos_fetcher_does_not_call_global_api_key_helper(self):
        def fake_request_json(url, headers=None, data=None):
            if "/channels?" in url:
                return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UPLOADS123"}}}]}
            if "/playlistItems?" in url:
                return {"items": [{"contentDetails": {"videoId": "VIDEO12345A"}}]}
            if "/videos?" in url:
                return {"items": [{"id": "VIDEO12345A", "snippet": {}, "statistics": {}}]}
            raise AssertionError(url)

        with mock.patch("scripts.ui_server.request_json", side_effect=fake_request_json), mock.patch(
            "scripts.ui_server.data_api", side_effect=AssertionError("global api-key helper should not be used")
        ):
            payload = ui_server.default_recent_videos_fetcher(
                root=ROOT,
                channel_slug="mist_of_ages",
                access_token="token-a",
                recent_count=12,
                channel={"youtube_channel_id": "UC123"},
            )

        self.assertEqual([item["id"] for item in payload["items"]], ["VIDEO12345A"])

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

    def test_parse_output_route_returns_parsed_preview_for_selected_project_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            __import__("shutil").copytree(ROOT / "workflows", root / "workflows")
            registry_path = root / "workflows" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "2"
            registry["channel_defaults"]["channel_a"] = {"workflow_id": "mist_of_ages_assisted_content"}
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8", newline="\n")
            make_channel(root, "channel_a", "UC1")
            created = channel_projects.create_channel_project(
                root,
                "channel_a",
                "VIDEO12345A",
                "https://youtube.com/watch?v=VIDEO12345A",
                {
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
                },
                created_at="2026-07-01T00:00:00+00:00",
            )
            project_dir = channel_workspace.canonical_channel_paths(root, "channel_a").projects_dir / created["project_slug"]
            prepare_step2_inputs(root, "channel_a", created["project_slug"])
            project = channel_projects.load_channel_project(root, "channel_a", created["project_slug"])
            bundle = channel_prompt_bundle.build_prompt_bundle(root, "channel_a", created["project_slug"], "prompt_2_historical_research", project, project_dir)
            status, data = ui_server.dispatch_v2_request(
                "POST",
                f"/api/v2/channels/channel_a/projects/{created['project_slug']}/workflow/steps/prompt_2_historical_research/parse-output",
                {
                    "bundle_sha256": bundle["bundle_sha256"],
                    "output_text": (
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
                    ),
                },
                context=ui_server.build_app_context(root=root),
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["status"], "VALID")
            self.assertEqual(len(data["artifacts"]), 2)
            before_tree = {}
            for path in sorted(project_dir.rglob("*")):
                before_tree[path.relative_to(project_dir).as_posix()] = ("dir", 0) if path.is_dir() else ("file", path.stat().st_size, path.read_bytes())
            status, data = ui_server.dispatch_v2_request(
                "POST",
                f"/api/v2/channels/channel_a/projects/{created['project_slug']}/workflow/steps/prompt_2_historical_research/parse-output",
                {
                    "bundle_sha256": bundle["bundle_sha256"],
                    "output_text": (
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
                    ),
                },
                context=ui_server.build_app_context(root=root),
            )
            after_tree = {}
            for path in sorted(project_dir.rglob("*")):
                after_tree[path.relative_to(project_dir).as_posix()] = ("dir", 0) if path.is_dir() else ("file", path.stat().st_size, path.read_bytes())
            self.assertEqual(before_tree, after_tree)
            dumped = json.dumps(data)
            self.assertNotIn(str(root), dumped)

    def test_parse_output_route_returns_stable_identity_mismatch_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            __import__("shutil").copytree(ROOT / "workflows", root / "workflows")
            registry_path = root / "workflows" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "2"
            registry["channel_defaults"]["channel_a"] = {"workflow_id": "mist_of_ages_assisted_content"}
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8", newline="\n")
            make_channel(root, "channel_a", "UC1")
            created = channel_projects.create_channel_project(
                root,
                "channel_a",
                "VIDEO12345A",
                "https://youtube.com/watch?v=VIDEO12345A",
                {
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
                },
                created_at="2026-07-01T00:00:00+00:00",
            )
            channel_projects.save_project_transcript(root, "channel_a", created["project_slug"], "real transcript " * 12)
            with self.assertRaises(ui_server.V2Error) as ctx:
                ui_server.dispatch_v2_request(
                    "POST",
                    f"/api/v2/channels/channel_a/projects/{created['project_slug']}/workflow/steps/prompt_1_transcript_analysis/parse-output",
                    {"bundle_sha256": "A" * 64, "output_text": "## Subject\nRome\n"},
                    context=ui_server.build_app_context(root=root),
                )
            self.assertEqual(ctx.exception.code, "BUNDLE_IDENTITY_MISMATCH")

    def test_parse_output_route_returns_invalid_for_malformed_ai_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            __import__("shutil").copytree(ROOT / "workflows", root / "workflows")
            registry_path = root / "workflows" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "2"
            registry["channel_defaults"]["channel_a"] = {"workflow_id": "mist_of_ages_assisted_content"}
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8", newline="\n")
            make_channel(root, "channel_a", "UC1")
            created = channel_projects.create_channel_project(
                root,
                "channel_a",
                "VIDEO12345A",
                "https://youtube.com/watch?v=VIDEO12345A",
                {
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
                },
                created_at="2026-07-01T00:00:00+00:00",
            )
            project_dir = channel_workspace.canonical_channel_paths(root, "channel_a").projects_dir / created["project_slug"]
            prepare_step2_inputs(root, "channel_a", created["project_slug"])
            project = channel_projects.load_channel_project(root, "channel_a", created["project_slug"])
            bundle = channel_prompt_bundle.build_prompt_bundle(root, "channel_a", created["project_slug"], "prompt_2_historical_research", project, project_dir)
            status, data = ui_server.dispatch_v2_request(
                "POST",
                f"/api/v2/channels/channel_a/projects/{created['project_slug']}/workflow/steps/prompt_2_historical_research/parse-output",
                {
                    "bundle_sha256": bundle["bundle_sha256"],
                    "output_text": "unexpected prefix\n=== FILE 2: evidence_ledger.md ===\nCLAIM:\nFact\n",
                },
                context=ui_server.build_app_context(root=root),
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["status"], "INVALID")
            self.assertEqual(data["artifacts"], [])

    def test_parse_output_route_rejects_non_string_output_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            __import__("shutil").copytree(ROOT / "workflows", root / "workflows")
            registry_path = root / "workflows" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "2"
            registry["channel_defaults"]["channel_a"] = {"workflow_id": "mist_of_ages_assisted_content"}
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8", newline="\n")
            make_channel(root, "channel_a", "UC1")
            created = channel_projects.create_channel_project(
                root,
                "channel_a",
                "VIDEO12345A",
                "https://youtube.com/watch?v=VIDEO12345A",
                {
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
                },
                created_at="2026-07-01T00:00:00+00:00",
            )
            with self.assertRaises(ui_server.V2Error) as ctx:
                ui_server.dispatch_v2_request(
                    "POST",
                    f"/api/v2/channels/channel_a/projects/{created['project_slug']}/workflow/steps/prompt_1_transcript_analysis/parse-output",
                    {"bundle_sha256": "A" * 64, "output_text": {"bad": True}},
                    context=ui_server.build_app_context(root=root),
                )
            self.assertEqual(ctx.exception.code, "OUTPUT_TEXT_REQUIRED")

    def test_candidate_approve_route_publishes_stable_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            __import__("shutil").copytree(ROOT / "workflows", root / "workflows")
            registry_path = root / "workflows" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "2"
            registry["channel_defaults"]["channel_a"] = {"workflow_id": "mist_of_ages_assisted_content"}
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8", newline="\n")
            make_channel(root, "channel_a", "UC1")
            created = channel_projects.create_channel_project(
                root,
                "channel_a",
                "VIDEO12345A",
                "https://youtube.com/watch?v=VIDEO12345A",
                {
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
                },
                created_at="2026-07-01T00:00:00+00:00",
            )
            channel_projects.save_project_transcript(root, "channel_a", created["project_slug"], "real transcript " * 12)
            project_dir = channel_workspace.canonical_channel_paths(root, "channel_a").projects_dir / created["project_slug"]
            project = channel_projects.load_channel_project(root, "channel_a", created["project_slug"])
            bundle = channel_prompt_bundle.build_prompt_bundle(root, "channel_a", created["project_slug"], "prompt_1_transcript_analysis", project, project_dir)
            saved = ui_server.dispatch_v2_request(
                "POST",
                f"/api/v2/channels/channel_a/projects/{created['project_slug']}/workflow/steps/prompt_1_transcript_analysis/revisions",
                {
                    "bundle_sha256": bundle["bundle_sha256"],
                    "output_text": "## Subject\nRome\n## Competitor Promise\nPromise\n## Narrative Map\nMap\n## Strong Idea-Level Elements\nStrong\n## Weak or Removable Elements\nWeak\n## Claims Requiring Verification\nClaims\n## Originality Risks\nRisks\n## Neutral Research Questions\nQuestions\n",
                    "expected_state_revision": 0,
                },
                context=ui_server.build_app_context(root=root),
            )[1]
            status, data = ui_server.dispatch_v2_request(
                "POST",
                f"/api/v2/channels/channel_a/projects/{created['project_slug']}/workflow/steps/prompt_1_transcript_analysis/candidate/approve",
                {
                    "candidate_group_id": saved["revision_group"]["revision_group_id"],
                    "expected_state_revision": 1,
                },
                context=ui_server.build_app_context(root=root),
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["status"], "CANDIDATE_APPROVED")
            self.assertIn("## Subject\nRome\n", (project_dir / "workflow" / "transcript_analysis.md").read_text(encoding="utf-8"))

    def test_workflow_read_routes_reject_pending_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            __import__("shutil").copytree(ROOT / "workflows", root / "workflows")
            registry_path = root / "workflows" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["workflows"]["mist_of_ages_assisted_content"]["default_version"] = "2"
            registry["channel_defaults"]["channel_a"] = {"workflow_id": "mist_of_ages_assisted_content"}
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8", newline="\n")
            make_channel(root, "channel_a", "UC1")
            created = channel_projects.create_channel_project(
                root,
                "channel_a",
                "VIDEO12345A",
                "https://youtube.com/watch?v=VIDEO12345A",
                {
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
                },
                created_at="2026-07-01T00:00:00+00:00",
            )
            channel_projects.save_project_transcript(root, "channel_a", created["project_slug"], "real transcript " * 12)
            project_dir = channel_workspace.canonical_channel_paths(root, "channel_a").projects_dir / created["project_slug"]
            (project_dir / "workflow" / "_transactions" / "txn_pending").mkdir(parents=True, exist_ok=True)
            with self.assertRaises(ui_server.V2Error) as workflow_ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/channel_a/projects/{created['project_slug']}/workflow",
                    context=ui_server.build_app_context(root=root),
                )
            self.assertEqual(workflow_ctx.exception.code, "WORKFLOW_RECOVERY_REQUIRED")
            with self.assertRaises(ui_server.V2Error) as bundle_ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/channel_a/projects/{created['project_slug']}/workflow/steps/prompt_1_transcript_analysis/bundle",
                    context=ui_server.build_app_context(root=root),
                )
            self.assertEqual(bundle_ctx.exception.code, "WORKFLOW_RECOVERY_REQUIRED")

    def test_v2_handler_returns_controlled_error_for_malformed_json_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = ui_server.APP_CONTEXT
            server = None
            thread = None
            try:
                ui_server.APP_CONTEXT = ui_server.build_app_context(root=root)
                server = ui_server.ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.request(
                    "POST",
                    "/api/v2/channels/channel_a/projects/demo/workflow/steps/alpha/parse-output",
                    body="{bad json",
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
                response = conn.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                conn.close()
                self.assertEqual(response.status, 400)
                self.assertEqual(payload["error"]["code"], "INVALID_REQUEST")
                self.assertEqual(payload["error"]["message"], "Request body must be valid JSON.")
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    thread.join(timeout=5)
                ui_server.APP_CONTEXT = previous

    def test_oauth_start_dispatch_create_rejects_existing_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            with self.assertRaises(ui_server.V2Error) as ctx:
                ui_server.dispatch_v2_request("GET", "/api/v2/oauth/start?channel_slug=channel_a&mode=create", context=ui_server.build_app_context(root=root, oauth_flow_starter=lambda **kwargs: (_ for _ in ()).throw(__import__("scripts.channel_oauth_browser", fromlist=[""]).OAuthFlowInvalidError("Channel workspace already exists."))))
            self.assertEqual(ctx.exception.code, "CHANNEL_ALREADY_EXISTS")

    def test_oauth_start_dispatch_returns_redirect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, data = ui_server.dispatch_v2_request(
                "GET",
                "/api/v2/oauth/start?channel_slug=channel_a&mode=create",
                context=ui_server.build_app_context(
                    root=root,
                    oauth_flow_starter=lambda **kwargs: type("Flow", (), {"authorization_url": "https://accounts.google.com/o/oauth2/auth?state=abc"})(),
                ),
            )
            self.assertEqual(status, 302)
            self.assertIn("redirect_url", data)

    def test_json_clients_prefer_oauth_redirect_payload_over_http_redirect(self):
        self.assertTrue(ui_server._client_prefers_json_redirect({"Accept": "application/json"}))
        self.assertTrue(ui_server._client_prefers_json_redirect({"Accept": "text/plain, application/json"}))
        self.assertFalse(ui_server._client_prefers_json_redirect({"Accept": "text/html"}))
        self.assertFalse(ui_server._client_prefers_json_redirect({}))

    def test_project_detail_is_channel_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            status, data = ui_server.dispatch_v2_request("GET", f"/api/v2/channels/channel_a/projects/{created['project_slug']}", context=ctx)
            self.assertEqual(status, 200)
            self.assertEqual(data["project"]["channel_slug"], "channel_a")
            self.assertEqual(set(data["project"].keys()), {
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
            })

    def test_project_detail_contains_no_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            _, data = ui_server.dispatch_v2_request("GET", f"/api/v2/channels/channel_a/projects/{created['project_slug']}", context=ctx)
            dumped = json.dumps(data)
            self.assertNotIn(str(root), dumped)

    def test_project_detail_reports_final_output_existence_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            project_dir = channel_workspace.canonical_channel_paths(root, "channel_a").projects_dir / created["project_slug"]
            (project_dir / "content.md").write_text("x", encoding="utf-8")
            _, data = ui_server.dispatch_v2_request("GET", f"/api/v2/channels/channel_a/projects/{created['project_slug']}", context=ctx)
            self.assertTrue(data["project"]["has_content"])
            self.assertFalse(data["project"]["has_publishing_package"])

    def test_transcript_read_returns_template_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            status, data = ui_server.dispatch_v2_request("GET", f"/api/v2/channels/channel_a/projects/{created['project_slug']}/transcript", context=ctx)
            self.assertEqual(status, 200)
            self.assertTrue(data["is_template"])
            self.assertFalse(data["has_real_content"])

    def test_transcript_read_returns_real_content_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            ui_server.dispatch_v2_request("POST", f"/api/v2/channels/channel_a/projects/{created['project_slug']}/transcript", {"transcript": "real transcript " * 10}, context=ctx)
            _, data = ui_server.dispatch_v2_request("GET", f"/api/v2/channels/channel_a/projects/{created['project_slug']}/transcript", context=ctx)
            self.assertFalse(data["is_template"])
            self.assertTrue(data["has_real_content"])

    def test_cross_channel_transcript_read_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            make_channel(root, "channel_b", "UC2")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            with self.assertRaises(ui_server.V2Error):
                ui_server.dispatch_v2_request("GET", f"/api/v2/channels/channel_b/projects/{created['project_slug']}/transcript", context=ctx)

    def test_missing_transcript_maps_to_stable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            transcript = channel_workspace.canonical_channel_paths(root, "channel_a").projects_dir / created["project_slug"] / "research" / "competitor_transcript.md"
            transcript.unlink()
            with self.assertRaises(ui_server.V2Error) as err:
                ui_server.dispatch_v2_request("GET", f"/api/v2/channels/channel_a/projects/{created['project_slug']}/transcript", context=ctx)
            self.assertEqual(err.exception.code, "TRANSCRIPT_NOT_FOUND")

    def test_open_channel_resolves_correct_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            seen = {}
            status, _ = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/open", context=ui_server.build_app_context(root=root, path_opener=lambda path: seen.setdefault("path", path)))
            self.assertEqual(status, 200)
            self.assertEqual(seen["path"], channel_workspace.canonical_channel_paths(root, "channel_a").channel_dir.resolve())

    def test_open_project_resolves_correct_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None), path_opener=lambda path: None)
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            seen = {}
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None), path_opener=lambda path: seen.setdefault("path", path))
            status, _ = ui_server.dispatch_v2_request("POST", f"/api/v2/channels/channel_a/projects/{created['project_slug']}/open", context=ctx)
            self.assertEqual(status, 200)
            self.assertEqual(seen["path"], (channel_workspace.canonical_channel_paths(root, "channel_a").projects_dir / created["project_slug"]).resolve())

    def test_open_transcript_resolves_correct_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            seen = {}
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None), path_opener=lambda path: seen.setdefault("path", path))
            status, _ = ui_server.dispatch_v2_request("POST", f"/api/v2/channels/channel_a/projects/{created['project_slug']}/open_transcript", context=ctx)
            self.assertEqual(status, 200)
            self.assertTrue(str(seen["path"]).endswith("competitor_transcript.md"))

    def test_path_opener_receives_only_canonical_descendant_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            seen = {}
            ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/open", context=ui_server.build_app_context(root=root, path_opener=lambda path: seen.setdefault("path", path)))
            seen["path"].resolve().relative_to(root.resolve())

    def test_secret_paths_cannot_be_opened(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ui_server.V2Error) as err:
                ui_server._safe_open_path(root, root / "secrets" / "youtube" / "x.json", lambda path: None)
            self.assertEqual(err.exception.code, "PATH_OPEN_FAILED")

    def test_cross_channel_open_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            make_channel(root, "channel_b", "UC2")
            ctx = ui_server.build_app_context(root=root, competitor_video_fetcher=lambda video_id: fake_video(video_id), thumbnail_fetcher=lambda url: (None, None))
            created = ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/projects", {"url": "https://youtube.com/watch?v=VIDEO12345A"}, context=ctx)[1]["project"]
            with self.assertRaises(ui_server.V2Error):
                ui_server.dispatch_v2_request("POST", f"/api/v2/channels/channel_b/projects/{created['project_slug']}/open", context=ctx)

    def test_path_open_failure_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            with self.assertRaises(ui_server.V2Error) as err:
                ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/open", context=ui_server.build_app_context(root=root, path_opener=lambda path: (_ for _ in ()).throw(RuntimeError("secret fail"))))
            self.assertEqual(err.exception.code, "PATH_OPEN_FAILED")
            self.assertNotIn("secret", err.exception.message.lower())

    def test_existing_v2_endpoints_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            status, data = ui_server.dispatch_v2_request("GET", "/api/v2/channels", context=ui_server.build_app_context(root=root))
            self.assertEqual(status, 200)
            self.assertIn("channels", data)

    def test_existing_legacy_routes_remain_unchanged(self):
        self.assertIn("Connect Channel", ui_server.HTML_PAGE)

    def test_legacy_create_project_keeps_workflow_outputs_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects_dir = root / "projects"
            channel_dir = root / "channel" / "mist_of_ages"
            config_dir = root / ".local"
            channel_dir.mkdir(parents=True, exist_ok=True)
            config_dir.mkdir(parents=True, exist_ok=True)
            (channel_dir / "channel_learnings_master.md").write_text("# Learnings\n\nApproved.\n", encoding="utf-8", newline="\n")
            (config_dir / "mist_of_ages_channel.json").write_text(
                json.dumps({"id": "UC1", "title": "Mist of Ages"}, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            with mock.patch.object(ui_server, "PROJECTS_DIR", projects_dir), \
                mock.patch.object(ui_server, "CHANNEL_DIR", channel_dir), \
                mock.patch.object(ui_server, "CONFIG_DIR", config_dir), \
                mock.patch.object(ui_server, "CHANNEL_CONFIG_FILE", config_dir / "mist_of_ages_channel.json"), \
                mock.patch.object(ui_server, "MASTER_LEARNINGS_FILE", channel_dir / "channel_learnings_master.md"), \
                mock.patch.object(ui_server, "fetch_competitor_video", lambda video_id: fake_video(video_id)), \
                mock.patch.object(ui_server, "download_thumbnail", lambda url, assets_dir: ""), \
                mock.patch.object(ui_server, "write_channel_files", lambda project_dir, count, window_days: {"status": "PASS"}):
                result = ui_server.create_project({"url": "https://youtube.com/watch?v=VIDEO12345A", "recent_count": 10, "window_days": 28})
            project_dir = projects_dir / result["project"]["project_slug"]
            self.assertTrue((project_dir / "project.json").exists())
            self.assertTrue((project_dir / "input" / "competitor_reference.md").exists())
            self.assertTrue((project_dir / "research" / "competitor_transcript.md").exists())
            self.assertTrue((project_dir / "workflow").exists())
            self.assertEqual(sorted(path.name for path in (project_dir / "workflow").glob("*")), [])
            self.assertFalse((project_dir / "workflow" / "transcript_analysis.md").exists())
            self.assertFalse((project_dir / "workflow" / "research_pack.md").exists())
            self.assertFalse((project_dir / "workflow" / "evidence_ledger.md").exists())

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
        before = snapshot_runtime_state(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            ui_server.dispatch_v2_request("GET", "/api/v2/channels", context=ui_server.build_app_context(root=root))
        after = snapshot_runtime_state(ROOT)
        self.assertEqual(before, after)

    def test_no_real_os_folder_file_is_opened(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root, "channel_a", "UC1")
            called = {"count": 0}
            ui_server.dispatch_v2_request("POST", "/api/v2/channels/channel_a/open", context=ui_server.build_app_context(root=root, path_opener=lambda path: called.__setitem__("count", called["count"] + 1)))
            self.assertEqual(called["count"], 1)


if __name__ == "__main__":
    unittest.main()
