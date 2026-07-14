import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import youtube_competitor_probe, youtube_research_core, youtube_topic_opportunity_scan


def make_video(
    video_id: str,
    *,
    title: str,
    channel_id: str,
    channel_title: str,
    published_at: str,
    duration: str,
    views: str,
    likes: str = "0",
    comments: str = "0",
) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "channelId": channel_id,
            "channelTitle": channel_title,
            "publishedAt": published_at,
        },
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": views, "likeCount": likes, "commentCount": comments},
    }


class FakeFetch:
    def __init__(self):
        self.calls: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        self.responses: dict[tuple[str, tuple[tuple[str, str], ...]], dict] = {}
        self.fail_once_keys: set[tuple[str, tuple[tuple[str, str], ...]]] = set()

    def add(self, resource: str, params: dict[str, object], payload: dict) -> None:
        key = (resource, tuple(sorted((name, str(value)) for name, value in params.items())))
        self.responses[key] = payload

    def fail_once(self, resource: str, params: dict[str, object]) -> None:
        key = (resource, tuple(sorted((name, str(value)) for name, value in params.items())))
        self.fail_once_keys.add(key)

    def __call__(self, *, resource: str, params: dict[str, object], api_key: str, timeout: int = 30) -> dict:
        key = (resource, tuple(sorted((name, str(value)) for name, value in params.items())))
        self.calls.append(key)
        if key in self.fail_once_keys:
            self.fail_once_keys.remove(key)
            raise urllib.error.HTTPError(
                url=f"https://example.test/{resource}",
                code=500,
                msg="boom",
                hdrs=None,
                fp=None,
            )
        if key not in self.responses:
            raise AssertionError(f"Unexpected API call: {resource} {dict(params)}")
        return self.responses[key]


