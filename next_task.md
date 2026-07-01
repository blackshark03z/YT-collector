# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 7C - Prompt Bundle Inputs and Workflow Execution Write Foundation

## Do Not Start Yet
Do not begin Phase 7C until a separate Tech Lead execution prompt authorizes it.

## Proposed Objective
Use the Phase 7B registry/definition foundation to prepare the next narrow backend layer for workflow execution reads and future writes, while still keeping runtime safety, version pinning, and channel isolation intact.

## Preconditions
- authoritative Prompt 1-7 source bodies must be provided or explicitly approved as external inputs
- prompt bundle source-of-truth and storage rules must be approved
- workflow execution write semantics must be approved separately

## Required Focus
- preserve immutable project workflow bindings
- preserve `LEGACY_SYNTHESIZED` read behavior for unbound legacy projects
- preserve zero-write GET behavior
- preserve channel-scoped `/api/v2/` ownership checks
- keep visible frontend cutover out of scope unless separately authorized

## Forbidden Work
- do not invent Prompt 1-7 bodies
- do not auto-migrate existing projects to a new workflow version
- do not add prompt editing UI
- do not add AI API calls
- do not add approval/retry/stale propagation unless separately approved
- do not mutate protected runtime data outside approved temporary-root tests

## Verification Requirements
- confirm authoritative prompt inputs exist before any prompt-bundle work starts
- confirm workflow version pinning still survives registry default changes
- confirm `legacy_unpinned_version` remains compatibility-pinned for legacy unbound projects unless a separately approved migration plan says otherwise
- confirm write tests use temporary roots only
- confirm real Mist of Ages runtime and token files remain untouched

## Reasoning Effort
High

## Exact First Action
Verify the baseline after Phase 7B, then request or locate the authoritative Prompt 1-7 source inputs before any Phase 7C execution work begins.
