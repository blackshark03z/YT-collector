# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Repository History and Secret Audit for Initial GitHub Push

## Do Not Start Yet
Wait for a separate execution prompt from the Tech Lead before any repository publication, remote configuration, Phase 6C2 implementation, or push activity.

## Proposed Objective
Audit repository history, staged publication safety, and secret exposure risk before adding a GitHub remote or attempting the first push.

## Expected Files
- repository history and git-configuration review outputs only if separately authorized
- unchanged source files unless factual status-doc corrections are required
- unchanged ignored canonical runtime files

## Required Tests
- inspect git history for runtime or secret leakage risk
- verify ignore coverage for runtime and secret paths before publication
- confirm no remote is configured before the audit begins
- confirm no push occurs during the audit phase
- canonical runtime files remain ignored
- preserve the approved Phase 6C1 UI state unchanged

## Stop Conditions
- repository history contains sensitive data requiring remediation planning
- canonical workspace or token is missing or invalid
- any legacy source changed unexpectedly
- secret or runtime data becomes staged without authorization

## Forbidden Work
- do not add a GitHub remote
- do not push
- do not perform Phase 6C2 implementation work
- do not perform unapproved runtime mutation
- do not mutate protected `jesus/`
- do not remove legacy routes

## Verification Requirements
- confirm Phase 6C1 approved UI state remains unchanged
- confirm no remote has been added
- confirm no push has been attempted
- confirm canonical metrics files remain valid under the canonical channel workspace only
- confirm the canonical token remains structurally valid and ignored
- confirm legacy sources remain unchanged
- keep channel status semantics at preserved `CONNECTED`

## Migration Baseline
- canonical Mist of Ages workspace now exists
- canonical OAuth token now exists
- canonical metrics now exist from one authorized sync
- canonical projects are still absent
- selected-channel V2 read cutover is implemented in the embedded frontend
- visible mutation controls remain intentionally disabled pending later phases

## Reasoning Effort
High

## Exact First Action
Wait for the separate repository-audit execution prompt, then verify that no GitHub remote exists and inspect history/ignore coverage without modifying runtime data or starting Phase 6C2.