class YouTubeResearchCoreTests(unittest.TestCase):
    def test_duration_parsing(self):
        self.assertEqual(youtube_research_core.parse_iso8601_duration("PT2M30S"), 150)
        self.assertEqual(youtube_research_core.parse_iso8601_duration("PT10M"), 600)
        self.assertEqual(youtube_research_core.parse_iso8601_duration("P1DT1H"), 90000)

    def test_duration_band_boundaries(self):
        self.assertEqual(youtube_research_core.classify_duration_band(179), "SHORT")
        self.assertEqual(youtube_research_core.classify_duration_band(180), "LONG_3_10")
        self.assertEqual(youtube_research_core.classify_duration_band(599), "LONG_3_10")
        self.assertEqual(youtube_research_core.classify_duration_band(600), "LONG_10_30")
        self.assertEqual(youtube_research_core.classify_duration_band(1799), "LONG_10_30")
        self.assertEqual(youtube_research_core.classify_duration_band(1800), "LONG_30_PLUS")

    def test_same_band_baseline_filtering(self):
        now = youtube_research_core.parse_datetime("2026-07-14T00:00:00Z")
        self.assertTrue(
            youtube_research_core.baseline_is_eligible(
                "target",
                "LONG_10_30",
                {"video_id": "other", "duration_band": "LONG_10_30", "age_hours": 72},
                baseline_min_age_hours=48,
                now=now,
            )
        )
        self.assertFalse(
            youtube_research_core.baseline_is_eligible(
                "target",
                "LONG_10_30",
                {"video_id": "other", "duration_band": "LONG_3_10", "age_hours": 72},
                baseline_min_age_hours=48,
                now=now,
            )
        )

    def test_minimum_baseline_age(self):
        now = youtube_research_core.parse_datetime("2026-07-14T00:00:00Z")
        self.assertFalse(
            youtube_research_core.baseline_is_eligible(
                "target",
                "LONG_3_10",
                {"video_id": "other", "duration_band": "LONG_3_10", "age_hours": 24},
                baseline_min_age_hours=48,
                now=now,
            )
        )

    def test_shorts_excluded_from_long_target_baseline(self):
        now = youtube_research_core.parse_datetime("2026-07-14T00:00:00Z")
        self.assertFalse(
            youtube_research_core.baseline_is_eligible(
                "target",
                "LONG_3_10",
                {"video_id": "short-1", "duration_band": "SHORT", "age_hours": 100},
                baseline_min_age_hours=48,
                now=now,
            )
        )

    def test_zero_median_returns_null_outlier(self):
        self.assertIsNone(youtube_research_core.outlier_ratio(100, None))
        self.assertIsNone(youtube_research_core.outlier_ratio(100, 0))

    def test_confidence_boundaries(self):
        self.assertEqual(youtube_research_core.baseline_confidence_label(0), "LOW")
        self.assertEqual(youtube_research_core.baseline_confidence_label(3), "LOW")
        self.assertEqual(youtube_research_core.baseline_confidence_label(4), "MEDIUM")
        self.assertEqual(youtube_research_core.baseline_confidence_label(7), "MEDIUM")
        self.assertEqual(youtube_research_core.baseline_confidence_label(8), "HIGH")

    def test_hidden_subscriber_behavior(self):
        now = youtube_research_core.parse_datetime("2026-07-14T00:00:00Z")
        normalized = youtube_research_core.normalize_video_metrics(
            make_video(
                "vid_1",
                title="Video",
                channel_id="chan_1",
                channel_title="Channel",
                published_at="2026-07-10T00:00:00Z",
                duration="PT8M",
                views="1000",
            ),
            channel_stats={"hiddenSubscriberCount": True, "subscriberCount": "500"},
            now=now,
        )
        self.assertIsNone(normalized["subscribers"])
        self.assertIsNone(normalized["views_per_subscriber"])

    def test_plan_validation_and_duplicate_query_rejection(self):
        with self.assertRaises(youtube_research_core.YouTubeResearchError):
            youtube_research_core.validate_topic_scan_plan(
                {
                    "schema_version": 1,
                    "cluster_id": "roman_republic",
                    "label": "Roman Republic",
                    "published_days": 365,
                    "minimum_duration_seconds": 300,
                    "maximum_duration_seconds": 720,
                    "baseline_recent_count": 20,
                    "baseline_min_age_hours": 48,
                    "groups": [
                        {
                            "topic_group_id": "group_a",
                            "label": "Group A",
                            "gateway_entity": "Caesar",
                            "queries": ["Caesar Rubicon", "caesar   rubicon"],
                        }
                    ],
                }
            )

    def test_cross_channel_status_boundaries(self):
        self.assertEqual(youtube_research_core.cross_channel_status(1), "SINGLE_CHANNEL")
        self.assertEqual(youtube_research_core.cross_channel_status(2), "TWO_CHANNELS")
        self.assertEqual(youtube_research_core.cross_channel_status(3), "MULTI_CHANNEL")

    def test_cache_hit_avoids_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch = FakeFetch()
            params = {"part": "snippet", "q": "rome", "type": "video", "order": "relevance", "maxResults": 5}
            fetch.add("search", params, {"items": []})
            client = youtube_research_core.YouTubeResearchClient("secret-key", cache_dir=Path(tmp), fetcher=fetch)
            client.get("search", **params)
            client.get("search", **params)
            self.assertEqual(len(fetch.calls), 1)
            self.assertEqual(client.stats.cache_hit_count, 1)

    def test_refresh_bypasses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch = FakeFetch()
            params = {"part": "snippet", "q": "rome", "type": "video", "order": "relevance", "maxResults": 5}
            fetch.add("search", params, {"items": []})
            client = youtube_research_core.YouTubeResearchClient("secret-key", cache_dir=Path(tmp), fetcher=fetch)
            client.get("search", **params)
            refreshed = youtube_research_core.YouTubeResearchClient("secret-key", cache_dir=Path(tmp), fetcher=fetch, refresh=True)
            refreshed.get("search", **params)
            self.assertEqual(len(fetch.calls), 2)

    def test_api_key_redaction(self):
        message = youtube_research_core.sanitize_error_message(
            "Bad request https://example.test?key=abc123 and abc123 failed",
            "abc123",
        )
        self.assertNotIn("abc123", message)
        self.assertIn("<redacted-api-key>", message)

    def test_bounded_retry_on_transient_http_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch = FakeFetch()
            params = {"part": "snippet", "q": "rome", "type": "video", "order": "relevance", "maxResults": 5}
            fetch.add("search", params, {"items": []})
            fetch.fail_once("search", params)
            sleeps: list[float] = []
            client = youtube_research_core.YouTubeResearchClient(
                "secret-key",
                cache_dir=Path(tmp),
                fetcher=fetch,
                sleeper=sleeps.append,
            )
            payload = client.get("search", **params)
            self.assertEqual(payload, {"items": []})
            self.assertEqual(len(fetch.calls), 2)
            self.assertEqual(sleeps, [0.5])


