# Next Task

## Status
BLOCKED_PENDING_PHASE_4A_REVIEW

## Proposed Phase
Phase 4B - OAuth Browser Integration and Minimal Multi-Channel UI

## Do Not Start Yet
Wait for Tech Lead approval after Phase 4A review.

## Proposed Objective
Integrate the approved additive `/api/v2/` backend into the existing UI with minimal channel controls and OAuth browser integration while preserving legacy fallback during the cutover.

## Expected Files
- `scripts/ui_server.py`
- `README.md`
- `tests/` files covering integrated server behavior and route safety

## Required Tests
- channel selector and status integration
- add/connect/reconnect channel flows using mocked services
- selected-channel metrics sync flow from the UI
- channel-scoped project create/list/load/save/validate route coverage
- regression for legacy collector behavior that must remain stable during integration
- compilation and `git diff --check`

## Stop Conditions
- integration requires migration of real data
- running UI behavior regresses for existing single-channel use
- channel ownership can be bypassed through HTTP routes
- secret or runtime data becomes staged
- OAuth browser integration requires moving the real global token prematurely

## Forbidden Work
- do not migrate legacy data
- do not move the real global OAuth token
- do not perform live OAuth or live API calls
- do not redesign the frontend beyond the minimal approved server integration
- do not remove legacy routes in Phase 4B

## Exact First Action
Audit the additive `/api/v2/` endpoints against the current UI controls and identify the smallest safe bridge for channel selection, OAuth connect/reconnect, metrics sync, and channel-scoped project actions.
