# Next Task

## Status
BLOCKED_PENDING_PHASE_5B_EXECUTION_PROMPT

## Proposed Phase
Phase 5B - Apply Legacy Mist of Ages Migration

## Do Not Start Yet
Wait for a separate Tech Lead execution prompt.

## Proposed Objective
Apply the approved Mist of Ages migration from the verified legacy sources into the canonical `channels/mist_of_ages/` and `secrets/youtube/` layout using the exact dry-run mapping, with rollback evidence and no UI cutover.

## Expected Files
- migration-apply implementation files
- focused migration-apply tests and rollback fixtures
- updated migration report and status documents with real apply evidence only

## Required Tests
- byte-identical learnings copy verification
- token destination safety and rollback verification
- canonical `channel.json` generation verification
- transcript/workflow/content/publishing-package preservation checks
- project metadata conversion verification
- collision and rollback verification
- post-apply canonical workspace validation
- compilation and `git diff --check`

## Stop Conditions
- any source/destination hash deviates from the dry-run evidence without explanation
- rollback cannot restore pre-migration state
- canonical ownership cannot be proven
- secret or runtime data becomes staged

## Forbidden Work
- do not perform UI cutover
- do not perform live OAuth reconnect during apply
- do not sync metrics during apply
- do not mutate protected `jesus/`
- do not remove legacy routes

## Dry-Run Derived Operations
- create `channels/mist_of_ages/channel.json`
- generate `channels/mist_of_ages/channel_profile.md`
- copy `channel/mist_of_ages/channel_learnings_master.md` byte-for-byte
- copy `youtube_oauth_token.json` to `secrets/youtube/mist_of_ages_oauth_token.json` only if structure remains approved at apply time
- no legacy projects currently require migration
- leave canonical metrics absent and require post-migration selected-channel sync

## Verification Requirements
- prove `.local/mist_of_ages_channel.json`, `channel/mist_of_ages/channel_learnings_master.md`, and `youtube_oauth_token.json` match expected pre-apply identities
- record before/after hashes for copied manual files
- confirm canonical workspace paths exist only after approved apply
- confirm no transcript, workflow, content, or publishing file content was rewritten
- confirm `migration_dry_run.md` and apply docs reflect the real result

## Rollback Plan
- if any step fails after destination creation begins, remove only newly created canonical paths
- restore any replaced destination token only from the pre-apply byte snapshot
- leave all legacy source paths untouched

## Reasoning Effort
High

## Exact First Action
Re-verify the Phase 5A source hashes and destination absence, then implement an apply-only migration path with rollback before touching any real canonical path.
