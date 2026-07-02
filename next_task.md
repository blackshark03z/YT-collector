# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 7C2C3B - Replacement History Read Surface

## Do Not Start Yet
Do not begin Phase 7C2C3B until a separate Tech Lead execution prompt authorizes it.

## Proposed Objective
Build on completed Phase 7C2C3A by adding a narrow read-only replacement-history surface only, while preserving schema v3 authority, exact bundle identity, immutable decision history, and fail-closed stable-artifact authority.

## Current Phase Evidence
- Phase 7C2C3A replacement recovery matrix A-J is now proven locally.
- Direct, transitive, branch-safe, multi-input, and multi-output stale propagation behavior is now proven locally.
- Downstream approved-plus-candidate invalidation, first-candidate invalidation, and stale clearing are now proven locally.
- Schema-v3 conversion remains write-only and locally proven.
- History and restore remain blocked; no history/restore production code exists in the current diff.

## Preconditions
- Phase 7C1 prompt assets, workflow v2, manifest, and bundle endpoint must remain the only source of truth for prompt text
- Phase 7C2B parse endpoint and UI preview must remain the only source of truth for accepted raw-output identity before any artifact write is permitted
- the completed Phase 7C2C2 trust rule must remain authoritative: workflow-generated files are trusted only from approved workflow state, never from file existence alone
- the completed Phase 7C2C2 production-path audit must remain true: both active production project creators now obey no-output-scaffolding, and no production workflow-placeholder writer remains
- no migration of existing v1-bound projects may occur without explicit authorization
- the protected real-runtime baseline must now be treated accurately as canonical channel identity/profile/learnings plus canonical metrics, legacy identity/learnings/token, and canonical token present, with no canonical project directories and no real `workflow_state.json`

## Required Focus
- preserve immutable project workflow bindings
- preserve `LEGACY_SYNTHESIZED` read behavior for unbound legacy projects
- preserve zero-write GET behavior for read routes and zero-write parse behavior for the Phase 7C2B preview path
- preserve channel-scoped `/api/v2/` ownership checks
- keep visible frontend changes narrowly limited to separately authorized 7C2C3 follow-up only
- preserve the verified Prompt 2 topic contract and the pathless optional pronunciation-notes contract from Phase 7C1
- preserve exact bundle SHA and raw-output identity matching before any candidate approval, rejection, or stable publication follow-up
- preserve the new schema-v3 approved-plus-candidate model, replacement decision compatibility, stale propagation semantics, and stale bundle gating from Phase 7C2C3A

## Forbidden Work
- do not rewrite canonical prompt bodies or prompt digests
- do not auto-migrate existing projects to workflow version `2`
- do not add prompt editing UI
- do not add AI API calls
- do not bypass the read-only bundle plus parse-preview identity checks by approving or publishing output directly from pasted text
- do not add restore behavior; Phase 7C2C3C restore remains blocked pending a separate Tech Lead execution prompt
- do not broaden history beyond the separately approved Phase 7C2C3B read surface
- do not mutate protected runtime data outside approved temporary-root tests
- do not weaken the no-placeholder-overwrite rule or occupied-target fail-closed behavior

## Verification Requirements
- confirm workflow v2 prompt-set validation still rejects tampering and path escape
- confirm workflow version pinning still survives registry default changes
- confirm `legacy_unpinned_version` remains compatibility-pinned for legacy unbound projects unless a separately approved migration plan says otherwise
- preserve the verified Phase 7C2C3A recovery model: replacement approval publishes replacement stable artifacts then decision then workflow state then cleanup; rejection publishes decision then workflow state then cleanup
- preserve the verified Phase 7C2C1 lock-ownership rule: cleanup may remove only the lock still owned by the current transaction token
- confirm the read-only UI bundle identity rules and Phase 7C2B parse identity rules still prevent stale or mismatched output acceptance
- confirm the Phase 7C2C2 trust rule still rejects unmanaged placeholder files and other occupied stable targets as approval blockers
- keep the corrected legacy route disposition intact: `/api/create_project` may remain registered, but it must stay parity-safe with the no-output-scaffolding contract
- confirm real Mist of Ages runtime and token files remain untouched
- preserve the corrected runtime-baseline methodology: compare before/after protected-runtime hashes instead of relying on zero-count assumptions or wrapped `Measure-Object` mistakes

## Reasoning Effort
High

## Deferred Later Phase
Phase 7C2C3C - Restore

## Explicitly Blocked
- Phase 7C2C3B history remains blocked pending a separate Tech Lead execution prompt.
- Phase 7C2C3C restore remains blocked pending a separate Tech Lead execution prompt.

## Exact First Action
Verify the baseline after the completed Phase 7C2C3A verification round, then define the exact separately authorized history-only Phase 7C2C3B read surface without implementing restore or any broader mutation flow.
