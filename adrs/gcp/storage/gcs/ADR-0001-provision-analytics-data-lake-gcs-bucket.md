---
id: ADR-0001
title: Provision analytics data lake GCS bucket
status: Proposed
date: 2026-07-17
author: Cloud Engineering
cloud: Google Cloud Platform
service: Cloud Storage (GCS) Bucket
category: storage
tags: []
---

# ADR-0001: Provision analytics data lake GCS bucket

| | |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-07-17 |
| **Author** | Cloud Engineering |
| **Cloud** | Google Cloud Platform |
| **Service** | Cloud Storage (GCS) Bucket |
| **Category** | storage |

## Context

The analytics platform needs durable, versioned object storage for its raw data lake.

## Decision

We will provision a single-region, CMEK-encrypted, private GCS bucket with versioning.

## Architecture & Configuration

- region: us-central1
- storage class: STANDARD
- versioning: enabled
- uniform bucket-level access: on
- lifecycle: transition to NEARLINE after 30d

## Security & Compliance

Encryption at rest via Cloud KMS (CMEK); public access prevention enforced; uniform bucket-level access; data access audit logs shipped to central logging.

> Security guidance is derived from the organization's Cloud Security Standard.
> See references below. Replace placeholder links with your Confluence pages.

## Standards & Naming Conventions

Name: org-dev-analytics-datalake-gcs. Labels: owner, cost-center, data-classification=Confidential, environment=dev, app=analytics, managed-by=terraform.

## Consequences

**Positive**
- Durable and fully managed
- Versioning protects against accidental overwrite
- CMEK gives key control

**Negative / Trade-offs**
- Cross-region egress incurs cost
- CMEK adds key lifecycle management overhead

## Alternatives Considered

Considered a multi-region bucket (rejected: higher cost, residency requirement is single-region).

## Infrastructure as Code (Automation Hint)

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

## Automation Notes

_To be completed by the automation team._

## References

- Cloud Security Standard — <CONFLUENCE_LINK_PLACEHOLDER>
- Cloud Architecture Standard — <CONFLUENCE_LINK_PLACEHOLDER>
