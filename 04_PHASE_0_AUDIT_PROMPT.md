# Phase 0 Prompt — Read-Only Architecture Audit

```text
MODEL: GPT-5.4
REASONING EFFORT: MEDIUM

ROLE:
You are the implementation worker.
The current ChatGPT session is the Tech Lead.

ACTIVE PHASE:
Phase 0 — Read-only architecture audit.

SCOPE:
Audit the existing Mist of Ages Input Collector repository for the approved
Multi-Channel MVP.

Do not modify any file.
Do not create files.
Do not install dependencies.
Do not commit or push.
Do not continue into Phase 1.

APPROVED PRODUCT BOUNDARY:
- local personal-use web UI;
- filesystem storage;
- no database;
- no AI API calls;
- no transcript downloads;
- no video upload;
- no new frontend framework;
- preserve the existing launch command;
- preserve manual files and user data.

TARGET FEATURE:
- multiple YouTube channels;
- one channel workspace per channel;
- one OAuth token per channel;
- learnings, metrics, and projects isolated per channel;
- selected channel required for project creation;
- legacy Mist of Ages data migrated non-destructively later.

EXPECTED CANONICAL LAYOUT:

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
      <project>/
        project.json
        input/
        research/
        workflow/

secrets/
  youtube/
    <channel_slug>_oauth_token.json

Global:
- youtube_api_key.txt
- youtube_oauth_client.json

READ-ONLY INSPECTION:

1. Confirm:
   - CWD
   - branch
   - HEAD
   - latest commit subject
   - working tree status

2. Inspect:
   - README.md
   - scripts/ui_server.py
   - UI assets/templates
   - API routes
   - services/modules
   - YouTube Data API client
   - OAuth helpers
   - Analytics client
   - Reporting client
   - token storage
   - project creation
   - project listing/open/save/validate
   - project.json schema
   - channel learnings handling
   - channel metrics handling
   - tests
   - .gitignore
   - current generated folder layout

3. Trace the current data flow:
   - Connect Channel
   - Sync Analytics/Reporting
   - Create Research Project
   - Save Transcript
   - Validate Inputs
   - Open Project

4. Find every single-channel hard-code:
   - mist_of_ages
   - channel/mist_of_ages
   - global projects root
   - one fixed OAuth token path
   - one fixed learnings path
   - one fixed metrics path
   - routes without channel context
   - UI state assuming one channel

5. Identify reusable components:
   - path helpers
   - JSON/Markdown/CSV helpers
   - OAuth flow
   - API clients
   - project service
   - validation
   - UI patterns
   - tests/fixtures

6. Evaluate migration risk:
   - legacy projects
   - manual transcript files
   - workflow artifacts
   - content.md
   - publishing_package.md
   - token files
   - current project.json compatibility

7. Propose the smallest safe Phase 1 only:
   - exact files to add
   - exact files to modify
   - exact tests to add
   - no UI implementation yet
   - no OAuth refactor yet
   - no migration yet

RETURN EXACTLY:

1. STATUS
   READY_FOR_PHASE_1 or BLOCKED

2. REPOSITORY BASELINE
   CWD:
   Branch:
   HEAD:
   Subject:
   Working tree:

3. CURRENT SINGLE-CHANNEL DATA FLOW

4. CURRENT FILE/FOLDER LAYOUT

5. REUSABLE COMPONENTS

6. HARD-CODED SINGLE-CHANNEL POINTS
   Include file paths and symbols/functions where possible.

7. CURRENT SECRET/TOKEN HANDLING

8. CURRENT PROJECT SCHEMA

9. MIGRATION RISKS

10. PROPOSED PHASE 1 FILES
    Files to add:
    Files to modify:

11. PHASE 1 FOCUSED TEST PLAN

12. BLOCKERS / OPEN QUESTIONS

13. GIT STATUS

14. NEXT EXACT ACTION

Do not make any repository mutation.
```
