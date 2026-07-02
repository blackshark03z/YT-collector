# Changelog

## Unreleased

### Phase 7C2B - In-Memory Output Parsing and Preview
- Added `scripts/channel_output_parser.py` as a dedicated zero-write output parser that resolves the exact selected project binding, workflow version, step output contract, and current bundle identity server-side.
- Added `POST /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow/steps/<step_id>/parse-output` in `scripts/ui_server.py` as the only computational parse endpoint for pasted AI output.
- Enforced exact bundle-identity verification before parsing by rebuilding the current bundle and comparing the authoritative SHA-256 against the request `bundle_sha256`; stale or mismatched bundle identity now fails with controlled `BUNDLE_IDENTITY_MISMATCH`.
- Implemented generic parser branching only by committed contract response modes: `SINGLE_ARTIFACT`, `MULTI_ARTIFACT_TOOL_ENVELOPE`, and `MULTI_ARTIFACT_PROMPT_NATIVE`.
- Preserved exact raw output bytes in memory for SHA-256 and character-count reporting; the parser does not normalize, trim, log, or write raw output.
- Added structural validation for required-heading presence/duplication/order, marker presence/duplication/order, unknown marker lines, non-whitespace prefix text, empty artifact bodies, and contract/artifact identity consistency.
- Added embedded UI intake for `Paste AI Output` and `Parse and Preview`, with in-memory-only state for raw text, parse identity, parse result, parse error, and stale-response generation tracking.
- Added stale parse-response protection so older parse results cannot replace newer output, newer bundle identity, or newer selected channel/project/step state.
- Added generic parsed artifact preview cards with filename, artifact id, validation status, SHA-256, character count, structural errors, and full plain-text preview content rendered through readonly textareas only.
- Extended `tests/test_channel_output_parser.py`, `tests/test_multichannel_api.py`, and `tests/test_ui_frontend_contract.py` with parser coverage for LF/CRLF, exact whitespace preservation, per-artifact heading validation, generic three-artifact parsing, malformed JSON handling, disabled-before-bundle state, no auto-parse on paste, stale-parse invalidation, parse-failure raw-text retention, and inert untrusted content rendering.
- Verification round confirmed there is no real canonical project directory and no real `workflow_state.json` under `channels/mist_of_ages/projects/`; the earlier contrary manual count was a measurement mistake from `@(Get-ChildItem ... | Measure-Object).Count`.
- Verification round recorded the protected real-runtime baseline accurately as canonical channel identity/profile/learnings plus canonical metrics, legacy identity/learnings/token, and canonical token present, with no canonical project directories and no real `workflow_state.json`.
- Verification round re-ran runtime-harness, compile, and full-regression commands with before/after protected-runtime snapshots and proved exact path-set, size, and SHA-256 equality across the protected runtime set.
- Re-ran the focused parser, frontend, prompt-bundle, workflow, and multichannel API suites successfully, then re-ran the full offline regression successfully (`343` run, `342` passed, `0` failures, `0` errors, `1` skipped).
- Confirmed production workflow defaults remained `default_version = 1` and `legacy_unpinned_version = 1`.
- Confirmed workflow v1 SHA-256 `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`, workflow v2 SHA-256 `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606`, and prompt manifest SHA-256 `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602` remained unchanged.
- Preserved the real Mist of Ages runtime, canonical token paths, legacy source files, and unrelated `implement.docx` without mutation.
- Kept artifact writes, revisions, workflow-state mutation, approval/reject/retry semantics, stale downstream propagation, migration, and model/API calls out of scope.

