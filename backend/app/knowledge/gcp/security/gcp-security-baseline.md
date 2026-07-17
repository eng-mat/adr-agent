# GCP Security Baseline (GENERIC PLACEHOLDER)

> ⚠️ GCP-specific placeholder. Applies **only** to GCP ADRs. Replace with your real
> Confluence content. Source (to be set): `<CONFLUENCE_GCP_SECURITY_URL>`

- **Encryption:** default to **CMEK via Cloud KMS**; enable key rotation.
- **GCS:** enforce **Public Access Prevention** + **Uniform bucket-level access**.
- **IAM:** predefined/custom roles with least privilege; avoid primitive roles (Owner/Editor) in prod.
- **Identity:** service accounts with **Workload Identity**; no exported SA keys.
- **Secrets:** Secret Manager; never in env vars or ADRs.
- **Network:** VPC Service Controls for data perimeters; Private Google Access; default-deny firewall.
- **Logging:** Cloud Audit Logs (Admin + Data Access) to the central logging project.
- **Mandatory labels:** `owner`, `cost-center`, `data-classification`, `environment`, `app`, `managed-by`.
