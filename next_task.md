# Next Task

## Status
BLOCKED_PENDING_SEPARATE_EXECUTION_PROMPT

## Proposed Phase
Phase 7D1B2 - Push Review and Prompt 3 Bundle Preparation Gate

## Do Not Start Yet
Do not begin Phase 7D1B2 until a separate Tech Lead execution prompt authorizes final push review for the committed parser fix and then separately authorizes Prompt 3 bundle preparation.

## Proposed Objective
Close out the committed parser-fix branch state safely, then prepare and verify the Prompt 3 bundle for the current pilot project in a separate workflow step without running Prompt 3 itself.

## Current Phase Evidence
- Phase 7D1B1 confirmed the exact parser defect root cause: Prompt 2 `evidence_ledger` headings were counted globally, valid multi-record ledgers were rejected, and Markdown field labels such as `## CLAIM:` were not recognized.
- The local parser now supports repeatable ordered evidence-ledger records with both plain and Markdown-prefixed field labels while preserving non-ledger behavior.
- Focused parser regression passed (`32` tests), the focused multichannel parse-route regression passed, and the live API parse-preview smoke on the current restarted single-listener server returned `VALID`.
- The real Prompt 2 raw response parsed validly with raw SHA-256 `CA6C664A86C5AC52F54E3C7F4CAD3A14543286E8CD0D3AF98F7D0FC877B9960D`.
- Prompt 2 candidate `grp_000002` was approved, `research_pack` `rev_000001` and `evidence_ledger` `rev_000001` were published to stable, workflow state revision is now `4`, and Prompt 3 is effectively `READY`.
- The exact next workflow step id is `prompt_3_creative_package`.
- The parser fix has been committed locally on `master`, the repository is ahead of `origin/master` by one commit, and no push has been performed.

## Preconditions
- Do not alter the live pilot runtime while reviewing the parser fix commit scope.
- Preserve workflow defaults, prompt/workflow assets, prompt manifests, and registry defaults unchanged.
- Preserve the current pilot project state at workflow schema `2`, state revision `4`, Prompt 1 `APPROVED`, Prompt 2 `APPROVED`, and Prompt 3 `READY` until the next separate execution prompt.

## Required Focus
- preserve the reviewed parser fix diff exactly as validated
- preserve non-ledger parser behavior
- preserve the approved Prompt 2 stable artifacts and decision state unchanged
- preserve workflow/prompt asset digests and registry default semantics
- prepare Prompt 3 bundle verification only in a later separate step

## Forbidden Work
- do not modify the parser implementation or parser tests unless a separate prompt authorizes further changes
- do not mutate the real pilot project runtime
- do not change workflow defaults or prompt/workflow assets
- do not build or run Prompt 3 in this closeout/commit-review gate
- do not add AI API calls
- do not mutate protected runtime data outside approved temporary-root tests
- do not start History or Restore work

## Verification Requirements
- confirm the exact five tracked files intended for commit only
- confirm no runtime or protected files are included in commit scope
- confirm parser module SHA-256 for `scripts/channel_output_parser.py` remains `71A967ABF55373D1795612A900CD20F7975180F58D72F007C52A7BE9C9901EA0`
- confirm the pilot remains at Prompt 3 `READY` without bundling or running Prompt 3
- confirm real Mist of Ages runtime and token files remain protected from accidental mutation

## Reasoning Effort
High

## Deferred Later Phase
History and Restore remain deferred

## Explicitly Blocked
- Final push remains blocked pending separate review.
- Prompt 3 bundle preparation remains blocked pending a separate execution prompt.
- History remains deferred.
- Restore remains deferred.

## Exact First Action
Review the committed parser-fix change for final push readiness, then authorize a separate Prompt 3 bundle preparation step for `prompt_3_creative_package`.
