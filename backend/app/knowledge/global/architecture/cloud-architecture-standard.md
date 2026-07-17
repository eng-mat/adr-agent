# Cloud Architecture Standard (GENERIC PLACEHOLDER)

> ⚠️ Generic placeholder mirroring the organization's Confluence
> **Cloud Architecture Standard**. Replace with the real page when available.
>
> Source (to be set): `<CONFLUENCE_ARCHITECTURE_STANDARD_URL>`

## 1. Naming Conventions

- Resource names: `<org>-<env>-<app>-<service>-<qualifier>`, lowercase, hyphen-separated.
- Environments: `dev`, `staging`, `prod`.
- Everything is provisioned as code (Terraform preferred). No click-ops in prod.

## 2. Regions & Residency

- Default region documented per business unit; do not deploy outside approved regions.
- Multi-region only when an availability or residency requirement justifies it.

## 3. Reliability

- Stateful services: automated backups + tested restore; define RPO/RTO in the ADR.
- Prefer managed services over self-hosted where the capability exists.
- Design for a single-AZ failure at minimum for production workloads.

## 4. Cost

- Right-size by default; document expected sizing and scaling in the ADR.
- Apply lifecycle/retention policies to control storage growth.

## 5. Tagging (mandatory)

`owner`, `cost-center`, `data-classification`, `environment`, `app`, `managed-by`.

## 6. ADR Expectations

- One ADR per significant resource/decision, filed under the correct CSP folder.
- Must state alternatives considered and consequences.
- Must reference the applicable Security Standard controls.
