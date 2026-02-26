---
id: QLIK-PS-006
title: Backend changes with frontend impact require frontend verification and impact reporting
status: draft
type: compliance
priority: p0
product_area: testing-and-quality
tags:
  - testing
  - backend
  - frontend
  - impact-detection
  - regression-testing
  - qlik-atlas
spec_scope: project
project_key: qlik_atlas
owners: []
reviewers: []
created: 2026-02-26
updated: 2026-02-26
target_release: null

links:
  epics: []
  tickets: []
  adrs: []
  related_specs:
    - PS-003
    - PS-004
    - PS-005
    - QLIK-PS-002
    - QLIK-PS-004

classification:
  user_impact: high
  business_impact: high
  delivery_risk: medium
  confidence: medium

dedup_check:
  compared_specs:
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-004_agent-testing-spec-compliance-and-feature-validation.md"
    - ".product-specs/SPECS/QLIK-PS-002_testing-concept-spec-compliance-and-feature-validation.md"
    - ".product-specs/SPECS/QLIK-PS-004_db-source-of-truth-for-ui-lineage-and-stats.md"
  result: partial_overlap
  action: create_new
  notes: PS-004 and QLIK-PS-002 define general/project testing obligations; this spec adds a specific mandatory frontend verification rule when backend changes can affect frontend behavior, plus explicit impact reporting and solution proposals.
---

# 1. Context

## Observed Facts

`qlik_atlas` contains backend and frontend components that interact through APIs, shared data assumptions, and backend-derived UI data.

Project testing already requires general testing and reporting (`QLIK-PS-002`), but backend changes can still cause frontend regressions if frontend verification is not explicitly triggered.

## Assumptions

Not every backend change affects frontend behavior, but impact detection is sometimes uncertain from code changes alone.

Frontend verification may currently be manual smoke testing in many cases until automated frontend coverage is standardized.

# 2. Problem Statement

Backend changes can unintentionally break or alter frontend behavior (API contracts, payload shapes, semantics, error handling, derived UI data) if frontend verification is omitted. Without an explicit project rule, agents may complete backend testing only and miss frontend-side regressions.

# 3. Goals & Success Metrics

## Goals

- Require explicit frontend impact assessment for backend changes.
- Require additional frontend verification when backend changes may affect frontend behavior.
- Make frontend impact findings visible in testing/reporting outputs.
- Require solution proposals when backend changes produce frontend impacts.

## Success Metrics

- Backend changes include an explicit frontend-impact assessment in the execution/testing flow.
- Potential frontend-impacting backend changes trigger frontend verification in addition to normal backend testing.
- Testing outputs document whether frontend impact was detected and what the proposed remediation options are.

# 4. Users / Stakeholders

## Primary Users

- Users requesting backend changes in `qlik_atlas`
- Reviewers validating that backend changes do not silently regress frontend behavior

## Stakeholders

- Backend maintainers
- Frontend maintainers
- Reviewers responsible for release safety and regression control

# 5. Scope

## In Scope

- Agent behavior when backend changes are implemented or reviewed
- Detection/assessment of possible frontend impact from backend changes
- Mandatory additional frontend verification when impact is possible/relevant
- Reporting of detected frontend impacts and remediation options

## Boundaries

- Does not require a specific frontend test framework
- Does not replace `QLIK-PS-002` (it extends project testing obligations for a specific trigger)
- Does not mandate frontend code changes in the same task if the user scope does not include fixes (but impacts and solutions must still be reported)

# 6. Non-Goals

- Classifying every backend internal refactor as frontend-impacting by default without assessment
- Defining final UI/UX decisions for every frontend impact
- Replacing product review when backend changes intentionally alter frontend behavior

# 7. Requirements

## Functional Requirements

- For backend changes, the agent MUST perform an explicit frontend-impact assessment before finalizing testing.
- If the backend change may affect frontend behavior, contracts, or backend-derived UI data, the agent MUST perform frontend verification in addition to normal backend testing.
- Frontend-impact assessment MUST consider at least these backend change categories when relevant:
  - API endpoint behavior or response payload changes
  - request validation / error response behavior changes
  - authentication/authorization behavior visible to frontend flows
  - backend business logic affecting values rendered or interpreted in the UI
  - database/query changes that alter backend data exposed to frontend dashboards/views
- If impact certainty is unclear, the agent MUST default to `potential frontend impact` and either:
  - run minimal frontend verification, or
  - explicitly ask for clarification if frontend verification is not feasible
- Frontend verification MAY be manual smoke checks when automated frontend tests are unavailable, but MUST be documented as manual.
- If frontend verification would require reading productive data (e.g. local DB/API payloads with real project data), the agent MUST first ask for explicit user approval and describe the minimal read scope.
- The agent MUST report frontend verification results in the testing output and explicitly state one of:
  - no frontend impact detected
  - frontend impact detected
  - frontend impact not fully verifiable (with blocker/limitation)
- If frontend impact is detected, the agent MUST:
  - describe the observed impact
  - describe affected flow/page/component/API assumption (as precisely as feasible)
  - propose one or more remediation options / solution suggestions
- The agent MUST continue to follow `PS-004`, `PS-005`, and `QLIK-PS-002` testing/data-safety rules.

### Frontend Verification Minimum Expectations (when backend impact is possible)

