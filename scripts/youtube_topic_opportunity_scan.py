#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import youtube_research_core as core


CANDIDATE_VIDEO_COLUMNS = [
    "video_id",
    "topic_group_id",
    "topic_group_label",
    "queries",
    "query_hit_count",
    "best_rank",
    "title",
    "channel",
    "channel_id",
    "published_at",
    "age_days",
    "duration",
    "duration_seconds",
    "duration_band",
    "views",
    "lifetime_views_per_day",
    "subscribers",
    "views_per_subscriber",
    "baseline_count",
    "baseline_confidence",
    "median_baseline_views",
    "median_baseline_lifetime_views_per_day",
    "views_outlier_score",
    "velocity_outlier_score",
    "likes",
    "comments",
    "url",
]

TOPIC_GROUP_COLUMNS = [
    "topic_group_id",
    "label",
    "gateway_entity",
    "candidate_video_count",
    "unique_channel_count",
    "qualifying_outlier_video_count",
    "qualifying_outlier_channel_count",
    "median_velocity_outlier",
    "max_velocity_outlier",
    "median_lifetime_views_per_day",
    "recent_competitor_count",
    "cross_channel_status",
    "quality_label",
    "baseline_confidence",
    "verdict",
    "reasons",
]


def _load_plan(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if args.plan:
        plan_path = Path(args.plan)
        try:
            raw = json.loads(plan_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise core.YouTubeResearchError("PLAN_NOT_FOUND", f"Plan file not found: {plan_path}.", 404) from exc
        except json.JSONDecodeError as exc:
            raise core.YouTubeResearchError("INVALID_PLAN", "Plan file is not valid JSON.") from exc
        plan = core.validate_topic_scan_plan(raw)
        return plan, core.sha256_text(core.stable_json_dumps(plan))

    plan = core.synthesize_plan_from_queries(
        args.query or [],
        published_days=args.published_days,
        minimum_duration_seconds=args.minimum_duration_seconds,
        maximum_duration_seconds=args.maximum_duration_seconds,
        baseline_recent_count=args.baseline_recent_count,
        baseline_min_age_hours=args.baseline_min_age_hours,
    )
    return plan, core.sha256_text(core.stable_json_dumps(plan))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic YouTube topic opportunity scanner.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", help="Path to a structured topic scan plan JSON file.")
    source.add_argument("--query", action="append", help="Direct query mode for backward-compatible scans.")
    parser.add_argument("--results-per-query", type=int, default=8)
    parser.add_argument("--published-days", type=int, default=core.DEFAULT_PUBLISHED_DAYS)
    parser.add_argument("--minimum-duration-seconds", type=int, default=300)
    parser.add_argument("--maximum-duration-seconds", type=int, default=720)
    parser.add_argument("--baseline-recent-count", type=int, default=core.DEFAULT_BASELINE_RECENT_COUNT)
    parser.add_argument("--baseline-min-age-hours", type=int, default=core.DEFAULT_BASELINE_MIN_AGE_HOURS)
    parser.add_argument("--output-dir", default="topic_opportunity_scan")
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--api-key")
    return parser.parse_args(argv)


def _query_video_hits(
    client: core.YouTubeResearchClient,
    *,
    query: str,
    published_after: str,
    results_per_query: int,
) -> list[dict[str, Any]]:
    payload = client.get(
        "search",
        part="snippet",
        q=query,
        type="video",
        order="relevance",
        maxResults=min(max(results_per_query, 1), 50),
        publishedAfter=published_after,
    )
    hits: list[dict[str, Any]] = []
    for rank, item in enumerate(payload.get("items", []), start=1):
        video_id = item.get("id", {}).get("videoId", "")
        if not video_id:
            continue
        hits.append({"video_id": video_id, "query": query, "rank": rank})
    return hits


def _baseline_stats(
    target: dict[str, Any],
    baseline_videos: list[dict[str, Any]],
    *,
    baseline_min_age_hours: int,
    now,
) -> dict[str, Any]:
    eligible = [
        row
        for row in baseline_videos
        if core.baseline_is_eligible(
            target["video_id"],
            target["duration_band"],
            row,
            baseline_min_age_hours=baseline_min_age_hours,
            now=now,
        )
    ]
    median_views = core.median_or_none([float(row["views"]) for row in eligible])
    median_velocity = core.median_or_none([float(row["lifetime_views_per_day"]) for row in eligible])
    baseline_count = len(eligible)
    return {
        "eligible": eligible,
        "baseline_count": baseline_count,
        "baseline_confidence": core.baseline_confidence_label(baseline_count),
        "median_baseline_views": round(median_views, 6) if median_views is not None else None,
        "median_baseline_lifetime_views_per_day": round(median_velocity, 6) if median_velocity is not None else None,
        "views_outlier_score": core.outlier_ratio(target["views"], median_views),
        "velocity_outlier_score": core.outlier_ratio(target["lifetime_views_per_day"], median_velocity),
    }


def _group_summary(topic_group: dict[str, Any], candidate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    unique_channels = sorted({row["channel_id"] for row in candidate_rows if row["channel_id"]})
    qualifying_rows = [
        row
        for row in candidate_rows
        if row["velocity_outlier_score"] is not None and row["velocity_outlier_score"] >= core.QUALIFYING_VELOCITY_OUTLIER_THRESHOLD
    ]
    qualifying_channels = sorted({row["channel_id"] for row in qualifying_rows if row["channel_id"]})
    confidence_counts = [row["baseline_count"] for row in candidate_rows]
    highest_confidence = core.baseline_confidence_label(max(confidence_counts or [0]))
    quality_label = core.quality_label_from_group(
        qualifying_outlier_channel_count=len(qualifying_channels),
        qualifying_outlier_video_count=len(qualifying_rows),
        confidence=highest_confidence,
    )
    verdict, reasons = core.verdict_from_group(
        quality_label=quality_label,
        confidence=highest_confidence,
        qualifying_outlier_channel_count=len(qualifying_channels),
    )
    median_velocity = core.median_or_none([row["velocity_outlier_score"] for row in candidate_rows if row["velocity_outlier_score"] is not None])
    max_velocity = max((row["velocity_outlier_score"] for row in candidate_rows if row["velocity_outlier_score"] is not None), default=None)
    median_views_per_day = core.median_or_none([row["lifetime_views_per_day"] for row in candidate_rows])
    return {
        "topic_group_id": topic_group["topic_group_id"],
        "label": topic_group["label"],
        "gateway_entity": topic_group["gateway_entity"],
        "candidate_video_count": len(candidate_rows),
        "unique_channel_count": len(unique_channels),
        "qualifying_outlier_video_count": len(qualifying_rows),
        "qualifying_outlier_channel_count": len(qualifying_channels),
        "median_velocity_outlier": round(median_velocity, 6) if median_velocity is not None else None,
        "max_velocity_outlier": round(max_velocity, 6) if max_velocity is not None else None,
        "median_lifetime_views_per_day": round(median_views_per_day, 6) if median_views_per_day is not None else None,
        "recent_competitor_count": len(candidate_rows),
        "cross_channel_status": core.cross_channel_status(len(unique_channels)),
        "quality_label": quality_label,
        "baseline_confidence": highest_confidence,
        "verdict": verdict,
        "reasons": reasons,
    }


def _sort_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            {"SHORTLIST": 0, "HOLD": 1, "REJECT": 2}.get(row.get("group_verdict", "REJECT"), 9),
            row["topic_group_id"],
            -float(row["velocity_outlier_score"] or -1.0),
            -float(row["views_outlier_score"] or -1.0),
            row["best_rank"],
            row["video_id"],
        ),
    )


def _sort_group_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            {"SHORTLIST": 0, "HOLD": 1, "REJECT": 2}.get(row["verdict"], 9),
            {"STRONG": 0, "SUPPORTED": 1, "DIRECTIONAL": 2, "WEAK": 3}.get(row["quality_label"], 9),
            -(row["qualifying_outlier_channel_count"]),
            row["topic_group_id"],
        ),
    )


