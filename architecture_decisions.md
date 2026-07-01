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
