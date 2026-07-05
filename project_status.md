# Project Status

## Project
Mist of Ages Multi-Channel Input Collector

## Product Boundary
- local personal-use tool
- filesystem based
- no database
- no AI API
- no transcript download
- no video upload

## Current Phase
Project Closeout - Maintenance Mode

## Phase Status
CORE_PROJECT_COMPLETE

## Approval
LIVE_VERIFIED_COMMITTED_PUSHED

## Final Repository Baseline
- Branch: `master`
- `HEAD = origin/master = 76bcff92d5a79af2845cf19f0a7c977b300eb799`
- Latest commit subject: `feat: simplify operator workspace ui`

## Final Verification Summary
- Frontend tests: `python -m unittest tests.test_ui_frontend_contract` (`91` run, `91` passed, `0` failures, `0` errors)
- Analytics collector tests: `python -m unittest tests.test_channel_analytics_collector` (`13` run, `13` passed, `0` failures, `0` errors)
- Production export tests: `python -m unittest tests.test_channel_production_export` (`6` run, `6` passed, `0` failures, `0` errors)
- Live operator UI verification: `PASS`

## Final Project State
- `CORE_PROJECT_COMPLETE`
- `MAINTENANCE_MODE`
- `SAFE_TO_STOP`

## Phase 10A Scope
- Redesigned the embedded UI in `scripts/ui_server.py` around three operator-first work areas: `Overview`, `Content Workflow`, and `Analytics`, while keeping the existing single-server architecture and `/api/v2/` backend contract unchanged.
- Added a compact application header that surfaces the application name, selected channel, selected project, and a context-aware status badge derived from existing frontend state only.
- Reworked the primary layout into a stable sidebar plus main workspace, with navigation switching handled entirely in the browser without duplicating backend fetches.
- Simplified `Overview` into a deterministic operational summary: channel connection, selected project, workflow lifecycle, production package readiness, analytics readiness, bulk-report readiness, and one deterministic `Recommended Next Action` block.
- Reworked the selected-project workflow area into a compact Prompt 1-7 step rail, preserved explicit project creation and project selection, and kept only the selected workflow step expanded.
- Preserved all supported workflow operations and route behavior for bundle build/copy, parse-preview, save candidate, approve candidate, reject candidate, transcript save, and validation.
- Simplified the default information hierarchy further for operators: the header now hides raw project slugs and status codes, the sidebar collapses maintenance actions into `Channel Settings`, the workflow workspace collapses project management into `Change Project` / `Create New Project`, and analytics now leads with friendly status, sync freshness, table readiness, and bulk-report state.
- Completed a final operator-context repair so selected projects persist safely per channel across workspace changes, summary refreshes, project refreshes, and practical browser reloads using only local browser state for channel slug plus project slug.
- Repaired the header-state semantics so the default badge now shows `Workflow Status` when a project is selected and `Analytics Status` when no project is selected, while raw workflow and analytics codes remain inside collapsed `Technical Details` only.
- Preserved automatic operator flow for single-project channels by restoring the sole valid project without any write action and keeping production-ready projects pointed at `Download Production Package` as the recommended action.
- Completed a final live UX micro repair so the shared workspace introduction now matches the selected workspace, the orphan visible create-state panel is removed from the default workflow view, and completed `PRODUCTION_READY` workflow/handoff content now appears before project-management controls.
- Completed a final content-workflow compression and status repair so `PRODUCTION_READY` projects now show one handoff/download area only, the Prompt 1-7 rail is rendered in a genuinely compact two-row-friendly format, selected styling no longer overrides actual step status, and the redundant project-summary grid is removed from the default completed-project view.
- Renamed collapsed diagnostic sections from `Advanced Details` to `Technical Details` and kept raw IDs, slugs, hashes, state revisions, workflow binding, query-group breakdowns, report readiness, and API status detail there only.
- Promoted production-handoff status for `PRODUCTION_READY` projects with visible completion messaging, `Download Production ZIP`, and read-only artifact links.
- Reworked the Analytics workspace into a plain-language operational view with separate counts for discovered report types versus generated-report readiness, friendlier `PARTIAL` messaging, compact normalized-table rendering, and explicit empty-table reasons.
- Preserved existing backend conflict/error handling, action disabling during busy states, and duplicate-submission protection without adding live API calls, analytics sync, reporting jobs, new framework code, or runtime mutation.

## Phase 10A Verification
- Focused compile verification passed: `python -m py_compile scripts/ui_server.py tests/test_ui_frontend_contract.py`.
- Focused embedded UI contract/runtime suite passed: `python -m unittest tests.test_ui_frontend_contract` (`91` run, `91` passed, `0` failures, `0` errors).
- Phase 10A.4 coverage now verifies the three primary navigation areas, deterministic overview action logic, operator-first header wording, hidden raw project slugs in the default header, context-aware `Workflow Status` versus `Analytics Status`, workspace-specific introduction copy, compact workflow rail rendering, single-step expansion, collapsed `Technical Details`, production handoff visibility, one production download action only for completed projects, one completion message only, selected approved-step semantics, selected-project persistence across workspace switching, channel-summary refresh, project-list refresh, sole-project auto-selection, stale saved-project clearing, read-only project restoration, orphan create-state removal from the default workflow view, completion-first ordering for `PRODUCTION_READY` projects, redundant project-summary removal, disabled/busy action presentation, project-management collapse by default, channel/project selection, workflow loading and step switching, prompt bundle behavior, parse/preview behavior, candidate save/approve/reject controls, stale/conflict handling, OAuth/connect wiring, safe rendering, and duplicate-submission blocking.
- Final live operator verification passed after the implementation sequence was completed and published.
- No workflow runtime, analytics runtime, token file, or production artifact was mutated by Phase 10A.

## Phase 10A Repository State
- Phase 10A through 10A.4 is complete, live-verified, committed, and pushed on `master`.
- Final synchronized baseline is `76bcff92d5a79af2845cf19f0a7c977b300eb799` (`feat: simplify operator workspace ui`).
- `implement.docx` remains unrelated and untracked.
- Approved workflow runtime, analytics runtime, production artifacts, revisions, decisions, workflow state, token files, and protected channel data remain outside this implementation scope and were not modified.

## Resume Instructions
- Verify the repository is on branch `master` and confirm Git status before resuming work.
- Synchronize local `master` with the shared baseline before starting a new scoped task.
- Start `scripts.ui_server` on port `8766` for normal operator use.
- Do not affect the unrelated local service on port `8765`.
- Resume with normal operation or define and approve a new scoped development phase before making additional changes.

## Phase 9 Scope
- Added `scripts/channel_analytics_collector.py` as a focused analytics collection, normalization, status, and export module for canonical channel workspaces.
- Kept Phase 9 strictly out of workflow-authoring scope: no approved workflow project artifact, revision, decision, transaction, or workflow state mutation is performed by the collector.
- Added supported collector routes in `scripts/ui_server.py` for the selected canonical channel:
  - `GET /api/v2/channels/<channel_slug>/analytics`
  - `POST /api/v2/channels/<channel_slug>/analytics/discover`
  - `POST /api/v2/channels/<channel_slug>/analytics/sync`
  - `GET /api/v2/channels/<channel_slug>/analytics/export`
- Implemented Reporting API capability discovery with sanitized `capability_snapshot.json`, preserved existing job/runtime state, incremental report download, separate report-type availability versus generated-report readiness tracking, and no Phase 9 job creation.
- Repaired capability snapshot consistency so discovered report-type `status = AVAILABLE` remains separate from generated-report readiness, and zero-generated-report jobs now persist as `generated_report_status = PENDING` instead of appearing ready.
- Implemented Data API full upload-catalog collection for the authorized channel and persisted a deterministic `video_catalog.csv`.
- Repaired targeted Analytics API query compatibility to use canonical filtered video-daily paging, country summary instead of unsupported `day,country`, per-video retention, per-playlist day queries, subscriber-status retry, cards-only targeted handling, and bulk-pending handling for reach/end screens.
- Implemented source-level aggregation with `SUCCESS`, `PARTIAL`, and `ERROR`, plus separate `last_completed_sync_at` versus `last_successful_sync_at`.
- Implemented deterministic normalized CSV outputs under `channels/<slug>/analytics/normalized/` with stable column ordering, natural-key deduplication, and preservation of already successful CSV outputs when later groups fail or remain bulk-pending.
- Implemented collector state and diagnostics under `channels/<slug>/analytics/state/` with sanitized source-level results, query-group results, report jobs, ingested report identities, row counts, and timestamps.
- Implemented a read-only in-memory Analytics ZIP export containing `manifest.json`, `capabilities.json`, `collector_status.json`, `unavailable_metrics.json`, and every normalized CSV currently present.
- Added a focused embedded UI Analytics Collector section with capability discovery, analytics sync, `SUCCESS/PARTIAL/ERROR` source visibility, separate discovered-report-type counts versus generated-report readiness counts, normalized table row counts, and `Download Analytics ZIP`.
- The collector state, capability snapshot, UI summary, and exported `capabilities.json` now share the same report-type and generated-report count model.

## Phase 9 Normalized Outputs
- Required minimum normalized files now written deterministically:
  - `video_catalog.csv`
  - `channel_daily.csv`
  - `video_daily.csv`
  - `traffic_source_daily.csv`
  - `country_daily.csv`
  - `country_summary.csv`
  - `device_daily.csv`
  - `subscriber_status_daily.csv`
  - `reach_daily.csv`
  - `retention.csv`
  - `playlists_daily.csv`
- Additional focused tables are also supported when query groups run:
  - `playback_location_daily.csv`
  - `engagement_daily.csv`
  - `cards_daily.csv`
  - `end_screens_daily.csv`
  - `monetary_daily.csv`

## Phase 9 Verification
- Focused compile verification passed: `python -m py_compile scripts/channel_analytics_collector.py scripts/ui_server.py tests/test_channel_analytics_collector.py tests/test_ui_frontend_contract.py`.
- Focused collector regression passed: `python -m unittest tests.test_channel_analytics_collector` (`13` run, `13` passed, `0` failures, `0` errors).
- Focused UI runtime analytics-panel verification passed: `python -m unittest tests.test_ui_frontend_contract.UiFrontendRuntimeTests.test_analytics_collector_panel_renders_actions_counts_and_export_link`.
- Full embedded UI contract rerun passed after the focused Analytics Collector additions: `python -m unittest tests.test_ui_frontend_contract` (`51` run, `51` passed, `0` failures, `0` errors).
- Added focused coverage for dynamic capability discovery, no duplicate Reporting jobs, canonical video-filter paging, country summary fallback, subscriber retry, persistent subscriber error with honest `PARTIAL`, per-video retention isolation, per-playlist daily queries, reach/end-screen bulk pending behavior, unauthorized monetary metrics, generated-report pending/ready/error semantics, snapshot/state/export count consistency, `last_completed_sync_at` versus `last_successful_sync_at`, successful CSV preservation, ZIP contents/hashes, no secret or absolute-path leakage, no workflow-project mutation, and UI rendering/action wiring for separated availability/readiness semantics.

## Phase 9 Repository State
- The Phase 9 implementation is local only and has not been committed or pushed.
- `implement.docx` remains unrelated and untracked.
- Protected runtime files, OAuth token contents, approved workflow outputs, and canonical production pilot artifacts remain outside this implementation scope.

## Phase 8A Scope
- Added a focused read-only production handoff/export module in `scripts/channel_production_export.py` for canonical channel projects whose supported workflow read model reports `PRODUCTION_READY`.
- Added a supported summary endpoint and a supported ZIP download endpoint in `scripts/ui_server.py` for the selected canonical project:
  - `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/production-package`
  - `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/production-package/download`
