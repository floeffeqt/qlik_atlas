---
id: QLIK-PS-009
title: Auto-run runtime refresh commands after changes that require rebuild/restart
status: active
type: compliance
priority: p1
product_area: developer-workflow
tags:
  - workflow
  - docker
  - developer-experience
  - frontend
  - backend
spec_scope: project
project_key: qlik_atlas
owners: []
reviewers: []
created: 2026-03-04
updated: 2026-03-04
target_release: null

links:
  epics: []
  tickets: []
  adrs: []
  related_specs:
    - QLIK-PS-002
    - QLIK-PS-006
    - QLIK-PS-007

classification:
  user_impact: high
  business_impact: medium
  delivery_risk: low
  confidence: high

dedup_check:
  compared_specs:
    - .product-specs/SPECS/QLIK-PS-002_testing-concept-spec-compliance-and-feature-validation.md
    - .product-specs/SPECS/QLIK-PS-006_backend-changes-with-frontend-impact-require-frontend-verification.md
  result: partial_overlap
  action: create_new
  notes: Existing specs require testing/verification, but do not require automatic execution of runtime refresh commands needed to make changes visible immediately in the app.
---

# 1. Context

In `qlik_atlas`, code changes are often not visible in the running app until rebuild/restart commands are executed (for example via Docker Compose). This creates avoidable delay and confusion after delivery.

# 2. Problem Statement

If required runtime refresh commands are not executed automatically after relevant changes, users cannot immediately validate results in UI/API, even when implementation is complete.

# 3. Goals

- Ensure changes are visible immediately after delivery whenever environment permits.
- Remove manual "please run docker compose ..." follow-up steps for standard workflows.
- Make executed refresh actions transparent in delivery output.

# 4. Requirements

## Functional Requirements

- After implementation, the agent MUST determine whether runtime refresh is required for visibility.
- If required, the agent MUST automatically execute the minimal necessary command set before final handover.
- Default command selection:
  - frontend-only impact: `docker compose up -d --build frontend`
  - backend-only impact: `docker compose up -d --build backend`
  - mixed/unclear impact: `docker compose up -d --build`
- Agent MUST report which command(s) were executed and whether they succeeded.
- If auto-execution is blocked (permissions/tooling/environment), the agent MUST:
  - attempt the required escalation flow, and
  - report the exact fallback command(s) for manual execution.

## Non-Functional Requirements

- Keep refresh scope minimal to reduce unnecessary runtime cost.
- Do not run destructive commands.
- Preserve existing safety constraints (no production secrets/data exposure).

# 5. Acceptance Criteria

- AC-001: For changes requiring rebuild/restart to become visible, the agent runs appropriate runtime refresh command(s) automatically.
- AC-002: Final delivery message includes executed command(s) and result status.
- AC-003: If auto-run is not possible, final delivery includes the exact minimal manual command(s) and blocker reason.
- AC-004: No unnecessary full-stack rebuild is executed when a narrower service rebuild is sufficient.

# 6. Examples

- Frontend HTML/CSS/JS change in containerized runtime:
  - run `docker compose up -d --build frontend`
- Backend API/query change:
  - run `docker compose up -d --build backend`
- Frontend + backend change:
  - run `docker compose up -d --build`

