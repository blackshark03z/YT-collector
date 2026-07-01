# Next Task

## Status
BLOCKED_PENDING_PHASE_3_REVIEW

## Proposed Phase
Phase 4 - Server Integration and Minimal Multi-Channel UI

## Do Not Start Yet
Wait for Tech Lead approval after Phase 3 review.

## Proposed Objective
Integrate the approved channel workspace, OAuth service, and channel-scoped project service into the existing server with the smallest safe multi-channel UI extension.

## Expected Files
- `scripts/ui_server.py`
- `README.md`
- `tests/` files covering integrated server behavior and route safety

## Required Tests
- channel selector and status integration
- add/connect/reconnect channel flows using mocked services
- channel-scoped project create/list/load/save/validate route coverage
- regression for legacy collector behavior that must remain stable during integration
- compilation and `git diff --check`

## Stop Conditions
- integration requires migration of real data
- running UI behavior regresses for existing single-channel use
- channel ownership can be bypassed through HTTP routes
- secret or runtime data becomes staged

## Forbidden Work
- do not migrate legacy data
- do not move the real global OAuth token
- do not perform live OAuth or live API calls
- do not redesign the frontend beyond the minimal approved server integration

## Exact First Action
Audit `scripts/ui_server.py` route-by-route and identify the smallest insertion points for channel selection and channel-scoped project operations without changing legacy behavior prematurely.