- The ZIP is built in memory and contains exactly `content.md`, `publishing_package.md`, and `manifest.json`.
- `manifest.json` includes `schema_version`, `channel_slug`, `project_slug`, `workflow_id`, `workflow_version`, `state_revision`, `lifecycle`, `approved_group_id`, artifact filenames, character counts, SHA-256 values, and the export timestamp.
- Export refuses unless the workflow read model is `PRODUCTION_READY`, both stable artifacts exist, and the stable artifact bytes match the approved revision metadata for the final approved group.
- The implementation uses the supported workflow read model rather than trusting nullable derived fields directly from `workflow_state.json`.
- Added an embedded UI Production Handoff section for the selected project that shows readiness, approved artifact identity, read-only artifact links, and a `Download Production ZIP` action.
- Kept the phase strictly read-only with respect to approved runtime workflow artifacts, revisions, decisions, workflow state, and transaction directories.

## Phase 8A Verification
- Focused compile verification passed: `python -m py_compile scripts/channel_production_export.py scripts/ui_server.py tests/test_channel_production_export.py`.
- Focused production-export regression passed: `python -m unittest tests.test_channel_production_export` (`6` run, `6` passed, `0` failures, `0` errors).
- Focused UI runtime verification for the Production Handoff panel passed: `python -m unittest tests.test_ui_frontend_contract.UiFrontendRuntimeTests.test_production_handoff_panel_renders_ready_download_and_artifact_links`.
- Added focused coverage for successful export, `PRODUCTION_READY` gating, missing stable-artifact rejection, hash/revision mismatch rejection, exact ZIP/manifest contents, and no-project-mutation guarantees.
- Added focused UI coverage proving the selected-project detail panel renders the Production Handoff section, readiness summary, artifact links, and ZIP download action from supported backend state.

## Phase 8A Pilot Baseline
- The authoritative pilot project remains `channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes`.
- The supported workflow read model baseline for this phase is `workflow_id = mist_of_ages_assisted_content`, `workflow_version = 2`, `state_revision = 14`, `lifecycle = PRODUCTION_READY`, and final approved group `grp_000007`.
- The required stable production artifacts remain `content.md` with SHA-256 `FD5E257BE6B34B0A45919D6E0CFCEA5167D33A73481E0F5D72589595C4501D9F` and `publishing_package.md` with SHA-256 `E4FD22AE4D40057C0D192839B94C65DF1C5542EA22405EACF5E4B3B5052B02BC`.

## Phase 8A Repository State
- The Production Handoff MVP implementation is local only and has not been committed or pushed.
- No approved project artifact, workflow revision, decision record, workflow state file, or transaction directory was modified by the implementation pass.
- `implement.docx` remains unrelated and untracked.

## Phase 7D1B2 Scope
- Confirmed the Prompt 3 UI mismatch exactly: the live backend read model reported `save_candidate = true` for `prompt_3_creative_package` in `READY`, but the embedded UI still surfaced the blocked save helper and disabled the button from stale workflow capability state.
- Narrowly updated the embedded frontend in `scripts/ui_server.py` so a successful Parse and Preview now refreshes the selected workflow read model for the same channel/project/step while preserving the visible workflow, selected step, loaded bundle, and valid parsed preview.
- Kept Save Candidate gated by both conditions only: parsed preview must remain `VALID`, and the latest backend `available_actions[step_id].save_candidate` must be `true`.
- Preserved the existing backend-controlled decision gating: Approve and Reject remain disabled unless a current candidate exists and backend `approve_candidate` / `reject_candidate` are true.
- Avoided widening scope into workflow assets, prompt assets, parser behavior, runtime mutation, or candidate actions.

## Phase 7D1B2 Verification
- Focused compile check passed: `python -m py_compile scripts/ui_server.py`.
- Focused frontend contract rerun passed: `python -m unittest tests.test_ui_frontend_contract` (`48` run, `48` passed, `0` failures, `0` errors).
- Live UI retry passed: the blocked helper disappeared and `Save Candidate` became enabled for Prompt 3 after a valid Parse and Preview while backend capability remained authoritative.
- Added focused UI coverage for Prompt 3 capability refresh after parse, valid-preview save enablement only when backend capability is true, valid-preview save blocking when backend capability is false, invalid-preview save blocking even when backend capability is true, and candidate-decision buttons following backend capability plus candidate presence.
- Prompt 3 raw output identity remained stable through the successful live retry and save path: character count `16504`, SHA-256 `0FC2C5CB100A99424D6550539C8C34F51FFAFF68FAD107FD856759EE36EFE65A`.
- No runtime project, workflow asset, prompt asset, manifest, registry, token file, or protected channel runtime was modified during the implementation pass.

## Prompt 3 Pilot Result
- Prompt 3 candidate group `grp_000003` was saved successfully from the live UI retry path and then approved through the supported workflow decision API.
- `locked_creative_package` candidate revision `rev_000001` was published to stable `workflow/locked_creative_package.md`.
- Stable `locked_creative_package` SHA-256 is `0FC2C5CB100A99424D6550539C8C34F51FFAFF68FAD107FD856759EE36EFE65A`.
- Workflow state schema remains `2` and state revision is now `6`.
- Prompt 1 remains `APPROVED`.
- Prompt 2 remains `APPROVED`.
- Prompt 3 is now `APPROVED` with approved group `grp_000003`.
- Prompt 4 effective status is now `READY`.
- The current actionable step id is `prompt_4_retention_outline`.
- The read model `next_step_id` is `prompt_5_narration_v1`.

## Phase 7D1B1 Scope
- Confirmed the Prompt 2 `evidence_ledger` parser defect exactly: `scripts/channel_output_parser.py` counted configured required headings globally, so valid repeatable claim records failed as duplicates and Markdown label variants like `## CLAIM:` failed as missing headings.
- Added a narrowly scoped `evidence_ledger`-only validator in `scripts/channel_output_parser.py` that preserves existing non-ledger heading behavior while allowing one or more complete claim records with optional Markdown label prefixes `#` through `######`.
- Kept matching exact after optional prefix removal: case-sensitive, colon-sensitive, and literal against the configured heading names `CLAIM:`, `SOURCE:`, `STATUS:`, `ALLOWED WORDING:`, and `NOTES:`.
- Allowed blank lines between labels and content and ensured Markdown content such as `# The Tomb of Eurysaces...` inside `NOTES:` remains ordinary content instead of being misclassified as a field heading.
- Added focused parser coverage in `tests/test_channel_output_parser.py` for valid plain/Markdown/mixed repeatable records, incomplete records, duplicate fields, out-of-order fields, premature new-`CLAIM` boundaries, Markdown content inside `NOTES:`, and a realistic two-artifact Prompt 2 envelope carrying multiple ledger records.
- Preserved all non-ledger parser behavior, output markers, raw bytes, artifact SHA calculation, and STATUS-value validation semantics unchanged.

## Phase 7D1B1 Verification
- Focused parser regression passed: `python -m unittest tests.test_channel_output_parser` (`32` run, `32` passed, `0` failures, `0` errors).
- Focused API parse-route regression passed: `python -m unittest tests.test_multichannel_api.MultiChannelApiTests.test_parse_output_route_returns_parsed_preview_for_selected_project_step`.
- Live API smoke on the current restarted single-listener server returned `VALID` for a two-artifact Prompt 2 parse preview with repeated Markdown evidence-ledger labels.
- The real Prompt 2 raw response was parsed validly with raw SHA-256 `CA6C664A86C5AC52F54E3C7F4CAD3A14543286E8CD0D3AF98F7D0FC877B9960D`.
- No runtime project, workflow asset, prompt asset, manifest, registry default, token file, or protected channel runtime was modified by parser verification.

## Prompt 2 Pilot Result
- Prompt 2 candidate group `grp_000002` was approved through the supported workflow decision API.
- `research_pack` candidate revision `rev_000001` was published to stable `workflow/research_pack.md`.
- `evidence_ledger` candidate revision `rev_000001` was published to stable `workflow/evidence_ledger.md`.
- Stable `research_pack` SHA-256 is `1AAC8842AFDDB238FE243D4DE1F35417B4B3B3340435A703C120875BFBC1E72E`.
- Stable `evidence_ledger` SHA-256 is `B136B8C69D1875629C56CDD8894D68BDFBFD5B4DF13C42EE8F1C28D4763005D3`.
- Workflow state schema remains `2` and state revision is now `4`.
- Prompt 1 remains `APPROVED`.
- Prompt 2 is now `APPROVED` with approved group `grp_000002`.
- Prompt 3 effective status is `READY`.
- The exact next workflow step id is `prompt_3_creative_package`.

## Commit State
- Repository closeout for the Prompt 3 UI capability-refresh fix is in progress.
- This fix has not been pushed yet.
- Prompt 4 bundle preparation and verification remain a separate next workflow step and have not been started in this phase.

## Repository Baseline
- Branch: master
- HEAD before Phase 7C1 implementation: `24c477a`
- Subject before Phase 7C1 implementation: `feat: add versioned workflow foundation`
- Working tree before Phase 7C1 implementation: only unrelated untracked `implement.docx`

## MVP Status
MVP_ACCEPTED

## Phase 7D1A1 Scope
- Confirmed the real pilot blocker exactly: the canonical V2 create flow in `scripts/ui_server.py` called `channel_projects.create_channel_project(...)` without an explicit workflow binding, and `scripts/channel_projects.py` then fell back to `channel_workflow.get_channel_default_workflow(...)`.
- Confirmed the fallback chain terminated in `scripts/channel_workflow.py` against `workflows/registry.json` where `default_version = 1` and `legacy_unpinned_version = 1`, so a newly created canonical project was legitimately persisted with workflow version `1`.
- Added `channel_workflow.list_channel_workflow_options(...)` to expose server-owned workflow choices per selected channel from registry-owned workflow data only, with no hardcoded Mist-of-Ages or v2 browser default.
- Added `channel_workflow.resolve_explicit_channel_workflow_binding(...)` so canonical create requests must provide `workflow_id` and `workflow_version`, and the server now validates channel authorization, version availability, and the authoritative workflow definition digest itself.
- Updated the canonical `POST /api/v2/channels/<channel_slug>/projects` route in `scripts/ui_server.py` to reject missing binding with controlled `WORKFLOW_BINDING_REQUIRED`, reject unsupported client authority fields with `INVALID_REQUEST`, resolve the explicit binding before metadata fetch, and return the authoritative pinned binding in the create response.
- Updated `scripts/channel_projects.py:create_channel_project(...)` so the canonical caller can pass an already validated explicit binding and the low-level project creator no longer silently re-resolves a different default on that path.
- Updated the embedded UI in `scripts/ui_server.py` so visible canonical project creation now requires an explicit workflow selection from server-owned `available_workflows`, keeps Create disabled until a valid selection exists, refreshes options with the selected channel, and sends only `competitor_url`, optional `project_name`, `workflow_id`, and `workflow_version`.
- Verified the fix remains generic: no production code hardcodes `mist_of_ages`, `mist_of_ages_assisted_content`, workflow version `2`, prompt numbering, workflow digests, or prompt/workflow file paths as browser authority.
- Confirmed production workflow assets remained unchanged: `default_version = 1`, `legacy_unpinned_version = 1`, workflow v1 SHA-256 `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`, workflow v2 SHA-256 `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606`, and prompt manifest SHA-256 `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602`.

