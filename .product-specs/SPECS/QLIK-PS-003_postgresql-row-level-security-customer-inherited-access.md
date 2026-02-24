---
id: QLIK-PS-003
title: PostgreSQL Row-Level Security with customer-inherited access control
status: draft
type: security
priority: p0
product_area: authorization-and-data-isolation
tags:
  - security
  - authorization
  - postgresql
  - rls
  - customer-access
  - multitenancy
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
    - PS-003
    - PS-004
    - PS-005
    - QLIK-PS-001
    - QLIK-PS-002

classification:
  user_impact: high
  business_impact: high
  delivery_risk: high
  confidence: medium

dedup_check:
  compared_specs:
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-001_ai-action-execution-standard.md"
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-003_sustainable-and-efficient-code-changes.md"
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-004_agent-testing-spec-compliance-and-feature-validation.md"
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-005_no-production-data-in-agent-sessions.md"
    - ".product-specs/SPECS/QLIK-PS-001_critical-credentials-aes-256-gcm.md"
    - ".product-specs/SPECS/QLIK-PS-002_testing-concept-spec-compliance-and-feature-validation.md"
  result: unique
  action: create_new
  notes: Existing general/project specs define workflow, testing, and credential encryption, but none define PostgreSQL row-level authorization with customer-inherited access in qlik_atlas.
---

# 1. Context

## Observed Facts

`qlik_atlas` currently authenticates users and stores a coarse user role (`admin` / `user`) but does not yet persist customer/project access assignments for non-admin users.

Multiple domain tables (`customers`, `projects`, `qlik_apps`, `lineage_nodes`, `lineage_edges`) are stored in PostgreSQL and contain tenant/customer-scoped data.

## Assumptions

The application connects to PostgreSQL with a role that may also own the tables, so RLS enforcement may require `FORCE ROW LEVEL SECURITY`.

The application can set per-request PostgreSQL session variables (for example `app.user_id`, `app.role`) used by RLS policies.

# 2. Problem Statement

Without database-enforced row-level authorization, authenticated users may access or mutate data outside their allowed customer scope if API-layer checks are incomplete or regress.

# 3. Goals & Success Metrics

## Goals

- Enforce PostgreSQL RLS for customer/project-scoped data.
- Support admin full access and non-admin access inherited from assigned customers.
- Keep project CRUD available for non-admin users only within their assigned customers.
- Keep fetch jobs admin-only and execute background DB actions under the triggering user's context.

## Success Metrics

- Non-admin users can only read/write project-scoped rows tied to assigned customers.
- Admin users retain full access to all protected rows.
- Unauthorized reads/writes are blocked at the DB layer even if API code regresses.
- Fetch-job endpoints reject non-admin users.

# 4. Users / Stakeholders

## Primary Users

- Admin users managing customers, projects, and user access assignments
- Non-admin users working within assigned customer scopes

## Stakeholders

- Security/compliance owners
- Maintainers of backend authorization and data access code

# 5. Scope

## In Scope

- PostgreSQL RLS policies for customer/project-scoped tables
- `user_customer_access` mapping model for non-admin access assignments
- Request/background-job DB session context propagation (`user_id`, `role`)
- Route updates necessary to align app behavior with the RLS model

## Boundaries

- Full RBAC redesign beyond `admin` / `user`
- Frontend permission UX redesign
- Non-PostgreSQL database engines

# 6. Non-Goals

- Replacing JWT authentication
- Implementing column-level masking via RLS (customer detail output remains existing shape)
- Granting fetch-job execution to non-admin users

# 7. Requirements

## Functional Requirements

- The system MUST store explicit non-admin customer assignments in a `user_customer_access` model/table.
- PostgreSQL RLS MUST be enabled for `customers`, `projects`, `qlik_apps`, `lineage_nodes`, and `lineage_edges`.
- The system MUST enforce `admin` full access to protected rows.
- Non-admin users MUST be allowed to read customer details only for assigned customers.
- Non-admin users MUST be allowed to create, update, and delete projects only when the project's `customer_id` belongs to an assigned customer.
- Access to `qlik_apps`, `lineage_nodes`, and `lineage_edges` MUST inherit from the related project's customer assignment.
- Fetch-job endpoints MUST be admin-only.
- Background jobs triggered by fetch-job endpoints MUST execute database operations in the triggering user's DB context (no RLS bypass/service-context shortcut in this phase).
- The application MUST set DB session context values required by RLS policies for authenticated requests touching protected tables.

## Non-Functional Requirements

- Authorization enforcement SHOULD be centralized and not duplicated inconsistently across routes.
- RLS rollout SHOULD fail closed (missing context -> no unintended access).
- Implementation SHOULD avoid logging sensitive values or production data content.

# 8. User Flow / Scenarios / Edge Cases

## Main Flow

1. User authenticates and receives JWT with `user_id` and `role`.
2. Backend request handling sets PostgreSQL DB session context from JWT claims.
3. Route queries protected tables.
4. PostgreSQL RLS policy permits or denies rows based on `role` and assigned customers.

## Alternate Flows

- Admin manages customer assignments for a user via admin endpoints.
- Admin starts a fetch job; background DB sessions reuse the admin user's context for RLS checks.

## Edge Cases

- Missing DB session context must not grant access.
- Table-owner connections may bypass RLS unless `FORCE ROW LEVEL SECURITY` is enabled.
- Existing routes may return `404` for unauthorized resources after RLS filtering; this is acceptable if documented.

# 9. Acceptance Criteria

- AC-001: A `user_customer_access` mapping exists and is manageable by admin endpoints.
- AC-002: RLS is enabled on `customers`, `projects`, `qlik_apps`, `lineage_nodes`, and `lineage_edges`.
- AC-003: Admin can read and modify all protected rows.
- AC-004: Non-admin users can read only assigned customers and can CRUD projects only for assigned customers.
- AC-005: Project-scoped graph table access is restricted by inherited customer access.
- AC-006: Fetch-job endpoints require admin authorization.
- AC-007: Background fetch-job DB sessions run with the triggering user's DB context (no RLS bypass).
- AC-008: Testing summary documents spec-compliance and feature/regression validation without production data.

# 10. Dependencies / Risks / Assumptions

## Dependencies

- PostgreSQL support for RLS policies
- Backend ability to set per-session DB context (`set_config`/`SET LOCAL`)
- Non-production test data for validation

## Risks

- Incomplete session-context propagation could cause unexpected denials.
- RLS policy mistakes could block valid admin/user flows or over-permit access.
- Background jobs may fail if context is not set in every internal session.

## Assumptions (Decision-Relevant)

- Admin users should remain unrestricted for protected tables in this phase.
- Customer-level assignment is the authoritative source for non-admin project access inheritance.

# 11. Rollout / Release Considerations

- Apply RLS migration and ACL table migration in a controlled non-production environment first.
- Seed/assign customer access for non-admin users before enabling user-facing routes that depend on it.
- Validate fetch-job admin-only behavior and background-job DB context propagation after rollout.

# 12. Open Questions

- Should customer creation/update/delete remain admin-only long-term (current decision: yes)?
- Should non-admin users also be restricted from certain customer metadata fields in a later phase?
- Is a separate audit trail needed for admin changes to user-customer assignments?
