---
id: QLIK-PS-002
title: Project testing concept for spec compliance and feature validation
status: draft
type: compliance
priority: p0
product_area: testing-and-quality
tags:
  - testing
  - spec-compliance
  - regression-testing
  - project-testing
  - qlik-atlas
  - no-prod-data
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
    - PS-003
    - PS-004
    - PS-005
    - QLIK-PS-001

classification:
  user_impact: high
  business_impact: high
  delivery_risk: medium
  confidence: medium

dedup_check:
  compared_specs:
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-004_agent-testing-spec-compliance-and-feature-validation.md"
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-005_no-production-data-in-agent-sessions.md"
    - ".product-specs/SPECS/QLIK-PS-001_critical-credentials-aes-256-gcm.md"
  result: partial_overlap
  action: create_new
  notes: General specs define testing model and data-safety baseline; this spec defines qlik_atlas-specific testing capabilities, minimum test expectations, and known gaps.
---

# 1. Context

## Observed Facts

`qlik_atlas` currently has backend automated tests via `pytest` (`backend/tests/test_auth.py`, `backend/tests/test_credentials_crypto.py`) and a minimal `backend/pytest.ini`.

A visible frontend automated test setup (for example package manifest/test runner config) is not currently evident in the repository root/frontend working tree snapshot, while frontend assets/pages exist and are actively changed.

## Assumptions

Backend tests can be run in a local dev environment with project dependencies available.

Frontend verification may currently rely on manual smoke checks until a dedicated automated frontend test setup is standardized.

# 2. Problem Statement

Without a project-specific testing concept, agents may test inconsistently across backend/frontend/security-sensitive changes and may fail to prove compatibility with project specs and acceptance criteria.

# 3. Goals & Success Metrics

## Goals

- Apply the shared testing model (`PS-004`) concretely to `qlik_atlas`.
- Ensure project-spec compliance testing is visible and traceable.
- Define minimum testing expectations by change type and risk.
- Enforce no-production-data/no-production-secret usage during agent testing.

## Success Metrics

- Code/feature changes include a structured testing summary with what/how/result/impact.
- Relevant project and general specs are mapped to test outcomes.
- Blocked/missing tests and known gaps (e.g. frontend automation gaps) are explicitly reported.

# 4. Users / Stakeholders

## Primary Users

- Users requesting code changes in `qlik_atlas`
- Reviewers validating release safety and spec compliance

## Stakeholders

- Maintainers of backend/frontend/auth/security areas
- Security/compliance stakeholders for credential and data handling

# 5. Scope

## In Scope

- Agent testing behavior for backend, frontend, auth/security, and API-impacting changes in `qlik_atlas`
- Spec-Compliance-Testing for applicable general/project specs
- Feature/Regression testing expectations by change type
- Testing summary requirements for end-user review
- Data-safety constraints for testing inputs (no productive data/secrets)

## Boundaries

- CI pipeline implementation details
- Full automated frontend test framework selection/rollout
- Performance/load testing standardization (unless a task explicitly requires it)

# 6. Non-Goals

- Mandating a single test tool for all future frontend testing
- Requiring exhaustive end-to-end tests for every small change
- Replacing security review for high-risk changes

# 7. Requirements

## Functional Requirements

- For code/behavior changes, the agent MUST apply both testing focus areas from `PS-004`:
  - Spec-Compliance-Testing
  - Feature/Regression-Testing
- The agent MUST identify applicable general specs and project specs before testing (including security specs like `QLIK-PS-001` when relevant).
- The agent MUST produce a structured testing summary using the central template `Desktop/Ki/specs/TEMPLATES/TESTING_SUMMARY.md` or an equivalent format with the same fields.
- The testing summary MUST make clear:
  - what was tested
  - how it was tested
  - result status
  - impact/notes
  - blocked/not-run items
- The agent MUST NOT use productive data or productive secrets in testing/debugging.
- The agent MUST request sanitized/synthetic/mock/staging-non-prod alternatives if needed.

### Minimum Testing Expectations by Change Type (qlik_atlas)

- Backend API/Auth/Security changes:
  - run relevant backend automated tests where available (pytest)
  - include focused manual/API verification if behavior changed and no automated coverage exists
  - explicitly mention security-sensitive paths and affected specs (e.g. `QLIK-PS-001`)
- Backend non-API internal logic changes:
  - run targeted backend tests where available
  - perform focused verification of changed behavior and likely regression surface
- Frontend UI/UX changes:
  - perform manual smoke checks of affected page/flow(s) until automated frontend tests are standardized
  - verify API interaction assumptions if frontend behavior depends on backend endpoints