class TopicOpportunityScanTests(unittest.TestCase):
    def build_scan_fetch(self) -> FakeFetch:
        fetch = FakeFetch()
        search_common = {"part": "snippet", "type": "video", "order": "relevance", "maxResults": 8, "publishedAfter": "2025-07-14T00:00:00Z"}
        fetch.add(
            "search",
            {**search_common, "q": "Caesar crossed the Rubicon history documentary"},
            {
                "items": [
                    {"id": {"videoId": "video_a"}, "snippet": {"title": "A", "channelTitle": "Channel A"}},
                    {"id": {"videoId": "video_b"}, "snippet": {"title": "B", "channelTitle": "Channel B"}},
                ]
            },
        )
        fetch.add(
            "search",
            {**search_common, "q": "river Caesar was forbidden to cross history"},
            {
                "items": [
                    {"id": {"videoId": "video_a"}, "snippet": {"title": "A", "channelTitle": "Channel A"}},
                    {"id": {"videoId": "video_c"}, "snippet": {"title": "C", "channelTitle": "Channel C"}},
                ]
            },
        )
        fetch.add(
            "videos",
            {
                "part": "snippet,contentDetails,statistics",
                "id": "video_a,video_b,video_c",
                "maxResults": 3,
            },
            {
                "items": [
                    make_video("video_a", title="Crossing the Rubicon", channel_id="chan_a", channel_title="Channel A", published_at="2026-07-01T00:00:00Z", duration="PT8M", views="9000", likes="9", comments="2"),
                    make_video("video_b", title="Rome in Crisis", channel_id="chan_b", channel_title="Channel B", published_at="2026-07-02T00:00:00Z", duration="PT9M", views="8500", likes="8", comments="1"),
                    make_video("video_c", title="Caesar vs Senate", channel_id="chan_c", channel_title="Channel C", published_at="2026-07-03T00:00:00Z", duration="PT7M", views="4000", likes="7", comments="1"),
                ]
            },
        )
        fetch.add(
            "channels",
            {"part": "snippet,contentDetails,statistics", "id": "chan_a,chan_b,chan_c", "maxResults": 3},
            {
                "items": [
                    {"id": "chan_a", "snippet": {"title": "Channel A"}, "contentDetails": {"relatedPlaylists": {"uploads": "upl_a"}}, "statistics": {"subscriberCount": "1000", "hiddenSubscriberCount": False}},
                    {"id": "chan_b", "snippet": {"title": "Channel B"}, "contentDetails": {"relatedPlaylists": {"uploads": "upl_b"}}, "statistics": {"subscriberCount": "1200", "hiddenSubscriberCount": False}},
                    {"id": "chan_c", "snippet": {"title": "Channel C"}, "contentDetails": {"relatedPlaylists": {"uploads": "upl_c"}}, "statistics": {"subscriberCount": "1300", "hiddenSubscriberCount": False}},
                ]
            },
        )
        for playlist_id, ids in {"upl_a": ["a_r1", "a_r2"], "upl_b": ["b_r1", "b_r2"], "upl_c": ["c_r1", "c_r2"]}.items():
            fetch.add(
                "playlistItems",
                {"part": "contentDetails,snippet", "playlistId": playlist_id, "maxResults": 20},
                {"items": [{"contentDetails": {"videoId": item_id}} for item_id in ids]},
            )
        recent_batch_ids = "a_r1,a_r2,b_r1,b_r2,c_r1,c_r2"
        fetch.add(
            "videos",
            {"part": "snippet,contentDetails,statistics", "id": recent_batch_ids, "maxResults": 6},
            {
                "items": [
                    make_video("a_r1", title="A1", channel_id="chan_a", channel_title="Channel A", published_at="2026-06-20T00:00:00Z", duration="PT8M", views="2000"),
                    make_video("a_r2", title="A2", channel_id="chan_a", channel_title="Channel A", published_at="2026-06-19T00:00:00Z", duration="PT8M", views="2200"),
                    make_video("b_r1", title="B1", channel_id="chan_b", channel_title="Channel B", published_at="2026-06-20T00:00:00Z", duration="PT9M", views="1800"),
                    make_video("b_r2", title="B2", channel_id="chan_b", channel_title="Channel B", published_at="2026-06-18T00:00:00Z", duration="PT9M", views="2100"),
                    make_video("c_r1", title="C1", channel_id="chan_c", channel_title="Channel C", published_at="2026-06-21T00:00:00Z", duration="PT7M", views="1400"),
                    make_video("c_r2", title="C2", channel_id="chan_c", channel_title="Channel C", published_at="2026-06-22T00:00:00Z", duration="PT7M", views="1500"),
                ]
            },
        )
        return fetch

    def write_plan(self, root: Path) -> Path:
        plan = {
            "schema_version": 1,
            "cluster_id": "roman_republic_collapse",
            "label": "Roman Republic collapse",
            "published_days": 365,
            "minimum_duration_seconds": 300,
            "maximum_duration_seconds": 720,
            "baseline_recent_count": 20,
            "baseline_min_age_hours": 48,
            "groups": [
                {
                    "topic_group_id": "caesar_rubicon",
                    "label": "Caesar crosses the Rubicon",
                    "gateway_entity": "Julius Caesar",
                    "queries": [
                        "Caesar crossed the Rubicon history documentary",
                        "river Caesar was forbidden to cross history",
                    ],
                }
            ],
        }
        path = root / "plan.json"
        path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return path

    def test_multi_query_video_dedup_with_preserved_query_hits(self):
        fetch = self.build_scan_fetch()
        fixed_now = youtube_research_core.parse_datetime("2026-07-14T00:00:00Z")
        with tempfile.TemporaryDirectory() as tmp:
            client = youtube_research_core.YouTubeResearchClient("secret", cache_dir=Path(tmp) / "cache", fetcher=fetch)
            with mock.patch.object(
            youtube_topic_opportunity_scan.core, "utc_now", return_value=fixed_now
            ), mock.patch.object(
                youtube_topic_opportunity_scan.core, "YouTubeResearchClient", return_value=client
            ):
                root = Path(tmp)
                args = youtube_topic_opportunity_scan._parse_args(
                    ["--plan", str(self.write_plan(root)), "--output-dir", str(root / "out")]
                )
                result = youtube_topic_opportunity_scan.run_topic_scan(args)
                rows = result["candidate_rows"]
                video_a_rows = [row for row in rows if row["video_id"] == "video_a"]
                self.assertEqual(len(video_a_rows), 1)
                self.assertIn("Caesar crossed the Rubicon history documentary", video_a_rows[0]["queries"])
                self.assertIn("river Caesar was forbidden to cross history", video_a_rows[0]["queries"])

    def test_multi_channel_topic_aggregation(self):
        fetch = self.build_scan_fetch()
        with tempfile.TemporaryDirectory() as tmp:
            client = youtube_research_core.YouTubeResearchClient("secret", cache_dir=Path(tmp) / "cache", fetcher=fetch)
            with mock.patch.object(
                youtube_topic_opportunity_scan.core, "utc_now", return_value=youtube_research_core.parse_datetime("2026-07-14T00:00:00Z")
            ), mock.patch.object(
                youtube_topic_opportunity_scan.core, "YouTubeResearchClient", return_value=client
            ):
                root = Path(tmp)
                args = youtube_topic_opportunity_scan._parse_args(
                    ["--plan", str(self.write_plan(root)), "--output-dir", str(root / "out")]
                )
                result = youtube_topic_opportunity_scan.run_topic_scan(args)
                group = result["group_rows"][0]
                self.assertEqual(group["unique_channel_count"], 3)
                self.assertEqual(group["cross_channel_status"], "MULTI_CHANNEL")
                self.assertEqual(group["verdict"], "HOLD")
                self.assertIn("Low-confidence evidence", group["reasons"][0])

    def test_deterministic_output_ordering(self):
        fetch = self.build_scan_fetch()
        fixed_now = youtube_research_core.parse_datetime("2026-07-14T00:00:00Z")
        with tempfile.TemporaryDirectory() as tmp:
            client = youtube_research_core.YouTubeResearchClient("secret", cache_dir=Path(tmp) / "cache", fetcher=fetch)
            with mock.patch.object(
                youtube_topic_opportunity_scan.core, "utc_now", return_value=fixed_now
            ), mock.patch.object(
                youtube_topic_opportunity_scan.core, "YouTubeResearchClient", return_value=client
            ):
                root = Path(tmp)
                args = youtube_topic_opportunity_scan._parse_args(
                    ["--plan", str(self.write_plan(root)), "--output-dir", str(root / "out")]
                )
                youtube_topic_opportunity_scan.run_topic_scan(args)
                first = (root / "out" / "candidate_videos.json").read_text(encoding="utf-8")
                youtube_topic_opportunity_scan.run_topic_scan(args)
                second = (root / "out" / "candidate_videos.json").read_text(encoding="utf-8")
                self.assertEqual(first, second)

    def test_legacy_direct_query_mode(self):
        fetch = self.build_scan_fetch()
        with tempfile.TemporaryDirectory() as tmp:
            client = youtube_research_core.YouTubeResearchClient("secret", cache_dir=Path(tmp) / "cache", fetcher=fetch)
            with mock.patch.object(
                youtube_topic_opportunity_scan.core, "YouTubeResearchClient", return_value=client
            ), mock.patch.object(
                youtube_topic_opportunity_scan.core,
                "utc_now",
                return_value=youtube_research_core.parse_datetime("2026-07-14T00:00:00Z"),
            ):
                args = youtube_topic_opportunity_scan._parse_args(
                    [
                        "--query",
                        "Caesar crossed the Rubicon history documentary",
                        "--query",
                        "river Caesar was forbidden to cross history",
                        "--output-dir",
                        str(Path(tmp) / "out"),
                    ]
                )
                result = youtube_topic_opportunity_scan.run_topic_scan(args)
                self.assertEqual(result["plan"]["groups"][0]["topic_group_id"], "direct_query_group")

    def test_empty_results(self):
        fetch = FakeFetch()
        fetch.add(
            "search",
            {
                "part": "snippet",
                "q": "No results",
                "type": "video",
                "order": "relevance",
                "maxResults": 8,
                "publishedAfter": "2025-07-14T00:00:00Z",
            },
            {"items": []},
        )
        fixed_now = youtube_research_core.parse_datetime("2026-07-14T00:00:00Z")
        with tempfile.TemporaryDirectory() as tmp:
            client = youtube_research_core.YouTubeResearchClient("secret", cache_dir=Path(tmp) / "cache", fetcher=fetch)
            with mock.patch.object(
                youtube_topic_opportunity_scan.core, "utc_now", return_value=fixed_now
            ), mock.patch.object(
                youtube_topic_opportunity_scan.core, "YouTubeResearchClient", return_value=client
            ):
                root = Path(tmp)
                args = youtube_topic_opportunity_scan._parse_args(
                    ["--query", "No results", "--output-dir", str(root / "out")]
                )
                result = youtube_topic_opportunity_scan.run_topic_scan(args)
                self.assertEqual(result["candidate_rows"], [])
                self.assertEqual(result["group_rows"][0]["verdict"], "REJECT")

    def test_no_live_http_in_tests(self):
        class FailFetcher:
            def __call__(self, **kwargs):
                raise AssertionError("Live HTTP is not allowed in tests.")

        client = youtube_research_core.YouTubeResearchClient("secret", fetcher=FailFetcher())
        with self.assertRaises(AssertionError):
            client.fetcher(resource="search", params={}, api_key="secret", timeout=30)