## Phase 7D1A1 Runtime Safety
- The blocked pilot artifact at `channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes/` remained untouched and must stay a failed initialization artifact until a separate cleanup prompt authorizes action.
- The blocked pilot project's persisted binding remained the previously observed workflow version `1`; this phase did not edit, validate, migrate, rename, delete, or recreate that project.
- Transcript save was not executed.
- Prompt 1 and later workflow execution were not started.
- No second real project was created.
- Real canonical counts remained `1` canonical project directory and `0` real `workflow_state.json` files throughout the phase.
- Protected canonical and legacy runtime files were snapshotted before implementation and again after focused/full regression; the blocked pilot project remained byte-identical across those snapshots.
- `implement.docx` remained untouched and untracked.

## Phase 7D1A1 Evidence
- Focused project-service regression: `python -m unittest tests.test_channel_projects` passing (`49` run, `49` passed, `0` failures, `0` errors, `0` skipped).
- Focused V2 backend regression: `python -m unittest tests.test_multichannel_api` passing (`66` run, `66` passed, `0` failures, `0` errors, `0` skipped).
- Focused frontend contract plus runtime harness: `python -m unittest tests.test_ui_frontend_contract` passing (`44` run, `44` passed, `0` failures, `0` errors, `0` skipped).
- Added deterministic coverage for missing binding, explicit v2 binding, explicit v1 binding, unknown workflow id/version, client-supplied authority-field rejection, cross-channel workflow rejection, server-calculated digest persistence, no-output-scaffolding regression, and no `workflow_state.json` at project creation.
- Added frontend runtime coverage for server-owned workflow options, disabled create state without selection, exact selected id/version request payload, no digest/path authority leakage, stale option invalidation on channel change, and workflow-version visibility after successful create/read flow.
- Cleanup and pilot retry remain blocked pending separate authorization.
- History and Restore remain deferred.

## Post-MVP Documentation
- Preserved the intentional post-MVP planning document at `docs/post_mvp/video_production_optimization_proposals.md`.
- Document state remains `DOCUMENTED_FOR_LATER_RESEARCH`.
- Authorization state remains `NO_IMPLEMENTATION_AUTHORIZED`.
- No proposal module has been approved for implementation.
- No production behavior changed.
- No canonical runtime data changed.
- Cleanup remains the next maintenance action and must be rerun from the new baseline.
- `implement.docx` remains unrelated and untracked.

## Completed
- Phase 0: read-only architecture audit completed
- Phase 1: channel workspace foundation completed and committed
- Phase 2: isolated channel OAuth service completed and committed
- Phase 3: channel-scoped project service completed and verified locally
- Phase 4A: channel metrics service and additive `/api/v2/` backend completed and verified locally
- Phase 4B1: OAuth browser flow and UI-support backend endpoints completed and committed
- Phase 5A: legacy Mist of Ages dry-run planner, report, and real-repository dry run completed without mutation
- Phase 5B: authorized real Mist of Ages migration completed locally with validation and second-apply refusal
- Phase 5B1: post-migration regression isolation fix completed and verified without mutating canonical runtime data
- Phase 6A: one selected-channel metrics sync completed locally for canonical Mist of Ages; narrow runtime compatibility fixes remain uncommitted for Tech Lead review
- Phase 6A1: metrics-sync status semantics resolved conservatively; canonical Mist of Ages status restored to `CONNECTED`; approved fixes and tests are ready to commit
- Phase 6B: read-only UI cutover readiness audit completed with evidence-based cutover phases and explicit preconditions
- Phase 6C1: embedded production UI read cutover implemented with explicit selected-channel state, `/api/v2/` channel reads, disabled legacy mutations, focused UI contract coverage, and local non-external smoke evidence
- Repository history and secret audit: completed with reachable-history decision `HISTORY_SAFE_FOR_PUBLIC_PUSH`, exact live-secret scan result `EXACT_LIVE_SECRET_NOT_FOUND_IN_HISTORY`, narrow ignore hardening, initial `master` publication, and remote-tracking setup on `origin/master`
- Phase 6C2: embedded production UI now wires selected-channel OAuth and metrics actions to canonical V2 routes with separate action state, duplicate/stale-response protection, focused frontend contract coverage, and local non-external smoke evidence
- Phase 6C3: embedded production UI now wires canonical selected-channel project listing, project creation, project detail reads, transcript save, and validation using V2 routes with duplicate/stale-response protection and isolated temporary-root smoke evidence
- Phase 6C4: final MVP cutover verification completed with active UI-route audit, legacy-dependency classification, real read-only smoke, temporary-root end-to-end smoke, narrow frontend cleanup, and MVP readiness documentation
- Phase 7B: versioned workflow registry/definition foundation, immutable project workflow binding, legacy synthesized binding reads, workflow state read synthesis, and channel-scoped workflow read API completed locally without runtime mutation
- Phase 7C1: authoritative Mist of Ages prompt-set ingestion, immutable workflow v2, generic prompt-manifest validation, prompt-bundle builder, and read-only bundle API completed locally without runtime mutation
- Phase 7C2A: embedded read-only workflow panel, selected-step bundle preview/copy flow, and stale-response-safe bundle UI completed locally without runtime mutation
- Phase 7C2B: pasted AI output intake, zero-write output parser, structural validation, and in-memory parsed artifact preview completed locally without runtime mutation
- Phase 7C2C1: candidate-only workflow write path, persisted workflow state v2, immutable revision/group storage, per-project transaction locking, recovery-aware candidate commit, Save Candidate API, and minimal Save Candidate UI completed locally without runtime mutation
- Phase 7C2C2: approval/rejection write path, stable publication gate, no-placeholder-overwrite rule, workflow-generated output scaffold removal, approved-state trust enforcement, and recovery verification completed locally without runtime mutation
- Phase 7C2C3A: workflow-state schema v3, write-time v2-to-v3 replacement conversion, approved-plus-candidate coexistence, replacement save/approve/reject, stable replacement recovery, content-hash changed-artifact detection, downstream stale propagation, downstream candidate invalidation, stale bundle gating, and minimal replacement/stale UI completed locally without runtime mutation

## Phase 7C2C3A Scope
- Introduced workflow-state schema v3 in `scripts/channel_workflow_write.py` so an approved group and a replacement candidate group can coexist safely on the same step while preserving the exact allowed status vocabulary `READY`, `CANDIDATE`, and `APPROVED`.
- Kept reads backward-compatible for schema v1/v2, but made replacement-specific writes convert approved schema-v2 state to schema v3 in the same authorized transaction only.
- Extended candidate save to allow replacement candidates on approved steps when trusted upstream inputs remain valid, while keeping the old approved stable bytes authoritative until approval.
- Extended approve/reject to support replacement decisions with unchanged decision-file layout at `workflow/revisions/decisions/<revision_group_id>.json`, including optional `replaces_approved_group_id`.
- Implemented stable replacement publication guarded by old-byte identity plus transaction-manifest `previous_sha256` and `target_sha256`, and extended recovery to resume only when old/new byte identity remains provable.
- Added generic changed-artifact detection and generic producer/consumer traversal from the pinned workflow definition; no Prompt-specific stale propagation logic was introduced.
- Added step-level `stale_reason` and `invalidated_candidate_group_id` metadata only; stale stable files remain inspectable but no longer satisfy downstream workflow-produced required inputs.
- Extended `scripts/channel_prompt_bundle.py` so stale workflow-produced required inputs fail closed with `STALE_INPUT_ARTIFACT`, while stale steps themselves may still build replacement bundles when their own upstream inputs are trusted.
- Extended the embedded UI in `scripts/ui_server.py` minimally with replacement save labeling, stale badges/notices, invalidated-candidate notices, and replacement approve/reject readiness while keeping history/restore/diff out of scope.

## Phase 7C2C3A Evidence
- Focused workflow-write regression: `python -m unittest tests.test_channel_workflow_write` passing (`71` run, `70` passed, `0` failures, `0` errors, `1` skipped for unsupported symlink capability in this environment).
- Focused output-parser regression: `python -m unittest tests.test_channel_output_parser` passing.
- Focused workflow regression: `python -m unittest tests.test_channel_workflow` passing with the existing environment-dependent symlink skip.
- Focused prompt-bundle regression: `python -m unittest tests.test_channel_prompt_bundle` passing (`20` run, `20` passed, `0` failures, `0` errors, `0` skipped).
- Focused V2 backend regression: `python -m unittest tests.test_multichannel_api` passing (`58` run, `58` passed, `0` failures, `0` errors, `0` skipped).
- Focused frontend contract plus runtime harness: `python -m unittest tests.test_ui_frontend_contract` passing (`40` run, `40` passed, `0` failures, `0` errors, `0` skipped).
- Explicit Node-backed runtime harness: `python -m unittest tests.test_ui_frontend_contract.UiFrontendRuntimeTests` passing (`16` run, `16` passed, `0` failures, `0` errors, `0` skipped).
- Replacement-specific coverage now includes replacement save conversion, replacement rejection, replacement approval stale propagation, downstream approved-plus-candidate invalidation, stale bundle gating, and replacement recovery after decision publication before state replacement.
- Replacement-specific coverage now also proves the full replacement recovery matrix A-J, direct/transitive/branch-safe stale propagation, first-candidate invalidation, stale clearing, write-only schema-v3 conversion, and inert stale-reason rendering.
- Production workflow defaults remain unchanged: `default_version = 1`, `legacy_unpinned_version = 1`.
- Workflow v1 SHA-256 remains `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`.
- Workflow v2 SHA-256 remains `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606`.
- Prompt manifest SHA-256 remains `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602`.
- Full offline regression: `python -m unittest discover -s tests` passing (`430` run, `428` passed, `0` failures, `0` errors, `2` skipped for unsupported symlink capability in this environment).
- Protected-runtime snapshots before focused verification, after focused verification, and after full regression remained byte-identical; all new write-path tests use temporary roots only.
- No history endpoint, history UI, restore flow, diff viewer, decision-number counter, or manual stale-accept path was added.

## Phase 7C2C3A Gate
- Replacement candidate save/approve/reject now exists on the local implementation path only.
- Downstream stale propagation and stale input gating now exist without introducing any history or restore surface.
- Phase 7C2C3B history remains blocked pending a separate Tech Lead execution prompt.
- Phase 7C2C3C restore remains blocked pending a separate Tech Lead execution prompt.
- No Phase 7C2C3A commit has been created.
- No Phase 7C2C3A push has been performed.

## Phase 7C2C2 Scope
- Removed workflow-generated stable artifact scaffolding from new workflow-bound project creation in `scripts/channel_projects.py`. New projects now create only legitimate source/input artifacts plus an empty `workflow/` directory.
- Audited every active production project-creation path and confirmed there are now only two supported creators:
  - canonical `/api/v2/channels/<channel_slug>/projects` -> `scripts/channel_projects.py:create_channel_project(...)`
  - legacy `/api/create_project` -> `scripts/ui_server.py:create_project(...)`
