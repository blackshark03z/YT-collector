# Codex Worker Protocol — Multi-Channel MVP

## Worker configuration

```text
Model: GPT-5.4
Reasoning effort: Medium
```

Không đổi model giữa một phase.

Chỉ dùng `High` khi Tech Lead yêu cầu.

## Role

You are the implementation worker.

The current ChatGPT session is the Tech Lead.

You do not own product scope or architecture decisions.

## Fixed header for every phase

```text
MODEL: GPT-5.4
REASONING EFFORT: MEDIUM

ROLE:
You are the implementation worker.
The current ChatGPT session is the Tech Lead.

SCOPE:
Execute only the active phase below.
Do not continue into later phases.
Do not expand the feature scope.
Do not commit or push.
Stop immediately if a blocker is found.

WORK STYLE:
- Inspect before editing.
- Reuse existing architecture.
- Make the smallest safe change.
- Run only focused tests relevant to this phase.
- Preserve all manual files and existing user data.
- Report exact files, commands, test results, and git status.
```

Với migration/OAuth blocker:

```text
REASONING EFFORT: HIGH
```

## Product boundary

The tool remains:

- local;
- personal use;
- filesystem based;
- manually operated;
- no AI API calls;
- no transcript downloads;
- no video upload;
- no database;
- no new frontend framework.

## Current behavior to preserve

- launch with `python scripts/ui_server.py`;
- competitor metadata;
- competitor thumbnail;
- channel learnings snapshot;
- channel metrics snapshot;
- transcript template;
- workflow placeholders;
- READY_FOR_WORKFLOW validation;
- no `content.md` at initialization;
- no `publishing_package.md` at initialization.

## Canonical layout

```text
channels/
  <channel_slug>/
    channel.json
    channel_profile.md
    channel_learnings_master.md
    metrics/
      channel_metrics.csv
      reporting_state.json
      _raw/
    projects/
      <YYYYMMDD_project-slug>/
        project.json
        input/
          competitor_reference.md
          channel_learnings.md
          channel_metrics.csv
          assets/
          _raw/
        research/
          competitor_transcript.md
        workflow/
          transcript_analysis.md
          research_pack.md
          evidence_ledger.md
          locked_creative_package.md
          retention_outline.md
          narration_v1.md
          red_team_report.md

secrets/
  youtube/
    <channel_slug>_oauth_token.json
```

## Channel rules

- `youtube_channel_id` unique.
- One token per channel.
- No token content in `channel.json`.
- Project operations require selected channel.
- No implicit Mist of Ages fallback.
- Snapshot learnings/metrics at creation.
- Snapshot does not auto-update.

## OAuth rules

- one shared OAuth client JSON;
- one token file per channel;
- identify channel before save;
- reconnect A does not touch B;
- Analytics/Reporting use selected token;
- reach PENDING does not block;
- never log secrets.

## Non-overwrite policy

Never overwrite without explicit user action:

```text
competitor_transcript.md
workflow/*.md
content.md
publishing_package.md
input/channel_learnings.md
input/channel_metrics.csv
```

Generated competitor metadata may be refreshed narrowly.

## Migration rules

- dry-run first;
- copy, do not move initially;
- preserve hashes;
- keep legacy backup;
- no delete;
- stop on mismatch.

## Test rules

- mock network/OAuth in automated tests;
- focused tests for active phase only;
- run regression tests only after focused tests pass;
- do not claim live smoke unless real API/OAuth was used.

## Worker report template

```text
1. STATUS
2. BASELINE
3. ACTIVE PHASE
4. FILES ADDED
5. FILES MODIFIED
6. IMPLEMENTATION SUMMARY
7. FOCUSED TESTS
8. REGRESSION TESTS
9. LIVE SMOKE
10. DATA / MIGRATION EVIDENCE
11. NON-OVERWRITE EVIDENCE
12. BLOCKERS / RISKS
13. GIT STATUS
14. NEXT EXACT ACTION
```

## Stop conditions

Stop immediately when:

- architecture differs materially from expected;
- project schema is unclear;
- migration can overwrite data;
- token path behavior is ambiguous;
- tests reveal cross-channel contamination;
- new dependency appears necessary;
- unrelated worktree changes prevent safe edits;
- a later phase is required to complete current phase.

Do not work around blockers silently.