### Phase 7C2A - Read-Only Workflow UI and Copy Bundle
- Modified the embedded production UI in `scripts/ui_server.py` to add a read-only workflow panel inside the selected project detail area without introducing a second frontend stack.
- Added selected-project workflow loading through `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow` after successful project-detail load.
- Rendered workflow binding, version, prompt-set availability, current lifecycle state, current step, next step, blocking reason, and generic step rows directly from workflow API data.
- Added explicit selected-step state with current-step defaulting, first-step fallback, and immediate loaded-bundle invalidation on step, project, channel, or workflow change.
- Added read-only bundle request flow to `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow/steps/<step_id>/bundle` only when the user clicks `Build Complete Bundle`.
- Added safe plain-text bundle preview, bundle metadata display, and `Copy Complete Bundle` behavior using the exact full bundle string returned by the API.
- Added stale-response and stale-identity protection so older workflow or bundle responses cannot overwrite the current selected channel/project/step state or remain copyable.
- Added a copy-time identity guard and invalid-bundle rejection so stale or internally inconsistent bundles are cleared instead of copied.
- Added fallback clipboard handling that still copies the exact stored bundle string when `navigator.clipboard` is unavailable or rejects, while cleaning up the temporary element and restoring focus.
- Kept required-input handling on Policy B: Build remains available and the controlled `BUNDLE_REQUIRED_INPUT_MISSING` message is surfaced from the server when required inputs are missing.
- Added focused safe error summaries for workflow and prompt-bundle domain errors, including unavailable prompt sets, missing required inputs, missing project context, invalid workflow state, unknown step, and generic bundle failures.
- Extended `tests/test_ui_frontend_contract.py` with focused contract coverage plus a Node-backed runtime harness for workflow routes, generic step rendering, stale workflow/bundle protection, inert HTML preview behavior, exact copy behavior, and clipboard fallback cleanup.
- Re-ran focused workflow, prompt-bundle, V2 API, and frontend-contract suites successfully, then re-ran the full offline regression suite successfully (`305/305`, `1` skipped).
- Confirmed production workflow defaults remained pinned to `default_version = 1` and `legacy_unpinned_version = 1`.
- Confirmed workflow v1 SHA-256 `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`, workflow v2 SHA-256 `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606`, and prompt manifest SHA-256 `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602` remained unchanged.
- Preserved the real Mist of Ages runtime, ignored token files, protected legacy sources, and unrelated `implement.docx` without mutation.
- Kept pasted-output handling, output parsing, artifact writes, workflow-state writes, approval/retry flows, migration, and model/API calls out of scope.

### Phase 7C1 - Versioned Prompt Set Ingestion and Bundle Backend
- Verified the approved source document `Mist_of_Ages_Prompt_Content_AI_Toi_Uu_V2.docx` by exact SHA-256 `3D63D7049BA69CFF7B87537429D145B742394138864BB06F41E0B21FEA0EC772`.
- Added `scripts/prompt_source_ingest.py` to verify the approved DOCX, extract the authoritative Prompt 1-7 bodies, and normalize them deterministically into canonical UTF-8 Markdown files.
- Added immutable workflow v2 assets under `workflows/mist_of_ages_assisted_content/v2/`, including seven canonical prompt files and `prompts/manifest.json`.
- Updated `workflows/registry.json` to register version `2` while keeping `default_version` and `legacy_unpinned_version` pinned to `1`.
- Extended `scripts/channel_workflow.py` with prompt-set availability metadata validation and safe workflow-definition path resolution for versioned prompt sets.
- Added `scripts/channel_prompt_bundle.py` for generic prompt-manifest validation, prompt/source/workflow digest enforcement, project-context injection, deterministic bundle generation, and controlled prompt-bundle domain errors.
- Added `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow/steps/<step_id>/bundle` in `scripts/ui_server.py`.
- Added `tests/test_channel_prompt_bundle.py` covering portable DOCX-fixture extraction, manifest failures, v1 immutability, topic derivation, bundle determinism, API behavior, alternate prompt-set loading, and real-runtime isolation.
- Confirmed workflow v1 remained byte-identical with SHA-256 `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`.
- Confirmed workflow v2 SHA-256 `5D236DC52EC23150033E40200E9DE3CB8B589A609CD5EF9D185004C9CC4B5606` and manifest SHA-256 `E78644AA2DED747A38414D0BEFFD6A0DECB0FD671CA759FD0A8EAA7CBF539602`.
- Tightened Prompt 2 Topic handling to use only canonical competitor metadata title and to fail with a controlled error when no trustworthy topic title exists.
- Kept Prompt 5 pronunciation notes pathless and non-blocking, reported only as an optional contextual input not provided.
- Re-ran focused prompt-bundle tests successfully with a portable required suite and temporary-root-only write coverage.
- Kept UI work, model/API calls, workflow output writes, approval flows, retries, revisions, stale propagation, and production default changes out of scope.

