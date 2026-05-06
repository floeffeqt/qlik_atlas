---
id: QLIK-PS-008
title: Alembic version names must be max 30 characters
status: active
type: compliance
priority: p1
product_area: backend-data-platform
tags:
  - backend
  - database
  - alembic
  - migrations
  - naming
spec_scope: project
project_key: qlik_atlas
owners: []
reviewers: []
created: 2026-03-03
updated: 2026-03-03
target_release: null

links:
  epics: []
  tickets: []
  adrs: []
  related_specs:
    - QLIK-PS-002
    - QLIK-PS-007

classification:
  user_impact: medium
  business_impact: medium
  delivery_risk: low
  confidence: high

dedup_check:
  compared_specs: []
  result: none
  action: create_new
  notes: Dedicated naming constraint for migration files/revision IDs.
---

# 1. Context

Migration names have become inconsistent and occasionally too long, which hurts readability and standardization in reviews and release notes.

# 2. Problem Statement

Without a strict naming limit, new Alembic versions may use long identifiers that reduce maintainability and increase human error in operations/docs.

# 3. Goals

- Enforce a clear maximum length for new Alembic version names.
- Keep migration naming short, predictable, and review-friendly.

# 4. Requirements

## Functional Requirements

- For every **new** Alembic migration:
  - migration file name (including `.py`) MUST be `<= 30` characters.
  - `revision` value in the migration file MUST be `<= 30` characters.
- Names SHOULD use concise snake_case and keep numeric revision prefix.
- If an auto-generated name exceeds the limit, it MUST be shortened before commit.

## Non-Functional Requirements

- Rule must be easy to check manually during review.
- Naming should remain unique and understandable.

# 5. Acceptance Criteria

- AC-001: Any newly added file in `backend/alembic/versions/` has a filename length `<= 30`.
- AC-002: `revision = "..."` in newly added migration files has length `<= 30`.
- AC-003: If violated during implementation, migration is renamed before final delivery.

# 6. Examples

- Valid file name: `0016_license_schema_status.py` (29 chars)
- Invalid file name: `0016_license_consumption_schema_and_status.py` (> 30 chars)


