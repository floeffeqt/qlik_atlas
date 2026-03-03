---
id: QLIK-PS-007
title: Proactive bug hunting during testing with mandatory fix-or-report and bugfix documentation
status: draft
type: compliance
priority: p0
product_area: testing-and-quality
tags:
  - testing
  - bug-hunting
  - bugfix
  - regression-testing
  - quality-gate
  - documentation
spec_scope: project
project_key: qlik_atlas
owners: []
reviewers: []
created: 2026-03-02
updated: 2026-03-02
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
    - QLIK-PS-006

classification:
  user_impact: high
  business_impact: high
  delivery_risk: medium
  confidence: medium

dedup_check:
  compared_specs:
    - "Desktop/Ki/specs/GENERAL_PRODUCT_SPECS/SPECS/PS-004_agent-testing-spec-compliance-and-feature-validation.md"
    - ".product-specs/SPECS/QLIK-PS-002_testing-concept-spec-compliance-and-feature-validation.md"
    - ".product-specs/SPECS/QLIK-PS-006_backend-changes-with-frontend-impact-require-frontend-verification.md"
  result: partial_overlap
  action: create_new
  notes: Existing specs define testing/reporting and frontend-impact checks; this spec adds a mandatory proactive bug-hunt, severity-based fix decisions, and centralized bugfix documentation duty.
---

# 1. Context

## Observed Facts

Testing can pass the requested feature scope while unrelated but nearby regressions remain undetected.

Current project specs define testing/reporting obligations but do not yet require an explicit proactive bug-hunt pass in the changed area.

## Assumptions

Bug discovery quality increases when agents intentionally probe likely failure sources instead of only validating the happy-path acceptance criteria.

# 2. Problem Statement

If testing only checks requested functionality, latent defects in adjacent code paths can remain in production. Without a fix-or-report rule, found bugs may be ignored or under-documented.

# 3. Goals & Success Metrics

## Goals

- Require a proactive bug-hunt during testing for code/behavior changes.
- Require found bugs to be severity-classified and either fixed in-task or explicitly reported with impact and remediation.
- Require bugfix outcomes to be documented in a centralized, mandatory template format.

## Success Metrics

- Testing summaries explicitly include a "bug-hunt" section with severity-tagged outcomes.
- Confirmed bugs are not silently ignored.
- `FIXES_APPLIED.md` records each delivered bugfix using the central template in `docs/TEMPLATES/BUGFIX_ENTRY.md`.

# 4. Users / Stakeholders

## Primary Users

- Users requesting implementation/review tasks in `qlik_atlas`
- Reviewers validating release readiness

## Stakeholders

- Backend/frontend maintainers
- Product/security stakeholders relying on stable behavior

# 5. Scope

## In Scope

- Agent behavior during testing for code-/behavior-relevant tasks
- Proactive bug-source discovery in changed and adjacent areas
- Mandatory fix-or-report handling for confirmed bugs
- Bugfix documentation requirements

## Boundaries

- Full security audit or pentest scope
- Performance/load benchmark programs unless requested
- Multi-sprint refactors beyond task scope without user approval

# 6. Non-Goals

- Requiring agents to fix every low-value cosmetic issue in every task
- Blocking urgent delivery for speculative/non-reproducible findings
- Replacing normal acceptance-criteria validation

# 7. Requirements

## Functional Requirements

- For code/behavior changes, the agent MUST perform a proactive bug-hunt step in addition to feature/spec validation.
- The bug-hunt MUST include at least targeted checks of likely bug sources relevant to the change, e.g.:
  - changed control-flow branches and edge-case inputs
  - error/exception handling paths and non-2xx API flows
  - data mapping/serialization/deserialization boundaries
  - contract mismatches between backend/frontend or DB/runtime reads
  - state transitions and filter/sorting/pagination effects
- The agent MUST classify findings as:
  - confirmed bug
  - suspected bug (not yet reproducible)
  - no bug found in checked scope
- The agent MUST assign a severity to each confirmed bug using this model:
  - `critical`: data loss/corruption, security exposure, auth bypass, production outage, or hard-stop core flow failure
  - `high`: major functional break in primary flow, severe incorrect results, or high-regression-risk contract break
  - `medium`: incorrect behavior with workaround or limited-scope functional defect
  - `low`: minor non-blocking defect with low user/business impact
- For each confirmed bug discovered during the task:
  - if safe/in-scope, the agent MUST implement a fix in the same task
  - if not safe/out-of-scope/high-risk, the agent MUST not hide it and MUST report impact, scope reason, and remediation proposal
