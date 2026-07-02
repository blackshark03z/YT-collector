# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 7C2B - Paste AI Output and In-Memory Parse Preview

## Do Not Start Yet
Do not begin Phase 7C2B until a separate Tech Lead execution prompt authorizes it.

## Proposed Objective
Use the approved Phase 7C2A read-only workflow UI and exact bundle-copy foundation to add the next narrow backend layer for pasting approved AI output and parsing/previewing it in memory only, while preserving runtime safety, version pinning, and channel isolation.

## Preconditions
- Phase 7C1 prompt assets, workflow v2, manifest, and bundle endpoint must remain the only source of truth for prompt text
- Phase 7C2A read-only workflow UI must remain zero-write until the separate write-path phase is explicitly authorized
- workflow artifact write semantics must remain deferred to a later phase
- no migration of existing v1-bound projects may occur without explicit authorization

## Required Focus
- preserve immutable project workflow bindings
- preserve `LEGACY_SYNTHESIZED` read behavior for unbound legacy projects
- preserve zero-write GET behavior for read routes
- preserve channel-scoped `/api/v2/` ownership checks
- keep visible frontend changes narrowly limited to in-memory paste/preview only if a separate prompt explicitly authorizes Phase 7C2B UI follow-up
- preserve the verified Prompt 2 topic contract and the pathless optional pronunciation-notes contract from Phase 7C1

## Forbidden Work
- do not rewrite canonical prompt bodies or prompt digests
- do not auto-migrate existing projects to workflow version `2`
- do not add prompt editing UI
- do not add AI API calls
- do not bypass the read-only bundle panel by writing output files directly from pasted text
- do not add approval/retry/stale propagation unless separately approved
- do not mutate protected runtime data outside approved temporary-root tests
- do not begin artifact writes, revisions, or workflow-state mutation until a separate Phase 7C2C prompt authorizes them

## Verification Requirements
- confirm workflow v2 prompt-set validation still rejects tampering and path escape
- confirm workflow version pinning still survives registry default changes
- confirm `legacy_unpinned_version` remains compatibility-pinned for legacy unbound projects unless a separately approved migration plan says otherwise
- confirm the read-only UI bundle identity rules still prevent stale bundle copying after any Phase 7C2B changes
- confirm Phase 7C2B remains in-memory only with no artifact writes
- confirm real Mist of Ages runtime and token files remain untouched

## Reasoning Effort
High

## Deferred Later Phase
Phase 7C2C - Artifact writes, revisions, and workflow-state mutation

## Exact First Action
Verify the baseline after Phase 7C2A, then define the narrow pasted-output parse/preview contract for one workflow step before implementing any in-memory handling.