def _collector_import_payload(plan: dict[str, Any], group_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    shortlisted_group_ids = {row["topic_group_id"] for row in group_rows if row["verdict"] == "SHORTLIST"}
    shortlisted_candidates = [
        {
            "topic_group_id": row["topic_group_id"],
            "video_id": row["video_id"],
            "title": row["title"],
            "channel": row["channel"],
            "url": row["url"],
            "velocity_outlier_score": row["velocity_outlier_score"],
            "views_outlier_score": row["views_outlier_score"],
            "queries": row["queries"],
        }
        for row in candidate_rows
        if row["topic_group_id"] in shortlisted_group_ids
    ]
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_TOPIC_HANDOFF",
        "cluster_id": plan["cluster_id"],
        "label": plan["label"],
        "shortlist_topic_groups": [row for row in group_rows if row["verdict"] == "SHORTLIST"],
        "shortlist_candidate_videos": shortlisted_candidates,
    }


def _top_opportunities_markdown(plan: dict[str, Any], group_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Top Topic Opportunities",
        "",
        f"- Cluster: `{plan['cluster_id']}`",
        f"- Label: {plan['label']}",
        f"- Topic groups: {len(group_rows)}",
        f"- Candidate videos: {len(candidate_rows)}",
        "",
    ]
    for group in group_rows:
        lines.extend(
            [
                f"## {group['label']}",
                "",
                f"- Topic group ID: `{group['topic_group_id']}`",
                f"- Verdict: `{group['verdict']}`",
                f"- Quality: `{group['quality_label']}`",
                f"- Confidence: `{group['baseline_confidence']}`",
                f"- Cross-channel status: `{group['cross_channel_status']}`",
                f"- Qualifying channels: `{group['qualifying_outlier_channel_count']}`",
                f"- Qualifying videos: `{group['qualifying_outlier_video_count']}`",
                f"- Reasons: {'; '.join(group['reasons']) if group['reasons'] else 'None'}",
                "",
            ]
        )
        sample_rows = [row for row in candidate_rows if row["topic_group_id"] == group["topic_group_id"]][:3]
        if sample_rows:
            lines.append("### Example candidates")
            lines.append("")
            for row in sample_rows:
                lines.append(
                    f"- [{row['title']}]({row['url']}) | {row['channel']} | velocity `{row['velocity_outlier_score']}` | band `{row['duration_band']}` | queries `{row['queries']}`"
                )
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def run_topic_scan(args: argparse.Namespace) -> dict[str, Any]:
    plan, plan_sha256 = _load_plan(args)
    api_key = core.load_api_key(args.api_key)
    cache_dir = Path(args.cache_dir) if args.cache_dir else Path(args.output_dir) / "raw_cache"
    client = core.YouTubeResearchClient(
        api_key,
        cache_dir=cache_dir,
        refresh=bool(args.refresh),
    )
    now = core.utc_now()
    published_after = core.iso_utc(now - timedelta(days=plan["published_days"]))

    video_group_hits: dict[str, dict[str, Any]] = {}
    for topic_group in plan["groups"]:
        for query in topic_group["queries"]:
            for hit in _query_video_hits(client, query=query, published_after=published_after, results_per_query=args.results_per_query):
                entry = video_group_hits.setdefault(
                    hit["video_id"],
                    {
                        "video_id": hit["video_id"],
                        "topic_groups": {},
                    },
                )
                group_entry = entry["topic_groups"].setdefault(
                    topic_group["topic_group_id"],
                    {
                        "topic_group_id": topic_group["topic_group_id"],
                        "topic_group_label": topic_group["label"],
                        "hits": [],
                    },
                )
                group_entry["hits"].append({"query": hit["query"], "rank": hit["rank"]})

    candidate_video_ids = sorted(video_group_hits)
    candidate_videos = core.batch_videos(client, candidate_video_ids)
    candidate_channel_ids = sorted(
        {
            item.get("snippet", {}).get("channelId", "")
            for item in candidate_videos.values()
            if item.get("snippet", {}).get("channelId")
        }
    )
    channels = core.batch_channels(client, candidate_channel_ids)

    recent_ids_by_channel: dict[str, list[str]] = {}
    all_recent_ids: list[str] = []
    for channel_id in candidate_channel_ids:
        channel = channels.get(channel_id, {})
        uploads_id = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
        if not uploads_id:
            recent_ids_by_channel[channel_id] = []
            continue
        recent_ids = core.recent_upload_ids(client, uploads_id, plan["baseline_recent_count"])
        recent_ids_by_channel[channel_id] = recent_ids
        all_recent_ids.extend(recent_ids)
    recent_videos = core.batch_videos(client, all_recent_ids)

    normalized_recent_by_channel: dict[str, list[dict[str, Any]]] = {}
    for channel_id, recent_ids in recent_ids_by_channel.items():
        channel_stats = channels.get(channel_id, {}).get("statistics", {})
        normalized_recent_by_channel[channel_id] = [
            core.normalize_video_metrics(recent_videos[video_id], channel_stats=channel_stats, now=now)
            for video_id in recent_ids
            if video_id in recent_videos
        ]

    candidate_rows: list[dict[str, Any]] = []
    for video_id in candidate_video_ids:
        raw_video = candidate_videos.get(video_id)
        if not raw_video:
            continue
        channel_id = raw_video.get("snippet", {}).get("channelId", "")
        channel_stats = channels.get(channel_id, {}).get("statistics", {})
        normalized_video = core.normalize_video_metrics(raw_video, channel_stats=channel_stats, now=now)
        if normalized_video["duration_seconds"] < plan["minimum_duration_seconds"] or normalized_video["duration_seconds"] > plan["maximum_duration_seconds"]:
            continue
        baseline = _baseline_stats(
            normalized_video,
            normalized_recent_by_channel.get(channel_id, []),
            baseline_min_age_hours=plan["baseline_min_age_hours"],
            now=now,
        )
        for topic_group_id, topic_group_hit in sorted(video_group_hits[video_id]["topic_groups"].items()):
            ordered_hits = sorted(topic_group_hit["hits"], key=lambda hit: (hit["rank"], core.normalize_query(hit["query"])))
            row = {
                **normalized_video,
                "topic_group_id": topic_group_id,
                "topic_group_label": topic_group_hit["topic_group_label"],
                "queries": " | ".join(hit["query"] for hit in ordered_hits),
                "query_hit_count": len(ordered_hits),
                "best_rank": min(hit["rank"] for hit in ordered_hits),
                "baseline_count": baseline["baseline_count"],
                "baseline_confidence": baseline["baseline_confidence"],
                "median_baseline_views": baseline["median_baseline_views"],
                "median_baseline_lifetime_views_per_day": baseline["median_baseline_lifetime_views_per_day"],
                "views_outlier_score": round(baseline["views_outlier_score"], 6) if baseline["views_outlier_score"] is not None else None,
                "velocity_outlier_score": round(baseline["velocity_outlier_score"], 6) if baseline["velocity_outlier_score"] is not None else None,
            }
            candidate_rows.append(row)

    group_rows: list[dict[str, Any]] = []
    group_by_id = {group["topic_group_id"]: group for group in plan["groups"]}
    for topic_group_id, topic_group in group_by_id.items():
        rows = [row for row in candidate_rows if row["topic_group_id"] == topic_group_id]
        group_rows.append(_group_summary(topic_group, rows))

    group_index = {row["topic_group_id"]: row for row in group_rows}
    for row in candidate_rows:
        row["group_verdict"] = group_index[row["topic_group_id"]]["verdict"]

    candidate_rows = _sort_candidate_rows(candidate_rows)
    group_rows = _sort_group_rows(group_rows)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": 1,
        "mode": "plan" if args.plan else "direct_query",
        "collected_at": core.utc_now_iso(),
        "plan_sha256": plan_sha256,
        "settings": {
            "cluster_id": plan["cluster_id"],
            "label": plan["label"],
            "published_days": plan["published_days"],
            "minimum_duration_seconds": plan["minimum_duration_seconds"],
            "maximum_duration_seconds": plan["maximum_duration_seconds"],
            "baseline_recent_count": plan["baseline_recent_count"],
            "baseline_min_age_hours": plan["baseline_min_age_hours"],
            "results_per_query": args.results_per_query,
            "refresh": bool(args.refresh),
            "qualifying_velocity_outlier_threshold": core.QUALIFYING_VELOCITY_OUTLIER_THRESHOLD,
        },
        "request_count": client.stats.request_count,
        "cache_hit_count": client.stats.cache_hit_count,
        "candidate_video_count": len(candidate_rows),
        "topic_group_count": len(group_rows),
        "shortlist_group_count": sum(1 for row in group_rows if row["verdict"] == "SHORTLIST"),
        "outputs": {},
    }

    candidate_json_payload = {"schema_version": 1, "results": candidate_rows}
    group_json_payload = {"schema_version": 1, "results": group_rows}
    collector_payload = _collector_import_payload(plan, group_rows, candidate_rows)
    markdown = _top_opportunities_markdown(plan, group_rows, candidate_rows)

    file_payloads = {
        "candidate_videos.csv": ("csv", candidate_rows, CANDIDATE_VIDEO_COLUMNS),
        "candidate_videos.json": ("json", candidate_json_payload, None),
        "topic_groups.csv": ("csv", [{**row, "reasons": " | ".join(row["reasons"])} for row in group_rows], TOPIC_GROUP_COLUMNS),
        "topic_groups.json": ("json", group_json_payload, None),
        "top_opportunities.md": ("text", markdown, None),
        "collector_import.json": ("json", collector_payload, None),
    }

    for file_name, payload in file_payloads.items():
        output_path = output_dir / file_name
        mode, value, columns = payload
        if mode == "csv":
            core.write_csv_rows(output_path, value, columns or [])
        elif mode == "json":
            core.write_json_atomic(output_path, value)
        else:
            core.write_text_atomic(output_path, value)
        contents = output_path.read_bytes()
        manifest["outputs"][file_name] = {
            "sha256": core.sha256_bytes(contents),
            "bytes": len(contents),
        }

    core.write_json_atomic(output_dir / "run_manifest.json", manifest)
    return {
        "manifest": manifest,
        "plan": plan,
        "plan_sha256": plan_sha256,
        "candidate_rows": candidate_rows,
        "group_rows": group_rows,
        "output_dir": output_dir,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_topic_scan(args)
    print(f"Topic scan complete. Candidate videos: {len(result['candidate_rows'])}")
    print(f"Topic groups: {len(result['group_rows'])}")
    print(f"Output directory: {result['output_dir']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except core.YouTubeResearchError as exc:
        print(f"ERROR [{exc.code}]: {exc.message}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