### Phase 7B - Versioned Workflow Foundation and Read API
- Added production workflow registry data at `workflows/registry.json`.
- Added production Mist of Ages workflow definition data at `workflows/mist_of_ages_assisted_content/v1/workflow.json`.
- Added `scripts/channel_workflow.py` for generic registry loading, versioned definition validation, digest verification, immutable workflow binding resolution, and workflow state read synthesis.
- Added immutable `workflow_binding` capture to new projects in `scripts/channel_projects.py` only when the selected channel has a configured default workflow; channels without a configured workflow still create projects without an implicit fallback binding.
- Preserved backward compatibility for legacy projects with no stored binding and synthesized `binding_source: LEGACY_SYNTHESIZED` at read time without rewriting `project.json`.
- Added `GET /api/v2/channels/<channel_slug>/projects/<project_slug>/workflow` in `scripts/ui_server.py`.
- Kept project detail, transcript, validation, legacy routes, and visible UI behavior unchanged.
- Added focused workflow coverage in `tests/test_channel_workflow.py` for registry validation, definition validation, immutable binding behavior, legacy synthesized binding behavior, workflow state synthesis/validation, API isolation, updateability via a temporary v2 fixture, and runtime preservation.
- Re-ran focused regressions successfully: workflow (`13/13`), projects (`43/43`), and V2 API (`48/48`).
- Verification round confirmed `project.json.schema_version` stays at `2` because `workflow_binding` is an additive optional field and existing version-2 readers already ignore extra keys safely.
- Verification round added explicit coverage proving `legacy_unpinned_version` remains the compatibility-pinned source for legacy unbound projects when only `default_version` changes.
- Verification round added CWD-independence coverage, exact-byte digest coverage, definition-path resolution escape coverage where symlinks are supported, and full temporary-project tree before/after checks proving workflow GET creates no file or directory.
- Full offline regression now passes via `python -m unittest discover -s tests` with `281/281` passing and `1` environment-dependent skip.
- Verified production v1 definition digest `BF0845A079F4083BB1AC8101AA8846D00577C738EAA2DCDAB582FDB4A4E9935E`.
- Confirmed temporary workflow reads do not create `workflow_state.json` and do not write synthesized bindings into legacy projects.
- Confirmed all write tests used temporary roots and did not mutate the real Mist of Ages runtime or `implement.docx`.
- Prompt-set blocker remains explicit: authoritative Prompt 1-7 bodies are still absent, so `prompt_set.status` remains `MISSING` and bundle generation stays deferred.

### Post-MVP Planning Document Preservation
- Preserved the intentional post-MVP planning document as `docs/post_mvp/video_production_optimization_proposals.md`.
- Kept the proposal in documented-only state: `DOCUMENTED_FOR_LATER_RESEARCH`.
- Kept the authorization state as `NO_IMPLEMENTATION_AUTHORIZED`.
- Did not approve or implement any proposed module.
- Did not change production behavior, runtime data, legacy sources, tests, or code.
- Cleanup remains the next maintenance action and must be rerun from the new baseline.
- `implement.docx` remained unrelated and untracked.

### Phase 6C4 - End-to-End UI Smoke and Legacy Dependency Closure
- Audited the final embedded frontend route inventory in `scripts/ui_server.py` and confirmed the visible production UI now uses canonical `/api/v2/` routes for channel reads, OAuth start, metrics sync, project list/detail, transcript save, and validation.
- Confirmed the visible frontend no longer actively invokes `/api/status`, `/oauth/start`, `/api/create_project`, `/api/save_transcript`, `/api/validate`, or `/api/open_path`.
- Classified remaining legacy production items as rollback compatibility only, migration source only, test only, dead frontend code, or no-action-required; no remaining legacy item was classified as an active cutover blocker.
- Removed the unused embedded-frontend constant `CUTOVER_PENDING_MESSAGE` as conclusively dead visible-frontend code.
- Performed a real read-only smoke on isolated loopback port `8773` against the repository root and confirmed Mist of Ages summary rendering, connected-channel action state, metrics/reporting visibility, and empty project-list rendering without clicking any mutating control.
- Performed a full temporary-root end-to-end UI smoke on isolated loopback port `8774` with connected and disconnected fixture channels; verified project creation, project detail reads, transcript save, validation, channel-switch clearing, disconnected-channel blocking, fixture-only writes under canonical `channels/<fixture_slug>/projects/`, and cleanup of the entire temporary root afterward.
- Captured request logs in the temporary-root smoke proving the visible UI exercised only canonical `/api/v2/...` routes.
- Preserved the real canonical Mist of Ages runtime, canonical token ignore safety, canonical profile/learnings, canonical metrics readability, and all legacy sources with no real project creation and no external API call.
- Extended `tests/test_ui_frontend_contract.py` with the final active-route allowlist assertion and the disconnected-channel project-creation block.
- Re-ran the full required regression suite successfully with no skips or xfails.
- MVP readiness decision: `ACCEPTED_WITH_MINOR_NON_BLOCKING_WARNINGS`.
- Non-blocking warnings recorded: rollback compatibility routes remain registered but unreachable from visible UI, legacy source files remain locally for rollback evidence, reporting remains `PENDING` by current product semantics, and Windows CRLF warnings may still appear while checks pass.
- Tech Lead approved Phase 6C4 closure and accepted the Mist of Ages Multi-Channel MVP.
- The final MVP closeout will commit and push the approved Phase 6C4 changes, keep runtime data unchanged, and create release baseline tag `v0.1.0`.
- No GitHub Release was created.
- Post-MVP work remains unauthorized pending separate user prioritization.
- Proposed next task: `POST_MVP_PLANNING_BLOCKED_PENDING_USER_PRIORITIZATION`.