- Fix obligation by severity MUST be:
  - `critical`/`high`: MUST be fixed in-task whenever technically feasible; if not feasible, agent MUST stop silent progression, flag blocker status, and request user decision with concrete remediation options
  - `medium`: SHOULD be fixed in-task; if deferred, explicit rationale + residual risk + follow-up recommendation is mandatory
  - `low`: MAY be deferred with explicit rationale and residual risk note
- Confirmed bug fixes MUST be documented in `FIXES_APPLIED.md` using the central template `docs/TEMPLATES/BUGFIX_ENTRY.md`.
- All mandatory fields from the central template MUST be filled (no placeholder-only entry).
- Testing Summary MUST include:
  - bug-hunt scope (what was probed)
  - method (how it was probed)
  - findings with severity and classification
  - fix-or-report decision for each confirmed bug
  - residual risk for non-fixed findings
- The agent MUST keep following no-production-data constraints (`PS-005`, `QLIK-PS-002`).

### Fix Decision Guardrails

- The agent SHOULD fix confirmed bugs immediately when:
  - blast radius is limited
  - behavior is clearly incorrect
  - testability is feasible in-session
- For `critical` and `high` bugs, this "immediate fix" expectation is the default unless explicitly blocked by safety/scope constraints.
- The agent MUST ask for explicit user direction before applying a fix when:
  - bugfix requires major architecture change
  - bugfix has high migration/data-risk
  - requirements are ambiguous and multiple behavior interpretations are plausible

## Non-Functional Requirements

- Bug-hunt effort should be risk-proportionate and timeboxed.
- Reporting should be actionable and auditable by reviewers.
- Documentation entries should be concise and searchable.

# 8. User Flow / Scenarios / Edge Cases

## Main Flow

1. Agent implements requested change.
2. Agent performs standard tests plus proactive bug-hunt checks.
3. Agent classifies findings.
4. Confirmed bugs are fixed or explicitly reported with rationale.
5. Bugfixes are documented in `FIXES_APPLIED.md`.
6. Testing Summary reports bug-hunt evidence and residual risks.

## Alternate Flows

- No confirmed bug found: agent reports checks and "no bug found in checked scope".
- Bug confirmed but not fixable safely in scope: agent reports impact and remediation plan.

## Edge Cases

- Bug exists in untouched legacy code but is surfaced by current change.
- Suspected bug cannot be reproduced reliably in the current environment.
- Fix would require production-data inspection (must not proceed without explicit approval and minimal scope).

# 9. Acceptance Criteria

- AC-001: Testing output for code/behavior tasks includes an explicit proactive bug-hunt section.
- AC-002: Confirmed bugs discovered during the task are severity-classified (`critical|high|medium|low`) and either fixed in-task or explicitly reported with rationale and impact.
- AC-003: Delivered bugfixes are documented in `FIXES_APPLIED.md` using `docs/TEMPLATES/BUGFIX_ENTRY.md`.
- AC-004: Testing Summary includes bug-hunt scope/method/result and residual risks.
- AC-005: No productive data or productive secrets are used during bug-hunt/testing.

# 10. Dependencies / Risks / Assumptions

## Dependencies

- Access to test environment and tooling for targeted checks
- Existing testing/reporting workflow from `QLIK-PS-002`
- A maintained bugfix documentation target (`FIXES_APPLIED.md`) and central template (`docs/TEMPLATES/BUGFIX_ENTRY.md`)

## Risks

| Risk ID | Description | Impact | Likelihood | Mitigation / Test Strategy | Residual Risk |
|---|---|---|---|---|---|
| R-001 | Scope creep from aggressive bug-hunting | medium | medium | Risk-based/timeboxed checks and fix guardrails | low |
| R-002 | False positives consume time | medium | medium | Reproduction-first classification and evidence | low |
| R-003 | Non-fixed bugs get buried | high | low | Mandatory fix-or-report + residual risk field | low |
| R-004 | Missing bugfix traceability | high | low | Required `FIXES_APPLIED.md` entry using central template | low |

## Data Safety / Privacy Constraints

- Production data allowed in agent session: no
- Production secrets allowed in agent session: no
- Allowed testing data: synthetic, sanitized, mock, staging-non-prod

## Assumptions (Decision-Relevant)

- Proactive bug-hunting improves release quality without requiring full audits each task.
- Maintainers accept concise bugfix documentation as part of definition-of-done.

# 11. Rollout / Release Considerations

- Apply immediately to all code/behavior tasks handled by agents in `qlik_atlas`.
- Enforce in conjunction with `QLIK-PS-002` testing summaries.
- Add periodic review to tune bug-hunt depth/timebox based on delivery impact.

# 12. Open Questions

- Should project policy define a strict default timebox for bug-hunt checks per task size?
- Should project policy define strict SLAs by severity for deferred `medium`/`low` bugs?
