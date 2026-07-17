---
id: KT-0001
adr: ADR-0001
title: KT — Provision analytics data lake GCS bucket
audience: Cloud Operations
author: Cloud Engineering
date: 2026-07-17
cloud: Google Cloud Platform
service: Cloud Storage (GCS) Bucket
category: storage
---

# KT-0001 — Knowledge Transfer: Provision analytics data lake GCS bucket

> Handover from **Cloud Engineering** (Cloud Engineering) to **Cloud Operations**.
> Source decision: **ADR-0001**. This resource will be passed to Automation for build.

| | |
|---|---|
| **KT ID** | KT-0001 |
| **ADR** | ADR-0001 |
| **Cloud** | Google Cloud Platform |
| **Service** | Cloud Storage (GCS) Bucket |
| **Date** | 2026-07-17 |
| **Built by** | Cloud Engineering (Cloud Engineering) |
| **Operated by** | Cloud Operations |

## 1. Summary — what was provisioned

The analytics platform needs durable, versioned object storage for its raw data lake.

**Decision:** We will provision a single-region, CMEK-encrypted, private GCS bucket with versioning.

## 2. Architecture & Configuration

- region: us-central1
- storage class: STANDARD
- versioning: enabled
- uniform bucket-level access: on
- lifecycle: transition to NEARLINE after 30d

## 3. Access & Security

Encryption at rest via Cloud KMS (CMEK); public access prevention enforced; uniform bucket-level access; data access audit logs shipped to central logging.

## 4. How it is built (Infrastructure as Code)

**Tooling:** Terraform (`hashicorp/google`) · CLI `gcloud`

**Primary Terraform resource(s):** `google_storage_bucket`, `google_storage_bucket_iam_binding`

**Suggested module namespace:** `registry.terraform.io/terraform-google-modules`

**Key inputs the automation team should parameterize:**

- name
- location/region
- encryption key (CMEK)
- versioning
- lifecycle rules
- public access block

**Guardrails to encode:** private access by default, CMEK encryption, least-privilege IAM, audit logging, and the mandatory tag set.

## 5. Operational Runbook

- **Provision / Apply:** built by Automation from the ADR's IaC (Terraform). Do not click-op in prod.
- **Verify healthy:** _confirm the resource exists, encryption + private access are enforced, and tags are present._
- **Monitoring & alerting:** _wire to the central monitoring workspace per the monitoring standard._
- **Backup / restore:** _document RPO/RTO and test restore for stateful services._
- **Rollback:** _revert the IaC change and re-apply the previous known-good state._

## 6. Ownership & Escalation

- **Built by:** Cloud Engineering (Cloud Engineering)
- **Operated by:** Cloud Operations
- **Escalation path:** _<team / on-call / pager — to be completed>_

## 7. Standards Applied

Name: org-dev-analytics-datalake-gcs. Labels: owner, cost-center, data-classification=Confidential, environment=dev, app=analytics, managed-by=terraform.

## 8. References

- ADR: `gcp/storage/gcs/ADR-0001-provision-analytics-data-lake-gcs-bucket.md`
- Cloud Security Standard — <CONFLUENCE_LINK_PLACEHOLDER>
- Cloud Architecture Standard — <CONFLUENCE_LINK_PLACEHOLDER>