### Phase 6C3 - Project And Collector UI Wiring
- Modified the embedded production UI in `scripts/ui_server.py` to add selected-channel canonical project list, project creation, project detail, transcript save, and validation state without adding a separate frontend stack.
- Wired visible project listing to `GET /api/v2/channels/<selectedChannelSlug>/projects`.
- Wired visible project creation to `POST /api/v2/channels/<selectedChannelSlug>/projects` using only `url` and optional `project_name`.
- Wired selected-project detail reads to `GET /api/v2/channels/<selectedChannelSlug>/projects/<selectedProjectSlug>` and transcript reads to `GET /api/v2/channels/<selectedChannelSlug>/projects/<selectedProjectSlug>/transcript`.
- Wired transcript save to `POST /api/v2/channels/<selectedChannelSlug>/projects/<selectedProjectSlug>/transcript` and validation to `POST /api/v2/channels/<selectedChannelSlug>/projects/<selectedProjectSlug>/validate`.
- Added project-list loading/error state, empty canonical project state, selected-project detail state, transcript draft state, structured validation rendering, and project feedback scoped to channel slug plus project slug.
- Added duplicate-request and stale-response protection for project list refresh, project creation, transcript save, and validation while preserving the existing Phase 6C2 OAuth and metrics controls.
- Kept raw-path opening disabled in the visible frontend and preserved backend legacy compatibility routes for rollback.
- Extended `tests/test_ui_frontend_contract.py` and `tests/test_multichannel_api.py` with focused 6C3 contract coverage.
- Performed a local non-external smoke on isolated loopback port `8768` using a temporary fixture root only; the smoke verified empty project state, fixture project creation, detail rendering, transcript save, validation rendering, and fixture-only writes under the temporary canonical workspace.
- Preserved canonical Mist of Ages runtime data, canonical token ignore safety, canonical metrics readability, canonical profile/learnings, and all legacy sources.
- Tech Lead approved Phase 6C3 closure after the project-workflow V2 wiring, isolated smoke, and full regression rerun.
- Confirmed Phase 6C3 closes with commit and push only; no real Mist of Ages project was created and no additional runtime mutation was performed.
- Proposed next task: `Phase 6C4 - End-to-End UI Smoke and Legacy Dependency Closure`.
- Phase 6C4 remains blocked pending separate Tech Lead review and execution authorization.

### Phase 6C2 - OAuth And Metrics UI Wiring
- Modified the embedded production UI in `scripts/ui_server.py` to add selected-channel OAuth and metrics action state without creating a separate frontend stack.
- Wired visible OAuth start to canonical `GET /api/v2/oauth/start?channel_slug=<slug>&mode=reconnect` using the explicit current selected channel only.
- Added a narrow backend compatibility adjustment so JSON-preferring UI clients can receive the OAuth redirect payload safely while the existing redirect-oriented backend behavior remains available.
- Wired visible metrics sync to canonical `POST /api/v2/channels/<selectedChannelSlug>/sync_metrics` using only `window_days` and `recent_count`.
- Added separate busy, feedback, duplicate-request, and stale-selection protection for OAuth and metrics actions.
- Refreshed only the same selected-channel summary after successful OAuth-start acceptance or metrics-sync completion.
- Kept project creation, transcript save, validation, collector submission, raw-path opening, and other legacy mutation controls disabled.
- Extended `tests/test_ui_frontend_contract.py` and `tests/test_multichannel_api.py` with focused 6C2 contract coverage.
- Re-ran the required frontend, API, workspace, OAuth, metrics, project, and collector suites successfully with no external calls.
- Performed a local non-external smoke on isolated loopback port `8767` and verified selected-channel summary rendering, OAuth label state, metrics eligibility state, and continued disabled project/collector controls.
- Preserved canonical runtime data, canonical token ignore safety, canonical metrics readability, canonical profile/learnings, and all legacy sources.
- Tech Lead approved Phase 6C2 closure after the focused UI cutover wiring, regression rerun, and staged-diff secret review.
- Confirmed Phase 6C2 closes with commit and push only; Phase 6C3 remains blocked.
- Proposed next task: `Phase 6C3 - Project And Collector UI Wiring`.
- Phase 6C3 remains blocked pending a separate Tech Lead execution prompt.

