---
name: adr-authoring
description: How to author a standards-compliant Architecture Decision Record.
when_to_use: Whenever drafting or updating the content of an ADR.
---

# Skill: ADR Authoring

You write ADRs that the automation team can act on directly. An ADR is a decision record,
not a tutorial — be precise and prescriptive.

## Required quality bar for every section

- **Context** — the problem/need in 2-4 sentences. Why does this resource exist?
- **Decision** — a single clear decision, stated affirmatively ("We will provision…").
- **Architecture & Configuration** — concrete, automatable settings: region, sizing,
  networking (public/private), encryption, versioning/backup, access model. Prefer a
  short bullet list of key/value settings the automation team can translate to IaC.
- **Security & Compliance** — cite the specific controls from the Cloud Security Standard
  that apply (encryption, IAM least-privilege, network posture, logging, tagging). Never
  invent controls — use the knowledge base via the `get_knowledge` tool.
- **Standards & Naming Conventions** — apply the naming pattern and mandatory tags from
  the Architecture Standard.
- **Consequences** — honest positives and trade-offs.
- **Alternatives Considered** — at least one, with why it was not chosen.
- **Infrastructure as Code (Automation Hint)** — auto-generated per cloud/service
  (Terraform resource(s), CLI, key inputs, guardrails). Leave the `iac` field blank to use
  the generated hint; only override it if you have something more specific.
- **Automation Notes** — any extra, request-specific guidance for the automation team.

## Process

1. Identify the target cloud + service (use `search_catalog` if unsure).
2. Pull the relevant security & architecture guidance with `get_knowledge`.
3. Ask the user for anything decision-critical you cannot reasonably default
   (environment, data classification, region) — but propose sensible defaults.
4. Draft, then call `save_adr` with fully-populated fields.

## Defaults (state them explicitly when you apply them)

- Environment: `dev` unless told otherwise.
- Encryption: customer-managed key, at rest + in transit.
- Network: private access only; public access blocked.
- Tags: `owner`, `cost-center`, `data-classification`, `environment`, `app`, `managed-by`.
