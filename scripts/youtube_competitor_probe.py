#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import youtube_research_core as core


def _slugify(value: str) -> str:
    return core.deterministic_slug(value)[:60] or "channel"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic competitor probe using YouTube Data API data only.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--query")
    source.add_argument("--video-id")
    parser.add_argument("--recent", type=int, default=12)
    parser.add_argument("--baseline-min-age-hours", type=int, default=core.DEFAULT_BASELINE_MIN_AGE_HOURS)
    parser.add_argument("--api-key")
    parser.add_argument("--output-dir", default="competitor_probe_output")
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args(argv)


def _resolve_video_id(client: core.YouTubeResearchClient, args: argparse.Namespace) -> tuple[str, list[dict[str, str]]]:
    if args.query:
        return core.find_video_by_query(client, args.query)
    return core.parse_video_id(args.video_id), []


def run_competitor_probe(args: argparse.Namespace) -> dict[str, Any]:
    api_key = core.load_api_key(args.api_key)
    cache_dir = Path(args.cache_dir) if args.cache_dir else Path(args.output_dir) / "raw_cache"
    client = core.YouTubeResearchClient(api_key, cache_dir=cache_dir, refresh=bool(args.refresh))
    video_id, preview_results = _resolve_video_id(client, args)
    target_raw = core.batch_videos(client, [video_id]).get(video_id)
    if not target_raw:
        raise core.YouTubeResearchError("TARGET_VIDEO_NOT_FOUND", f"Could not load target video '{video_id}'.", 404)

    target_channel_id = target_raw.get("snippet", {}).get("channelId", "")
    channel_raw = core.batch_channels(client, [target_channel_id]).get(target_channel_id)
    if not channel_raw:
        raise core.YouTubeResearchError("TARGET_CHANNEL_NOT_FOUND", f"Could not load target channel '{target_channel_id}'.", 404)
    uploads_id = channel_raw.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
    if not uploads_id:
        raise core.YouTubeResearchError("TARGET_CHANNEL_UPLOADS_MISSING", "Could not load uploads playlist for the target channel.", 404)

    recent_ids = core.recent_upload_ids(client, uploads_id, args.recent)
    recent_raw = core.batch_videos(client, recent_ids)
    now = core.utc_now()
    channel_stats = channel_raw.get("statistics", {})
    target = core.normalize_video_metrics(target_raw, channel_stats=channel_stats, now=now)
    recent = [
        core.normalize_video_metrics(recent_raw[recent_id], channel_stats=channel_stats, now=now)
        for recent_id in recent_ids
        if recent_id in recent_raw
    ]
    baseline_rows = [
        row
        for row in recent
        if core.baseline_is_eligible(
            target["video_id"],
            target["duration_band"],
            row,
            baseline_min_age_hours=args.baseline_min_age_hours,
            now=now,
        )
    ]
    median_views = core.median_or_none([float(row["views"]) for row in baseline_rows])
    median_velocity = core.median_or_none([float(row["lifetime_views_per_day"]) for row in baseline_rows])
    baseline_count = len(baseline_rows)
    summary = {
        "schema_version": 1,
        "collected_at": core.utc_now_iso(),
        "query_preview": preview_results,
        "target_video": {
            **target,
            "views_outlier_score": round(core.outlier_ratio(target["views"], median_views), 6) if core.outlier_ratio(target["views"], median_views) is not None else None,
            "velocity_outlier_score": round(core.outlier_ratio(target["lifetime_views_per_day"], median_velocity), 6) if core.outlier_ratio(target["lifetime_views_per_day"], median_velocity) is not None else None,
        },
        "channel": {
            "channel_id": target_channel_id,
            "title": channel_raw.get("snippet", {}).get("title", ""),
            "published_at": channel_raw.get("snippet", {}).get("publishedAt", ""),
            "subscriber_count": None if channel_stats.get("hiddenSubscriberCount", False) else core.safe_int(channel_stats.get("subscriberCount")),
            "hidden_subscriber_count": bool(channel_stats.get("hiddenSubscriberCount", False)),
            "total_views": core.safe_int(channel_stats.get("viewCount")),
            "video_count": core.safe_int(channel_stats.get("videoCount")),
            "uploads_playlist_id": uploads_id,
            "url": f"https://www.youtube.com/channel/{target_channel_id}",
        },
        "baseline": {
            "recent_count_requested": args.recent,
            "recent_count_received": len(recent),
            "baseline_count": baseline_count,
            "baseline_confidence": core.baseline_confidence_label(baseline_count),
            "baseline_min_age_hours": args.baseline_min_age_hours,
            "duration_band": target["duration_band"],
            "median_views_excluding_target": round(median_views, 6) if median_views is not None else None,
            "median_lifetime_views_per_day_excluding_target": round(median_velocity, 6) if median_velocity is not None else None,
        },
        "recent_videos": recent,
        "request_count": client.stats.request_count,
        "cache_hit_count": client.stats.cache_hit_count,
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = _slugify(summary["channel"]["title"])
    json_path = output_dir / f"{prefix}_probe.json"
    csv_path = output_dir / f"{prefix}_recent_videos.csv"
    summary_path = output_dir / f"{prefix}_summary.txt"

    core.write_json_atomic(json_path, summary)
    core.write_csv_rows(
        csv_path,
        recent,
        [
            "video_id",
            "title",
            "published_at",
            "age_hours",
            "age_days",
            "duration",
            "duration_seconds",
            "duration_band",
            "views",
            "lifetime_views_per_day",
            "likes",
            "comments",
            "url",
        ],
    )
    target_outlier = summary["target_video"]["views_outlier_score"]
    velocity_outlier = summary["target_video"]["velocity_outlier_score"]
    lines = [
        f"TARGET VIDEO: {summary['target_video']['title']}",
        f"VIDEO ID: {summary['target_video']['video_id']}",
        f"VIDEO URL: {summary['target_video']['url']}",
        f"VIEWS: {summary['target_video']['views']:,}",
        f"PUBLISHED: {summary['target_video']['published_at']}",
        f"AGE DAYS: {summary['target_video']['age_days']}",
        f"DURATION: {summary['target_video']['duration']}",
        f"DURATION BAND: {summary['target_video']['duration_band']}",
        "",
        f"CHANNEL: {summary['channel']['title']}",
        f"CHANNEL ID: {summary['channel']['channel_id']}",
        f"SUBSCRIBERS: {'HIDDEN' if summary['channel']['hidden_subscriber_count'] else summary['channel']['subscriber_count']}",
        "",
        f"BASELINE COUNT: {summary['baseline']['baseline_count']}",
        f"BASELINE CONFIDENCE: {summary['baseline']['baseline_confidence']}",
        f"MEDIAN VIEWS EXCLUDING TARGET: {summary['baseline']['median_views_excluding_target']}",
        f"MEDIAN LIFETIME VIEWS PER DAY EXCLUDING TARGET: {summary['baseline']['median_lifetime_views_per_day_excluding_target']}",
        f"VIEWS OUTLIER SCORE: {target_outlier if target_outlier is not None else 'null'}",
        f"VELOCITY OUTLIER SCORE: {velocity_outlier if velocity_outlier is not None else 'null'}",
        "",
        f"JSON: {json_path}",
        f"CSV: {csv_path}",
    ]
    core.write_text_atomic(summary_path, "\n".join(lines) + "\n")
    return {"summary": summary, "json_path": json_path, "csv_path": csv_path, "summary_path": summary_path}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_competitor_probe(args)
    print(f"Competitor probe complete: {result['summary']['target_video']['video_id']}")
    print(f"JSON: {result['json_path']}")
    print(f"CSV: {result['csv_path']}")
    print(f"SUMMARY: {result['summary_path']}")
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