### Repository History And Secret Audit + Initial GitHub Push
- Audited the complete tracked tree and all history reachable from `master` before publication.
- Confirmed no tracked file exists under `.local/`, `channels/`, `secrets/`, root `projects/`, or the local runtime token path.
- Confirmed reachable-history decision `HISTORY_SAFE_FOR_PUBLIC_PUSH`.
- Confirmed exact live-secret scan result `EXACT_LIVE_SECRET_NOT_FOUND_IN_HISTORY`.
- Ran `git fsck --full` and found dangling unreachable trees only; no reachable-history integrity blocker was found.
- Narrowly hardened `.gitignore` in `c40d9af` to cover `.env`, `.env.*`, `.oauth-state*.json`, and `oauth-state*.json` before publication.
- Added remote `origin` for `https://github.com/blackshark03z/YT-collector.git`.
- Confirmed the remote was empty before publication.
- Performed the initial push of `master` and established tracking to `origin/master`.
- Preserved canonical runtime files, canonical token ignore protections, canonical metrics, legacy source files, and unrelated `implement.docx` locally without pushing them.
- No tags were pushed and no branch other than `master` was published.
- Proposed next task: `Phase 6C2 - OAuth And Metrics UI Wiring`.
- Phase 6C2 remains blocked pending a separate Tech Lead execution prompt.

### Phase 6C1 - Frontend Channel State and V2 Read Client Cutover
- Modified the embedded production UI in `scripts/ui_server.py` to introduce explicit selected-channel frontend state with persisted slug restore and stale-selection clearing.
- Added a reusable `/api/v2/` frontend request helper with nested V2 error handling, malformed-response fallback, and async supersession safety.
- Replaced the visible legacy status read with `GET /api/v2/channels` and `GET /api/v2/channels/<selectedChannelSlug>`.
- Added safe loading, no-channel, stale-selection, and disconnected UI states for the selected canonical channel.
- Disabled visible OAuth, metrics mutation, project creation, transcript save, validation, and open-path controls so the frontend no longer invokes legacy mutation routes during the read cutover phase.
- Added `tests/test_ui_frontend_contract.py` with focused embedded-UI contract coverage for selected-channel state, V2 read usage, stale async protection, nested error handling, and disabled legacy mutation controls.
- Re-ran the required UI, API, workspace, OAuth, metrics, projects, and collector regression suites successfully with no external calls.
- Performed a local non-external smoke on a temporary loopback port and confirmed the embedded UI renders the selected-channel summary, uses `/api/v2/`, and no longer references `/api/status`.
- Preserved canonical runtime data, canonical metrics readability, canonical token ignore safety, canonical profile/learnings, and all legacy sources.
- Tech Lead approved Phase 6C1 and authorized closure only.
- Confirmed no GitHub remote was added and no push occurred during the phase.
- Proposed next task: `Repository History and Secret Audit for Initial GitHub Push`.
- OAuth, metrics mutation, project creation, transcript mutation, validation mutation, collector workflow cutover, and legacy backend-route removal remain blocked pending separate authorization.

