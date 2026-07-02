# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 7C2C - Artifact Writes, Revisions, and Workflow-State Mutation

## Do Not Start Yet
Do not begin Phase 7C2C until a separate Tech Lead execution prompt authorizes it.

## Proposed Objective
Use the approved Phase 7C2B zero-write parse/preview foundation to add the first authorized write path for accepted workflow outputs, immutable revisions, and explicit workflow-state mutation while preserving bundle identity, channel isolation, and rollback safety.

## Preconditions
- Phase 7C1 prompt assets, workflow v2, manifest, and bundle endpoint must remain the only source of truth for prompt text
- Phase 7C2B parse endpoint and UI preview must remain the only source of truth for accepted raw-output identity before any artifact write is permitted
- workflow artifact write semantics remain blocked until explicitly authorized in Phase 7C2C
- no migration of existing v1-bound projects may occur without explicit authorization
- the protected real-runtime baseline must now be treated accurately as canonical channel identity/profile/learnings plus canonical metrics, legacy identity/learnings/token, and canonical token present, with no canonical project directories and no real `workflow_state.json`

## Required Focus
- preserve immutable project workflow bindings
- preserve `LEGACY_SYNTHESIZED` read behavior for unbound legacy projects
- preserve zero-write GET behavior for read routes and zero-write parse behavior for the Phase 7C2B preview path
- preserve channel-scoped `/api/v2/` ownership checks
- keep visible frontend changes narrowly limited to write-path controls only if a separate prompt explicitly authorizes Phase 7C2C UI follow-up
- preserve the verified Prompt 2 topic contract and the pathless optional pronunciation-notes contract from Phase 7C1
- preserve exact bundle SHA and raw-output identity matching before any accepted write

## Forbidden Work
- do not rewrite canonical prompt bodies or prompt digests
- do not auto-migrate existing projects to workflow version `2`
- do not add prompt editing UI
- do not add AI API calls
- do not bypass the read-only bundle plus parse-preview identity checks by writing output files directly from pasted text
- do not add approval/retry/stale propagation unless separately approved in Phase 7C2C or later
- do not mutate protected runtime data outside approved temporary-root tests
- do not begin artifact writes, revisions, or workflow-state mutation until a separate Phase 7C2C prompt authorizes them

## Verification Requirements
- confirm workflow v2 prompt-set validation still rejects tampering and path escape
- confirm workflow version pinning still survives registry default changes
- confirm `legacy_unpinned_version` remains compatibility-pinned for legacy unbound projects unless a separately approved migration plan says otherwise
- confirm the read-only UI bundle identity rules and Phase 7C2B parse identity rules still prevent stale or mismatched output acceptance
- confirm accepted-write behavior creates only the authorized artifact/revision/workflow-state files and nothing else
- confirm real Mist of Ages runtime and token files remain untouched
- preserve the corrected runtime-baseline methodology: compare before/after protected-runtime hashes instead of relying on zero-count assumptions or wrapped `Measure-Object` mistakes

## Reasoning Effort
High

## Deferred Later Phase
Phase 7C2D - Approval, rejection, retry, and downstream stale propagation

## Exact First Action
Verify the baseline after Phase 7C2B, then define the exact accepted-write transaction boundary from parsed output identity to immutable revision plus artifact write before implementing any mutation path.
