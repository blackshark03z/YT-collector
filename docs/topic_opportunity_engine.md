# Topic Opportunity Engine

## Scope

The topic opportunity engine is a deterministic YouTube research helper for selecting the next video topic.

It does:
- collect YouTube Data API metadata;
- normalize candidate videos and recent same-channel baselines;
- compare total views and lifetime views per day honestly;
- aggregate evidence by structured topic group;
- export read-only shortlist files for operator review.

It does not:
- call any AI API;
- download transcripts;
- create Collector projects automatically;
- change workflow runtime, analytics runtime, OAuth tokens, or production artifacts.

## Canonical scripts

- `scripts/youtube_topic_opportunity_scan.py`
- `scripts/youtube_competitor_probe.py`
- shared core: `scripts/youtube_research_core.py`

Untracked root copies remain source inputs only and are not overwritten by this implementation.

## Duration bands

The engine uses four canonical duration bands:

- `SHORT`: under 180 seconds
- `LONG_3_10`: 180-599 seconds
- `LONG_10_30`: 600-1799 seconds
- `LONG_30_PLUS`: 1800 seconds and above

Baseline comparison always uses the same duration band as the target video.

This prevents Shorts or very long uploads from distorting a long-form baseline.

## Honest metric model

Two outlier metrics are kept separate:

1. `views_outlier_score`
   - descriptive only
   - formula: target total views / median eligible baseline total views

2. `velocity_outlier_score`
   - primary age-normalized comparison
   - formula: target `lifetime_views_per_day` / median eligible baseline `lifetime_views_per_day`

`lifetime_views_per_day` is a lifetime average. It is not current velocity and must not be described that way.

If the eligible baseline median is absent or zero, outlier scores return `null`.

## Baseline eligibility

The engine excludes:
- the target video itself;
- baseline videos outside the target duration band;
- baseline videos younger than `baseline_min_age_hours` (default `48`).

Baseline confidence is reported explicitly:

- `LOW`: fewer than 4 eligible baseline videos
- `MEDIUM`: 4-7 eligible baseline videos
- `HIGH`: 8 or more eligible baseline videos

No topic group may become `SHORTLIST` from `LOW` confidence evidence alone.

## Structured topic groups

Plan mode groups multiple search phrases under one deterministic historical topic group.

Each group contains:
- `topic_group_id`
- `label`
- `gateway_entity`
- one or more queries

The engine deduplicates videos globally while preserving every matching query and topic-group association.

If one candidate appears in multiple groups, it is counted in each matching group without duplicate video-detail requests.

## Group-level evidence

Each topic group reports:
- candidate video count;
- unique channel count;
- qualifying outlier video count;
- qualifying outlier channel count;
- median and max velocity outlier;
- median `lifetime_views_per_day`;
- recent competitor count;
- cross-channel status;
- quality label;
- verdict and reasons.

Internal quality labels:
- `WEAK`
- `DIRECTIONAL`
- `SUPPORTED`
- `STRONG`

Verdicts:
- `SHORTLIST`
- `HOLD`
- `REJECT`

The current qualifying threshold constant is `1.5` for `velocity_outlier_score`.

## Cache and refresh behavior

The shared core supports a sanitized request cache:
- stable request fingerprints exclude the API key;
- cache keys and output files never contain the secret;
- `--refresh` bypasses the cache and forces new requests.

Default cache location:
- scan: `<output-dir>/raw_cache`
- competitor probe: `<output-dir>/raw_cache`

## Direct query compatibility

Direct repeated `--query` mode is preserved for older usage.

It now synthesizes one deterministic topic group internally instead of bypassing the structured plan path.

`--plan` and `--query` are mutually exclusive.

## Output contract

Plan mode writes:
- `run_manifest.json`
- `candidate_videos.csv`
- `candidate_videos.json`
- `topic_groups.csv`
- `topic_groups.json`
- `top_opportunities.md`
- `collector_import.json`
- optional sanitized `raw_cache/`

`collector_import.json` is read-only handoff data. It is not a Collector import action.

## Limitations

- The engine only sees YouTube Data API metadata, not recommendation-system internals.
- `views_outlier_score` can still be inflated by older evergreen hits, which is why `velocity_outlier_score` is the primary comparison.
- Hidden subscriber counts remain hidden and `views_per_subscriber` becomes `null` in that case.
- Cross-channel proof improves confidence, but it still does not guarantee Mist of Ages package fit.

## One-line PowerShell examples

```powershell
python scripts/youtube_topic_opportunity_scan.py --plan config/topic_scan_plan.example.json --output-dir topic_opportunity_scan
```

```powershell
python scripts/youtube_topic_opportunity_scan.py --query "Caesar crossed the Rubicon history documentary" --query "river Caesar was forbidden to cross history" --output-dir topic_opportunity_scan --refresh
```

```powershell
python scripts/youtube_competitor_probe.py --video-id https://www.youtube.com/watch?v=oKs9qnzuHMg --output-dir competitor_probe_output
```