### Phase 6B - UI Cutover Readiness Audit
- Completed a read-only audit of the current UI, route registration, channel services, project services, and tests at commit `8312c5c`.
- Tech Lead approved the audit conclusion and accepted the readiness decision `READY_WITH_PRECONDITIONS`.
- Confirmed the production UI is still embedded in `scripts/ui_server.py`; there is no separate `ui/index.html` or `ui/app.js` to cut over independently.
- Confirmed the visible UI still calls legacy single-channel routes and legacy storage helpers, while the canonical multi-channel backend already exists under `/api/v2/`.
- Classified the active legacy production dependencies, mapped the UI workflows, and built a minimal cutover phase breakdown.
- Audit result: `READY_WITH_PRECONDITIONS`.
- Preconditions are frontend/API-client cutover, explicit selected-channel state, channel-scoped project wiring, and removal of live UI dependence on legacy root paths.
- Re-ran the relevant backend and API regression suites without external calls.
- UI cutover implementation remains blocked pending a separate execution prompt for Phase 6C1.

### Phase 6A - Selected-Channel Metrics Sync
- Modified `scripts/channel_oauth.py` to accept migrated canonical tokens whose `expires_at` field is stored as epoch seconds.
- Modified `scripts/channel_workspace.py` and `scripts/channel_metrics.py` so successful metrics sync preserves the current channel status and updates only metrics metadata.
- Modified `scripts/ui_server.py` so the selected-channel recent-video metrics path uses the canonical bearer token for video-detail lookup instead of the global API-key helper.
- Modified `tests/test_channel_oauth.py`, `tests/test_multichannel_api.py`, and `tests/test_channel_metrics.py` with focused regression coverage for migrated token compatibility, bearer-only metrics fetch behavior, and preserved channel-status semantics.
- Re-ran the required focused regression suite successfully after the narrow Phase 6A fixes.
- Executed one authorized real sync through `POST /api/v2/channels/mist_of_ages/sync_metrics`.
- Persisted canonical metrics only under `channels/mist_of_ages/metrics/`, including CSV, reporting state, and sanitized raw snapshots.
- Reach reporting remained `PENDING` with the report type detected and stored by the existing implementation.
- A non-interactive canonical token refresh occurred successfully; the legacy token source remained unchanged.
- Resolved Phase 6A1 status semantics conservatively by preserving `CONNECTED` after successful metrics sync and restoring the real Mist of Ages runtime metadata locally without another API call.
- No project was created and UI cutover remained blocked.

### Phase 5B1 - Fix Post-Migration Regression Isolation
- Added `tests/runtime_isolation_helpers.py`.
- Modified `tests/test_channel_oauth.py`, `tests/test_multichannel_api.py`, `tests/test_channel_metrics.py`, and `tests/test_channel_projects.py`.
- Corrected four post-migration regression tests that still assumed the real repository must not contain canonical `channels/` or `secrets/` paths.
- Replaced obsolete repository-absence assertions with before/after runtime invariance checks against canonical and legacy file hashes.
- Confirmed the canonical runtime workspace and legacy sources remained unchanged while the tests ran.
- Re-ran the full required regression set successfully after the isolation fix.
- Metrics sync and UI cutover remain blocked pending separate Tech Lead authorization.

### Phase 5B - Apply Legacy Mist of Ages Migration
- Extended `scripts/legacy_migration.py` with an explicit rollback-safe apply API and `--apply` CLI mode.
- Expanded `tests/test_legacy_migration.py` to cover apply success, refusal to overwrite, source-hash gates, rollback, source preservation, secrecy, and second-apply safety.
- Verified the real repository gates, then ran exactly one authorized real apply command.
- Created `channels/mist_of_ages/channel.json`, `channels/mist_of_ages/channel_profile.md`, `channels/mist_of_ages/channel_learnings_master.md`, and `secrets/youtube/mist_of_ages_oauth_token.json`.
- Preserved all authorized legacy sources byte-for-byte.
- Did not inspect `jesus/`, did not modify `implement.docx`, and did not create metrics files or projects.
- Validated canonical channel identity, canonical token structure, byte-identical learnings copy, and safe second-apply refusal.
- No rollback was needed.
- Deferred selected-channel metrics sync and UI cutover.

### Phase 5A - Legacy Migration Dry Run
- Added `scripts/legacy_migration.py`.
- Added `tests/test_legacy_migration.py`.
- Added sanitized `migration_dry_run.md` from the real repository dry run.
- Added a read-only migration planner, report renderer, and `--dry-run` CLI with no apply mode.
- Verified legacy Mist of Ages identity, learnings, OAuth-token structure, protected exclusions, and canonical destination state without mutating runtime data.
- Real repository dry run returned `READY_FOR_REAL_MIGRATION`.
- Tech Lead approved the Phase 5A dry-run result and closed the phase without starting Phase 5B.
- No legacy source, token, project, transcript, workflow artifact, or protected folder content was modified.
- Deferred all real migration, canonical data creation, metrics sync, OAuth reconnect, and UI cutover work.

