# Azure Security Baseline (GENERIC PLACEHOLDER)

> ⚠️ Azure-specific placeholder. Applies **only** to Azure ADRs. Replace with your real
> Confluence content. Source (to be set): `<CONFLUENCE_AZURE_SECURITY_URL>`

- **Encryption:** default to **customer-managed keys in Key Vault**; enable key rotation.
- **Storage:** disable public blob access; require secure transfer (HTTPS); use Private Endpoints.
- **Identity:** **Entra ID** with managed identities; RBAC least privilege; no shared keys where avoidable.
- **Secrets:** Azure Key Vault (with purge protection); never in env vars or ADRs.
- **Network:** default-deny NSGs; Private Link/Endpoints for PaaS data services.
- **Logging:** Azure Monitor + diagnostic settings to the central Log Analytics workspace.
- **Mandatory tags:** `owner`, `cost-center`, `data-classification`, `environment`, `app`, `managed-by`.
