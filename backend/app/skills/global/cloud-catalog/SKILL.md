---
name: cloud-catalog
description: Map a user's request to the right cloud, service, and CSP folder.
when_to_use: At the start of any ADR request, to resolve what is being decided and where it is filed.
---

# Skill: Cloud Catalog & Foldering

Every ADR is filed under a deterministic path:

```
adrs/<cloud>/<category>/<subpath?>/<service>/ADR-XXXX-<slug>.md
```

Examples:
- "GCS bucket"            → `adrs/gcp/storage/gcs/`
- "RDS Postgres"         → `adrs/aws/database/sql/postgresql/`
- "BigQuery dataset"     → `adrs/gcp/database/warehouse/bigquery/`
- "Azure Blob storage"   → `adrs/azure/storage/blob/`

## How to resolve a request

1. Determine the cloud (aws | gcp | azure). If ambiguous, ask.
2. Use `search_catalog` with the user's words. If it returns a match, pass that
   `cloud_slug` + `service_slug` to `save_adr` — the folder is derived from the catalog.
3. If nothing matches, **do not stop** — the catalog is a convenience, not a limit. File
   the ADR for the requested service anyway:
   - choose the best-fit `category` from the standard list below,
   - set a clean kebab-case `service_slug` (e.g. `sagemaker`, `eventarc`, `app-config`),
   - set a human `service_name` (e.g. "Amazon SageMaker Endpoint"),
   - optionally set a `subpath` to nest it (e.g. `sql`, `warehouse`, `training`),
   - pass all of these to `save_adr`. It creates the folder on demand.

## Standard categories (for ad-hoc services)

`compute`, `storage`, `database`, `networking`, `security-identity`, `containers`,
`serverless`, `analytics`, `messaging`, `monitoring`, `ai-ml`, `developer-tools`,
`management`, `other`.

## Database foldering (common source of confusion)

The `database` category splits by engine family:
- `sql/` → mysql, postgresql, aurora, azure-sql, spanner
- `nosql/` → dynamodb, firestore, bigtable, cosmos-db
- `warehouse/` → bigquery, redshift, synapse

Always pass the exact `cloud_slug` + `service_slug` from the catalog to `save_adr`.