- Kept the legacy route registered but corrected it independently so it no longer scaffolds any workflow-generated output placeholders.
- Kept output-artifact detection generic by resolving the exact pinned workflow definition and taking the union of every step `output_artifact_ids`; no Prompt-specific artifact list or Mist-of-Ages-only fallback was added.
- Preserved legitimate source/input scaffolding for competitor reference, transcript, learnings snapshot, metrics snapshot, and raw competitor metadata.
- Enforced the approved trust rule in `scripts/channel_prompt_bundle.py`: workflow-generated artifact files are trusted only when authoritative workflow state proves the producer step is `APPROVED`, an approved group exists, an approved revision head exists, no candidate head remains, and the stable bytes still match the approved revision content hash.
- Extended `scripts/channel_workflow_write.py` so approval/rejection recovery, downstream readiness, and publish-state derivation honor the same authoritative approved-artifact trust rule instead of raw stable-file existence.
- Preserved fail-closed occupied-target behavior: first approval never overwrites any existing stable canonical file, including old placeholder text, exact matching bytes, empty files, or unmanaged files at a canonical output path. The controlled result remains `STABLE_ARTIFACT_CONFLICT`.
- Completed approval/rejection verification locally: first approval now publishes stable files only when the stable target is absent; reject clears candidate state without creating stable output; interrupted approval/rejection transactions recover only through authorized write paths after lock acquisition.
- Closed the final missing recovery-evidence gap locally: approval failure before decision/stable staging completion now proves fail-closed recovery without mutation; corrupt rejection decisions stay unrecoverable without silent cleanup; reject recovery followed by idempotent replay reuses the original decision and performs no extra writes.
- Kept existing-project compatibility fail-closed: unmanaged placeholder files, empty files, matching-candidate bytes, arbitrary bytes, directories, case-colliding occupied paths, and symlink-backed occupied paths at stable output targets all fail closed without overwrite, adoption, deletion, decision creation, or state transition. No production migration is required because the real canonical project count remains `0`.

## Phase 7C2C2 Evidence
- Placeholder source classification result: `BOTH`.
- Exact placeholder-producing production paths:
  - `scripts/channel_projects.py`: `create_channel_project(...)` previously scaffolded workflow output placeholders; now removed.
  - `scripts/ui_server.py`: legacy `create_project(...)` previously scaffolded workflow output placeholders; now removed.
- Final production placeholder-eradication scan over `scripts/` returned no remaining exact workflow-placeholder creation matches.
- Legacy route disposition: `B` - the legacy project-creation route is still active and still reachable through `/api/create_project`, but it now independently obeys the same no-output-scaffolding rule as the canonical creator.
- Exact fixture sources corrected to match the approved contract:
  - `tests/test_channel_projects.py`
  - `tests/test_channel_prompt_bundle.py`
  - `tests/test_channel_output_parser.py`
  - `tests/test_channel_workflow_write.py`
  - `tests/test_multichannel_api.py`
- Focused project scaffolding regression: `python -m unittest tests.test_channel_projects` passing (`46` run, `46` passed, `0` failures, `0` errors, `0` skipped).
- Focused approval/rejection and recovery regression: `python -m unittest tests.test_channel_workflow_write` passing (`47` run, `46` passed, `0` failures, `0` errors, `1` skipped for unsupported symlink capability in this environment).
- Focused output-parser regression: `python -m unittest tests.test_channel_output_parser` passing (`22` run, `22` passed, `0` failures, `0` errors, `0` skipped).
- Focused workflow regression: `python -m unittest tests.test_channel_workflow` passing (`17` run, `16` passed, `0` failures, `0` errors, `1` skipped for unsupported symlink capability in this environment).
- Focused prompt-bundle regression: `python -m unittest tests.test_channel_prompt_bundle` passing (`19` run, `19` passed, `0` failures, `0` errors, `0` skipped).
- Focused V2 backend regression: `python -m unittest tests.test_multichannel_api` passing (`56` run, `56` passed, `0` failures, `0` errors, `0` skipped).
- Focused frontend contract regression: `python -m unittest tests.test_ui_frontend_contract` passing (`37` run, `37` passed, `0` failures, `0` errors, `0` skipped).
- Explicit Node-backed runtime harness: `python -m unittest tests.test_ui_frontend_contract.UiFrontendRuntimeTests` passing (`13` run, `13` passed, `0` failures, `0` errors, `0` skipped).
- Compile check: `python -m py_compile scripts\channel_projects.py scripts\channel_workflow_write.py scripts\channel_output_parser.py scripts\channel_prompt_bundle.py scripts\channel_workflow.py scripts\ui_server.py tests\test_channel_projects.py tests\test_channel_workflow_write.py tests\test_ui_frontend_contract.py` passing.
- Focused combined verification run across the required seven suites: `python -m unittest tests.test_channel_projects tests.test_channel_workflow_write tests.test_channel_output_parser tests.test_channel_workflow tests.test_channel_prompt_bundle tests.test_multichannel_api tests.test_ui_frontend_contract` passing (`242` run, `240` passed, `0` failures, `0` errors, `2` skipped for unsupported symlink capability in this environment).
- Full offline regression: `python -m unittest discover -s tests` passing (`400` run, `398` passed, `0` failures, `0` errors, `2` skipped for unsupported symlink capability in this environment).
- Production workflow defaults remained unchanged: `default_version = 1`, `legacy_unpinned_version = 1`.
- Workflow v1 SHA-256 remained `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`.
- Workflow v2 SHA-256 remained `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606`.
- Prompt manifest SHA-256 remained `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602`.
- Protected-runtime snapshots taken before focused verification, after focused verification, and after full regression remained byte-identical for canonical identity/profile/learnings/token plus legacy identity/learnings/token hashes.
- Real canonical project directories remained `0` and real `workflow_state.json` files remained `0`.
- No production migration is required now because the real canonical project count is `0`.
- `implement.docx` remained unrelated and untracked.

## Phase 7C2C2 Gate
- Output artifacts are no longer scaffolded before approval.
- Workflow-generated artifacts are no longer trusted from file existence alone.
- There is no placeholder overwrite exception.
- Existing occupied stable canonical paths fail closed with controlled conflict behavior.
- Approval/rejection and stable publication are now implemented and verified locally.
- Phase 7C2C3 remains blocked pending a separate Tech Lead execution prompt.

## Phase 7C2C1 Scope
- Added `scripts/channel_workflow_write.py` as the dedicated candidate-write domain module for workflow-state v2 validation, deterministic idempotency, per-project locking, staged transaction commit, incomplete-transaction recovery, and immutable candidate revision/group persistence.
- Added one new write endpoint only: `POST /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow/steps/<step_id>/revisions`.
- Kept Phase 7C2C1 candidate-only: no `active.json`, no stable canonical artifact publication, no approval, no rejection, no candidate supersede, no downstream stale propagation, no restore flow, and no history endpoint.
- Persisted `workflow/workflow_state.json` schema v2 lazily on first authorized candidate save with `state_revision`, `state_persisted`, per-step candidate summary, artifact candidate heads, and monotonic counters for group and per-artifact revision ids.
- Preserved zero-write GET behavior: absent state still synthesizes `state_revision = 0` with `state_persisted = false`; schema-v1 files still read without migration and only convert to schema v2 on an authorized write when the mapping is unambiguous.
- Added immutable candidate storage only beneath `workflow/revisions/` with server-owned paths:
  - `workflow/revisions/groups/grp_000001/metadata.json`
  - `workflow/revisions/artifacts/<artifact_id>/rev_000001/content.md`
  - `workflow/revisions/artifacts/<artifact_id>/rev_000001/metadata.json`
- Added transaction staging only beneath `workflow/_transactions/` with `.lock`, `txn_<id>/manifest.json`, `txn_<id>/next_workflow_state.json`, and staged final-file payloads; `workflow_state.json` is replaced last.
- Added deterministic idempotent replay keyed by channel slug, project slug, workflow id, workflow version, step id, bundle SHA-256, and raw-output SHA-256. Identical replay now returns the existing candidate group without creating files or incrementing `state_revision`; different output while a candidate exists returns controlled `CANDIDATE_EXISTS`.
- Extended the workflow read model and embedded UI so candidate status is visible, `state_revision` and `state_persisted` are visible, `Save Candidate` is enabled only for the current valid parsed preview, and the current raw text plus parsed preview remain visible across workflow refresh after save.
- Preserved stable artifact authority: bundle building still reads only canonical project artifact paths and never consumes candidate revision content as downstream input.
- Verification round narrowed the transaction contract explicitly to a recovery-aware, state-last filesystem transaction rather than claiming full atomic multi-file semantics.
- Verification round tightened recovery classification, immutable-target validation, and lock ownership cleanup so interrupted writes reuse original ids when provable and return controlled `WORKFLOW_RECOVERY_REQUIRED` when not provable.
- Verification round tightened schema-v2 validation so candidate groups and candidate heads must match the selected step output contract, counters must stay ahead of allocated ids, and extra files in immutable candidate directories fail safely.
- Verification round made schema-v1 conversion explicit: reads remain byte-identical and zero-write, while the first authorized write converts only `READY` current-step states and seeds v2 counters from any existing revision/group directories.

## Phase 7C2C1 Evidence
- Focused workflow-write coverage: `python -m unittest tests.test_channel_workflow_write` passing (`23` run, `23` passed, `0` failures, `0` errors, `0` skipped).
- Focused parser regression: `python -m unittest tests.test_channel_output_parser` passing (`22` run, `22` passed, `0` failures, `0` errors, `0` skipped).
- Focused workflow regression: `python -m unittest tests.test_channel_workflow` passing (`17` run, `16` passed, `0` failures, `0` errors, `1` skipped for unsupported symlink capability).
- Focused prompt-bundle regression: `python -m unittest tests.test_channel_prompt_bundle` passing (`19` run, `19` passed, `0` failures, `0` errors, `0` skipped).
- Focused V2 backend regression: `python -m unittest tests.test_multichannel_api` passing (`53` run, `53` passed, `0` failures, `0` errors, `0` skipped).
- Focused frontend contract plus runtime harness: `python -m unittest tests.test_ui_frontend_contract` passing (`35` run, `35` passed, `0` failures, `0` errors, `0` skipped).
- Explicit Node-backed runtime harness: `python -m unittest tests.test_ui_frontend_contract.UiFrontendRuntimeTests` passing (`11` run, `11` passed, `0` failures, `0` errors, `0` skipped).
- Compile check: `python -m py_compile scripts\channel_workflow_write.py scripts\channel_output_parser.py scripts\channel_prompt_bundle.py scripts\channel_workflow.py scripts\ui_server.py tests\test_channel_workflow_write.py tests\test_channel_output_parser.py tests\test_ui_frontend_contract.py` passing.
- Full offline regression: `python -m unittest discover -s tests` passing (`368` run, `367` passed, `0` failures, `0` errors, `1` skipped for unsupported symlink capability).
- Production workflow defaults remain unchanged: `default_version = 1`, `legacy_unpinned_version = 1`.
- Workflow v1 SHA-256 remained `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`.
- Workflow v2 SHA-256 remained `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606`.
- Prompt manifest SHA-256 remained `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602`.
- Candidate-save tests and recovery tests used temporary roots only; no real Mist of Ages project, canonical token, or legacy source file was mutated.
- Protected-runtime snapshots taken before focused tests, after focused tests, and after full regression remained byte-identical and still confirmed `0` real canonical project directories plus `0` real `workflow_state.json` files.
- `implement.docx` remained unrelated and untracked.

## Phase 7C2C1 Gate
- Candidate persistence, workflow-state schema v2, transaction storage, and Save Candidate are now implemented locally.
- Phase 7C2C2 remains blocked pending a separate Tech Lead execution prompt for approval/rejection, stable canonical artifact publication, and candidate replacement semantics.
- No Phase 7C2C1 commit has been created.
- No Phase 7C2C1 push has been performed.