- Cross-cutting changes (frontend + backend):
  - verify each side plus at least one end-to-end affected user flow (manual smoke is acceptable if no automated E2E exists)

### Test Result Reporting Requirements

- Testing Summary MUST include `what`, `how`, `result`, and `impact` for each relevant check.
- Blocked/not-run tests MUST be explicitly labeled with confidence/risk impact.
- Failures/fixes/retests MUST be documented when they occur.
- Manual checks MUST be labeled as manual and briefly describe the procedure.

## Non-Functional Requirements

- Testing should be risk-proportionate and efficient (aligned with `PS-003`).
- Reporting should be understandable for non-implementing end users.
- Known testing limitations must be explicit, not implicit.

# 8. User Flow / Scenarios / Edge Cases

## Main Flow

1. Agent matches applicable general and project specs.
2. Agent plans tests for spec compliance + feature/regression.
3. Agent runs available automated tests and/or manual checks as appropriate.
4. Agent documents results in a structured testing summary.
5. Agent documents failures/fixes/retests and residual risks.

## Alternate Flows

- If automated tests are unavailable for the changed area (e.g. frontend), agent uses manual smoke checks and marks automation gap.
- If a test cannot run due to environment constraints, agent marks it `blocker` or `not-run` with impact.

## Edge Cases

- Security-sensitive changes may require more targeted checks even if functional smoke passes.
- A change can pass local behavior checks but still fail spec compliance mapping (e.g. missing an acceptance criterion); this must be reported.
- Root README and backend/frontend runtime modes differ; agent must state the actual test path used during execution.

# 9. Acceptance Criteria

## Criteria List (empfohlen: AC-001, AC-002, ...)

- AC-001: For code/behavior changes in `qlik_atlas`, the agent applies both testing focus areas (spec compliance + feature/regression) or documents why one is not applicable.
- AC-002: The agent provides a testing summary that an end user can audit (`what`, `how`, `result`, `impact`).
- AC-003: Applicable general/project specs are referenced in the testing summary and mapped where relevant.
- AC-004: Blocked/not-run tests are explicitly labeled with impact on confidence/risk.
- AC-005: No productive data or productive secrets are used in agent testing sessions.

## Expected Results / Pass Conditions

- Reviewers can understand what was validated and what remains uncertain from the testing summary alone.
- Changes in areas with existing backend automated coverage trigger targeted pytest-based validation when feasible.
- Frontend changes without automation still produce explicit manual smoke evidence and stated gaps.

## Traceability (Requirements / Spec links)

- `PS-004` (general testing model and reporting)
- `PS-005` (no production data in agent sessions)
- `PS-003` (efficient/sustainable changes)
- `QLIK-PS-001` when credential/security persistence is affected

# 10. Dependencies / Risks / Assumptions

## Dependencies

- Local dev environment capable of running backend tests when required
- Access to safe non-production datasets or mocks for testing
- Discoverable applicable specs (general and project)

## Risks

### Risk Register (fuer relevante Risiken)

| Risk ID | Description | Impact | Likelihood | Mitigation / Test Strategy | Residual Risk |
|---|---|---|---|---|---|
| R-001 | Frontend automated test coverage not standardized in repo snapshot | medium | high | Manual smoke checks + explicit gap reporting | medium |
| R-002 | Environment/tooling limits prevent some tests from running | high | medium | Mark blocker/not-run with impact and next step | medium |
| R-003 | Product spec acceptance criteria are not granular enough for exact mapping | medium | medium | Use best-effort mapping + mark ambiguity + propose spec refinement | medium |
| R-004 | Unsafe data/secrets accidentally used in debugging/testing | high | medium | Enforce no-prod-data rule and require sanitized/mock alternatives | low |

## Data Safety / Privacy Constraints

- Production data allowed in agent session: no
- Production secrets allowed in agent session: no
- Allowed testing data: synthetic, sanitized, mock, staging-non-prod

## Assumptions (Decision-Relevant)

- Backend pytest tests remain the primary automated test baseline today.
- Manual smoke testing is temporarily acceptable for frontend changes until a dedicated frontend test setup is standardized.

# 11. Rollout / Release Considerations

- Apply immediately to all `qlik_atlas` code/feature changes handled by agents.
- Use the central testing summary template for user-facing verification.
- When Testing is relevant, the gateway should additionally match `Desktop/Ki/Masterprompts/testing-execution-runtime.md` for consistent test planning/execution/reporting.
- Create follow-up project specs for frontend automated testing standardization if/when introduced.

# 12. Open Questions

- What exact frontend pages/flows should be considered mandatory smoke paths by default?
- Should `qlik_atlas` standardize a frontend automated test runner in a dedicated follow-up spec?
- What is the preferred safe source for representative non-production lineage datasets in testing?