- Verify at least the directly affected frontend flow/page or API consumer path.
- Verify expected success behavior and at least one relevant failure/error path when feasible.
- If the backend change touches auth/session/security-relevant behavior, verify affected login/auth-protected frontend flow behavior.
- If the backend change affects backend-derived dashboard/lineage/stat data, verify representative frontend rendering/data-loading behavior for the impacted view.

### Reporting Requirements (Frontend Impact Addendum)

- Testing output MUST include a frontend-impact result summary for backend changes.
- The summary MUST include:
  - impact assessment (`none|possible|detected|not-verifiable`)
  - frontend verification performed (what/how)
  - observed impacts (if any)
  - remediation options / solution suggestions (if impact detected)
  - residual risk / blocker (if not fully verifiable)

## Non-Functional Requirements

- The rule should be applied consistently without requiring exhaustive frontend testing for every backend change.
- Frontend verification should be risk-proportionate and efficient (aligned with `PS-003`).
- Reporting should be clear enough for end users/reviewers to decide whether additional frontend work is needed.

# 8. User Flow / Scenarios / Edge Cases

## Main Flow

1. Agent implements or reviews a backend change.
2. Agent performs frontend-impact assessment.
3. Agent runs normal backend testing.
4. If frontend impact is possible, agent performs additional frontend verification.
5. Agent reports backend testing + frontend verification + frontend impact result.
6. If impact detected, agent provides remediation options.

## Alternate Flows

- If backend change is clearly internal and no frontend-facing behavior/data is affected, agent documents `no frontend impact detected` with rationale.
- If frontend verification is blocked by environment/tooling limits, agent marks `not-verifiable`, reports blocker and residual risk, and proposes next steps.

## Edge Cases

- Backend change appears contract-compatible but changes semantics used by frontend display logic; frontend verification is still required if impact is plausible.
- A backend change affects shared error messages/status codes and breaks frontend error handling assumptions.
- The user requests backend-only implementation and explicitly excludes frontend fixes; agent must still report detected frontend impacts and solution suggestions.

# 9. Acceptance Criteria

## Criteria List (empfohlen: AC-001, AC-002, ...)

- AC-001: For backend changes, the agent explicitly assesses potential frontend impact before finalizing work.
- AC-002: If frontend impact is possible, the agent performs frontend verification in addition to normal backend testing.
- AC-003: Frontend verification is documented in the testing output (including whether it was manual or automated).
- AC-004: The testing output explicitly reports frontend impact status (`none|possible|detected|not-verifiable`).
- AC-005: If frontend impact is detected, the agent reports observed impacts and at least one remediation option / solution suggestion.
- AC-006: If frontend verification cannot be completed, blocker/limitation and residual risk are explicitly reported.

## Expected Results / Pass Conditions

- Reviewers can see whether backend changes were checked for frontend effects without inferring it from raw test logs.
- Backend-only testing is not treated as sufficient when frontend impact is plausible.
- Detected frontend impacts are actionable because remediation options are documented.

## Traceability (Requirements / Spec links)

- `PS-003` (efficient/sustainable changes)
- `PS-004` (general testing model and reporting)
- `PS-005` (no production data in agent sessions)
- `QLIK-PS-002` (project testing concept and reporting)
- `QLIK-PS-004` (backend data as source of truth for UI lineage/stats, when relevant)

# 10. Dependencies / Risks / Assumptions

## Dependencies

- Availability of frontend runtime or test environment sufficient for smoke verification when required
- Availability of safe non-production data/mocks for frontend verification
- Discoverable mapping between changed backend area and affected frontend flow(s) where possible

## Risks

### Risk Register (fuer relevante Risiken)

| Risk ID | Description | Impact | Likelihood | Mitigation / Test Strategy | Residual Risk |
|---|---|---|---|---|---|
| R-001 | Backend changes with frontend impact are misclassified as internal-only | high | medium | Explicit frontend-impact assessment + default-to-potential when uncertain | medium |
| R-002 | Frontend verification is skipped due to tooling/time constraints | high | medium | Treat as blocker/not-verifiable and report residual risk | medium |
| R-003 | Manual frontend smoke checks miss edge regressions | medium | medium | Document limits, test representative critical flows, propose follow-up automation | medium |
| R-004 | Unsafe data used during frontend verification/debugging | high | low | Enforce `PS-005` / `QLIK-PS-002` no-prod-data rules | low |

## Data Safety / Privacy Constraints

- Production data allowed in agent session: no
- Production secrets allowed in agent session: no
- Allowed testing data: synthetic, sanitized, mock, staging-non-prod
- Any exception involving productive data reads for diagnosis/verification requires explicit user approval in advance and minimal-scope access only.

## Assumptions (Decision-Relevant)

- Frontend-impact assessment can often be made from API/data contract and flow knowledge even without full frontend automation.
- Reviewers prefer explicit frontend-impact reporting over silent assumptions of compatibility.

# 11. Rollout / Release Considerations

- Apply to all backend changes handled by agents in `qlik_atlas`.
- Use together with `QLIK-PS-002` and include frontend-impact findings in the Testing Summary output.
- Consider a future dedicated frontend smoke-path spec to standardize default verification targets.

# 12. Open Questions

- Which frontend pages/flows should be mandatory default verification targets for common backend change areas?
- Should a standardized `frontend-impact` subsection be added to the central `TESTING_SUMMARY` template or only required by project specs?
- Which backend directories/modules should be mapped to default frontend verification flows in project docs/specs?