### Phase 4B1 - OAuth Browser and UI-Support Backend
- Added `scripts/channel_oauth_browser.py`.
- Added `tests/test_channel_oauth_browser.py`.
- Modified `scripts/channel_oauth.py` to harden rollback when a newly created workspace fails after token preparation.
- Modified `tests/test_channel_oauth.py` to cover reconnect rollback and new-workspace rollback behavior.
- Modified `scripts/ui_server.py` to add additive `/api/v2/oauth/start`, project detail, transcript read, and safe open endpoints without changing legacy HTML, JavaScript, or routes.
- Modified `tests/test_multichannel_api.py` to cover the expanded V2 endpoint surface and path-opening safety.
- Added ADR-002 to require migration review before V2 UI cutover.
- Tests passed for browser state isolation, callback handling, transaction hardening, and UI-support V2 dispatch.
- No live OAuth, no real browser launch, no Google API calls, and no real token movement occurred.
- Deferred migration dry-run and all UI cutover work.

### Phase 4A - Channel Metrics and V2 Backend
- Added `architecture_decisions.md` with ADR-001 for additive backend-before-UI rollout.
- Added `scripts/channel_metrics.py`.
- Added `tests/test_channel_metrics.py`.
- Added `tests/test_multichannel_api.py`.
- Modified `scripts/channel_workspace.py` with metrics-sync metadata update support.
- Modified `scripts/ui_server.py` to add additive `/api/v2/` multi-channel backend endpoints while preserving all legacy routes, HTML, and JavaScript behavior.
- Added channel-scoped metrics synchronization with atomic CSV/JSON writes, reporting-state persistence, sanitized raw snapshots, and selected-channel isolation.
- Added `/api/v2/` endpoints for channel listing, channel status, project listing, metrics sync, project creation, transcript save, and project validation.
- Added stable V2 JSON error responses with sanitized codes/messages and no secret payloads.
- Tests passed for metrics isolation, V2 dispatch behavior, route-level channel scoping, and legacy collector compatibility.
- No live API, live OAuth, real token movement, real metrics sync, or real project creation occurred.
- Deferred Phase 4B OAuth browser integration and minimal multi-channel UI work.

### Phase 3 - Channel-Scoped Project Service
- Added `scripts/channel_projects.py`.
- Added `tests/test_channel_projects.py`.
- Added `project_status.md`, `changelog.md`, and `next_task.md`.
- Implemented channel-scoped project creation under `channels/<slug>/projects/<project>/`.
- Added atomic project creation using a temporary sibling directory and rename-on-success behavior.
- Added byte-identical snapshot copying for channel learnings and metrics.
- Added `project.json` schema version 2 with channel ownership and snapshot metadata.
- Added transcript save protection with explicit overwrite requirement for real transcript content.
- Added channel-scoped project validation and sanitized project listing.
- Added cross-channel ownership checks for load, transcript save, and validation operations.
- Focused tests passed for project creation, snapshot behavior, transcript safety, validation, and cross-channel protection.
- No real project, workspace, OAuth token, or manual content was moved or modified.
- Deferred server route integration and multi-channel UI work.

### Phase 2 - OAuth Isolation Foundation
- Added `scripts/channel_oauth.py`.
- Added `tests/test_channel_oauth.py`.
- Modified `scripts/channel_workspace.py` with channel connection metadata update support.
- Added isolated per-channel token loading, persistence, refresh, and authenticated identity validation.
- Added rollback protection so token changes are restored if metadata update fails during connection.
- Tests passed for OAuth isolation, channel identity mismatch safety, and token refresh behavior.
- No real OAuth token was moved.
- Deferred integration with the running server and current HTTP routes.

### Phase 1 - Channel Workspace Foundation
- Added `scripts/channel_workspace.py`.
- Added `tests/test_channel_workspace.py`.
- Added channel slug validation, canonical path helpers, atomic `channel.json` writes, channel listing, and duplicate-channel protections.
- Tests passed for workspace creation, non-overwrite behavior, path safety, and metadata validation.
- No real channel workspace was created.
- Deferred OAuth integration and project routing.

### Baseline
- Created local Git baseline.
