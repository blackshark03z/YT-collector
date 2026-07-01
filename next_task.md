# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
POST_MVP_PLANNING_BLOCKED_PENDING_USER_PRIORITIZATION

## Do Not Start Yet
The MVP is closed. Do not begin any post-MVP planning or implementation until the user provides a separate prioritization decision and execution prompt.

## Proposed Objective
Hold the repository at the accepted MVP baseline while waiting for the next user-prioritized scope decision.

## Expected Files
- `scripts/ui_server.py`
- updated UI-focused tests
- unchanged ignored canonical runtime files

## Required Tests
- preserve the accepted MVP baseline without introducing new runtime mutation
- preserve the canonical `/api/v2/` visible UI route inventory
- preserve the documented MVP acceptance state and release baseline tag
- canonical runtime files remain ignored
- existing backend regression suite stays green

## Stop Conditions
- canonical workspace or token is missing or invalid
- user reprioritizes the next scope or requests post-MVP implementation
- any legacy source changed unexpectedly
- secret or runtime data becomes staged without authorization

## Forbidden Work
- do not perform unapproved runtime mutation beyond the accepted MVP baseline
- do not run another real sync unless separately authorized by the execution prompt
- do not reconnect OAuth unless separately authorized by the execution prompt
- do not mutate protected `jesus/`
- do not remove legacy routes

## Verification Requirements
- confirm the documented visible UI actions remain channel-scoped and project-scoped
- confirm the selected-channel/project contract from Phases 6C1 through 6C4 remains intact
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
- MVP final acceptance is complete with decision `ACCEPTED_WITH_MINOR_NON_BLOCKING_WARNINGS`
- release baseline tag `v0.1.0` is the approved MVP reference point
- no GitHub Release was created
- post-MVP work is not yet authorized

## Reasoning Effort
High

## Exact First Action
Wait for the user's prioritization decision, then define the next post-MVP scope before making further repository changes.
