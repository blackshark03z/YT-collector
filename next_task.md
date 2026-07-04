# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 7D1B3 - Commit Review and Prompt 4 Bundle Preparation Gate

## Do Not Start Yet
Do not begin Phase 7D1B3 until a separate Tech Lead execution prompt authorizes repository commit review for the narrow Prompt 3 UI capability-refresh fix and then separately authorizes Prompt 4 bundle preparation.

## Proposed Objective
Close out the narrow Prompt 3 UI capability-refresh repository diff safely, then prepare and verify the Prompt 4 bundle for the current pilot project without running Prompt 4 itself.

## Current Phase Evidence
- The Prompt 3 UI defect root cause was confirmed exactly: the embedded UI kept stale `available_actions` after Parse and Preview, so backend `save_candidate = true` could still be displayed as blocked from older capability state.
- The local frontend fix now refreshes the selected workflow read model after Parse and Preview while preserving the current selected project/step, bundle, and parsed preview.
- Focused compile verification passed and `tests.test_ui_frontend_contract` passed (`48` tests).
- The live UI retry passed: the blocked helper disappeared and `Save Candidate` became enabled for Prompt 3.
- Prompt 3 candidate `grp_000003` was saved and approved, `locked_creative_package` `rev_000001` was published to stable, workflow state revision is now `6`, and Prompt 4 is effectively `READY`.
- The exact current actionable workflow step id is `prompt_4_retention_outline`.
- The read model `next_step_id` is `prompt_5_narration_v1`.
- Repository closeout for the Prompt 3 UI capability-refresh fix is in progress and the fix has not been pushed yet.

## Preconditions
- Do not alter the live pilot runtime while reviewing commit scope for the UI capability-refresh fix.
- Preserve workflow defaults, prompt/workflow assets, prompt manifests, and registry defaults unchanged.
- Preserve the current pilot project state at workflow schema `2`, state revision `6`, Prompt 1 `APPROVED`, Prompt 2 `APPROVED`, Prompt 3 `APPROVED`, and Prompt 4 `READY` until the next separate execution prompt.

## Required Focus
- preserve the narrow Prompt 3 capability-refresh diff exactly as validated
- preserve Prompt 1 and Prompt 2 candidate workflows
- preserve the approved Prompt 2 and Prompt 3 stable artifacts and decision state unchanged
- preserve workflow/prompt asset digests and registry default semantics
- prepare Prompt 4 bundle verification only in a later separate step

## Forbidden Work
- do not modify parser implementation, workflow assets, prompt assets, or protected runtime unless a separate prompt authorizes further changes
- do not mutate the real pilot project runtime in this closeout/commit-review gate
- do not change workflow defaults or prompt/workflow assets
- do not run Prompt 4
- do not add AI API calls
- do not mutate protected runtime data outside approved temporary-root tests
- do not start History or Restore work

## Verification Requirements
- confirm the narrow UI fix changes only `scripts/ui_server.py`, `tests/test_ui_frontend_contract.py`, and the minimal status documents
- confirm no runtime or protected files are included in diff scope
- confirm the pilot remains at Prompt 4 `READY` without bundling or running Prompt 4
- confirm real Mist of Ages runtime and token files remain protected from accidental mutation

## Reasoning Effort
High

## Deferred Later Phase
History and Restore remain deferred

## Explicitly Blocked
- Repository closeout remains blocked pending separate review.
- Prompt 4 bundle preparation remains blocked pending a separate execution prompt.
- History remains deferred.
- Restore remains deferred.

## Exact First Action
Finish repository closeout for the narrow Prompt 3 capability-refresh fix, then authorize a separate Prompt 4 bundle preparation step for `prompt_4_retention_outline`.
