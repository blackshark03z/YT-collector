# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 7C2C2 - Candidate Approval Boundary and Stable Publication Gate

## Do Not Start Yet
Do not begin Phase 7C2C2 until a separate Tech Lead execution prompt authorizes it.

## Proposed Objective
Use the completed Phase 7C2C1 candidate-persistence foundation to define and implement the next narrow boundary for candidate approval or rejection decisions and, only if separately authorized, the first stable canonical artifact publication path while preserving channel isolation, exact bundle identity, and rollback safety.

## Preconditions
- Phase 7C1 prompt assets, workflow v2, manifest, and bundle endpoint must remain the only source of truth for prompt text
- Phase 7C2B parse endpoint and UI preview must remain the only source of truth for accepted raw-output identity before any artifact write is permitted
- stable canonical artifact publication remains blocked until explicitly authorized in Phase 7C2C2
- no migration of existing v1-bound projects may occur without explicit authorization
- the protected real-runtime baseline must now be treated accurately as canonical channel identity/profile/learnings plus canonical metrics, legacy identity/learnings/token, and canonical token present, with no canonical project directories and no real `workflow_state.json`

## Required Focus
- preserve immutable project workflow bindings
- preserve `LEGACY_SYNTHESIZED` read behavior for unbound legacy projects
- preserve zero-write GET behavior for read routes and zero-write parse behavior for the Phase 7C2B preview path
- preserve channel-scoped `/api/v2/` ownership checks
- keep visible frontend changes narrowly limited to approval/publication controls only if a separate prompt explicitly authorizes Phase 7C2C2 UI follow-up
- preserve the verified Prompt 2 topic contract and the pathless optional pronunciation-notes contract from Phase 7C1
- preserve exact bundle SHA and raw-output identity matching before any candidate approval or stable publication

## Forbidden Work
- do not rewrite canonical prompt bodies or prompt digests
- do not auto-migrate existing projects to workflow version `2`
- do not add prompt editing UI
- do not add AI API calls
- do not bypass the read-only bundle plus parse-preview identity checks by approving or publishing output directly from pasted text
- do not add candidate supersede, downstream stale propagation, or restore behavior unless separately approved in Phase 7C2C2 or later
- do not mutate protected runtime data outside approved temporary-root tests
- do not begin artifact writes, revisions, or workflow-state mutation until a separate Phase 7C2C prompt authorizes them

## Verification Requirements
- confirm workflow v2 prompt-set validation still rejects tampering and path escape
- confirm workflow version pinning still survives registry default changes
- confirm `legacy_unpinned_version` remains compatibility-pinned for legacy unbound projects unless a separately approved migration plan says otherwise
- preserve the verified Phase 7C2C1 recovery model: recovery-aware, state-last, candidate-only filesystem transactions with no stable publication path
- preserve the verified Phase 7C2C1 lock-ownership rule: cleanup may remove only the lock still owned by the current transaction token
- confirm the read-only UI bundle identity rules and Phase 7C2B parse identity rules still prevent stale or mismatched output acceptance
- confirm candidate-only Phase 7C2C1 behavior remains intact until a separately approved approval/publication phase extends it
- confirm real Mist of Ages runtime and token files remain untouched
- preserve the corrected runtime-baseline methodology: compare before/after protected-runtime hashes instead of relying on zero-count assumptions or wrapped `Measure-Object` mistakes

## Reasoning Effort
High

## Deferred Later Phase
Phase 7C2D - Candidate supersede, restore, retry, and downstream stale propagation

## Exact First Action
Verify the baseline after the completed Phase 7C2C1 verification round, then define the exact approval/publication boundary from existing candidate group identity to stable canonical artifact authority before implementing any additional write path.