## Phase 7C2B Scope
- Added `scripts/channel_output_parser.py` as a generic zero-write parser that resolves the selected project binding, exact workflow version, exact prompt manifest output contract, exact current bundle identity, and pasted raw output entirely on the server side.
- Added one computational endpoint only: `POST /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow/steps/<step_id>/parse-output`.
- Added exact bundle SHA verification before parsing; mismatched or stale bundle identity now returns controlled `BUNDLE_IDENTITY_MISMATCH` instead of parsing against a stale contract.
- Implemented generic parser branching only by declared `response_mode`: `SINGLE_ARTIFACT`, `MULTI_ARTIFACT_TOOL_ENVELOPE`, and `MULTI_ARTIFACT_PROMPT_NATIVE`.
- Preserved exact raw output bytes in memory for SHA-256 and character-count calculation; the parser does not normalize, trim, or write raw output.
- Added structural validation only: marker presence/order/uniqueness, non-whitespace prefix, artifact-count identity, empty artifact bodies, required-heading presence, duplicate headings, and out-of-order headings.
- Added embedded UI intake in `scripts/ui_server.py` for `Paste AI Output` plus `Parse and Preview`, with memory-only state for raw output, parse request identity, parse result, and parse errors.
- Added stale parse-response protection keyed by channel slug, project slug, workflow id, workflow version, step id, bundle SHA, exact raw-output snapshot, and request generation id.
- Added generic parsed artifact preview cards with filename, status, SHA-256, character count, validation errors, and full plain-text preview content using readonly textareas only.
- Kept all Phase 7C2B behavior zero-write: no artifact writes, no workflow-state writes, no revisions, no approvals, no retries, no stale propagation, and no model/API calls.

## Phase 7C2B Evidence
- Phase 7C2A push completed earlier in this execution chain; the pushed baseline commit remains `31bde87104bd2073f87ec6229b7d1fba3b249f02` and no additional push occurred for Phase 7C2B.
- Focused parser coverage: `python -m unittest tests.test_channel_output_parser` passing (`22` run, `22` passed, `0` failures, `0` errors, `0` skipped).
- Focused frontend contract plus runtime harness: `python -m unittest tests.test_ui_frontend_contract` passing (`33` run, `33` passed, `0` failures, `0` errors, `0` skipped).
- Explicit JavaScript runtime harness: `python -m unittest tests.test_ui_frontend_contract.UiFrontendRuntimeTests` passing (`9` run, `9` passed, `0` failures, `0` errors, `0` skipped).
- Focused prompt-bundle regression: `python -m unittest tests.test_channel_prompt_bundle` passing (`19` run, `19` passed, `0` failures, `0` errors, `0` skipped).
- Focused workflow regression: `python -m unittest tests.test_channel_workflow` passing (`17` run, `16` passed, `0` failures, `0` errors, `1` skipped for unsupported symlink capability).
- Focused V2 backend regression: `python -m unittest tests.test_multichannel_api` passing (`53` run, `53` passed, `0` failures, `0` errors, `0` skipped).
- Compile check: `python -m py_compile scripts\channel_output_parser.py scripts\channel_prompt_bundle.py scripts\channel_workflow.py scripts\ui_server.py tests\test_channel_output_parser.py tests\test_ui_frontend_contract.py` passing.
- Full offline regression: `python -m unittest discover -s tests` passing (`343` run, `342` passed, `0` failures, `0` errors, `1` skipped for unsupported symlink capability).
- Diff check: `git diff --check` passing with only Git LF/CRLF working-copy warnings on modified tracked files.
- Production workflow defaults remain unchanged: `default_version = 1`, `legacy_unpinned_version = 1`.
- Workflow v1 SHA-256 remained `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`.
- Workflow v2 SHA-256 remained `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606`.
- Prompt manifest SHA-256 remained `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602`.
- Runtime-baseline investigation confirmed no real canonical project directory and no real `workflow_state.json` exist under `channels/mist_of_ages/projects/`; the earlier contrary manual report was a measurement mistake caused by `@(Get-ChildItem ... | Measure-Object).Count`, which counts the wrapped `Measure-Object` result item rather than the discovered file count.
- Protected runtime before/after snapshot across explicit runtime-harness, compile, and full-regression execution remained byte-identical for the full path set under `channels/mist_of_ages/`, `.local/mist_of_ages_channel.json`, `channel/mist_of_ages/channel_learnings_master.md`, `youtube_oauth_token.json`, and `secrets/youtube/mist_of_ages_oauth_token.json`.
- Protected runtime baseline is now recorded accurately as: canonical channel identity/profile/learnings present, canonical metrics present, legacy identity/learnings/token present, canonical token present, canonical project directories absent, and real `workflow_state.json` absent.
- Real Mist of Ages runtime paths and unrelated `implement.docx` remained untouched; all parser/write-safety coverage used temporary roots or embedded UI/runtime harnesses only.

## Phase 7C2B Gate
- In-memory output parsing and preview are now implemented locally and remain strictly zero-write.
- Phase 7C2C remains blocked pending a separate Tech Lead execution prompt for artifact writes, immutable revisions, workflow-state mutation, approval/reject/retry semantics, and stale downstream propagation.
- No Phase 7C2B commit has been created.
- No Phase 7C2B push has been performed.

## Phase 7C2A Scope
- Extended the embedded visible UI in `scripts/ui_server.py` only; no second frontend app and no backend write endpoint were added.
- Added read-only selected-project workflow state for workflow binding, workflow version, prompt-set availability, current lifecycle state, current step status, next step, and blocking reason.
- Rendered workflow steps from the workflow definition order instead of a hard-coded step count, with selected-step detail for model, conversation requirement, inputs, outputs, and resulting lifecycle state.
- Added explicit read-only bundle request flow to `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow/steps/<step_id>/bundle` only after the user clicks `Build Complete Bundle`.
- Added exact bundle preview and `Copy Complete Bundle` behavior that uses the full bundle string held in application state rather than reconstructing content from DOM fragments.
- Added stale-response and stale-identity invalidation for workflow loads and bundle loads across channel change, project change, workflow reload, and step change, plus a copy-time identity guard.
- Added bundle integrity checks so inconsistent bundle metadata is rejected instead of silently accepted.
- Added clipboard fallback behavior that still copies the exact stored bundle string when `navigator.clipboard` is unavailable or rejects.
- Added safe user-facing workflow and prompt-bundle error summaries for controlled domain errors without exposing absolute paths, traceback text, or token material.
- Kept required-input handling on Policy B: Build remains available for prompt-set-ready steps and the server-owned `BUNDLE_REQUIRED_INPUT_MISSING` response is shown as a controlled user message.
- Kept all Phase 7C2A behavior zero-write: no workflow-state creation, no artifact writes, no pasted-output handling, no parser, no approval flow, and no model/API calls.

## Phase 7C2A Evidence
- Phase 7C1 push completed before implementation; local `HEAD` now matches `origin/master` at pushed commit `9341deaa2e2e059fe21360241bae30b08d4aa81d`.
- Embedded UI contract now includes canonical workflow read and bundle read routes only for the selected channel/project/step context.
- Focused frontend contract plus runtime harness: `python -m unittest tests.test_ui_frontend_contract` passing (`27` run, `27` passed, `0` failures, `0` errors, `0` skipped).
- Focused workflow regression: `python -m unittest tests.test_channel_workflow` passing (`17/17`, `1` symlink-capability skip on unsupported Windows environments).
- Focused prompt-bundle regression: `python -m unittest tests.test_channel_prompt_bundle` passing (`19/19`).
- Focused V2 backend regression: `python -m unittest tests.test_multichannel_api` passing (`48/48`).
- Explicit JavaScript runtime harness: `python -m unittest tests.test_ui_frontend_contract.UiFrontendRuntimeTests` passing (`5` run, `5` passed, `0` failures, `0` errors, `0` skipped); the harness executes the embedded UI script with a mocked DOM/fetch/clipboard environment through the local Node runtime.
- JavaScript syntax check for the embedded UI script passed locally through a local parse-only Node check.
- Compile check: `python -m py_compile scripts\ui_server.py tests\test_ui_frontend_contract.py` passing.
- Full offline regression: `python -m unittest discover -s tests` passing (`305/305`, `1` skipped).
- Diff check: `git diff --check` passing with only LF/CRLF working-copy warnings from Git on modified tracked files.
- Production workflow defaults remain unchanged: `default_version = 1`, `legacy_unpinned_version = 1`.
- Workflow v1 SHA-256 remained `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`.
- Workflow v2 SHA-256 remained `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606`.
- Prompt manifest SHA-256 remained `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602`.
- All UI/bundle safety checks continued to use temporary roots or embedded contract inspection only; the real Mist of Ages runtime snapshot remained unchanged.

## Phase 7C2A Gate
- Read-only workflow inspection and exact bundle copy are now implemented locally.
- Phase 7C2B remains blocked pending a separate Tech Lead execution prompt for pasted AI output plus in-memory parse/preview only.
- Phase 7C2C remains blocked pending a later separate Tech Lead execution prompt for artifact writes, revisions, and workflow-state mutation.
- No Phase 7C2A commit has been created.
- No Phase 7C2A push has been performed.

## Phase 7C1 Scope
- Verified the approved source document `Mist_of_Ages_Prompt_Content_AI_Toi_Uu_V2.docx` by exact SHA-256 `3D63D7049BA69CFF7B87537429D145B742394138864BB06F41E0B21FEA0EC772`.
- Added `scripts/prompt_source_ingest.py` for exact-source verification, DOCX text extraction, and deterministic prompt-body normalization into canonical Markdown files.
- Added immutable workflow v2 assets under `workflows/mist_of_ages_assisted_content/v2/` with seven canonical prompt Markdown files and a cross-validated prompt manifest.
- Extended `scripts/channel_workflow.py` so workflow definitions can declare prompt-set availability metadata safely.
- Added `scripts/channel_prompt_bundle.py` for generic prompt-manifest loading, digest verification, output-contract validation, and deterministic read-only bundle construction from exact workflow bindings plus project artifacts.
- Added `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow/steps/<step_id>/bundle` in `scripts/ui_server.py`.
- Added focused bundle coverage in `tests/test_channel_prompt_bundle.py` for portable DOCX-fixture extraction, v1 immutability, manifest validation, topic derivation, bundle determinism, API behavior, and runtime isolation.
- Kept workflow execution writes, output parsing, artifact writes, approvals, retries, stale propagation, UI changes, and model/API calls out of scope.

## Phase 7C1 Evidence
- Source document filename: `Mist_of_Ages_Prompt_Content_AI_Toi_Uu_V2.docx`
- Source SHA-256: `3D63D7049BA69CFF7B87537429D145B742394138864BB06F41E0B21FEA0EC772`
- Workflow v1 definition SHA-256: `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E` (unchanged)
- Workflow v2 definition path: `workflows/mist_of_ages_assisted_content/v2/workflow.json`
- Workflow v2 definition SHA-256: `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606`
- Prompt manifest path: `workflows/mist_of_ages_assisted_content/v2/prompts/manifest.json`
- Prompt manifest SHA-256: `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602`
- Prompt 2 Topic context source: canonical competitor metadata title at `input/_raw/competitor_video.json:title`
- Prompt 5 pronunciation notes contract: optional contextual input only, explicitly reported as not provided, with no canonical file path introduced
- Default and legacy-unpinned workflow versions remain `1`.
- Bundle endpoint: `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow/steps/<step_id>/bundle`
- Focused prompt-bundle tests: `python -m unittest tests.test_channel_prompt_bundle` passing portably with no external-DOCX dependency in the required suite; optional operator audit may be run separately when the approved source file is available locally
- Compile check: `python -m py_compile scripts\prompt_source_ingest.py scripts\channel_prompt_bundle.py scripts\channel_workflow.py scripts\ui_server.py tests\test_channel_prompt_bundle.py` passing
- Full offline regression: `python -m unittest discover -s tests` passing after Phase 7C1 changes
- All prompt-bundle and API write-safety checks used temporary roots only; the real Mist of Ages runtime snapshot remained unchanged.

