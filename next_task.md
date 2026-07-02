# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 7D1A2 - Blocked Pilot Cleanup and Retry Gate

## Do Not Start Yet
Do not begin Phase 7D1A2 until a separate Tech Lead execution prompt authorizes cleanup of the blocked v1 pilot project and any later retry.

## Proposed Objective
Handle the failed real pilot artifact separately from the 7D1A1 create-path fix: decide whether to archive, delete, or otherwise clean up `channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes/`, then authorize a fresh pilot retry only after cleanup rules are explicit.

## Current Phase Evidence
- Phase 7D1A1 confirmed the real blocker exactly: canonical V2 project creation silently inherited registry `default_version = 1` because no explicit binding crossed the canonical create boundary.
- Canonical create now requires explicit `workflow_id` plus `workflow_version`, uses server-owned workflow choices only, and persists the authoritative server-calculated binding.
- Registry defaults remain unchanged at `default_version = 1` and `legacy_unpinned_version = 1`.
- The blocked v1 pilot project remains untouched and byte-identical.
- Transcript save and Prompt 1 execution were not performed.
- No second real project was created.
- Cleanup and pilot retry remain blocked pending separate authorization.
- History and Restore remain deferred.

## Preconditions
- Do not mutate the blocked project without an explicit cleanup decision.
- Do not treat the blocked project as automatically migrated to workflow version `2`.
- Preserve the explicit canonical create contract from Phase 7D1A1: browser authority is limited to `workflow_id` and `workflow_version`; digest/path authority remains server-owned.
- Preserve the real-runtime baseline with exactly one canonical project directory and zero real `workflow_state.json` files unless a separate cleanup prompt explicitly authorizes change.
- Preserve workflow defaults and prompt/workflow assets unchanged.

## Required Focus
- preserve immutable project workflow bindings
- preserve channel-scoped `/api/v2/` ownership checks
- preserve server-owned workflow-option authority
- preserve zero automatic migration of existing projects
- preserve the untouched blocked pilot artifact until cleanup is separately authorized
- preserve workflow/prompt asset digests and registry default semantics

## Forbidden Work
- do not edit, validate, delete, rename, or recreate the blocked pilot project without separate authorization
- do not save the real transcript for the blocked pilot project
- do not start Prompt 1 or any later workflow step on the blocked pilot project
- do not auto-migrate existing projects to workflow version `2`
- do not change workflow defaults away from `default_version = 1` and `legacy_unpinned_version = 1`
- do not add AI API calls
- do not mutate protected runtime data outside approved temporary-root tests
- do not start History or Restore work in this cleanup phase

## Verification Requirements
- confirm explicit workflow pinning still survives registry default values remaining at v1
- confirm the blocked pilot artifact is either preserved untouched or changed only by a separately authorized cleanup action
- confirm real Mist of Ages runtime and token files remain protected from accidental mutation
- preserve the runtime-baseline methodology: compare before/after protected-runtime hashes and blocked-project hashes
- keep `/api/create_project` parity-safe with the no-output-scaffolding contract
- keep browser authority limited to selection ids/versions, never digests or paths

## Reasoning Effort
High

## Deferred Later Phase
History and Restore remain deferred

## Explicitly Blocked
- Blocked pilot cleanup remains blocked pending a separate Tech Lead execution prompt.
- Pilot retry remains blocked pending a separate Tech Lead execution prompt.
- History remains deferred.
- Restore remains deferred.

## Exact First Action
Verify the blocked pilot project state and choose an explicit cleanup/disposition plan before authorizing any fresh real pilot creation attempt.
