"""Persist ADRs into the CSP folder taxonomy, numbered **per service**.

Layout:  <ADR_OUTPUT_DIR>/<cloud>/<category>/<subpath?>/<service>/ADR-XXXX-<slug>.md

Numbering restarts for every service, so `gcp/storage/gcs` and `gcp/containers/gke` each
begin at `ADR-0001`; the second GCS decision becomes `ADR-0002`. Because the displayed id
is therefore **not globally unique**, every record also carries a `uid`
(`<cloud>-<service>-<number>`, e.g. `gcp-gcs-0001`) which is what the API and UI key on.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import date as date_cls
from pathlib import Path

from app.config import settings
from app.services import config_store, kt
from app.services.adr_builder import ADRContent, render_markdown
from app.services.catalog import (
    Service,
    find_service,
    build_folder,
    normalize_category,
    CLOUD_BY_SLUG,
)
from app.services.iac import iac_hint_markdown


@dataclass
class SavedADR:
    uid: str             # globally unique key, e.g. "gcp-gcs-0001"
    id: str              # display id, unique per service, e.g. "ADR-0001"
    number: int
    cloud: str
    service: str
    title: str
    status: str
    date: str
    folder: str          # POSIX path relative to ADR root
    path: str            # absolute path on disk
    rel_path: str        # POSIX path relative to ADR root, incl. filename
    markdown: str
    kt_id: str = ""      # generated Knowledge Transfer doc display id
    kt_rel_path: str = ""


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "adr"


def _next_number(folder_abs: Path) -> int:
    """Next ADR number **within this service folder** (per-service sequence)."""
    max_n = 0
    if folder_abs.exists():
        for md in folder_abs.glob("ADR-*.md"):
            m = re.match(r"ADR-(\d+)", md.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def make_uid(cloud_slug: str, service_slug: str, number: int) -> str:
    return f"{cloud_slug}-{service_slug}-{number:04d}"


def save_adr(
    *,
    cloud_slug: str,
    service_slug: str,
    content: ADRContent,
    service_name: str | None = None,
    category: str | None = None,
    subpath: str = "",
    adr_date: str | None = None,
) -> SavedADR:
    """Persist an ADR.

    Works for two cases:
      * **Catalog service** — `service_slug` present in the catalog; folder, display name,
        and category come from the catalog.
      * **Ad-hoc service** — a `service_slug` not in the catalog plus a `category` (and
        optional `subpath`); the folder is derived from those, so the agent can create an
        ADR for *any* service on request.
    """
    cloud = CLOUD_BY_SLUG.get(cloud_slug)
    if not cloud:
        raise ValueError(
            f"Unknown cloud '{cloud_slug}'. Expected one of: {', '.join(CLOUD_BY_SLUG)}."
        )

    service: Service | None = find_service(cloud_slug, service_slug)
    if service:
        folder_rel = f"{cloud_slug}/{service.folder}"
        svc_name = service.name
        svc_slug = service.slug
        cat = service.category
    else:
        svc_slug = _slugify(service_slug or service_name or "service")
        svc_name = service_name or service_slug or svc_slug
        cat = normalize_category(category)
        folder_rel = f"{cloud_slug}/{build_folder(cat, subpath, svc_slug)}"

    updates: dict = {}
    if content.author in ("", "Cloud Engineering", "ADR Agent"):
        updates["author"] = config_store.author()
    if not content.references:
        cfg_refs = config_store.references_as_lines(cloud_slug)
        if cfg_refs:
            updates["references"] = cfg_refs
    if not content.iac.strip():
        updates["iac"] = iac_hint_markdown(
            cloud_slug=cloud_slug,
            service_slug=svc_slug,
            service_name=svc_name,
            category=cat,
        )
    if updates:
        content = content.model_copy(update=updates)

    folder_abs = settings.adr_dir / folder_rel
    folder_abs.mkdir(parents=True, exist_ok=True)

    number = _next_number(folder_abs)
    adr_id = f"ADR-{number:04d}"
    uid = make_uid(cloud_slug, svc_slug, number)
    adr_date = adr_date or date_cls.today().isoformat()

    filename = f"{adr_id}-{_slugify(content.title)}.md"
    path = folder_abs / filename

    markdown = render_markdown(
        adr_id=adr_id,
        date=adr_date,
        cloud_name=cloud.name,
        service_name=svc_name,
        category=cat,
        content=content,
    )
    path.write_text(markdown, encoding="utf-8")
    rel_path = f"{folder_rel}/{filename}"

    kt_id = kt_rel = ""
    if config_store.effective().get("features", {}).get("kt_docs", True):
        kt_doc = kt.generate(
            adr_uid=uid,
            adr_id=adr_id,
            adr_title=content.title,
            adr_rel_path=rel_path,
            cloud_slug=cloud_slug,
            cloud_name=cloud.name,
            service_name=svc_name,
            category=cat,
            folder_rel=folder_rel,
            content=content,
            author=content.author,
            date=adr_date,
        )
        kt_id, kt_rel = kt_doc.id, kt_doc.rel_path

    saved = SavedADR(
        uid=uid,
        id=adr_id,
        number=number,
        cloud=cloud_slug,
        service=svc_slug,
        title=content.title,
        status=content.status,
        date=adr_date,
        folder=folder_rel,
        path=str(path),
        rel_path=rel_path,
        markdown=markdown,
        kt_id=kt_id,
        kt_rel_path=kt_rel,
    )
    _append_index(saved)
    return saved


def _index_path() -> Path:
    return settings.adr_dir / "index.json"


def _append_index(saved: SavedADR) -> None:
    entries = _read_index()
    entry = {k: v for k, v in asdict(saved).items() if k != "markdown"}
    entries = [e for e in entries if e.get("uid") != saved.uid]
    entries.append(entry)
    _write_index(entries)


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


def list_adrs() -> list[dict]:
    """Newest first. Sorted by date then uid so per-service numbering still reads sensibly."""
    entries = _read_index()
    return sorted(
        entries,
        key=lambda e: (e.get("date", ""), e.get("uid", "")),
        reverse=True,
    )


def _find_entry(key: str) -> dict | None:
    """Look up by uid; fall back to legacy display id for pre-uid records."""
    entries = _read_index()
    for e in entries:
        if e.get("uid") == key:
            return e
    for e in entries:
        if e.get("id") == key:
            return e
    return None


def read_adr(key: str) -> dict | None:
    entry = _find_entry(key)
    if not entry:
        return None
    p = Path(entry["path"])
    if not p.exists():
        return None
    out = dict(entry)
    out["markdown"] = p.read_text(encoding="utf-8")
    return out


_FM_FIELD = {
    "title": re.compile(r"^title:\s*(.+)$", re.MULTILINE),
    "status": re.compile(r"^status:\s*(.+)$", re.MULTILINE),
}

# ---------- lifecycle ----------
STATUSES = ("Proposed", "Accepted", "Rejected", "Deprecated", "Superseded")

_FM_STATUS = re.compile(r"^status:\s*.*$", re.MULTILINE)
_TABLE_STATUS = re.compile(r"(\|\s*\*\*Status\*\*\s*\|)[^|]*(\|)")
_LINEAGE_BLOCK = re.compile(
    r"\n?<!-- adr-lineage -->.*?<!-- /adr-lineage -->\n?", re.DOTALL
)
_H1 = re.compile(r"^(#\s+.+)$", re.MULTILINE)


def _apply_status_to_markdown(markdown: str, status: str) -> str:
    """Keep the front-matter and the summary table in sync with the stored status."""
    markdown = _FM_STATUS.sub(f"status: {status}", markdown, count=1)
    markdown = _TABLE_STATUS.sub(rf"\1 {status} \2", markdown, count=1)
    return markdown


def _apply_lineage_to_markdown(markdown: str, lines: list[str]) -> str:
    """Insert (or replace) the supersede callout directly under the title."""
    markdown = _LINEAGE_BLOCK.sub("\n", markdown)
    if not lines:
        return markdown
    block = (
        "\n<!-- adr-lineage -->\n"
        + "\n".join(f"> {ln}" for ln in lines)
        + "\n<!-- /adr-lineage -->\n"
    )
    m = _H1.search(markdown)
    if not m:
        return block + markdown
    idx = m.end()
    return markdown[:idx] + "\n" + block + markdown[idx:]


def _lineage_lines(entry: dict, entries: list[dict]) -> list[str]:
    by_uid = {e["uid"]: e for e in entries if e.get("uid")}
    lines: list[str] = []
    sup_by = entry.get("superseded_by")
    sup = entry.get("supersedes")
    if sup_by and sup_by in by_uid:
        o = by_uid[sup_by]
        lines.append(
            f"⚠️ **Superseded by {o['id']} — {o['title']}.** This decision is no longer current."
        )
    if sup and sup in by_uid:
        o = by_uid[sup]
        lines.append(f"↩️ **Supersedes {o['id']} — {o['title']}.**")
    return lines


def _rewrite_document(entry: dict, entries: list[dict]) -> None:
    """Re-render an ADR file from its index entry (status + lineage callout)."""
    p = Path(entry["path"])
    if not p.exists():
        return
    md = p.read_text(encoding="utf-8")
    md = _apply_status_to_markdown(md, entry.get("status", "Proposed"))
    md = _apply_lineage_to_markdown(md, _lineage_lines(entry, entries))
    p.write_text(md, encoding="utf-8")


def set_status(key: str, status: str) -> dict | None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status '{status}'. Expected one of: {', '.join(STATUSES)}.")
    entries = _read_index()
    target = next(
        (e for e in entries if e.get("uid") == key or e.get("id") == key), None
    )
    if not target:
        return None
    target["status"] = status
    _write_index(entries)
    _rewrite_document(target, entries)
    return read_adr(target["uid"])


def supersede(new_key: str, old_key: str) -> dict | None:
    """`new_key` supersedes `old_key`. Both must belong to the same cloud + service."""
    entries = _read_index()
    new = next((e for e in entries if e.get("uid") == new_key), None)
    old = next((e for e in entries if e.get("uid") == old_key), None)
    if not new or not old:
        return None
    if new["uid"] == old["uid"]:
        raise ValueError("An ADR cannot supersede itself.")
    if (new.get("cloud"), new.get("service")) != (old.get("cloud"), old.get("service")):
        raise ValueError(
            "An ADR can only supersede another ADR for the same service "
            f"({new.get('cloud')}/{new.get('service')} vs {old.get('cloud')}/{old.get('service')})."
        )
    if new.get("number", 0) <= old.get("number", 0):
        raise ValueError(
            f"{new['id']} cannot supersede the later {old['id']} — supersede an earlier revision."
        )

    # Detach any previous link on either side so the graph stays consistent.
    for e in entries:
        if e.get("superseded_by") == new["uid"]:
            e.pop("superseded_by", None)
    new.pop("supersedes", None)

    new["supersedes"] = old["uid"]
    old["superseded_by"] = new["uid"]
    old["status"] = "Superseded"
    if new.get("status") == "Proposed":
        new["status"] = "Accepted"

    _write_index(entries)
    _rewrite_document(old, entries)
    _rewrite_document(new, entries)
    return read_adr(new["uid"])


def update_adr(key: str, markdown: str) -> dict | None:
    """Overwrite an ADR's markdown (inline editing) and re-sync the index.

    Title/status are re-read from the YAML front-matter so the document list stays
    consistent with whatever the user edited.
    """
    entry = _find_entry(key)
    if not entry:
        return None
    p = Path(entry["path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown, encoding="utf-8")

    entries = _read_index()
    for e in entries:
        if e.get("uid") == entry.get("uid"):
            for field, pattern in _FM_FIELD.items():
                m = pattern.search(markdown)
                if m:
                    e[field] = m.group(1).strip()
            break
    _write_index(entries)
    return read_adr(key)