## Phase 7B Scope
- Added file-driven workflow loading in `workflows/registry.json` and `workflows/mist_of_ages_assisted_content/v1/workflow.json`.
- Added generic workflow registry, definition, digest, binding, and state validation in `scripts/channel_workflow.py`.
- Added immutable `workflow_binding` capture at project creation time only when the selected channel has a configured default workflow.
- Preserved backward-compatible `project.json` schema version `2`; existing legacy projects without a binding remain readable.
- Added `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow` with explicit channel/project scoping, synthesized legacy binding support, and no filesystem writes.
- Kept workflow execution, artifact writes, approvals, retries, stale propagation, prompt bundles, and UI changes out of scope.

## Phase 7B Evidence
- Production workflow registry path: `workflows/registry.json`
- Production workflow definition path: `workflows/mist_of_ages_assisted_content/v1/workflow.json`
- Production definition SHA-256: `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`
- Focused workflow tests: `python -m unittest tests.test_channel_workflow` passing (`13/13`)
- Focused project regression: `python -m unittest tests.test_channel_projects` passing (`43/43`)
- Focused V2 API regression: `python -m unittest tests.test_multichannel_api` passing (`48/48`)
- Verification-round focused workflow tests: `python -m unittest tests.test_channel_workflow` passing (`17/17`, `1` symlink-capability skip on unsupported Windows environments)
- Compile check: `python -m py_compile scripts\channel_workflow.py scripts\channel_projects.py scripts\ui_server.py tests\test_channel_workflow.py` passing
- Full offline regression: `python -m unittest discover -s tests` passing (`281/281`, `1` skipped)
- Temporary v2 fixture test proved the generic loader/read model handled eight steps, changed order, changed model, added artifact, and default-version pinning without changing application workflow business logic.
- Schema-version decision: `project.json.schema_version` remains `2` because Phase 7B adds only an optional additive `workflow_binding` field, existing readers already tolerate extra keys, and both legacy and new version-2 projects remain distinguishable by `workflow_binding` presence.
- `legacy_unpinned_version` is compatibility-pinned for legacy unbound projects and must remain stable unless a separately approved migration plan changes legacy-project behavior.
- Legacy synthesized-binding GET coverage proved no `project.json` rewrite and no `workflow_state.json` creation during reads.
- Runtime isolation coverage continued to use temporary roots only and preserved the real Mist of Ages runtime snapshot.

## Phase 7C1 Gate
- Prompt-set status is now `AVAILABLE` for workflow version `2` only.
- Production defaults remain pinned to workflow version `1`, so no existing project was migrated.
- Phase 7C2 remains blocked pending a separate execution prompt for prompt-output parsing, artifact writes, and workflow-state write semantics.

## Current Architecture
- Channel workspace: explicit filesystem-based `channels/<slug>/...` model with atomic metadata writes
- OAuth: isolated per-channel OAuth service now accepts migrated canonical tokens whose `expires_at` arrived as epoch seconds as well as ISO timestamps
- OAuth browser: loopback-only one-shot OAuth browser flow exists for `/api/v2/oauth/start`, with isolated state, timeout, and rollback-safe connection handling
- Projects: explicit channel-scoped project service exists with atomic project creation, transcript save protection, validation, and channel snapshot copying
- UI: the current running UI remains embedded directly in `scripts/ui_server.py`; the visible frontend uses only canonical `/api/v2/` routes for channel reads, OAuth start, metrics sync, project list/detail, transcript save, and validation; raw-path opening remains disabled in the visible UI while backend compatibility routes stay registered for rollback
- Metrics: isolated per-channel metrics sync service writes channel-level CSV, reporting state, and sanitized raw snapshots atomically; successful sync now preserves the existing channel status instead of overwriting OAuth/connectivity state
- Migration: `scripts/legacy_migration.py` now supports dry-run and rollback-safe apply; canonical Mist of Ages workspace and token remain in place without touching legacy sources; post-migration tests are isolated from real runtime state

## Tests
- UI frontend contract and Node-backed runtime harness: `python -m unittest tests.test_ui_frontend_contract` passing (`27` run, `27` passed, `0` failures, `0` errors, `0` skipped)
- Legacy migration planner/apply: `python -m unittest tests.test_legacy_migration` passing (`43/43`)
- Channel workspace: `python -m unittest tests.test_channel_workspace` passing (`15/15`)
- OAuth: `python -m unittest tests.test_channel_oauth` passing (`42/42`)
- OAuth browser flow: `python -m unittest tests.test_channel_oauth_browser` passing (`24/24`)
- Project service: `python -m unittest tests.test_channel_projects` passing (`43/43`)
- Metrics service: `python -m unittest tests.test_channel_metrics` passing (`27/27`)
- V2 backend API: `python -m unittest tests.test_multichannel_api` passing (`48/48`)
- Legacy collector: `python -m unittest tests.test_collector` passing (`5/5`)
- Full offline regression total after Phase 7C2A: `305/305` passing with `1` skipped environment-dependent test
- Compilation: `python -m py_compile scripts\ui_server.py tests\test_ui_frontend_contract.py tests\test_multichannel_api.py tests\test_legacy_migration.py tests\test_channel_workspace.py tests\test_channel_oauth.py tests\test_channel_oauth_browser.py tests\test_channel_metrics.py tests\test_channel_projects.py tests\test_collector.py` passing
- Diff check: `git diff --check` passing

## Phase 6C4 Active UI Route Inventory
- `GET /api/v2/channels`
- `GET /api/v2/channels/<channel_slug>`
- `GET /api/v2/oauth/start?channel_slug=<channel_slug>&mode=reconnect`
- `POST /api/v2/channels/<channel_slug>/sync_metrics`
- `GET /api/v2/channels/<channel_slug>/projects`
- `POST /api/v2/channels/<channel_slug>/projects`
- `GET /api/v2/channels/<channel_slug>/projects/<project_slug>`
- `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/transcript`
- `POST /api/v2/channels/<channel_slug>/projects/<project_slug>/transcript`
- `POST /api/v2/channels/<channel_slug>/projects/<project_slug>/validate`
- Active visible frontend audit confirmed no handler invokes `/api/status`, `/oauth/start`, `/api/create_project`, `/api/save_transcript`, `/api/validate`, or `/api/open_path`.

## Phase 6C4 Legacy Dependency Classification
- Legacy route handlers in `scripts/ui_server.py`: `ROLLBACK_COMPATIBILITY_ONLY`
- Legacy root token helpers and refresh flow: `ROLLBACK_COMPATIBILITY_ONLY`
- Legacy channel identity helpers: `ROLLBACK_COMPATIBILITY_ONLY`
- Legacy root project helpers and legacy root project routes: `ROLLBACK_COMPATIBILITY_ONLY`
- `ensure_dirs()` legacy initialization: `ROLLBACK_COMPATIBILITY_ONLY`
- Legacy open-path behavior: `ROLLBACK_COMPATIBILITY_ONLY`
- Migration source paths and retained legacy files: `MIGRATION_SOURCE_ONLY`
- Remaining locally retained legacy runtime files: `MIGRATION_SOURCE_ONLY`
- Backend compatibility tests and runtime-isolation fixtures: `TEST_ONLY`
- Removed unused visible-frontend constant from the embedded UI: `DEAD_FRONTEND_CODE`
- No remaining legacy item was classified as `ACTIVE_CUTOVER_BLOCKER`

## Phase 6C4 Real Read-Only Smoke
- Started the production server against the real repository root on isolated loopback port `8773`.
- Loaded the visible UI and confirmed the channel list contains `mist_of_ages`.
- Selected Mist of Ages and confirmed summary rendering for display name, handle, channel ID, status `CONNECTED`, `last_metrics_sync_at`, reporting state, metrics presence, and empty project list.
- Confirmed visible OAuth state shows reconnect availability, metrics sync eligibility remains correct for the connected channel, and project-creation inputs render without clicking any mutating control.
- No OAuth start, no metrics sync, no project creation, no transcript save, and no validation were executed.

## Phase 6C4 Temporary-Root End-to-End Smoke
- Started an isolated temporary-root server on loopback port `8774` with two sanitized canonical fixture channels: one `CONNECTED` and one `DISCONNECTED`.
- Completed the visible UI flow for the connected fixture channel: list channels, load summary, confirm empty project state, create one fixture project, load detail, save a non-sensitive test transcript, run local validation, switch channels, confirm project state clears, switch back, and re-read the persisted fixture project safely.
- Confirmed the disconnected fixture channel blocks project creation and metrics sync while still allowing read-only summary and project-list viewing.
- Captured request logs proving the visible UI used only canonical `/api/v2/...` routes during the temporary-root smoke.
- Confirmed all writes remained under `channels/connected_fixture/projects/` and that no root `projects/`, root token file, `.local/mist_of_ages_channel.json`, or `channel/mist_of_ages/` path was created in the temporary root.
- Removed the temporary fixture root completely after the smoke and stopped both smoke servers cleanly.

## Phase 6C4 Error And Stale-State Verification
- Existing and extended UI contract coverage now proves stale channel-summary, project-list, project-detail, OAuth, metrics, create-project, transcript-save, and validation responses are guarded by explicit selected-channel and selected-project request-generation checks.
- Failed create/save/validate paths preserve current UI state or draft content through the embedded frontend contract.
- Nested V2 errors and malformed responses still flow through the shared safe frontend API helper without exposing raw payloads or secrets.
- Duplicate action clicks remain blocked through busy-state gating for OAuth, metrics, create-project, transcript-save, and validation actions.

## Phase 6C4 Frontend Cleanup
- Removed the unused embedded-frontend constant `CUTOVER_PENDING_MESSAGE`.
- No broader frontend refactor was performed.

## Phase 6C3 Backend Contract Inspection
- `GET /api/v2/channels/<channel_slug>/projects` returns `{"projects": [...]}` where each project entry is the canonical summary shape: `project_slug`, `channel_slug`, `youtube_channel_id`, `source_video_id`, `source_video_url`, `status`, `workflow_input_status`, `runnable`, `created_at`, and `updated_at`.
- `POST /api/v2/channels/<channel_slug>/projects` accepts `url` and optional `project_name`; the backend owns `source_video_id` parsing, metadata fetch/normalization, and project slug generation. It returns `{"project": ...}` using the project-summary shape.
- `GET /api/v2/channels/<channel_slug>/projects/<project_slug>` returns `{"project": ...}` with the project-summary shape plus `has_content` and `has_publishing_package`.
- `POST /api/v2/channels/<channel_slug>/projects/<project_slug>/transcript` accepts `transcript` and optional `overwrite`; it returns the existing local validation result shape `{"checks": {...}, "project": {...}}`.
- `POST /api/v2/channels/<channel_slug>/projects/<project_slug>/validate` requires no special payload fields and returns the same `{"checks": {...}, "project": {...}}` shape.
- Project slug safety and ownership are enforced by the existing backend and `scripts/channel_projects.py`: traversal, path separators, wrong-channel ownership, missing workspace, malformed metadata, and duplicate source video IDs are rejected without any root `projects/` fallback.
- Stable V2 error shape remains nested and sanitized through `V2Error`: the frontend reads `error.code` and `error.message` without exposing raw OAuth data, token material, or filesystem secrets.

