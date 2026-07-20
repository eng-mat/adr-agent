"""Knowledge Transfer (KT) documents.

Every ADR (automation document) produced by Cloud Engineering is accompanied by a KT
document handing the resource over to **Cloud Operations**: what was built, how it's
operated, and how to escalate.

KT docs mirror the ADR's per-service numbering — `KT-0001` belongs to that service's
`ADR-0001`. Records are keyed by the ADR's `uid` (e.g. `gcp-gcs-0001`), since the display
id repeats across services.

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
    uid: str          # the ADR's uid — KT is 1:1 with its ADR
    id: str           # display id, e.g. "KT-0001"
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
    adr_uid: str,
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

    doc = KTDoc(
        uid=adr_uid,
        id=kt_id,
        adr_id=adr_id,
        title=f"KT — {adr_title}",
        cloud=cloud_slug,
        service=service_name,
        date=date,
        rel_path=f"kt/{folder_rel}/{filename}",
        path=str(path),
    )
    _append_index(doc)
    return doc


def _index_path() -> Path:
    return kt_root() / "index.json"


def _read_index() -> list[dict]:
    p = _index_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _write_index(entries: list[dict]) -> None:
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _append_index(doc: KTDoc) -> None:
    entries = [e for e in _read_index() if e.get("uid") != doc.uid]
    entries.append(asdict(doc))
    _write_index(entries)


def list_kt() -> list[dict]:
    return sorted(_read_index(), key=lambda e: (e.get("date", ""), e.get("uid", "")), reverse=True)


def _find_entry(adr_uid: str) -> dict | None:
    for e in _read_index():
        if e.get("uid") == adr_uid:
            return e
    for e in _read_index():  # legacy records keyed by display id
        if e.get("id") == adr_uid or e.get("adr_id") == adr_uid:
            return e
    return None


def read_kt_for_adr(adr_uid: str) -> dict | None:
    entry = _find_entry(adr_uid)
    if not entry:
        return None
    p = Path(entry["path"])
    if not p.exists():
        return None
    out = dict(entry)
    out["markdown"] = p.read_text(encoding="utf-8")
    return out


def update_kt(adr_uid: str, markdown: str) -> dict | None:
    """Overwrite a KT document's markdown (inline editing)."""
    entry = _find_entry(adr_uid)
    if not entry:
        return None
    p = Path(entry["path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown, encoding="utf-8")
    return read_kt_for_adr(adr_uid)
