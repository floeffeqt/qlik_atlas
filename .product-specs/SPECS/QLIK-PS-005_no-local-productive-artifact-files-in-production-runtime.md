---
id: QLIK-PS-005
title: Production runtime must not persist or depend on local productive artifact files
status: draft
type: security
priority: p0
product_area: runtime-data-handling
tags:
  - production
  - file-artifacts
  - data-safety
  - backend
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
    - PS-005
    - QLIK-PS-002
    - QLIK-PS-004

classification:
  user_impact: high
  business_impact: high
  delivery_risk: high
  confidence: medium

dedup_check:
  compared_specs:
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-005_no-production-data-in-agent-sessions.md"
    - ".product-specs/SPECS/QLIK-PS-004_db-source-of-truth-for-ui-lineage-and-stats.md"
  result: partial_overlap
  action: create_new
  notes: PS-005 governs agent-session data handling and QLIK-PS-004 governs UI DB source-of-truth; this spec defines production runtime behavior prohibiting local productive artifact writes/reads as persistent application data dependencies.
---

# 1. Context

## Observed Facts

`qlik_atlas` currently uses local artifact files (for example under `backend/output/...`) for parts of its fetch/import pipeline and some API behavior.

In production operation, writing or reusing local files that contain productive business/lineage data increases data-sprawl risk and can create stale secondary sources of truth.

## Assumptions

PostgreSQL (and approved upstream APIs) should be the authoritative runtime source for productive application reads.

Operational logs, static application assets, and configuration files are not considered "productive artifact files" for this spec unless they contain productive data payloads.

# 2. Problem Statement

If the productive runtime writes or depends on local artifact files containing productive data, the application can violate data-handling expectations, create stale data divergence, and increase operational/security risk.

# 3. Goals & Success Metrics

## Goals

- Prevent production runtime from persisting productive data as local artifact files.
- Prevent production runtime from serving user-facing data from local productive artifact files.
- Keep runtime behavior anchored to approved authoritative sources (DB / upstream systems).

## Success Metrics

- Production runtime user-facing endpoints do not depend on local artifact files for productive data responses.
- Production runtime fetch/import flows do not persist productive lineage/business payloads to local filesystem artifacts.
- Any exceptions are explicitly documented, limited, and non-productive/non-sensitive.

# 4. Users / Stakeholders

## Primary Users

- Operators/admins running `qlik_atlas` in production
- End users consuming production UI/API results

## Stakeholders

- Security/compliance owners
- Backend maintainers responsible for runtime data flows

# 5. Scope

## In Scope

- Production runtime behavior (`APP_ENV=prod` or equivalent production deployment mode)
- Local filesystem artifact writes/reads containing productive application data
- User-facing API/UI data reads and background processing flows in production

## Boundaries

- Development/local test workflows using mock/sanitized artifacts
- Static frontend assets bundled with the application image
- Standard logs/metrics that do not contain productive payload data

# 6. Non-Goals

- Banning all filesystem access in production
- Replacing database backups or database-level persistence
- Defining the full production deployment architecture in one spec

# 7. Requirements

## Functional Requirements

- In production runtime, the application MUST NOT write productive lineage/business data payloads to local artifact files as part of normal operation.
- In production runtime, user-facing API/UI responses MUST NOT use local productive artifact files as the data source of truth.
- PostgreSQL (subject to RLS and authorization) MUST be used as the source of truth for productive UI lineage graph data and graph counts.
- Endpoints or code paths that rely on local artifact files for productive data MUST be disabled, replaced, or restricted from production runtime usage.
- If a temporary local file is technically required in production for a narrow operational reason, it MUST:
  - avoid storing productive payload data where feasible
  - be ephemeral and cleaned up
  - not become a persistent source of truth
  - be explicitly documented as an exception
- The system MUST avoid logging productive payload data while enforcing or transitioning this behavior.

## Non-Functional Requirements

- The production behavior SHOULD fail safe (prefer no data / explicit error over reading stale local artifacts).
- The implementation SHOULD make production-vs-non-production behavior explicit and reviewable.
- Migration away from artifact-backed paths SHOULD be phased and documented.

# 8. User Flow / Scenarios / Edge Cases

## Main Flow

1. Production user requests data in UI/API.
2. Backend reads from PostgreSQL / approved upstream source.
3. Backend returns results without reading local productive artifact files.

## Alternate Flows

- In non-production/dev mode, artifact-backed workflows may remain available for debugging/import development.
- During migration, production-incompatible artifact endpoints may be disabled rather than partially supported.

## Edge Cases

- Legacy endpoints may still exist in code but must be gated from production use.
- Cached data mechanisms must not silently degrade into local productive artifact files.
- Background jobs must avoid creating local productive artifacts even if UI endpoints are already DB-backed.

# 9. Acceptance Criteria

- AC-001: A documented list exists of artifact-backed endpoints/code paths and their production status (allowed/disabled/replaced).
- AC-002: Production UI lineage graph rendering and dashboard graph stats are DB-backed.
- AC-003: Production runtime does not persist productive lineage/business payloads to local artifact files in normal operation.
- AC-004: Any production exceptions for temporary files are explicitly documented and non-authoritative.
- AC-005: Verification/testing evidence is recorded without using production data.

# 10. Dependencies / Risks / Assumptions

## Dependencies

- DB-backed replacements for artifact-backed user-facing endpoints where required
- Clear production environment signaling (`APP_ENV` or equivalent)
- Operational validation in non-production before production rollout

## Risks

- Legacy artifact-dependent features may need redesign before full compliance.
- Disabling artifact-backed endpoints in production could temporarily reduce functionality if DB-native equivalents are missing.
- Mixed-mode operation (dev vs prod) can cause confusion if behavior is not clearly documented.

## Assumptions (Decision-Relevant)

- Productive data durability and runtime reads should be centralized in PostgreSQL / approved systems, not local files.
- Development flexibility can be preserved while enforcing stricter production behavior.

# 11. Rollout / Release Considerations

- Start with user-facing endpoints and dashboard/lineage views (already covered by `QLIK-PS-004`).
- Identify and phase out remaining production artifact writers/readers.
- Add production guards/config checks before enabling the final policy in production.

# 12. Open Questions

- Which remaining artifact-backed endpoints must be kept in production, if any?
- Should production artifact blocking be implemented as hard runtime guards (`APP_ENV=prod`) or deployment-time configuration only?
- Is a separate object storage solution needed for non-authoritative temporary operational files?
