# Architecture Decisions

## ADR-001 - Additive Multi-Channel Backend Before UI Cutover

### Status
Accepted

### Context
The existing server and UI are single-channel and currently operational.
The new channel workspace, OAuth, and project services are isolated and tested.

### Decision
Introduce a new additive `/api/v2/` multi-channel backend surface while
preserving all existing legacy routes and UI behavior.

Phase 4A adds backend APIs only.
Phase 4B will add OAuth browser integration and switch the UI to `/api/v2/`.
Legacy data migration remains a later phase.

### Consequences
- Existing daily-use behavior remains available during implementation.
- Multi-channel backend can be tested independently.
- Some temporary duplication with legacy helpers is acceptable.
- Legacy routes are not removed until migration and live smoke pass.

## ADR-002 - Migrate Canonical Mist of Ages Data Before UI Cutover

### Status
Accepted

### Context
The new V2 backend uses `channels/<slug>/`, but the real Mist of Ages
learnings, identity and OAuth token still exist in legacy locations.

Switching the UI before migration could expose an empty canonical state,
encourage duplicate channel creation, or snapshot the wrong learnings.

### Decision
Complete and validate the legacy-to-canonical Mist of Ages migration before
switching the daily-use UI to the V2 backend.

OAuth browser integration may be implemented first, but no live connection
or UI cutover occurs before migration review.

### Consequences
- Phase 4B1 completes backend OAuth and UI-support endpoints only.
- The next phase is migration dry-run, not UI cutover.
- UI cutover occurs only after migration and canonical-data validation pass.
