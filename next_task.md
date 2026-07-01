# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 6C4 - End-to-End UI Smoke and Legacy Dependency Closure

## Do Not Start Yet
Wait for a separate Tech Lead review and execution prompt before any Phase 6C4 smoke closure, legacy-dependency cleanup, or later collector workflow work.

## Proposed Objective
Close the embedded UI cutover with end-to-end smoke evidence and identify the remaining visible legacy dependencies that can be retired without breaking rollback safety or mutating current runtime data unexpectedly.

## Expected Files
- `scripts/ui_server.py`
- updated UI-focused tests
- unchanged ignored canonical runtime files

## Required Tests
- selected channel, selected project, and canonical V2 routes stay aligned through the visible UI
- visible frontend no longer depends on legacy single-channel mutation routes for the cut-over workflows
- safe smoke covers the enabled canonical read, create, transcript, and validation flows end to end
- no legacy root token or root project writes occur through the visible UI
- canonical runtime files remain ignored
- existing backend regression suite stays green

## Stop Conditions
- canonical workspace or token is missing or invalid
- visible cutover still depends on a legacy route or unsafe root-path assumption
- any legacy source changed unexpectedly
- secret or runtime data becomes staged without authorization

## Forbidden Work
- do not perform unapproved runtime mutation beyond the authorized Phase 6C4 scope
- do not run another real sync unless separately authorized by the execution prompt
- do not reconnect OAuth unless separately authorized by the execution prompt
- do not mutate protected `jesus/`
- do not remove legacy routes

## Verification Requirements
- confirm visible UI actions remain channel-scoped and project-scoped
- confirm the selected-channel/project contract from Phases 6C1 through 6C3 remains intact
- confirm canonical metrics files remain valid under the canonical channel workspace only
- confirm the canonical token remains structurally valid and ignored
- confirm legacy sources remain unchanged
- confirm no production UI cutover path depends on legacy root token state, legacy root project paths, or legacy Mist of Ages globals
- keep channel status semantics at preserved `CONNECTED`

## Migration Baseline
- canonical Mist of Ages workspace now exists
- canonical OAuth token now exists
- canonical metrics now exist from one authorized sync
- canonical projects are still absent
- selected-channel V2 read cutover is implemented in the embedded frontend
- visible OAuth and metrics controls are wired to canonical V2 routes
- visible canonical project listing, creation, transcript save, and validation are wired to canonical V2 routes
- raw-path opening and later collector actions remain intentionally disabled pending later phases
- Phase 6C3 is complete and Tech Lead approved for closure only

## Reasoning Effort
High

## Exact First Action
Wait for the separate Phase 6C4 review/execution prompt, then verify the approved selected-channel/project frontend contract and limit the work to smoke closure plus remaining visible legacy-dependency analysis only.
