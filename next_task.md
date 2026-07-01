# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 6C3 - Project And Collector UI Wiring

## Do Not Start Yet
Wait for a separate execution prompt from the Tech Lead before any project workflow cutover, transcript/validation wiring, collector submission flow, or other Phase 6C3 work.

## Proposed Objective
Wire the embedded selected-channel frontend to canonical project and collector workflow routes without reintroducing legacy single-channel mutations or changing current runtime data unexpectedly.

## Expected Files
- `scripts/ui_server.py`
- updated UI-focused tests
- unchanged ignored canonical runtime files

## Required Tests
- selected channel scopes project creation and collector workflow actions
- visible project and collector controls use canonical `/api/v2/` channel APIs only
- safe empty, disconnected, and in-progress states
- no legacy root token or root project writes through the visible UI
- canonical runtime files remain ignored
- existing backend regression suite stays green

## Stop Conditions
- canonical workspace or token is missing or invalid
- selected-channel project or collector action cannot be enforced safely
- any legacy source changed unexpectedly
- secret or runtime data becomes staged without authorization

## Forbidden Work
- do not perform unapproved runtime mutation beyond the authorized Phase 6C3 scope
- do not run another real sync unless separately authorized by the execution prompt
- do not reconnect OAuth unless separately authorized by the execution prompt
- do not mutate protected `jesus/`
- do not remove legacy routes

## Verification Requirements
- confirm visible UI actions remain channel-scoped
- confirm the selected-channel storage contract from Phase 6C1 and Phase 6C2 remains intact
- confirm canonical metrics files remain valid under the canonical channel workspace only
- confirm the canonical token remains structurally valid and ignored
- confirm legacy sources remain unchanged
- confirm no production UI project or collector control depends on legacy root token state, legacy root project paths, or legacy Mist of Ages globals
- keep channel status semantics at preserved `CONNECTED`

## Migration Baseline
- canonical Mist of Ages workspace now exists
- canonical OAuth token now exists
- canonical metrics now exist from one authorized sync
- canonical projects are still absent
- selected-channel V2 read cutover is implemented in the embedded frontend
- visible OAuth and metrics controls are wired to canonical V2 routes
- project and collector controls remain intentionally disabled pending later phases

## Reasoning Effort
High

## Exact First Action
Wait for the separate Phase 6C3 execution prompt, then verify the approved selected-channel frontend contract and limit the work to canonical project and collector UI wiring only.
