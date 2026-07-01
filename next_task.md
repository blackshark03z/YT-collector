# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 6C1 - Frontend Channel State and V2 Read Client Cutover

## Do Not Start Yet
Wait for a separate execution prompt from the Tech Lead before any UI cutover work.

## Proposed Objective
Switch the visible UI from legacy single-channel routes to selected-channel `/api/v2/` reads and actions, starting with explicit channel state and safe empty/disconnected handling.

## Expected Files
- `scripts/ui_server.py`
- possibly extracted UI assets if the implementation prompt explicitly allows it
- updated UI-focused tests
- unchanged ignored canonical runtime files

## Required Tests
- UI uses only canonical `/api/v2/` channel APIs
- selected channel scopes all visible actions
- safe no-channel and disconnected states
- no legacy root token or root project writes through the visible UI
- canonical runtime files remain ignored
- existing backend regression suite stays green

## Stop Conditions
- canonical workspace or token is missing or invalid
- selected-channel contract cannot be enforced safely
- any legacy source changed unexpectedly
- secret or runtime data becomes staged without authorization

## Forbidden Work
- do not perform unapproved runtime mutation
- do not run another real sync unless separately authorized
- do not reconnect OAuth unless separately authorized
- do not mutate protected `jesus/`
- do not remove legacy routes

## Verification Requirements
- confirm visible UI actions are always channel-scoped
- confirm canonical metrics files remain valid under the canonical channel workspace only
- confirm the canonical token remains structurally valid after non-interactive refresh
- confirm legacy sources remain unchanged
- confirm no production UI workflow still depends on root `projects/`, root token state, or legacy Mist of Ages globals
- keep channel status semantics at preserved `CONNECTED` unless a future prompt explicitly changes the architecture decision

## Migration Baseline
- canonical Mist of Ages workspace now exists
- canonical OAuth token now exists
- canonical metrics now exist from one authorized sync
- canonical projects are still absent

## Reasoning Effort
High

## Exact First Action
Wait for the separate Phase 6C1 execution prompt, then verify the approved selected-channel state contract and `/api/v2/` cutover scope before implementing.
