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
Phase 4B1 - OAuth Browser and UI-Support Backend

## Phase Status
COMPLETE

## Repository Baseline
- Branch: master
- HEAD: 19bbd4b
- Subject: feat: add multichannel metrics and v2 api
- Working tree: Phase 4B1 source, tests, browser flow, ADR update, and status docs are uncommitted; implement.docx remains untracked

## Completed
- Phase 0: read-only architecture audit completed
- Phase 1: channel workspace foundation completed and committed
- Phase 2: isolated channel OAuth service completed and committed
- Phase 3: channel-scoped project service completed and verified locally
- Phase 4A: channel metrics service and additive `/api/v2/` backend completed and verified locally
- Phase 4B1: OAuth browser flow and UI-support backend endpoints completed and verified locally

## Current Architecture
- Channel workspace: explicit filesystem-based `channels/<slug>/...` model with atomic metadata writes
- OAuth: isolated per-channel OAuth service exists, not yet integrated into the running server
- OAuth browser: loopback-only one-shot OAuth browser flow exists for `/api/v2/oauth/start`, with isolated state, timeout, and rollback-safe connection handling
- Projects: explicit channel-scoped project service exists with atomic project creation, transcript save protection, validation, and channel snapshot copying
- UI: current running HTML and JavaScript remain unchanged; additive `/api/v2/` backend now includes OAuth start and UI-support read/open endpoints alongside legacy routes
- Metrics: isolated per-channel metrics sync service writes channel-level CSV, reporting state, and sanitized raw snapshots atomically
- Migration: not started

## Tests
- Channel workspace: `python -m unittest tests.test_channel_workspace` passing (`15/15`)
- OAuth: `python -m unittest tests.test_channel_oauth` passing (`37/37`)
- OAuth browser flow: `python -m unittest tests.test_channel_oauth_browser` passing (`24/24`)
- Project service: `python -m unittest tests.test_channel_projects` passing (`43/43`)
- Metrics service: `python -m unittest tests.test_channel_metrics` passing (`25/25`)
- V2 backend API: `python -m unittest tests.test_multichannel_api` passing (`44/44`)
- Legacy collector: `python -m unittest tests.test_collector` passing (`5/5`)
- Compilation: `python -m py_compile scripts\channel_workspace.py scripts\channel_oauth.py scripts\channel_oauth_browser.py scripts\channel_projects.py scripts\channel_metrics.py scripts\ui_server.py tests\test_channel_workspace.py tests\test_channel_oauth.py tests\test_channel_oauth_browser.py tests\test_channel_projects.py tests\test_channel_metrics.py tests\test_multichannel_api.py` passing
- Diff check: `git diff --check` passing

## Real Data State
- Real OAuth token moved: no
- Real OAuth browser flow used: no
- Real channel workspace created: no
- Real metrics synced: no
- Real project created through `/api/v2/`: no
- Legacy projects migrated: no
- Manual content touched: no
- Live API used: no

## Risks / Blockers
- No confirmed blocker in Phase 4B1 implementation.
- `/api/v2/` is still additive only; the current UI still points at legacy routes.
- ADR-002 blocks UI cutover until legacy-to-canonical migration review.

## Next Gate
Phase 4B1 review and approval before any migration dry-run or UI cutover work.
