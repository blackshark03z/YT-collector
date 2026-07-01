# Next Task

## Status
BLOCKED_PENDING_SEPARATE_TECH_LEAD_PROMPT

## Proposed Phase
Phase 6B - Await Next Authorized Step

## Do Not Start Yet
Wait for a separate Tech Lead prompt before any additional runtime, UI, migration, or workflow action.

## Proposed Objective
Hold the repo at the committed Phase 6A boundary with canonical metrics present, canonical token valid, legacy sources preserved, and UI cutover still blocked.

## Expected Files
- no new files unless separately authorized
- canonical metrics and canonical token remaining ignored at runtime
- status documents reflecting the closed Phase 6A boundary

## Required Tests
- verify the committed Phase 6A baseline before any new work
- confirm canonical runtime files still exist and remain ignored
- confirm legacy sources remain unchanged
- confirm no UI cutover occurred

## Stop Conditions
- canonical workspace or token is missing or invalid
- committed Phase 6A boundary no longer matches the approved state
- any legacy source changed unexpectedly
- secret or runtime data becomes staged without authorization

## Forbidden Work
- do not perform UI cutover
- do not create projects
- do not run another real sync unless separately authorized
- do not reconnect OAuth unless separately authorized
- do not mutate protected `jesus/`
- do not remove legacy routes

## Verification Requirements
- confirm canonical metrics files remain valid under the canonical channel workspace only
- confirm the canonical token remains structurally valid after non-interactive refresh
- confirm legacy sources remain unchanged
- confirm status docs reflect the closed Phase 6A result
- keep channel status semantics at preserved `CONNECTED` unless a future prompt explicitly changes the architecture decision

## Migration Baseline
- canonical Mist of Ages workspace now exists
- canonical OAuth token now exists
- canonical metrics now exist from one authorized sync
- canonical projects are still absent

## Reasoning Effort
High

## Exact First Action
Wait for the next Tech Lead prompt and verify the committed baseline before acting.
