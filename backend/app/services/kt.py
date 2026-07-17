"""Knowledge Transfer (KT) documents.

Every ADR (automation document) produced by Cloud Engineering is accompanied by a KT
document that hands the resource over to **Cloud Operations**: what was built, how it's
operated, and how to escalate. KT docs live in a parallel tree and share the ADR's number.

Layout:  <ADR_OUTPUT_DIR>/kt/<cloud>/<service-folder>/KT-XXXX-<slug>.md
Index:   <ADR_OUTPUT_DIR>/kt/index.json
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from app.config import settings
from app.services.adr_builder import ADRContent


@dataclass
class KTDoc:
    id: str
    adr_id: str
    title: str
    cloud: str
    service: str
    date: str
    rel_path: str
    path: str


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "kt"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- _None recorded._"


def kt_root() -> Path:
    return settings.adr_dir / "kt"


def generate(
    *,
    adr_id: str,
    adr_title: str,
    adr_rel_path: str,
    cloud_slug: str,
    cloud_name: str,
    service_name: str,
    category: str,
    folder_rel: str,
    content: ADRContent,
    author: str,
    date: str,
) -> KTDoc:
    kt_id = adr_id.replace("ADR-", "KT-")
    folder = kt_root() / folder_rel
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{kt_id}-{_slugify(adr_title)}.md"
    path = folder / filename

    references = content.references or [
        "Cloud Security Standard — <CONFLUENCE_LINK_PLACEHOLDER>",
        "Cloud Architecture Standard — <CONFLUENCE_LINK_PLACEHOLDER>",
    ]

    md = f"""---
id: {kt_id}
adr: {adr_id}
title: KT — {adr_title}
audience: Cloud Operations
author: {author}
date: {date}
cloud: {cloud_name}
service: {service_name}
category: {category}
---

# {kt_id} — Knowledge Transfer: {adr_title}

> Handover from **{author}** (Cloud Engineering) to **Cloud Operations**.
> Source decision: **{adr_id}**. This resource will be passed to Automation for build.

| | |
|---|---|
| **KT ID** | {kt_id} |
| **ADR** | {adr_id} |
| **Cloud** | {cloud_name} |
| **Service** | {service_name} |
| **Date** | {date} |
| **Built by** | {author} (Cloud Engineering) |
| **Operated by** | Cloud Operations |

## 1. Summary — what was provisioned

{content.context.strip()}

**Decision:** {content.decision.strip()}

## 2. Architecture & Configuration

{content.architecture.strip()}

## 3. Access & Security

{content.security.strip()}

## 4. How it is built (Infrastructure as Code)

{content.iac.strip() or "_See the ADR's IaC hint._"}

## 5. Operational Runbook

- **Provision / Apply:** built by Automation from the ADR's IaC (Terraform). Do not click-op in prod.
- **Verify healthy:** _confirm the resource exists, encryption + private access are enforced, and tags are present._
- **Monitoring & alerting:** _wire to the central monitoring workspace per the monitoring standard._
- **Backup / restore:** _document RPO/RTO and test restore for stateful services._
- **Rollback:** _revert the IaC change and re-apply the previous known-good state._

## 6. Ownership & Escalation

- **Built by:** {author} (Cloud Engineering)
- **Operated by:** Cloud Operations
- **Escalation path:** _<team / on-call / pager — to be completed>_

## 7. Standards Applied

{content.standards.strip()}

## 8. References

- ADR: `{adr_rel_path}`
{_bullets([f"{r}" for r in references])}
"""
    path.write_text(md, encoding="utf-8")

    kt = KTDoc(
        id=kt_id,
        adr_id=adr_id,
        title=f"KT — {adr_title}",
        cloud=cloud_slug,
        service=service_name,
        date=date,
        rel_path=f"kt/{folder_rel}/{filename}",
        path=str(path),
    )
    _append_index(kt)
    return kt


def _append_index(kt: KTDoc) -> None:
    index_path = kt_root() / "index.json"
    entries: list[dict] = []
    if index_path.exists():
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
    entries = [e for e in entries if e.get("id") != kt.id]
    entries.append(asdict(kt))
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def list_kt() -> list[dict]:
    index_path = kt_root() / "index.json"
    if not index_path.exists():
        return []
    try:
        entries = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return sorted(entries, key=lambda e: e.get("id", ""), reverse=True)


def read_kt(kt_id: str) -> dict | None:
    for entry in list_kt():
        if entry.get("id") == kt_id:
            p = Path(entry["path"])
            if p.exists():
                entry = dict(entry)
                entry["markdown"] = p.read_text(encoding="utf-8")
                return entry
    return None


def read_kt_for_adr(adr_id: str) -> dict | None:
    return read_kt(adr_id.replace("ADR-", "KT-"))
