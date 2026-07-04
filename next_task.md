# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 8A1 - Production Handoff Live Verification and Commit Review

## Do Not Start Yet
Do not begin Phase 8A1 until a separate Tech Lead execution prompt authorizes live verification of the new production-package endpoints and UI, followed by repository commit review for the narrow Production Handoff MVP diff.

## Proposed Objective
Verify the new production handoff/export behavior against the canonical production-ready pilot project, then close out the narrow repository diff safely without mutating approved runtime workflow data.

## Current Phase Evidence
- A focused read-only production export module now exists in `scripts/channel_production_export.py`.
- Supported production-package summary and ZIP download endpoints now exist in `scripts/ui_server.py`.
- The ZIP contains exactly `content.md`, `publishing_package.md`, and `manifest.json`, and the manifest is built from supported workflow/read-model identity plus approved revision metadata.
- Export currently refuses unless the selected project read model is `PRODUCTION_READY`, both required stable files exist, and their bytes match the approved final-group revision metadata.
- Focused compile verification passed, `tests.test_channel_production_export` passed (`6` tests), and the focused Production Handoff UI runtime test passed.
- The canonical pilot project remains `channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes` with `workflow_version = 2`, `state_revision = 14`, `lifecycle = PRODUCTION_READY`, and approved group `grp_000007`.
- The implementation remains local only; no commit or push has occurred.

## Preconditions
- Do not alter the live pilot runtime while verifying the production handoff/export behavior.
- Preserve workflow defaults, prompt/workflow assets, prompt manifests, registry defaults, and protected runtime unchanged.
- Preserve the current pilot project state at workflow schema `2`, state revision `14`, lifecycle `PRODUCTION_READY`, and approved group `grp_000007` until the next separate execution prompt.

## Required Focus
- preserve the narrow Production Handoff MVP diff exactly as validated
- verify the production-package summary and ZIP behavior against the supported read model only
- preserve approved stable production artifacts, workflow revisions, decisions, and workflow state unchanged
- preserve workflow/prompt asset digests and registry default semantics
- keep any later commit/push decision separate from implementation verification

## Forbidden Work
- do not mutate the real pilot project runtime in this verification/closeout gate
- do not change workflow defaults, prompt/workflow assets, manifest files, or registry data
- do not add AI API calls
- do not mutate protected runtime data outside approved focused tests
- do not start unrelated workflow phases, History work, or Restore work

## Verification Requirements
- confirm the Production Handoff diff is limited to the export module, the focused UI integration, focused tests, and the minimal status documents
- confirm no runtime or protected files are included in diff scope
- confirm the pilot remains `PRODUCTION_READY` without mutating approved artifacts or workflow state
- confirm real Mist of Ages runtime and token files remain protected from accidental mutation

## Reasoning Effort
High

## Deferred Later Phase
History and Restore remain deferred

## Explicitly Blocked
- Repository commit review remains blocked pending separate review.
- Live production-package verification remains blocked pending a separate execution prompt.
- History remains deferred.
- Restore remains deferred.

## Exact First Action
Run a read-only live verification of the production-package summary endpoint, the ZIP download endpoint, and the selected-project Production Handoff UI against the canonical `PRODUCTION_READY` pilot project, then review commit scope in a separate step.
