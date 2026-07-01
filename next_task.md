# Next Task

## Status
BLOCKED_PENDING_PHASE_4B1_REVIEW

## Proposed Phase
Phase 5A - Legacy Migration Dry Run

## Do Not Start Yet
Wait for Tech Lead approval after Phase 4B1 review.

## Proposed Objective
Produce a dry-run-only migration report for the legacy Mist of Ages identity, learnings, metrics references, and project locations into the canonical `channels/mist_of_ages/` structure without mutating any real data.

## Expected Files
- migration dry-run planning/reporting files
- focused migration tests or dry-run fixtures
- documentation updates recording dry-run evidence only

## Required Tests
- legacy source discovery without mutation
- canonical destination planning without mutation
- hash/count evidence generation
- transcript/workflow/final-output preservation checks
- compilation and `git diff --check`

## Stop Conditions
- any step attempts real data movement
- hash/count evidence is incomplete
- canonical ownership cannot be proven
- secret or runtime data becomes staged

## Forbidden Work
- do not mutate legacy data
- do not move the real global OAuth token
- do not perform live OAuth, live API calls, or live UI cutover
- do not create a real canonical channel workspace
- do not remove legacy routes

## Exact First Action
Enumerate the exact legacy Mist of Ages sources and exact canonical destinations, then produce a dry-run mapping and evidence plan before touching any real file.
