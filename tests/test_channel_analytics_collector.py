import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_analytics_collector, channel_workspace, ui_server


class FakeApiError(Exception):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.message = message
        self.status = status


def tree_hashes(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    return result


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FakeCollectorBackend:
    def __init__(self):
        self.created_jobs: list[str] = []
        self.download_count = 0
        self.analytics_calls: list[dict[str, str]] = []
        self.subscriber_failures_remaining = 0
        self.video_daily_error = False
        self.retention_fail_video_ids: set[str] = set()
        self.cards_supported = False
        self.report_list_errors: dict[str, tuple[str, int]] = {}
        base_types = [
            ("channel_basic_a2", "Channel Basic", True),
            ("video_reach_a1", "Video Reach", False),
            ("channel_reach_basic_a1", "Channel Reach", False),
            ("channel_end_screen_a1", "End Screen", False),
        ]
        extra_types = [(f"custom_report_{index:02d}", f"Custom Report {index:02d}", False) for index in range(1, 17)]
        self.report_types = [
            {"id": report_type_id, "name": name, "systemManaged": system_managed}
            for report_type_id, name, system_managed in [*base_types, *extra_types]
        ]
        self.jobs = [
            {
                "id": f"job_{report_type_id}",
                "reportTypeId": report_type_id,
                "name": f"{report_type_id}-job",
                "systemManaged": system_managed,
            }
            for report_type_id, _name, system_managed in [*base_types, *extra_types]
        ]
        self.reports = {job["id"]: [] for job in self.jobs}
        self.report_bytes = {
            "https://download.local/report_001": b"video_id,impressions\nvid_b,100\n",
        }

    def token_provider(self, root, slug):
        return "token"

    def data_api_fetcher(self, *, path, params, **kwargs):
        if path == "channels":
            return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "uploads_1"}}}]}
        if path == "playlistItems":
            page_token = params.get("pageToken", "")
            if not page_token:
                return {
                    "items": [
                        {"contentDetails": {"videoId": "vid_b"}},
                        {"contentDetails": {"videoId": "vid_a"}},
                    ],
                    "nextPageToken": "page-2",
                }
            return {
                "items": [
                    {"contentDetails": {"videoId": "vid_a"}},
                    {"contentDetails": {"videoId": "vid_c"}},
                ]
            }
        if path == "playlists":
            return {"items": [{"id": "PL123"}, {"id": "PL999"}]}
        if path == "videos":
            ids = params["id"].split(",")
            records = {
                "vid_a": {
                    "id": "vid_a",
                    "snippet": {
                        "title": "Video A",
                        "description": "Desc A",
                        "publishedAt": "2026-06-01T00:00:00Z",
                        "channelId": "UC123",
                        "categoryId": "22",
                        "tags": ["rome", "history"],
                        "liveBroadcastContent": "none",
                    },
                    "contentDetails": {"duration": "PT10M", "caption": "true"},
                    "statistics": {"viewCount": "10", "likeCount": "2", "commentCount": "1"},
                    "status": {"privacyStatus": "public", "uploadStatus": "processed", "license": "youtube", "embeddable": True, "madeForKids": False, "publicStatsViewable": True},
                },
                "vid_b": {
                    "id": "vid_b",
                    "snippet": {
                        "title": "Video B",
                        "description": "Desc B",
                        "publishedAt": "2026-06-02T00:00:00Z",
                        "channelId": "UC123",
                        "categoryId": "24",
                        "tags": [],
                        "liveBroadcastContent": "none",
                    },
                    "contentDetails": {"duration": "PT5M", "caption": "false"},
                    "statistics": {"viewCount": "20", "likeCount": "5", "commentCount": "0"},
                    "status": {"privacyStatus": "public", "uploadStatus": "processed", "license": "youtube", "embeddable": True, "madeForKids": False, "publicStatsViewable": True},
                },
                "vid_c": {
                    "id": "vid_c",
                    "snippet": {
                        "title": "Video C",
                        "description": "Desc C",
                        "publishedAt": "2026-06-03T00:00:00Z",
                        "channelId": "UC123",
                        "categoryId": "27",
                        "tags": ["empire"],
                        "liveBroadcastContent": "none",
                    },
                    "contentDetails": {"duration": "PT7M", "caption": "true"},
                    "statistics": {"viewCount": "30", "likeCount": "6", "commentCount": "4"},
                    "status": {"privacyStatus": "public", "uploadStatus": "processed", "license": "youtube", "embeddable": True, "madeForKids": False, "publicStatsViewable": True},
                },
            }
            return {"items": [records[item] for item in ids if item in records]}
        raise AssertionError(f"Unexpected data path: {path}")

    def reporting_api_fetcher(self, *, method, path, payload, **kwargs):
        if method == "GET" and path == "reportTypes":
            return {"reportTypes": self.report_types}
        if method == "GET" and path == "jobs":
            return {"jobs": self.jobs}
        if method == "POST" and path == "jobs":
            self.created_jobs.append(str(payload.get("reportTypeId", "")))
            raise AssertionError("Collector must not create additional Reporting API jobs during Phase 9 repair.")
        if method == "GET" and path.startswith("jobs/") and path.endswith("/reports"):
            job_id = path.split("/")[1]
            if job_id in self.report_list_errors:
                message, status = self.report_list_errors[job_id]
                raise FakeApiError(message, status)
            return {"reports": self.reports.get(job_id, [])}
        raise AssertionError(f"Unexpected reporting path: {method} {path}")

    def report_download_fetcher(self, *, url, **kwargs):
        self.download_count += 1
        return self.report_bytes[url]

    def analytics_query_fetcher(self, *, params, **kwargs):
        self.analytics_calls.append(dict(params))
        dimensions = params["dimensions"]
        metrics = params["metrics"]
        filters = params.get("filters", "")
        start_index = params.get("startIndex", "")
        if metrics == "estimatedRevenue,grossRevenue,cpm":
            raise FakeApiError("The user is not authorized for monetary metrics.", 403)
        if metrics == "cardImpressions,cardTeaserImpressions" and not self.cards_supported:
            raise FakeApiError("Unsupported dimensions or metrics.", 400)
        if dimensions == "day" and metrics == "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,subscribersLost":
            return {
                "columnHeaders": [{"name": "day"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}, {"name": "averageViewDuration"}, {"name": "averageViewPercentage"}, {"name": "likes"}, {"name": "comments"}, {"name": "shares"}, {"name": "subscribersGained"}, {"name": "subscribersLost"}],
                "rows": [["2026-07-01", 100, 200, 30, 60, 5, 2, 1, 4, 1]],
            }
        if dimensions == "day,video":
            if self.video_daily_error:
                raise FakeApiError("Internal server error", 500)
            self._assert_video_filter(filters)
            if not start_index:
                return {
                    "columnHeaders": [{"name": "day"}, {"name": "video"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}, {"name": "averageViewDuration"}, {"name": "averageViewPercentage"}, {"name": "likes"}, {"name": "comments"}, {"name": "shares"}],
                    "rows": [
                        ["2026-07-01", "vid_b", 30, 50, 40, 70, 2, 0, 0],
                        ["2026-07-01", "vid_a", 10, 20, 30, 60, 1, 1, 1],
                    ],
                    "nextPageToken": "2",
                }
            return {
                "columnHeaders": [{"name": "day"}, {"name": "video"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}, {"name": "averageViewDuration"}, {"name": "averageViewPercentage"}, {"name": "likes"}, {"name": "comments"}, {"name": "shares"}],
                "rows": [["2026-07-01", "vid_a", 10, 20, 30, 60, 1, 1, 1]],
            }
        if dimensions == "day,insightTrafficSourceType":
            return {"columnHeaders": [{"name": "day"}, {"name": "insightTrafficSourceType"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": [["2026-07-01", "YT_SEARCH", 11, 22]]}
        if dimensions == "country":
            return {"columnHeaders": [{"name": "country"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": [["VN", 5, 8], ["US", 9, 10], ["US", 9, 10]]}
        if dimensions == "day,deviceType,operatingSystem":
            return {"columnHeaders": [{"name": "day"}, {"name": "deviceType"}, {"name": "operatingSystem"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": [["2026-07-01", "MOBILE", "ANDROID", 8, 12]]}
        if dimensions == "day,subscribedStatus":
            if self.subscriber_failures_remaining:
                self.subscriber_failures_remaining -= 1
                raise FakeApiError("Internal server error", 500)
            return {"columnHeaders": [{"name": "day"}, {"name": "subscribedStatus"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": [["2026-07-01", "SUBSCRIBED", 6, 11]]}
        if dimensions == "day,insightPlaybackLocationType":
            return {"columnHeaders": [{"name": "day"}, {"name": "insightPlaybackLocationType"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": []}
        if dimensions == "day" and metrics == "likes,comments,shares":
            return {"columnHeaders": [{"name": "day"}, {"name": "likes"}, {"name": "comments"}, {"name": "shares"}], "rows": [["2026-07-01", 5, 2, 1]]}
        if dimensions == "day" and metrics == "cardImpressions,cardTeaserImpressions":
            return {"columnHeaders": [{"name": "day"}, {"name": "cardImpressions"}, {"name": "cardTeaserImpressions"}], "rows": [["2026-07-01", 7, 3]]}
        if dimensions == "day" and metrics == "views,estimatedMinutesWatched" and filters.startswith("playlist=="):
            playlist_id = filters.split("==", 1)[1]
            views = {"PL123": 4, "PL999": 6}[playlist_id]
            return {"columnHeaders": [{"name": "day"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": [["2026-07-01", views, views + 3]]}
        if dimensions == "elapsedVideoTimeRatio":
            video_id = filters.split("==", 1)[1]
            if video_id in self.retention_fail_video_ids:
                raise FakeApiError("Internal server error", 500)
            return {"columnHeaders": [{"name": "elapsedVideoTimeRatio"}, {"name": "audienceWatchRatio"}, {"name": "relativeRetentionPerformance"}], "rows": [[0.1, 0.8, 1.1]]}
        raise AssertionError(f"Unexpected analytics query: {dimensions} / {metrics} / {filters}")

    def _assert_video_filter(self, filters: str) -> None:
        if not filters.startswith("video=="):
            raise AssertionError(f"Expected video filter, got: {filters}")
        ids = filters.split("==", 1)[1].split(",")
        if ids != ["vid_a", "vid_b", "vid_c"]:
            raise AssertionError(f"Expected canonical video IDs, got: {ids}")


def make_channel(root: Path, slug: str = "mist_of_ages") -> None:
    channel_workspace.create_channel_workspace(root, slug, "Mist of Ages", "UC123", "@mistofages")


def write_oauth_client_config(root: Path) -> None:
    (root / "youtube_oauth_client.json").write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://127.0.0.1/callback"],
                }
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def write_expired_channel_token(root: Path, slug: str = "mist_of_ages") -> None:
    token_path = channel_workspace.canonical_channel_paths(root, slug).oauth_token_file
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(
        json.dumps(
            {
                "access_token": "stale-token",
                "refresh_token": "refresh-token",
                "token_type": "Bearer",
                "expires_at": "2026-07-01T00:00:00+00:00",
                "expires_in": 3600,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def make_http_error(url: str, code: int, body: str, message: str = "Bad Request") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, message, hdrs=None, fp=io.BytesIO(body.encode("utf-8")))


class RequestJsonErrorShapeTests(unittest.TestCase):
    def test_request_json_uses_nested_error_message_when_error_is_mapping(self):
        error = make_http_error("https://example.invalid", 400, json.dumps({"error": {"message": "nested error"}}))
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ui_server.AppError) as ctx:
                ui_server.request_json("https://example.invalid")
        self.assertEqual(ctx.exception.message, "nested error")
        self.assertEqual(ctx.exception.status, 400)

    def test_request_json_uses_error_description_for_string_error_payload(self):
        error = make_http_error(
            "https://example.invalid",
            400,
            json.dumps({"error": "invalid_grant", "error_description": "Token expired or revoked"}),
        )
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ui_server.AppError) as ctx:
                ui_server.request_json("https://example.invalid")
        self.assertEqual(ctx.exception.message, "Token expired or revoked")
        self.assertEqual(ctx.exception.status, 400)

    def test_request_json_uses_top_level_string_error_when_description_missing(self):
        error = make_http_error(
            "https://example.invalid",
            400,
            json.dumps({"error": "invalid_request"}),
        )
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ui_server.AppError) as ctx:
                ui_server.request_json("https://example.invalid")
        self.assertEqual(ctx.exception.message, "invalid_request")
        self.assertEqual(ctx.exception.status, 400)

    def test_request_json_handles_json_string_and_plain_text_or_empty_bodies(self):
        cases = [
            ('"oauth failed"', "oauth failed"),
            ("plain text failure", "plain text failure"),
            ("", "HTTP Error 400: Bad Request"),
        ]
        for body, expected in cases:
            error = make_http_error("https://example.invalid", 400, body)
            with self.subTest(body=body or "<empty>"):
                with mock.patch("urllib.request.urlopen", side_effect=error):
                    with self.assertRaises(ui_server.AppError) as ctx:
                        ui_server.request_json("https://example.invalid")
                self.assertEqual(ctx.exception.message, expected)
                self.assertEqual(ctx.exception.status, 400)


class ChannelAnalyticsCollectorTests(unittest.TestCase):
    def test_dynamic_capability_discovery_persists_sanitized_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            snapshot = channel_analytics_collector.discover_channel_analytics_capabilities(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                reporting_api_fetcher=backend.reporting_api_fetcher,
            )
            self.assertEqual(snapshot["channel_slug"], "mist_of_ages")
            self.assertEqual(len(snapshot["capabilities"]), 20)
            stored = json.loads((root / "channels" / "mist_of_ages" / "analytics" / "state" / "capability_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["report_type_counts"]["AVAILABLE"], 20)
            self.assertEqual(stored["generated_report_counts"]["PENDING"], 20)
            self.assertTrue(all(item["availability_status"] == "AVAILABLE" for item in stored["capabilities"]))
            self.assertTrue(all(item["status"] == "AVAILABLE" for item in stored["capabilities"]))
            self.assertNotIn("access_token", json.dumps(stored).lower())

    def test_sync_uses_canonical_video_filters_country_summary_and_existing_jobs_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            self.assertEqual(backend.created_jobs, [])
            self.assertEqual(backend.download_count, 0)
            self.assertEqual(status["capability_counts"]["AVAILABLE"], 20)
            self.assertEqual(status["report_readiness_counts"]["READY"], 0)
            self.assertEqual(status["report_readiness_counts"]["PENDING"], 20)
            self.assertEqual(status["query_group_results"]["country_summary"]["status"], "SUCCESS")
            self.assertEqual(status["query_group_results"]["country_daily_bulk"]["status"], "UNAVAILABLE")
            self.assertEqual(status["query_group_results"]["reach_daily"]["status"], "UNAVAILABLE")
            self.assertEqual(status["query_group_results"]["end_screens_daily"]["status"], "UNAVAILABLE")
            self.assertTrue(any(call.get("filters", "").startswith("video==vid_a,vid_b,vid_c") for call in backend.analytics_calls))
            self.assertFalse(any(call.get("dimensions") == "day,country" for call in backend.analytics_calls))
            self.assertFalse(any(call.get("metrics") == "impressions,impressionsCtr" for call in backend.analytics_calls))
            self.assertFalse(any("endScreenElement" in call.get("metrics", "") for call in backend.analytics_calls))

            video_rows = csv_rows(root / "channels" / "mist_of_ages" / "analytics" / "normalized" / "video_daily.csv")
            self.assertEqual([row["video_id"] for row in video_rows], ["vid_a", "vid_b"])
            country_summary_rows = csv_rows(root / "channels" / "mist_of_ages" / "analytics" / "normalized" / "country_summary.csv")
            self.assertEqual([row["country"] for row in country_summary_rows], ["US", "VN"])
            country_daily_rows = csv_rows(root / "channels" / "mist_of_ages" / "analytics" / "normalized" / "country_daily.csv")
            self.assertEqual(country_daily_rows, [])

            snapshot = json.loads((root / "channels" / "mist_of_ages" / "analytics" / "state" / "capability_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["report_type_counts"]["AVAILABLE"], 20)
            self.assertEqual(snapshot["generated_report_counts"]["READY"], 0)
            self.assertEqual(snapshot["generated_report_counts"]["PENDING"], 20)
            self.assertEqual(snapshot["generated_report_counts"]["ERROR"], 0)

    def test_subscriber_retry_recovers_after_one_server_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            backend.subscriber_failures_remaining = 1
            status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            self.assertEqual(status["query_group_results"]["subscriber_status_daily"]["status"], "SUCCESS")
            attempts = [call for call in backend.analytics_calls if call.get("dimensions") == "day,subscribedStatus"]
            self.assertEqual(len(attempts), 2)

    def test_partial_error_preserves_successful_normalized_data_and_tracks_completed_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            healthy = FakeCollectorBackend()
            first = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=healthy.token_provider,
                data_api_fetcher=healthy.data_api_fetcher,
                analytics_query_fetcher=healthy.analytics_query_fetcher,
                reporting_api_fetcher=healthy.reporting_api_fetcher,
                report_download_fetcher=healthy.report_download_fetcher,
                window_days=30,
            )
            first_video_rows = csv_rows(root / "channels" / "mist_of_ages" / "analytics" / "normalized" / "video_daily.csv")
            degraded = FakeCollectorBackend()
            degraded.video_daily_error = True
            second = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=degraded.token_provider,
                data_api_fetcher=degraded.data_api_fetcher,
                analytics_query_fetcher=degraded.analytics_query_fetcher,
                reporting_api_fetcher=degraded.reporting_api_fetcher,
                report_download_fetcher=degraded.report_download_fetcher,
                window_days=30,
            )
            second_video_rows = csv_rows(root / "channels" / "mist_of_ages" / "analytics" / "normalized" / "video_daily.csv")
            self.assertEqual(second["query_group_results"]["video_daily"]["status"], "ERROR")
            self.assertEqual(second["source_results"]["analytics_queries"]["status"], "PARTIAL")
            self.assertEqual(first_video_rows, second_video_rows)
            self.assertEqual(second["last_successful_sync_at"], first["last_successful_sync_at"])
            self.assertIsNotNone(first["last_completed_sync_at"])
            self.assertIsNotNone(second["last_completed_sync_at"])

    def test_persistent_subscriber_error_keeps_partial_sync_exportable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            backend.subscriber_failures_remaining = 2
            status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            self.assertEqual(status["query_group_results"]["subscriber_status_daily"]["status"], "ERROR")
            self.assertEqual(status["source_results"]["analytics_queries"]["status"], "PARTIAL")
            export = channel_analytics_collector.build_channel_analytics_export(root, "mist_of_ages")
            archive = zipfile.ZipFile(io.BytesIO(export["body_bytes"]))
            self.assertIn("capabilities.json", archive.namelist())

    def test_generated_report_status_ready_when_report_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            backend.reports["job_video_reach_a1"] = [
                {
                    "id": "report_001",
                    "downloadUrl": "https://download.local/report_001",
                    "jobReportTypeId": "video_reach_a1.csv",
                    "startTime": "2026-01-01T00:00:00Z",
                    "endTime": "2026-01-31T00:00:00Z",
                }
            ]
            status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            self.assertEqual(status["report_readiness_counts"]["READY"], 1)
            self.assertEqual(status["report_readiness_counts"]["PENDING"], 19)
            self.assertEqual(backend.download_count, 1)

    def test_generated_report_status_error_when_report_list_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            backend.report_list_errors["job_video_reach_a1"] = ("Internal report list error", 500)
            status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            self.assertEqual(status["report_readiness_counts"]["ERROR"], 1)
            self.assertEqual(status["report_readiness_counts"]["PENDING"], 19)
            snapshot = json.loads((root / "channels" / "mist_of_ages" / "analytics" / "state" / "capability_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["generated_report_counts"]["ERROR"], 1)

    def test_snapshot_state_and_export_counts_stay_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            snapshot = json.loads((root / "channels" / "mist_of_ages" / "analytics" / "state" / "capability_snapshot.json").read_text(encoding="utf-8"))
            export = channel_analytics_collector.build_channel_analytics_export(root, "mist_of_ages")
            archive = zipfile.ZipFile(io.BytesIO(export["body_bytes"]))
            capabilities_payload = json.loads(archive.read("capabilities.json").decode("utf-8"))
            self.assertEqual(status["capability_counts"], snapshot["report_type_counts"])
            self.assertEqual(status["capability_counts"], capabilities_payload["report_type_counts"])
            self.assertEqual(status["report_readiness_counts"], snapshot["generated_report_counts"])
            self.assertEqual(status["report_readiness_counts"], capabilities_payload["generated_report_counts"])

    def test_retention_and_playlists_are_scoped_per_entity_and_keep_partial_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            backend.retention_fail_video_ids = {"vid_c"}
            status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            retention_rows = csv_rows(root / "channels" / "mist_of_ages" / "analytics" / "normalized" / "retention.csv")
            self.assertEqual([row["video_id"] for row in retention_rows], ["vid_a", "vid_b"])
            playlist_rows = csv_rows(root / "channels" / "mist_of_ages" / "analytics" / "normalized" / "playlists_daily.csv")
            self.assertEqual([row["playlist_id"] for row in playlist_rows], ["PL123", "PL999"])
            self.assertEqual(status["query_group_results"]["retention"]["status"], "SUCCESS")
            retention_calls = [call for call in backend.analytics_calls if call.get("dimensions") == "elapsedVideoTimeRatio"]
            self.assertEqual(sorted(call["filters"] for call in retention_calls), ["video==vid_a", "video==vid_b", "video==vid_c"])
            playlist_calls = [call for call in backend.analytics_calls if call.get("filters", "").startswith("playlist==")]
            self.assertEqual(sorted(call["filters"] for call in playlist_calls), ["playlist==PL123", "playlist==PL999"])

    def test_optional_metrics_remain_nonfatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            self.assertEqual(status["query_group_results"]["monetary_daily"]["status"], "UNAUTHORIZED")
            self.assertEqual(status["query_group_results"]["cards_daily"]["status"], "UNSUPPORTED")
            self.assertEqual(status["source_results"]["analytics_queries"]["status"], "SUCCESS")

    def test_export_zip_contents_manifest_hashes_and_no_secret_or_absolute_path_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            export = channel_analytics_collector.build_channel_analytics_export(root, "mist_of_ages")
            archive = zipfile.ZipFile(io.BytesIO(export["body_bytes"]))
            names = sorted(archive.namelist())
            self.assertIn("country_summary.csv", names)
            self.assertIn("cards_daily.csv", names)
            self.assertIn("end_screens_daily.csv", names)
            self.assertNotIn("cards_end_screens_daily.csv", names)
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            for name in names:
                if name == "manifest.json":
                    self.assertNotIn(name, manifest["file_hashes"])
                    continue
                self.assertEqual(manifest["file_hashes"][name], hashlib.sha256(archive.read(name)).hexdigest().upper())
            dumped = archive.read("collector_status.json").decode("utf-8")
            self.assertNotIn("access_token", dumped.lower())
            self.assertNotIn(str(root).lower(), dumped.lower())

    def test_sync_does_not_mutate_existing_workflow_project_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            project_workflow = root / "channels" / "mist_of_ages" / "projects" / "pilot" / "workflow"
            project_workflow.mkdir(parents=True, exist_ok=True)
            (project_workflow / "workflow_state.json").write_text('{"state_revision":14}\n', encoding="utf-8")
            before = tree_hashes(root / "channels" / "mist_of_ages" / "projects")
            backend = FakeCollectorBackend()
            channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            after = tree_hashes(root / "channels" / "mist_of_ages" / "projects")
            self.assertEqual(before, after)

    def test_route_export_returns_zip_for_selected_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()
            context = ui_server.build_app_context(root=root)
            context["token_provider"] = backend.token_provider
            context["data_api_fetcher"] = backend.data_api_fetcher
            context["analytics_query_api_fetcher"] = backend.analytics_query_fetcher
            context["reporting_api_fetcher"] = backend.reporting_api_fetcher
            context["report_download_fetcher"] = backend.report_download_fetcher
            ui_server.dispatch_v2_request("POST", "/api/v2/channels/mist_of_ages/analytics/sync", payload={"window_days": 30}, context=context)
            status, data = ui_server.dispatch_v2_request("GET", "/api/v2/channels/mist_of_ages/analytics/export", context=context)
            self.assertEqual(status, 200)
            archive = zipfile.ZipFile(io.BytesIO(data["__binary__"]))
            self.assertIn("country_summary.csv", archive.namelist())
            self.assertIn("end_screens_daily.csv", archive.namelist())

    def test_sync_route_handles_string_oauth_error_without_attribute_error_and_preserves_existing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            write_oauth_client_config(root)
            write_expired_channel_token(root)
            backend = FakeCollectorBackend()

            seeded_status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )
            baseline_completed = seeded_status["last_completed_sync_at"]
            baseline_successful = seeded_status["last_successful_sync_at"]
            normalized_before = tree_hashes(root / "channels" / "mist_of_ages" / "analytics" / "normalized")

            data_api_calls = 0
            analytics_calls = 0
            reporting_calls = 0
            download_calls = 0

            def counting_data_api_fetcher(**kwargs):
                nonlocal data_api_calls
                data_api_calls += 1
                return backend.data_api_fetcher(**kwargs)

            def counting_analytics_query_fetcher(**kwargs):
                nonlocal analytics_calls
                analytics_calls += 1
                return backend.analytics_query_fetcher(**kwargs)

            def counting_reporting_api_fetcher(**kwargs):
                nonlocal reporting_calls
                reporting_calls += 1
                return backend.reporting_api_fetcher(**kwargs)

            def counting_report_download_fetcher(**kwargs):
                nonlocal download_calls
                download_calls += 1
                return backend.report_download_fetcher(**kwargs)

            context = ui_server.build_app_context(root=root)
            context["data_api_fetcher"] = counting_data_api_fetcher
            context["analytics_query_api_fetcher"] = counting_analytics_query_fetcher
            context["reporting_api_fetcher"] = counting_reporting_api_fetcher
            context["report_download_fetcher"] = counting_report_download_fetcher

            oauth_error = make_http_error(
                "https://oauth2.googleapis.com/token",
                400,
                json.dumps({"error": "invalid_grant", "error_description": "Token expired or revoked"}),
            )

            with mock.patch("urllib.request.urlopen", side_effect=oauth_error):
                with self.assertRaises(ui_server.V2Error) as ctx:
                    ui_server.dispatch_v2_request(
                        "POST",
                        "/api/v2/channels/mist_of_ages/analytics/sync",
                        payload={"window_days": 30},
                        context=context,
                    )

            self.assertEqual(ctx.exception.code, "OAUTH_RECONNECT_REQUIRED")
            self.assertEqual(ctx.exception.status, 409)
            self.assertNotIn("AttributeError", ctx.exception.message)
            self.assertIn("Token expired or revoked", ctx.exception.message)
            self.assertEqual(data_api_calls, 0)
            self.assertEqual(analytics_calls, 0)
            self.assertEqual(reporting_calls, 0)
            self.assertEqual(download_calls, 0)

            state = json.loads((root / "channels" / "mist_of_ages" / "analytics" / "state" / "collector_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["last_completed_sync_at"], baseline_completed)
            self.assertEqual(state["last_successful_sync_at"], baseline_successful)
            self.assertEqual(state["source_results"]["token"]["status"], "UNAUTHORIZED")
            self.assertEqual(state["source_results"]["token"]["message"], "Token expired or revoked")
            self.assertEqual(state["errors"], ["Token expired or revoked"])
            normalized_after = tree_hashes(root / "channels" / "mist_of_ages" / "analytics" / "normalized")
            self.assertEqual(normalized_before, normalized_after)
            self.assertEqual(backend.created_jobs, [])

    def test_successful_sync_overwrites_stale_token_unauthorized_state_and_export_reflects_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_channel(root)
            backend = FakeCollectorBackend()

            stale_state = {
                "schema_version": channel_analytics_collector.SCHEMA_VERSION,
                "channel_slug": "mist_of_ages",
                "last_attempt_at": "2026-07-10T02:15:23+00:00",
                "last_completed_sync_at": "2026-07-04T15:31:59+00:00",
                "last_successful_sync_at": None,
                "collection_window": {},
                "source_results": {
                    "token": {
                        "status": "UNAUTHORIZED",
                        "checked_at": "2026-07-10T02:15:23+00:00",
                        "message": "Token expired or revoked.",
                    }
                },
                "query_group_results": {},
                "report_jobs": {},
                "ingested_reports": {},
                "row_counts": {},
                "report_type_counts": {"AVAILABLE": 0, "PENDING": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "UNAVAILABLE": 0, "ERROR": 0},
                "generated_report_counts": {"READY": 0, "PENDING": 0, "UNAVAILABLE": 0, "UNAUTHORIZED": 0, "UNSUPPORTED": 0, "ERROR": 0},
                "errors": ["Token expired or revoked."],
            }
            state_path = root / "channels" / "mist_of_ages" / "analytics" / "state" / "collector_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(stale_state, indent=2) + "\n", encoding="utf-8")

            status = channel_analytics_collector.sync_channel_analytics(
                root,
                "mist_of_ages",
                token_provider=backend.token_provider,
                data_api_fetcher=backend.data_api_fetcher,
                analytics_query_fetcher=backend.analytics_query_fetcher,
                reporting_api_fetcher=backend.reporting_api_fetcher,
                report_download_fetcher=backend.report_download_fetcher,
                window_days=30,
            )

            self.assertEqual(status["source_results"]["token"]["status"], "SUCCESS")
            self.assertEqual(status["source_results"]["token"]["checked_at"], status["last_completed_sync_at"])
            self.assertNotIn("message", status["source_results"]["token"])
            self.assertEqual(status["last_completed_sync_at"], status["last_attempt_at"])

            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["source_results"]["token"]["status"], "SUCCESS")
            self.assertEqual(persisted["source_results"]["token"]["checked_at"], persisted["last_attempt_at"])
            self.assertNotIn("message", persisted["source_results"]["token"])

            export = channel_analytics_collector.build_channel_analytics_export(root, "mist_of_ages")
            archive = zipfile.ZipFile(io.BytesIO(export["body_bytes"]))
            collector_status = json.loads(archive.read("collector_status.json").decode("utf-8"))
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            self.assertEqual(collector_status["source_results"]["token"]["status"], "SUCCESS")
            self.assertNotIn("message", collector_status["source_results"]["token"])
            self.assertEqual(manifest["source_statuses"]["token"]["status"], "SUCCESS")
            self.assertNotIn("message", manifest["source_statuses"]["token"])


if __name__ == "__main__":
    unittest.main()