## Phase 6C3 Scope
- Added explicit embedded-frontend state for canonical project lists, selected project detail, transcript text, validation result, busy/error states, and project feedback scoped to channel slug plus project slug.
- Wired visible canonical project listing to `GET /api/v2/channels/<selectedChannelSlug>/projects`.
- Wired visible canonical project creation to `POST /api/v2/channels/<selectedChannelSlug>/projects` using only `url` and optional `project_name`.
- Wired selected-project detail reads to `GET /api/v2/channels/<selectedChannelSlug>/projects/<selectedProjectSlug>` and transcript reads to `GET /api/v2/channels/<selectedChannelSlug>/projects/<selectedProjectSlug>/transcript`.
- Wired transcript save to `POST /api/v2/channels/<selectedChannelSlug>/projects/<selectedProjectSlug>/transcript` and validation to `POST /api/v2/channels/<selectedChannelSlug>/projects/<selectedProjectSlug>/validate`.
- Kept visible raw-path opening disabled and preserved all legacy backend compatibility routes for rollback.

## Phase 6C3 Selection And Safety Rules
- Project state belongs only to the current explicit `selectedChannelSlug`.
- Channel changes clear old project lists, selected project state, validation state, transcript draft, and project feedback.
- No visible project action falls back to `mist_of_ages`, root `projects/`, or a prior project selected from another channel.
- Project list refresh, project creation, transcript save, and validation each bind captured channel/project slugs plus request-generation ids so late responses cannot overwrite a newer channel or project selection.
- If a refreshed list no longer contains the selected project slug, the UI safely deselects that project.
- The frontend continues to avoid legacy `/api/create_project`, `/api/save_transcript`, `/api/validate`, and `/api/open_path`.

## Phase 6C3 Test And Smoke Evidence
- Extended `tests/test_ui_frontend_contract.py` with focused assertions for project list routes, create payload shape, transcript/validate routes, project state presence, and continued absence of legacy visible mutations.
- Extended `tests/test_multichannel_api.py` with focused assertions for empty project lists and stable detail response shape.
- Local isolated smoke succeeded on loopback port `8768` using a temporary canonical fixture root only and verified:
  - fake selected channel loads without touching real Mist of Ages data
  - empty canonical project state renders safely
  - one fixture project can be created through the visible V2 UI flow
  - the created project appears in the list and detail panel
  - transcript save succeeds with fixture text only inside the temporary canonical project workspace
  - local validation succeeds and renders structured checks
  - no OAuth start, no metrics sync, no Google or YouTube API call, and no real repository project creation occurred

## Phase 6C3 Runtime Preservation
- Canonical channel identity remained `mist_of_ages` / `UCYVuamt3HabLFAicDxcsMdg` / `@mistofages`.
- Canonical status remained `CONNECTED`.
- `last_metrics_sync_at` remained present and unchanged.
- Canonical metrics remained readable with `10` data rows and readable reporting state.
- Canonical token remained present and ignored.
- Canonical profile and learnings remained unchanged.
- Legacy sources remained unchanged.
- No real canonical project directory was created.
- Remote configuration and upstream tracking remained unchanged.
- Phase 6C3 closes with approved commit-and-push only; no additional runtime mutation is authorized.
- `implement.docx` remained untouched and untracked.

## Phase 6C4 Runtime Preservation
- Canonical channel identity remained `mist_of_ages` / `UCYVuamt3HabLFAicDxcsMdg` / `@mistofages`.
- Canonical status remained `CONNECTED`.
- `last_metrics_sync_at` remained present and unchanged.
- Canonical metrics remained readable with `10` data rows and readable reporting state.
- Canonical token remained present and ignored.
- Canonical profile and learnings remained unchanged.
- Legacy sources remained unchanged.
- No real canonical project directory was created.
- Git remote and upstream state remained unchanged.
- No push occurred for Phase 6C4.
- `implement.docx` remained untouched and untracked.

## MVP Readiness Decision
- Decision: `ACCEPTED_WITH_MINOR_NON_BLOCKING_WARNINGS`
- Visible production UI now operates through canonical `/api/v2/` routes only.
- Selected-channel and selected-project scoping is explicit across the visible mutation flows.
- Real Mist of Ages runtime can be viewed safely without mutation.
- Temporary-root end-to-end project workflow succeeds without touching real runtime data.
- Remaining warnings are non-blocking and consistent with the approved MVP boundary:
  - backend rollback compatibility routes remain registered but are unreachable from the visible UI
  - legacy source files remain locally for rollback and migration evidence
  - reporting metrics remain `PENDING` by the existing product semantics
  - Windows CRLF warnings may appear during diff checks while checks still pass
- Tech Lead approved Phase 6C4 closure and accepted the Mist of Ages Multi-Channel MVP with the warnings above.
- Release baseline tag approved: `v0.1.0`
- No GitHub Release was created.
- Post-MVP work is not authorized in this phase.

## Phase 6C2 Scope
- Extended the existing embedded frontend state with separate OAuth and metrics action state, action feedback, and per-action request generation tracking.
- Wired visible OAuth start to canonical `GET /api/v2/oauth/start?channel_slug=<slug>&mode=reconnect` using the explicit selected channel only.
- Added a narrow backend compatibility adjustment so JSON-preferring UI clients receive the OAuth redirect payload without changing the tested dispatch contract used by rollback-compatible browser navigation.
- Wired visible metrics sync to canonical `POST /api/v2/channels/<slug>/sync_metrics` using only the accepted `window_days` and `recent_count` payload fields.
- Refreshed only the currently selected channel summary after successful OAuth-start acceptance or successful metrics-sync completion.
- Left project creation, project opening, transcript save, validation, collector submission, raw-path opening, and all legacy mutation routes disabled in the visible frontend.

## Phase 6C2 Action Eligibility
- OAuth action requires an explicit selected channel plus a loaded selected-channel summary.
- The visible OAuth label distinguishes disconnected versus connected channels as `Connect Channel` versus `Reconnect Channel`, while the existing backend mode remains `reconnect` for an already existing canonical workspace.
- Metrics sync requires an explicit selected channel, a loaded selected-channel summary, and channel status `CONNECTED`.
- Missing selection, stale selection, summary-unavailable state, disconnected state, and in-flight duplicate requests all block the relevant action safely.

## Phase 6C2 Safety Rules
- No action silently falls back to `mist_of_ages`.
- Duplicate OAuth and metrics requests are blocked per selected slug.
- Channel-list loading, selected-summary loading, OAuth busy state, and metrics busy state remain separate.
- Selection changes clear action feedback that belongs to the previous channel.
- Late OAuth or metrics responses are ignored when their captured slug or request generation no longer matches the current selection.
- Nested V2 errors are rendered through the shared frontend API helper without exposing raw response bodies, tokens, OAuth codes, headers, or browser state values.

## Phase 6C2 Test And Smoke Evidence
- Extended `tests/test_ui_frontend_contract.py` with focused assertions for canonical OAuth and metrics routes, duplicate/stale-request protection, and continued disabled project/collector controls.
- Added a focused backend contract test in `tests/test_multichannel_api.py` for JSON-preferring OAuth redirect handling.
- Local non-external smoke succeeded on isolated loopback port `8767` and verified:
  - the channel selector and selected-channel summary still render
  - with no selection, OAuth and metrics controls remain disabled
  - after selecting `mist_of_ages`, the visible OAuth label changes to `Reconnect Channel`
  - after selecting `mist_of_ages`, the visible metrics control becomes enabled for the connected channel
  - project and collector controls remain disabled
  - no legacy frontend route strings appear in the active embedded page source
- No browser OAuth flow, no real metrics sync, no Google or YouTube API call, and no project creation occurred during implementation or smoke testing.

## Phase 6C2 Runtime Preservation
- Canonical channel identity remained `mist_of_ages` / `UCYVuamt3HabLFAicDxcsMdg` / `@mistofages`.
- Canonical status remained `CONNECTED`.
- `last_metrics_sync_at` remained present.
- Canonical metrics remained readable with `10` data rows and readable reporting state.
- Canonical token remained present and ignored.
- Canonical profile and learnings remained unchanged.
- Legacy sources remained unchanged.
- No canonical project directory was created.
- `implement.docx` remained untouched and untracked.

## Publication Audit Result
- Reachable-history decision: `HISTORY_SAFE_FOR_PUBLIC_PUSH`
- Exact live-secret scan result: `EXACT_LIVE_SECRET_NOT_FOUND_IN_HISTORY`
- Repository integrity result: reachable history is valid; `git fsck --full` reported dangling unreachable trees only, not reachable corruption
- Ignore-rule result: narrow hardening committed in `c40d9af` to cover `.env`, `.env.*`, `.oauth-state*.json`, and `oauth-state*.json` in addition to existing runtime ignores
- Remote name: `origin`
- Remote repository: `blackshark03z/YT-collector`
- Initial push completed: yes
- Branch pushed: `master`
- Upstream established: `origin/master`
- No runtime channel data, token files, metrics files, legacy source data, or `implement.docx` were pushed
- Canonical runtime remained local and ignored throughout publication
- No tags were pushed

## Phase 6C1 Scope
- Implemented only the approved embedded-frontend read cutover inside `scripts/ui_server.py`.
- Added explicit frontend state for available channels, `selectedChannelSlug`, selected summary, loading, and error handling.
- Added a reusable `/api/v2/` frontend request helper with nested error handling and malformed-response fallback.
- Replaced the visible legacy status read with `GET /api/v2/channels` and `GET /api/v2/channels/<selectedChannelSlug>`.
- Added safe no-channel, stale-selection, loading, and disconnected states.
- Disabled not-yet-cut-over controls so the visible frontend no longer invokes `/oauth/start`, `/api/create_project`, `/api/save_transcript`, `/api/validate`, or `/api/open_path`.
- Left all backend compatibility routes in place for rollback safety.

## Phase 6C1 Frontend Contract
- No action silently falls back to `mist_of_ages`.
- Saved selection is restored only when the slug still exists in the current channel list.
- Invalid or stale saved selection is cleared from local storage.
- Each channel-scoped read derives its route from the explicit selected slug.
- Changing selection invalidates the previous summary and reloads safely.
- Late responses from older selections cannot replace the current selected-channel summary.

## Phase 6C1 Test And Smoke Evidence
- Added `tests/test_ui_frontend_contract.py` for explicit UI-contract assertions rather than full-page snapshots.
- Verified the embedded UI references `/api/v2/channels` and `/api/v2/channels/<slug>` and no longer references `/api/status` or visible legacy mutation routes.
- Verified stale-selection clearing, no fallback selection behavior, nested V2 error parsing, async supersession guards, and disabled mutation controls through focused contract tests.
- Local non-external smoke succeeded by serving the existing local app on a temporary loopback port and confirming:
  - the page renders the selected-channel summary UI
  - the embedded page references `/api/v2/`
  - the embedded page no longer references `/api/status`
  - disabled controls are rendered for not-yet-cut-over actions
  - `GET /api/v2/channels` returns the canonical Mist of Ages channel list locally without external calls
- Confirmed no GitHub remote has been added and no push has been performed during Phase 6C1.

## Phase 6C1 Runtime Preservation
- Canonical channel identity remained `mist_of_ages` / `UCYVuamt3HabLFAicDxcsMdg` / `@mistofages`.
- Canonical status remained `CONNECTED`.
- `last_metrics_sync_at` remained present.
- Canonical metrics remained readable with `10` data rows.
- Canonical token remained present and ignored.
- Canonical profile and learnings remained unchanged.
- Legacy sources remained unchanged.
- No canonical project directory was created.
- `implement.docx` remained untouched and untracked.

## Phase 6B Baseline Verification
- Verified branch `master` and exact HEAD `8312c5c`.
- Confirmed no tracked modifications exist; only unrelated untracked `implement.docx` remains.
- Confirmed canonical Mist of Ages runtime still points to `mist_of_ages` / `UCYVuamt3HabLFAicDxcsMdg` / status `CONNECTED`.
- Confirmed `last_metrics_sync_at` is present and canonical metrics remain readable with `10` data rows.
- Confirmed canonical token remains present and ignored.
- Confirmed no canonical project directory exists.
- Confirmed canonical runtime ignore rules still apply and legacy sources remain unchanged.

