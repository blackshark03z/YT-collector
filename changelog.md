# Changelog

## Unreleased

### Phase 3 - Channel-Scoped Project Service
- Added `scripts/channel_projects.py`.
- Added `tests/test_channel_projects.py`.
- Added `project_status.md`, `changelog.md`, and `next_task.md`.
- Implemented channel-scoped project creation under `channels/<slug>/projects/<project>/`.
- Added atomic project creation using a temporary sibling directory and rename-on-success behavior.
- Added byte-identical snapshot copying for channel learnings and metrics.
- Added `project.json` schema version 2 with channel ownership and snapshot metadata.
- Added transcript save protection with explicit overwrite requirement for real transcript content.
- Added channel-scoped project validation and sanitized project listing.
- Added cross-channel ownership checks for load, transcript save, and validation operations.
- Focused tests passed for project creation, snapshot behavior, transcript safety, validation, and cross-channel protection.
- No real project, workspace, OAuth token, or manual content was moved or modified.
- Deferred server route integration and multi-channel UI work.

### Phase 2 - OAuth Isolation Foundation
- Added `scripts/channel_oauth.py`.
- Added `tests/test_channel_oauth.py`.
- Modified `scripts/channel_workspace.py` with channel connection metadata update support.
- Added isolated per-channel token loading, persistence, refresh, and authenticated identity validation.
- Added rollback protection so token changes are restored if metadata update fails during connection.
- Tests passed for OAuth isolation, channel identity mismatch safety, and token refresh behavior.
- No real OAuth token was moved.
- Deferred integration with the running server and current HTTP routes.

### Phase 1 - Channel Workspace Foundation
- Added `scripts/channel_workspace.py`.
- Added `tests/test_channel_workspace.py`.
- Added channel slug validation, canonical path helpers, atomic `channel.json` writes, channel listing, and duplicate-channel protections.
- Tests passed for workspace creation, non-overwrite behavior, path safety, and metadata validation.
- No real channel workspace was created.
- Deferred OAuth integration and project routing.

### Baseline
- Created local Git baseline.
