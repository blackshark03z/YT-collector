# Mist of Ages Input Collector

Local personal-use web UI for preparing Mist of Ages research project inputs.

It creates the project folder, competitor metadata file, channel learning snapshot, manual transcript template, workflow placeholders, and validation status. It does not call AI APIs, download transcripts, or run the video pipeline.

## First Run

1. Enable these APIs in Google Cloud:
   - YouTube Data API v3
   - YouTube Analytics API
   - YouTube Reporting API
2. Copy `youtube_api_key.example.txt` to `youtube_api_key.txt` and paste your Data API key.
3. Download a Google OAuth Desktop Client JSON and save it as `youtube_oauth_client.json`.
4. Start the UI:

```powershell
python scripts/ui_server.py
```

5. Open:

```text
http://127.0.0.1:8765
```

6. Click `Connect Channel`, sign in to the Mist of Ages YouTube account, then return to the UI.
7. Paste a competitor video URL and click `Create Research Project`.
8. Paste the manually collected transcript into the UI or into `research/competitor_transcript.md`.
9. Click `Validate Inputs`. When it shows `READY_FOR_WORKFLOW`, start Prompt 1 with:
   - `input/competitor_reference.md`
   - `research/competitor_transcript.md`
   - `input/channel_learnings.md`

## Generated Structure

```text
projects/<project-slug>/
  project.json
  input/
    competitor_reference.md
    channel_learnings.md
    channel_metrics.csv
    assets/
      competitor_thumbnail.<ext>
    _raw/
      competitor_video.json
      channel_analytics.json
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
```

## Safety Rules

- `competitor_transcript.md` is created only if missing.
- Workflow files are created only if missing.
- `content.md` and `publishing_package.md` are never created during project initialization.
- Refreshes are scoped to generated metadata/channel files.
- Reach data can be `PENDING`; that does not block project creation.

## Approved Learnings

The app reads approved channel learnings from:

```text
channel/mist_of_ages/channel_learnings_master.md
```

The file is created with a starter placeholder on first run.
