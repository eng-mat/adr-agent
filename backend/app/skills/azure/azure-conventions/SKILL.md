---
name: azure-conventions
description: Azure-specific naming, tagging, and service conventions for ADRs.
when_to_use: Only when the target cloud is Azure.
---

# Skill: Azure Conventions (Azure only)

Apply these when — and only when — the ADR targets **Azure**. Do not use Azure resource
types, service names, or terminology in an AWS or GCP ADR.

- **Naming:** `org-<env>-<app>-<service>` (lowercase, hyphen). Example: `acme-prod-billing-blob`.
- **Tags (mandatory):** `owner`, `cost-center`, `data-classification`, `environment`, `app`,
  `managed-by=terraform`.
- **Regions:** default `eastus` unless a data-residency requirement says otherwise.
- **Encryption:** customer-managed keys in Key Vault; enable rotation.
- **Terminology to use:** Virtual Network, NSG, Entra ID, Blob Storage, Azure SQL, Key Vault,
  Azure Monitor, Managed Identity, Private Endpoint.
- Ground the security section in the **Azure Security Baseline** knowledge doc (azure scope).
