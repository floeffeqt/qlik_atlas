---
id: QLIK-PS-004
title: Database as source of truth for UI lineage data and dashboard graph stats
status: draft
type: architecture
priority: p0
product_area: lineage-data-access
tags:
  - data-source
  - backend
  - frontend
  - lineage
  - postgresql
  - source-of-truth
spec_scope: project
project_key: qlik_atlas
owners: []
reviewers: []
created: 2026-02-24
updated: 2026-02-24
target_release: null

links:
  epics: []
  tickets: []
  adrs: []
  related_specs:
    - PS-001
    - PS-004
    - PS-005
    - QLIK-PS-002
    - QLIK-PS-003

classification:
  user_impact: high
  business_impact: high
  delivery_risk: medium
  confidence: medium

dedup_check:
  compared_specs:
    - ".product-specs/SPECS/QLIK-PS-002_testing-concept-spec-compliance-and-feature-validation.md"
    - ".product-specs/SPECS/QLIK-PS-003_postgresql-row-level-security-customer-inherited-access.md"
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-001_ai-action-execution-standard.md"
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-004_agent-testing-spec-compliance-and-feature-validation.md"
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-005_no-production-data-in-agent-sessions.md"
  result: unique
  action: create_new
  notes: Existing specs cover workflow/testing/security/RLS but do not define DB-vs-file source-of-truth behavior for UI lineage and dashboard graph stats.
---

# 1. Context

## Observed Facts

`qlik_atlas` currently maintains local lineage/file artifacts and an in-memory `GraphStore`, while PostgreSQL also stores lineage graph data.

UI-visible graph statistics and some graph endpoints can return `GraphStore`-derived values even when the database is empty or out of sync.

## Assumptions

The database should represent the authoritative user-facing lineage state after import/persistence steps complete.

Artifact files may still be needed for fetch/import pipeline stages and diagnostic workflows.

# 2. Problem Statement

When UI lineage views or dashboard graph statistics use local artifact-backed memory state instead of PostgreSQL, users may see stale or misleading data that does not reflect the database.

# 3. Goals & Success Metrics

## Goals

- Make PostgreSQL the source of truth for UI lineage graph rendering and dashboard graph node/edge counts.
- Preserve artifact-based processing only where needed for import/pipeline steps.
- Keep behavior compatible with RLS (user sees only authorized DB rows).

## Success Metrics

- Dashboard node/edge stats match DB-visible rows, not local artifact files.
- UI lineage graph loading uses DB-backed endpoints consistently.
- Legacy artifact-backed endpoints are identified/documented for phased migration.

# 4. Users / Stakeholders

## Primary Users

- End users viewing dashboard and lineage UI
- Admins validating imports and access-controlled data visibility

## Stakeholders

- Backend/frontend maintainers
- Security owners relying on RLS-enforced visibility

# 5. Scope

## In Scope

- Dashboard graph statistics data source
- UI lineage graph endpoints and aliases used by frontend
- Documentation/analysis of remaining artifact-backed endpoints

## Boundaries

- Full replacement of all artifact-based endpoints in one phase
- Changes to fetch/import artifact generation pipeline itself
- Redesign of dashboard UX labels beyond what is needed for correctness

# 6. Non-Goals

- Removing `GraphStore` entirely
- Eliminating local artifacts used for import/processing/debug workflows
- Rewriting all lineage-analysis algorithms to DB-native implementations in this phase

# 7. Requirements

## Functional Requirements

- The dashboard UI MUST display graph node/edge counts derived from PostgreSQL, not `GraphStore` artifact-memory state.
- DB-derived dashboard counts MUST respect the requesting user's RLS-visible scope.
- The UI lineage graph page MUST use DB-backed endpoints for graph rendering (all-project and per-project modes).
- The backend SHOULD provide a clear DB-backed endpoint for dashboard graph stats without breaking infrastructure health checks.
- The legacy `/api/graph/all` endpoint SHOULD return DB-backed graph data (or delegate to a DB-backed path) to avoid stale artifact behavior.
- Artifact-backed endpoints that remain in use MUST be documented as such for follow-up migration planning.

## Non-Functional Requirements

- Changes SHOULD minimize disruption to existing Docker health checks and operational probes.
- Reporting/testing must avoid production data use.
- Endpoint behavior should remain predictable under RLS (empty results rather than leaked data).

# 8. User Flow / Scenarios / Edge Cases

## Main Flow

1. Authenticated user opens dashboard.
2. Frontend requests DB-backed dashboard stats endpoint.
3. Backend applies RLS context and returns DB-visible node/edge counts.
4. User opens lineage page; frontend loads DB-backed graph endpoint (`all` or project-specific).

## Alternate Flows

- DB is empty but artifact files exist: dashboard/lineage UI still shows DB-empty results (expected).
- Artifacts exist for import/debug endpoints: those endpoints may still return file-backed data until migrated.

## Edge Cases

- Public health checks must continue to work without auth and without requiring DB graph row access.
- RLS may cause per-user counts/graphs to differ from admin/global views.

# 9. Acceptance Criteria

- AC-001: Dashboard graph node/edge stats shown in UI come from PostgreSQL counts.
- AC-002: Dashboard DB stats endpoint applies authenticated user RLS context.
- AC-003: `/api/graph/all` returns DB-backed graph data (directly or via aliasing).
- AC-004: Existing Docker/backend health checks remain functional.
- AC-005: A reviewable analysis lists remaining artifact-backed code paths after the change.

# 10. Dependencies / Risks / Assumptions

## Dependencies

- PostgreSQL lineage tables populated via import/store pipeline
- RLS context propagation for authenticated DB reads
- Frontend ability to call authenticated API endpoints

## Risks

- Mixed artifact/DB endpoints may still confuse users if undocumented.
- DB-empty states may look like regressions when artifacts still exist locally.
- Additional DB queries for dashboard stats may add small overhead.

## Assumptions (Decision-Relevant)

- UI correctness vs. DB state is more important than matching leftover local artifact files.
- `filesLoaded` may remain an artifact/pipeline metric if clearly separated from graph row counts.

# 11. Rollout / Release Considerations

- Deploy with DB migration/RLS changes already applied when applicable.
- Communicate that dashboard graph stats now reflect DB-visible rows and may differ from local artifacts.
- Follow up with phased migration/removal plan for remaining artifact-backed endpoints.

# 12. Open Questions

- Should `/api/health` eventually stop reporting artifact-backed `nodesCount/edgesCount` to avoid ambiguity?
- Should dashboard also surface DB/project counts separately from artifact pipeline metrics?
- Which artifact-backed endpoints should be prioritized next for DB-native migration?