class CompetitorProbeTests(unittest.TestCase):
    def build_probe_fetch(self) -> FakeFetch:
        fetch = FakeFetch()
        fetch.add(
            "search",
            {"part": "snippet", "q": "Roman rival", "type": "video", "maxResults": 5, "order": "relevance"},
            {"items": [{"id": {"videoId": "target_vid"}, "snippet": {"title": "Target", "channelTitle": "History Rival"}}]},
        )
        fetch.add(
            "videos",
            {"part": "snippet,contentDetails,statistics", "id": "target_vid", "maxResults": 1},
            {"items": [make_video("target_vid", title="Target", channel_id="chan_a", channel_title="History Rival", published_at="2026-07-01T00:00:00Z", duration="PT8M", views="9000")]},
        )
        fetch.add(
            "channels",
            {"part": "snippet,contentDetails,statistics", "id": "chan_a", "maxResults": 1},
            {"items": [{"id": "chan_a", "snippet": {"title": "History Rival", "publishedAt": "2020-01-01T00:00:00Z"}, "contentDetails": {"relatedPlaylists": {"uploads": "upl_a"}}, "statistics": {"subscriberCount": "1000", "hiddenSubscriberCount": False, "viewCount": "9999", "videoCount": "20"}}]},
        )
        fetch.add(
            "playlistItems",
            {"part": "contentDetails,snippet", "playlistId": "upl_a", "maxResults": 12},
            {"items": [{"contentDetails": {"videoId": "target_vid"}}, {"contentDetails": {"videoId": "base_1"}}, {"contentDetails": {"videoId": "base_2"}}, {"contentDetails": {"videoId": "short_1"}}]},
        )
        fetch.add(
            "videos",
            {"part": "snippet,contentDetails,statistics", "id": "target_vid,base_1,base_2,short_1", "maxResults": 4},
            {
                "items": [
                    make_video("target_vid", title="Target", channel_id="chan_a", channel_title="History Rival", published_at="2026-07-01T00:00:00Z", duration="PT8M", views="9000"),
                    make_video("base_1", title="Base 1", channel_id="chan_a", channel_title="History Rival", published_at="2026-06-20T00:00:00Z", duration="PT8M", views="2000"),
                    make_video("base_2", title="Base 2", channel_id="chan_a", channel_title="History Rival", published_at="2026-06-18T00:00:00Z", duration="PT8M", views="2200"),
                    make_video("short_1", title="Short 1", channel_id="chan_a", channel_title="History Rival", published_at="2026-06-18T00:00:00Z", duration="PT59S", views="100000"),
                ]
            },
        )
        return fetch

    def test_competitor_probe_shared_core_behavior(self):
        fetch = self.build_probe_fetch()
        fixed_now = youtube_research_core.parse_datetime("2026-07-14T00:00:00Z")
        with tempfile.TemporaryDirectory() as tmp:
            client = youtube_research_core.YouTubeResearchClient("secret", cache_dir=Path(tmp) / "cache", fetcher=fetch)
            with mock.patch.object(
                youtube_competitor_probe.core, "utc_now", return_value=fixed_now
            ), mock.patch.object(
                youtube_competitor_probe.core, "YouTubeResearchClient", return_value=client
            ):
                args = youtube_competitor_probe._parse_args(["--query", "Roman rival", "--output-dir", str(Path(tmp) / "out")])
                result = youtube_competitor_probe.run_competitor_probe(args)
                baseline = result["summary"]["baseline"]
                self.assertEqual(baseline["duration_band"], "LONG_3_10")
                self.assertEqual(baseline["baseline_count"], 2)
                self.assertEqual(baseline["baseline_confidence"], "LOW")
                self.assertIsNotNone(result["summary"]["target_video"]["views_outlier_score"])
                self.assertIsNotNone(result["summary"]["target_video"]["velocity_outlier_score"])


if __name__ == "__main__":
    unittest.main()
