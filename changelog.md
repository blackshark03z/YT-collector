# Changelog

## Unreleased

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
