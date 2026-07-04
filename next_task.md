# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 9A - Analytics Collector Live Verification, Runtime Preservation Check, and Commit Review

## Do Not Start Yet
Do not begin Phase 9A until a separate Tech Lead execution prompt authorizes live verification of the repaired analytics collector routes and UI, followed by repository commit review for the narrow Phase 9 diff.

## Proposed Objective
Verify the repaired analytics collector behavior against the canonical `mist_of_ages` workspace, confirm successful analytics runtime preservation, then close out the narrow repository diff safely without mutating approved workflow runtime data.

## Current Phase Evidence
- A focused analytics collector/export module now exists in `scripts/channel_analytics_collector.py`.
- Supported analytics status, capability discovery, analytics sync, and Analytics ZIP export endpoints now exist in `scripts/ui_server.py`.
- The collector now writes sanitized capability and state snapshots plus deterministic normalized CSVs under `channels/<slug>/analytics/`.
- The focused repair now separates discovered report-type availability from generated-report readiness and exposes source-level `SUCCESS`, `PARTIAL`, and `ERROR`.
- The focused repair now keeps capability snapshot, collector status, UI summary, and exported `capabilities.json` aligned on report-type availability versus generated-report readiness counts.
- The focused repair now preserves previously successful normalized CSVs when later syncs encounter true query errors or bulk-report pending states.
- The Analytics ZIP now includes `manifest.json`, `capabilities.json`, `collector_status.json`, `unavailable_metrics.json`, and every normalized CSV currently present.
- Focused compile verification passed, `tests.test_channel_analytics_collector` passed (`13` tests), the focused Analytics Collector UI runtime test passed, and the full embedded UI contract suite passed (`51` tests).
- The implementation remains local only; no commit or push has occurred.

## Preconditions
- Do not alter approved workflow projects, revisions, decisions, stable production artifacts, or protected OAuth/token runtime while verifying the analytics collector behavior.
- Preserve workflow defaults, prompt/workflow assets, prompt manifests, registry defaults, and protected runtime unchanged.
- Preserve the current channel workspace ownership and protected runtime files for `mist_of_ages` until the next separate execution prompt.

## Required Focus
- preserve the narrow Phase 9 analytics diff exactly as validated
- verify capability discovery, analytics sync, capability-snapshot consistency, source aggregation, normalized outputs, and Analytics ZIP behavior against the supported collector state only
- preserve approved stable production artifacts, workflow revisions, decisions, and workflow state unchanged
- preserve workflow/prompt asset digests and registry default semantics
- keep any later commit/push decision separate from implementation verification

## Forbidden Work
- do not mutate approved workflow project runtime in this verification/closeout gate
- do not change workflow defaults, prompt/workflow assets, manifest files, or registry data
- do not add AI API calls
- do not expose token contents, secret files, or absolute local paths
- do not mutate protected runtime data outside approved focused tests
- do not start unrelated workflow phases, History work, or Restore work

## Verification Requirements
- confirm the analytics diff is limited to the collector/export module, focused UI integration, focused tests, and the minimal status documents
- confirm no runtime or protected files are included in diff scope
- confirm approved workflow projects remain unchanged while the analytics collector writes only under `channels/<slug>/analytics/`
- confirm real Mist of Ages runtime and token files remain protected from accidental mutation

## Reasoning Effort
High

## Deferred Later Phase
History and Restore remain deferred

## Explicitly Blocked
- Repository commit review remains blocked pending separate review.
- Live analytics collector verification remains blocked pending a separate execution prompt.
- History remains deferred.
- Restore remains deferred.

## Exact First Action
Run a focused live verification of analytics capability discovery, capability-snapshot/generated-report count consistency, analytics sync aggregation semantics, normalized-output preservation, generated-report readiness reporting, and Analytics ZIP export for canonical channel `mist_of_ages`, then review commit scope in a separate step.
