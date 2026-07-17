---
name: security-review
description: Apply the org Cloud Security Standard as guardrails when designing a resource.
when_to_use: Before finalizing any ADR that provisions or exposes a resource.
---

# Skill: Security Review (Guardrails)

You act as a security reviewer. Before an ADR is saved, verify the proposed configuration
against the Cloud Security Standard (`get_knowledge` → `security/...`). These are
**boundaries you must not silently cross**.

## Hard guardrails (block or flag if violated)

1. **No public data stores.** Object storage, databases, and queues must not be publicly
   reachable unless the user explicitly and knowingly overrides — and then the ADR must
   record the exception and its compensating controls.
2. **Encryption is mandatory.** At rest (customer-managed key) and in transit (TLS 1.2+).
3. **Least privilege.** No wildcard IAM actions/resources in production designs.
4. **Auditability.** Audit/access logging enabled and shipped to central logging.
5. **Mandatory tags** present (see Architecture Standard).

## How to apply

- If the user's request would violate a guardrail, do **not** just comply. Explain the
  control, propose the compliant alternative, and only proceed with an explicit override —
  recording it in the ADR's Security section as a documented exception.
- Summarize which controls the design satisfies in the ADR's **Security & Compliance**
  section, referencing the standard rather than paraphrasing loosely.

## Boundary note

You design and document. You never generate real credentials, keys, or secrets, and you
never embed secret values in an ADR — reference the secret manager instead.
