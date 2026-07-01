# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
POST_MVP_REPOSITORY_CLEANUP_PENDING

## Do Not Start Yet
Do not begin post-MVP feature development. The proposal has been preserved as documentation only, and the next action is a conservative repository cleanup rerun from the new baseline.

## Proposed Objective
Rerun the conservative post-MVP repository cleanup audit after preserving the planning document, while continuing to protect runtime data, legacy sources, rollback capability, and unrelated local files.

## Expected Files
- `docs/post_mvp/video_production_optimization_proposals.md`
- unchanged ignored canonical runtime files
- unchanged project status documentation

## Required Tests
- preserve the accepted MVP baseline without introducing runtime mutation
- preserve the documented-only proposal state with no implementation authorization
- preserve the release baseline tag and protected runtime ignores
- canonical runtime files remain ignored
- cleanup rerun starts from a verified baseline

## Stop Conditions
- canonical workspace or token is missing or invalid
- unexpected tracked or untracked files appear beyond the approved baseline
- any legacy source changed unexpectedly
- secret or runtime data becomes staged without authorization

## Forbidden Work
- do not implement any proposal from the preserved planning document
- do not perform unapproved runtime mutation beyond the accepted MVP baseline
- do not run another real sync unless separately authorized by the execution prompt
- do not reconnect OAuth unless separately authorized by the execution prompt
- do not mutate protected `jesus/`
- do not remove legacy routes

## Verification Requirements
- confirm the preserved proposal remains documentation only
- confirm no implementation authorization is recorded for any proposed module
- confirm canonical metrics files remain valid under the canonical channel workspace only
- confirm the canonical token remains structurally valid and ignored
- confirm legacy sources remain unchanged
- confirm cleanup can be rerun from the new baseline

## Migration Baseline
- canonical Mist of Ages workspace now exists
- canonical OAuth token now exists
- canonical metrics now exist from one authorized sync
- canonical projects are still absent
- MVP final acceptance is complete with decision `ACCEPTED_WITH_MINOR_NON_BLOCKING_WARNINGS`
- release baseline tag `v0.1.0` is the approved MVP reference point
- no GitHub Release was created
- post-MVP proposal document is preserved at `docs/post_mvp/video_production_optimization_proposals.md`
- no proposal implementation is authorized

## Reasoning Effort
High

## Exact First Action
Verify the new documentation baseline, then rerun the conservative repository cleanup audit without touching runtime data or unrelated local files.
