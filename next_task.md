# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 10A.4 - Live UI Verification and Commit Review

## Do Not Start Yet
Do not begin Phase 10A.4 live verification until a separate Tech Lead execution prompt authorizes verification of the simplified embedded UI, followed by repository commit review for the narrow Phase 10A diff.

## Proposed Objective
Verify the simplified operator UI against the canonical `mist_of_ages` workspace, confirm that workflow and analytics behavior remain intact without runtime mutation, then close out the narrow repository diff safely.

## Current Phase Evidence
- The embedded UI now exposes three primary work areas: `Overview`, `Content Workflow`, and `Analytics`.
- The header now surfaces selected channel, selected project, and a context-aware status badge without changing backend behavior.
- The Overview now shows deterministic operator summaries and one `Recommended Next Action` block derived from existing state only.
- The workflow workspace now uses a compact Prompt 1-7 rail, keeps only the selected step expanded, preserves all supported workflow actions, and collapses technical metadata into `Technical Details`.
- The analytics workspace now presents plain-language status, separate report-type availability versus generated-report readiness counts, a compact normalized-table view, and explicit empty-table reasons.
- Selected project persistence is now channel-scoped and restores valid project context across workspace switching, summary refreshes, project refreshes, and practical browser reloads using browser-local channel/project slugs only.
- Production-ready restored projects now recommend `Download Production Package`, and the header distinguishes `Workflow Status` from `Analytics Status` so default operator context is no longer ambiguous.
- The shared workspace introduction now matches the selected workspace, the default workflow view no longer leaks a visible create-state panel, and completed projects now surface workflow completion plus production handoff before project-management controls.
- Completed projects now show one handoff/download area only, the Prompt 1-7 rail is compact enough for operator scanning, Prompt 7 approved selection no longer regresses to `Ready`, and redundant completed-project summaries are removed.
- Focused compile verification passed and `python -m unittest tests.test_ui_frontend_contract` passed (`91` tests) with the broader pre-Phase-10A frontend/API regression coverage restored and expanded for the operator-first UI pass.
- The implementation remains local only; no commit or push has occurred.

## Preconditions
- Do not alter approved workflow projects, revisions, decisions, workflow state, stable production artifacts, analytics runtime, or protected OAuth/token runtime while verifying the UI behavior.
- Preserve workflow defaults, prompt/workflow assets, prompt manifests, registry defaults, and protected runtime unchanged.
- Preserve the current canonical workspace ownership and protected runtime files for `mist_of_ages` until the next separate execution prompt.

## Required Focus
- preserve the narrow Phase 10A UI diff exactly as validated
- verify the simplified navigation, overview, workflow, production-handoff, and analytics presentation against existing supported backend state only
- preserve approved stable production artifacts, workflow revisions, decisions, workflow state, and analytics runtime unchanged
- preserve workflow/prompt asset digests, analytics collector semantics, and registry default behavior
- keep any later commit/push decision separate from implementation verification

## Forbidden Work
- do not mutate approved workflow or analytics runtime in this verification/closeout gate
- do not change workflow defaults, prompt/workflow assets, manifest files, or registry data
- do not add AI API calls
- do not expose token contents, secret files, or absolute local paths
- do not mutate protected runtime data outside approved focused tests
- do not start unrelated workflow phases, History work, or Restore work

## Verification Requirements
- confirm the UI diff is limited to the embedded UI, focused UI tests, and the minimal status documents
- confirm no runtime or protected files are included in diff scope
- confirm approved workflow projects and analytics runtime remain unchanged during UI verification
- confirm real Mist of Ages runtime and token files remain protected from accidental mutation

## Reasoning Effort
High

## Deferred Later Phase
History and Restore remain deferred

## Explicitly Blocked
- Repository commit review remains blocked pending separate review.
- Live UI verification remains blocked pending a separate execution prompt.
- History remains deferred.
- Restore remains deferred.

## Exact First Action
Run a focused live verification of the three primary UI work areas, deterministic overview action logic, compact workflow rail behavior, production-handoff presentation, analytics status wording, separated readiness counts, and unchanged backend/runtime behavior for canonical channel `mist_of_ages`, then review commit scope in a separate step.
