---
name: aws-conventions
description: AWS-specific naming, tagging, and service conventions for ADRs.
when_to_use: Only when the target cloud is AWS.
---

# Skill: AWS Conventions (AWS only)

Apply these when — and only when — the ADR targets **AWS**. Do not use AWS resource types,
service names, or terminology in a GCP or Azure ADR.

- **Naming:** `org-<env>-<app>-<service>` (lowercase, hyphen). Example: `acme-prod-billing-s3`.
- **Tags (mandatory):** `owner`, `cost-center`, `data-classification`, `environment`, `app`,
  `managed-by=terraform`.
- **Regions:** default `us-east-1` unless a data-residency requirement says otherwise.
- **Encryption:** SSE-KMS with a customer-managed key; enable rotation.
- **Terminology to use:** VPC, Security Group, IAM Role, S3, RDS, KMS, CloudWatch, Secrets Manager.
- Ground the security section in the **AWS Security Baseline** knowledge doc (aws scope).
