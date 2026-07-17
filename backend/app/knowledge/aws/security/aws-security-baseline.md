# AWS Security Baseline (GENERIC PLACEHOLDER)

> ⚠️ AWS-specific placeholder. Applies **only** to AWS ADRs. Replace with your real
> Confluence content. Source (to be set): `<CONFLUENCE_AWS_SECURITY_URL>`

- **Encryption:** default to SSE-KMS with a **customer-managed KMS key**; enable key rotation.
- **S3:** enable **Block Public Access** at account + bucket; enforce TLS via bucket policy.
- **IAM:** roles over users; no wildcard `Action`/`Resource` in prod; use permission boundaries.
- **Secrets:** AWS Secrets Manager (rotation enabled); never in env vars or ADRs.
- **Network:** private subnets for data; Security Groups default-deny; VPC endpoints for AWS APIs.
- **Logging:** CloudTrail (org trail) + resource-level access logging to the central log account.
- **Mandatory tags:** `owner`, `cost-center`, `data-classification`, `environment`, `app`, `managed-by`.
