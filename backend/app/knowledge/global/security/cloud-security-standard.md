# Cloud Security Standard (GENERIC PLACEHOLDER)

> ⚠️ This is a generic placeholder mirroring the organization's Confluence
> **Cloud Security Standard**. Replace the content and the reference link below with
> your real published page when available.
>
> Source (to be set): `<CONFLUENCE_SECURITY_STANDARD_URL>`

## 1. Identity & Access

- Enforce least-privilege IAM. No wildcard (`*`) actions on resources in production.
- Human access is federated via SSO; no long-lived local users.
- Service-to-service auth uses workload identity / instance roles, not static keys.
- Rotate any unavoidable static credentials at most every 90 days.

## 2. Encryption

- **At rest:** all data encrypted with a customer-managed key (CMK/KMS/Key Vault).
- **In transit:** TLS 1.2+ enforced; plaintext protocols disabled.
- Key rotation enabled; key deletion protected by a waiting period.

## 3. Network

- Default-deny network posture. Only explicitly required ports/CIDRs are opened.
- No public ingress to data stores. Access via private endpoints / VPC-internal only.
- Egress controlled and logged where feasible.

## 4. Data Protection

- Classify data (Public / Internal / Confidential / Restricted) and tag resources.
- Block public access on object storage by default.
- Enable versioning and a retention/backup policy on stateful stores.

## 5. Logging & Monitoring

- Enable audit logging (control-plane and data-plane where available).
- Ship logs to the central logging account/workspace.
- Alert on anomalous access and policy changes.

## 6. Compliance Baselines

- Tag every resource with: `owner`, `cost-center`, `data-classification`, `environment`.
- Resources must pass the org policy-as-code checks before promotion to production.
