---
id: QLIK-PS-001
title: Critical credentials stored in the database must be encrypted with AES-256-GCM
status: draft
type: security
priority: p0
product_area: credentials-and-secrets
tags:
  - security
  - credentials
  - encryption
  - aes-256-gcm
  - secrets-at-rest
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
  related_specs: ["PS-001"]

classification:
  user_impact: high
  business_impact: high
  delivery_risk: medium
  confidence: medium

dedup_check:
  compared_specs:
    - "GENERAL_PRODUCT_SPECS/SPECS/PS-001_ai-action-execution-standard.md"
    - ".product-specs/SPECS (empty at creation time)"
  result: unique
  action: create_new
  notes: No existing general or project spec defines encryption requirements for credentials persisted to the database.
---

# 1. Context

## Observed Facts

The project stores data in a database, and some records may contain credentials.

Credentials persisted without strong authenticated encryption create a high risk of compromise if the database is exposed.

## Assumptions

"Critical credentials" means secrets that grant direct or privileged access to systems or data, including but not limited to API keys, client secrets, passwords, tokens, and private keys.

The project can access a secure key source outside the database (for example environment secret store, KMS, or equivalent).

# 2. Problem Statement

Without a binding project rule, critical credentials may be stored in plaintext or with inconsistent protection, increasing breach impact and reducing auditability.

# 3. Goals & Success Metrics

## Goals

- Ensure all critical credentials written to the database are encrypted before persistence.
- Standardize on AES-256-GCM for authenticated encryption at rest.
- Make failures explicit so plaintext is never written as a fallback.

## Success Metrics

- New code paths that persist critical credentials use AES-256-GCM.
- No plaintext critical credentials are newly written to the database.
- Tests verify encryption/decryption behavior and tamper detection for credential records.

# 4. Users / Stakeholders

## Primary Users

- Developers implementing credential persistence
- Reviewers validating security-sensitive changes

## Stakeholders

- Security/compliance owners
- Operators responsible for secret/key management

# 5. Scope

## In Scope

- All application code in `qlik_atlas` that writes critical credentials to any database table/collection
- Encryption requirement for data at rest in the database
- Storage of required metadata for AES-256-GCM decryption and integrity verification (for example nonce/IV, auth tag, key version/id)

## Boundaries

- Transport encryption (TLS) requirements
- Full key-management implementation design (KMS/provider choice)
- Non-critical configuration values that are not credentials

# 6. Non-Goals

- Mandating a specific database vendor feature for encryption
- Defining UI masking behavior
- Defining backup encryption policy

# 7. Requirements

## Functional Requirements

- The system MUST classify and treat critical credentials as sensitive secrets before database persistence.
- The system MUST encrypt every critical credential value before writing it to the database.
- The encryption algorithm MUST be AES-256-GCM.
- Each encryption operation MUST use a unique nonce/IV appropriate for AES-GCM usage.
- The system MUST store or derive the metadata required for successful decryption and authentication verification (including nonce/IV and auth tag; key identifier/version if applicable).
- Encryption keys MUST NOT be stored as plaintext in the same database field/record as the protected credential value.
- If encryption fails, the write operation MUST fail closed and MUST NOT persist plaintext as fallback.
- Decryption routines MUST verify the GCM authentication tag and reject modified ciphertext.

## Non-Functional Requirements

- The encryption/decryption implementation SHOULD be centralized in a reusable module/service to reduce inconsistent handling.
- The solution SHOULD support key rotation via key id/version metadata without requiring plaintext storage.
- Logging and error handling MUST avoid emitting plaintext credential values.

# 8. User Flow / Scenarios / Edge Cases

## Main Flow

1. Application receives a critical credential to persist.
2. Application calls the credential encryption component.
3. Component encrypts the credential using AES-256-GCM with a fresh nonce/IV.
4. Application stores ciphertext plus required metadata in the database.
5. On read/use, application decrypts and verifies the auth tag before use.

## Alternate Flows

- If the key source is unavailable, the operation fails and no credential is written.
- If ciphertext integrity verification fails during decryption, the system rejects the value and raises a security-relevant error.

## Edge Cases

- Existing plaintext rows created before this spec may require a migration plan (out of scope for this spec but must be tracked separately).
- Composite records containing both secret and non-secret fields must encrypt only the credential fields while preserving data model integrity.

# 9. Acceptance Criteria

- Any new or modified code path that writes critical credentials persists ciphertext, not plaintext.
- The implementation uses AES-256-GCM for critical credential encryption.
- Stored records include the metadata necessary for decryption/authentication verification.
- Automated tests cover:
  - successful encrypt -> persist -> decrypt roundtrip
  - encryption failure fails closed (no plaintext write)
  - tampered ciphertext or auth tag causes decryption failure
- Code review evidence shows no plaintext credential logging in the affected path(s).

# 10. Dependencies / Risks / Assumptions

## Dependencies

- Availability of a secure encryption key source outside the database
- A project implementation decision for key rotation and key storage provider

## Risks

- Incorrect nonce handling can break AES-GCM security guarantees.
- Partial rollout may leave legacy plaintext credentials in storage.
- Developers may misclassify credentials without a maintained sensitive-field inventory.

## Assumptions (Decision-Relevant)

- AES-256-GCM is acceptable for the project's compliance/security requirements.
- The project can introduce or reuse a crypto library that correctly supports AES-256-GCM.

# 11. Rollout / Release Considerations

- Apply to all new credential persistence changes immediately.
- Create follow-up work to inventory critical credential fields and legacy plaintext data.
- Add security review checks for credential persistence paths.

# 12. Open Questions

- What is the authoritative list of "critical credential" fields in `qlik_atlas`?
- Which key source/provider will be used (env secret, OS secret store, KMS, HSM, other)?
- Is a migration spec needed now for existing plaintext credentials already stored in the database?

