# ADR Agent

An AI-agent-driven system for generating **Architecture Decision Records (ADRs)** for
cloud services across **AWS, GCP, and Azure**. Talk to the agent (e.g. _"I need an ADR
for a GCS bucket"_), and it drafts a standards-compliant ADR, files it into the correct
Cloud Service Provider (CSP) folder, and can publish it to GitHub and Confluence.

## Features

- 🤖 **Conversational agent** — runs on **Google Gemini** now; swappable to **AWS Bedrock**
  or Anthropic via a single provider abstraction (`LLM_PROVIDER`).
- 🔐 **Login + RBAC** — free login now (Admin / User), designed for **SSO group mapping**
  on GKE later. Admins get the Admin Console; users get ADR creation only.
- ⚙️ **Admin Console** — configure GitHub & Confluence, set the author and admin group,
  toggle features, and **upload knowledge docs / add skills** — all per cloud.
- 📚 **Per-CSP skills & knowledge** — skills and standards are scoped `global | aws | gcp |
  azure`. The agent loads only *global + the target cloud*, so it **never mixes clouds**
  (no Azure details in an AWS ADR).
- 🗂️ **CSP folder taxonomy** — ADRs filed under `adrs/<cloud>/<category>/<service>/`,
  e.g. `adrs/gcp/database/warehouse/bigquery/`, `adrs/aws/database/sql/postgresql/`.
- ♾️ **Any service** — not limited to the catalog; unknown services get a best-fit category
  and a folder on demand — the agent never refuses.
- 🏗️ **IaC automation hints** — every ADR auto-includes a per-cloud Terraform/CLI hint.
- 📘 **KT documents** — every ADR auto-generates a **Knowledge Transfer** doc (operations
  handover to Cloud Operations) into a parallel `adrs/kt/` tree.
- 📄 **Word export** — download any ADR or KT as a `.docx`.
- 🚀 **Publishing** — pushes to GitHub + Confluence (local stubs until creds are set in the
  Admin Console).
- 🖥️ **Modern UI** — React + Vite: **resizable/collapsible** three-pane workspace,
  **day/night theme toggle**, fully responsive. Author defaults to **Cloud Engineering**.

## Architecture

```
adr-app/
├── backend/            FastAPI + agent + skills + knowledge
│   └── app/
│       ├── main.py         API routes
│       ├── config.py       settings (.env)
│       ├── llm/            LLM provider abstraction (Claude → Bedrock)
│       ├── agent/         agent loop + tools
│       ├── skills/        agent skills (SKILL.md files)
│       ├── services/      catalog, adr builder, storage, publishers
│       ├── knowledge/     Confluence-mirrored docs (placeholders)
│       └── templates/     ADR markdown template
├── frontend/           React + Vite UI
└── adrs/               generated ADRs, organized by CSP
```

## Quick start

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then edit .env and add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Swapping to AWS Bedrock later

All LLM calls go through `backend/app/llm/provider.py`. Set `LLM_PROVIDER=bedrock` in
`.env` and fill in the Bedrock section — no other code changes required.
