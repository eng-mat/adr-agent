---
name: gcp-conventions
description: GCP-specific naming, labeling, and service conventions for ADRs.
when_to_use: Only when the target cloud is GCP.
---

# Skill: GCP Conventions (GCP only)

Apply these when — and only when — the ADR targets **GCP**. Do not use GCP resource types,
service names, or terminology in an AWS or Azure ADR.

- **Naming:** `org-<env>-<app>-<service>` (lowercase, hyphen). Example: `acme-prod-billing-gcs`.
- **Labels (mandatory):** `owner`, `cost-center`, `data-classification`, `environment`, `app`,
  `managed-by=terraform`.
- **Regions:** default `us-central1` unless a data-residency requirement says otherwise.
- **Encryption:** CMEK via Cloud KMS; enable rotation.
- **Terminology to use:** VPC Network, Firewall, IAM, GCS, Cloud SQL, BigQuery, Cloud KMS,
  Secret Manager, Workload Identity.
- Ground the security section in the **GCP Security Baseline** knowledge doc (gcp scope).
