# Next Task

## Status
BLOCKED_PENDING_PHASE_5B_REVIEW

## Proposed Phase
Phase 6A - Selected-Channel Metrics Sync

## Do Not Start Yet
Wait for Tech Lead review of the completed Phase 5B migration.

## Proposed Objective
Run the first selected-channel metrics sync against the canonical Mist of Ages workspace after migration, without UI cutover.

## Expected Files
- metrics sync evidence files under `channels/mist_of_ages/metrics/`
- focused sync validation tests if the implementation changes
- updated status documents with post-migration metrics evidence only

## Required Tests
- canonical workspace and token precondition verification
- selected-channel metrics sync success/failure handling
- no legacy-source mutation verification
- no UI cutover verification
- compilation and `git diff --check`

## Stop Conditions
- canonical workspace or token is missing or invalid
- selected-channel isolation cannot be guaranteed
- any legacy source changes unexpectedly
- secret or runtime data becomes staged

## Forbidden Work
- do not perform UI cutover
- do not create projects
- do not reconnect OAuth unless separately authorized
- do not mutate protected `jesus/`
- do not remove legacy routes

## Verification Requirements
- confirm canonical `channel.json` and canonical token remain valid
- confirm metrics files are created only under the canonical channel workspace
- confirm legacy sources remain unchanged
- confirm status docs reflect the first real metrics sync result

## Migration Baseline
- canonical Mist of Ages workspace now exists
- canonical OAuth token now exists
- canonical metrics are still absent
- canonical projects are still absent

## Reasoning Effort
High

## Exact First Action
Verify the canonical Mist of Ages workspace and token, then decide whether to authorize a selected-channel metrics sync before any UI work.
