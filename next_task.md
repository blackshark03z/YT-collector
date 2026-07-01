# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 7C2 - Bundle Output Parsing and Workflow Artifact Write Path

## Do Not Start Yet
Do not begin Phase 7C2 until a separate Tech Lead execution prompt authorizes it.

## Proposed Objective
Use the approved Phase 7C1 prompt bundle foundation to add the next narrow backend layer for parsing approved model outputs and writing canonical workflow artifacts, while preserving runtime safety, version pinning, and channel isolation.

## Preconditions
- Phase 7C1 prompt assets, workflow v2, manifest, and bundle endpoint must remain the only source of truth for prompt text
- workflow artifact write semantics must be approved separately
- no migration of existing v1-bound projects may occur without explicit authorization

## Required Focus
- preserve immutable project workflow bindings
- preserve `LEGACY_SYNTHESIZED` read behavior for unbound legacy projects
- preserve zero-write GET behavior for read routes
- preserve channel-scoped `/api/v2/` ownership checks
- keep visible frontend work out of scope unless separately authorized
- preserve the verified Prompt 2 topic contract and the pathless optional pronunciation-notes contract from Phase 7C1

## Forbidden Work
- do not rewrite canonical prompt bodies or prompt digests
- do not auto-migrate existing projects to workflow version `2`
- do not add prompt editing UI
- do not add AI API calls
- do not add approval/retry/stale propagation unless separately approved
- do not mutate protected runtime data outside approved temporary-root tests

## Verification Requirements
- confirm workflow v2 prompt-set validation still rejects tampering and path escape
- confirm workflow version pinning still survives registry default changes
- confirm `legacy_unpinned_version` remains compatibility-pinned for legacy unbound projects unless a separately approved migration plan says otherwise
- confirm write tests use temporary roots only
- confirm real Mist of Ages runtime and token files remain untouched

## Reasoning Effort
High

## Exact First Action
Verify the baseline after Phase 7C1, then define the narrow artifact-write contract for one workflow step before implementing any write path.