## Phase 6B Workflow Audit
- The current production UI has no separate `ui/index.html` or `ui/app.js`; the visible interface is embedded in `scripts/ui_server.py` as `HTML_PAGE`.
- The running UI still calls legacy single-channel endpoints: `/api/status`, `/oauth/start`, `/api/create_project`, `/api/validate`, `/api/save_transcript`, and `/api/open_path`.
- The additive canonical backend already exposes the cutover-target routes under `/api/v2/` for channel listing, channel summary, OAuth start, metrics sync, project listing, project creation, project detail, transcript read/write, validation, and safe open actions.
- There is currently no frontend channel selector, no persisted selected-channel state, no channel-scoped empty-state UI, and no project-list UI for the canonical backend.

## Phase 6B Legacy Coupling Findings
- `scripts/ui_server.py` still contains active production dependencies on legacy root paths such as `projects/`, `.local/mist_of_ages_channel.json`, `channel/mist_of_ages/channel_learnings_master.md`, and `youtube_oauth_token.json` for the current rendered UI and legacy helper routes.
- These active references are cutover blockers only where the production UI still invokes the legacy route family; the canonical `/api/v2/` backend itself is channel-scoped and uses canonical storage.
- Startup still calls `ensure_dirs()` for the legacy layout when serving the legacy UI and `/api/status`.
- Existing legacy files on disk are not blockers by themselves; the blocker is the current production UI's live dependency on them.

## Phase 6B Readiness Decision
- Decision: `READY_WITH_PRECONDITIONS`
- The multi-channel backend is sufficiently mature for UI cutover implementation.
- The remaining work is concentrated in the frontend state and route wiring, not in a missing backend architecture.
- Preconditions before safe cutover implementation:
  - replace legacy UI calls with canonical `/api/v2/` channel-scoped calls
  - introduce an explicit selected-channel UI contract and no-channel/disconnected states
  - wire project list/detail/transcript/open flows to channel-scoped canonical routes
  - verify no production UI workflow still depends on root `projects/`, root token state, or legacy Mist of Ages globals

## Proposed Phase 6C Breakdown
- Phase 6C1: frontend channel state and API client cutover inside `scripts/ui_server.py`
- Phase 6C2: OAuth and metrics UI wiring to selected-channel `/api/v2/` actions
- Phase 6C3: project list, project creation, transcript, validation, and open-action cutover
- Phase 6C4: focused smoke verification and closure of remaining production legacy references

## Phase 6C1 Gate
- Next task title: `Phase 6C1 - Frontend Channel State and V2 Read Client Cutover`
- Phase 6C1 remains blocked pending a separate execution prompt from the Tech Lead.

## Phase 6C2 Gate
- Proposed next task title: `Phase 6C2 - OAuth And Metrics UI Wiring`
- OAuth connect/reconnect, metrics sync mutation, project creation, transcript mutation, validation mutation, collector workflow actions, and open-path actions remain blocked pending a separate execution prompt from the Tech Lead.

## Proposed Next Task
- `POST_MVP_REPOSITORY_CLEANUP_PENDING`
- The post-MVP optimization proposal has been preserved as documentation only. Repository cleanup remains the next maintenance action and must be rerun from the new baseline.

## Phase 5B1 Root Cause
- Four regression tests still assumed the real repository root must not contain `channels/` or `secrets/`, which stopped being true after the authorized canonical migration in Phase 5B.
- The affected tests were `tests.test_channel_oauth.ChannelOAuthTests.test_no_real_repository_credential_or_runtime_path_is_touched`, `tests.test_multichannel_api.MultiChannelApiTests.test_no_real_repository_runtime_data_is_touched`, `tests.test_channel_metrics.ChannelMetricsTests.test_no_real_repository_path_is_touched`, and `tests.test_channel_projects.ChannelProjectTests.test_no_real_repository_runtime_folder_is_touched`.

## Phase 5B1 Correction
- Added a test-only runtime snapshot helper to capture canonical-runtime and legacy-source hashes without reading protected content recursively.
- Replaced obsolete repository-absence assertions with before/after invariance checks around temp-fixture execution.
- Kept all test fixtures isolated from the existing canonical workspace and token while preserving the real migrated runtime state unchanged.

## Phase 6A Pre-Sync Gates
- Verified branch `master` and exact HEAD `d55ca6c`.
- Confirmed only unrelated untracked `implement.docx` existed before the Phase 6A code fixes.
- Validated canonical `channel.json` for `mist_of_ages` with `UCYVuamt3HabLFAicDxcsMdg` / `Mist of Ages` / `@mistofages` and baseline status `CONNECTED`.
- Confirmed the canonical token file existed, was valid JSON, contained the required OAuth structure, and retained a refresh token.
- Confirmed canonical metrics and canonical projects were absent before the sync attempt.
- Captured runtime snapshots for canonical identity, profile, learnings, token, and all three legacy sources before any external call.
- Re-ran the required focused regression set before the real sync attempt.

## Phase 6A Runtime Compatibility Fix
- `scripts/channel_oauth.py` now accepts migrated canonical tokens whose `expires_at` field is epoch seconds instead of rejecting them before refresh logic can run.
- `scripts/ui_server.py` now keeps the selected-channel recent-video metrics path on bearer-token calls all the way through video detail lookup instead of falling back to the global API-key helper.
- `scripts/channel_workspace.py` and `scripts/channel_metrics.py` now preserve the existing channel status on successful metrics sync instead of silently rewriting it to `READY`.
- Added focused regression coverage for all three fixes in `tests/test_channel_oauth.py`, `tests/test_multichannel_api.py`, and `tests/test_channel_metrics.py`.

## Phase 6A Real Sync
- Invocation path: existing additive route `POST /api/v2/channels/mist_of_ages/sync_metrics`.
- Result: HTTP `200` with selected channel `mist_of_ages` and YouTube channel `UCYVuamt3HabLFAicDxcsMdg`.
- Metrics result: `rows_written = 10`, overall status `PENDING`, metrics status `PENDING_REACH`.
- Reporting result: reach report type was detected and persisted; reach metrics remain pending in the current implementation.
- Non-interactive token refresh: occurred successfully through the existing OAuth library during the authorized sync.
- Interactive reconnect: not required.

## Phase 6A Validation
- Metrics were written only under `channels/mist_of_ages/metrics/`.
- Persisted files are valid in the project-approved formats: CSV plus sanitized JSON state and raw snapshots.
- `reporting_state.json` identifies `mist_of_ages` and `UCYVuamt3HabLFAicDxcsMdg`.
- `last_metrics_sync_at` was recorded and the persisted metrics re-read correctly through `GET /api/v2/channels/mist_of_ages`.
- Metrics CSV still contains `10` data rows.
- No canonical project directory was created.
- Canonical profile and canonical learnings remained unchanged.
- Canonical token remained structurally valid after the non-interactive refresh and retained a refresh token.
- Legacy sources remained unchanged.
- `jesus/` was not recursively inspected.
- `implement.docx` remained untouched and untracked.

## Phase 6A1 Status-Semantics Finding
- The current architecture lists channel states including `CONNECTED` and `READY`, but it does not explicitly define a documented transition from `CONNECTED` to `READY` after a successful initial metrics sync.
- Existing migration, OAuth, and channel metadata flows consistently use `CONNECTED` to describe authenticated channel state.
- No existing project-creation guard or channel-read path demonstrated that `READY` is required after metrics sync.
- Conservative decision: successful metrics sync must preserve the existing channel status and update only metrics-specific metadata such as `last_metrics_sync_at`.
- For the real Mist of Ages runtime, local metadata was corrected back to `CONNECTED` without changing metrics artifacts or making any external API call.

## Real Dry Run
- Command: `python scripts\legacy_migration.py --root . --channel-slug mist_of_ages --dry-run --report migration_dry_run.md`
- Result: `READY_FOR_REAL_MIGRATION`
- Report path: `migration_dry_run.md`
- Legacy identity: present, valid, mapped to `UCYVuamt3HabLFAicDxcsMdg` / `Mist of Ages` / `@mistofages`
- Legacy learnings: present, non-empty, byte hash captured internally
- Legacy OAuth token: present, valid structure, refresh token present, planned canonical status `CONNECTED`
- Legacy projects: `0`
- Protected exclusions: `jesus/` present and excluded without recursive inspection
- Unclassified legacy files: none
- Canonical workspace state: `DESTINATION_ABSENT`
- Canonical token state: `DESTINATION_ABSENT`
- Canonical metrics state: `POST_MIGRATION_SYNC_REQUIRED`
- Blockers: none
- Warnings: none

## Real Apply
- Command: `python scripts\legacy_migration.py --root . --channel-slug mist_of_ages --apply`
- Result: `APPLIED`
- Canonical files created:
  - `channels/mist_of_ages/channel.json`
  - `channels/mist_of_ages/channel_profile.md`
  - `channels/mist_of_ages/channel_learnings_master.md`
  - `secrets/youtube/mist_of_ages_oauth_token.json`
- Rollback required: no
- Second apply attempt: refused safely without overwriting canonical destinations

## Validation
- Canonical `channel.json` is valid and points to `UCYVuamt3HabLFAicDxcsMdg` / `Mist of Ages` / `@mistofages`
- Canonical channel status is `CONNECTED`
- Canonical profile was generated successfully
- Canonical learnings file is byte-identical to the legacy source
- Canonical OAuth token is structurally valid and byte-identical to the legacy token source
- Refresh token remains present
- No metrics files exist yet
- No canonical projects were created

## Legacy Source Preservation
- `.local/mist_of_ages_channel.json` hash unchanged across dry run and apply
- `channel/mist_of_ages/channel_learnings_master.md` hash unchanged across dry run and apply
- `youtube_oauth_token.json` hash unchanged across dry run and apply
- Canonical runtime files unchanged during Phase 5B1 test-isolation correction
- Canonical profile and canonical learnings remained unchanged during the authorized Phase 6A sync
- Legacy token source remained unchanged while the canonical token refreshed non-interactively
- `projects/` inventory unchanged
- `jesus/` existence metadata unchanged
- `implement.docx` remained untouched and untracked

## Real Data State
- Real OAuth token moved: yes, into canonical secret destination only
- Real OAuth browser flow used: no
- Real OAuth reconnect performed: no
- Real channel workspace created: yes
- Real canonical token created: yes
- Real metrics synced: yes, one authorized selected-channel sync for canonical Mist of Ages
- Real project created through `/api/v2/`: no
- Legacy projects migrated: no
- Manual content touched: no
- Live API used: yes, one authorized metrics sync and non-interactive token refresh only

## Risks / Blockers
- No blocker remains for proving selected-channel metrics sync on canonical Mist of Ages.
- The authorized sync succeeded only after narrow, uncommitted runtime compatibility fixes for migrated token timestamps and bearer-only video detail fetches.
- Final Phase 6A semantics preserve `CONNECTED` after successful metrics sync; `READY` remains listed in architecture notes but is not used as an automatic post-sync transition.
- `/api/v2/` is still additive only; the current UI still points at legacy routes.
- ADR-002 blocks UI cutover until legacy-to-canonical migration review.
- UI cutover remained explicitly blocked during and after the Phase 6A sync.

## Next Gate
Do not begin post-MVP feature implementation. The next maintenance action is a rerun of the repository cleanup audit from the new documentation baseline.
