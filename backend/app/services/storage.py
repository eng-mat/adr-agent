"""Persist ADRs into the CSP folder taxonomy and assign sequential IDs.

Layout:  <ADR_OUTPUT_DIR>/<cloud>/<category>/<subpath?>/<service>/ADR-XXXX-<slug>.md
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
    id: str
    cloud: str
    service: str
    title: str
    status: str
    date: str
    folder: str          # POSIX path relative to ADR root
    path: str            # absolute path on disk
    rel_path: str        # POSIX path relative to ADR root, incl. filename
    markdown: str
    kt_id: str = ""      # generated Knowledge Transfer doc id
    kt_rel_path: str = ""


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "adr"


def _next_id() -> str:
    """Global monotonically increasing ADR id across all clouds."""
    root = settings.adr_dir
    max_n = 0
    if root.exists():
        for md in root.rglob("ADR-*.md"):
            m = re.match(r"ADR-(\d+)", md.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return f"ADR-{max_n + 1:04d}"


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
      * **Catalog service** — pass a `service_slug` present in the catalog; folder,
        display name, and category come from the catalog.
      * **Ad-hoc service** — pass a `service_slug` (or name) not in the catalog plus a
        `category` (and optional `subpath`); the folder is derived from those so the
        agent can create an ADR for *any* service on request.
    """
    cloud = CLOUD_BY_SLUG.get(cloud_slug)
    if not cloud:
        raise ValueError(
            f"Unknown cloud '{cloud_slug}'. Expected one of: "
            f"{', '.join(CLOUD_BY_SLUG)}."
        )

    service: Service | None = find_service(cloud_slug, service_slug)
    if service:
        folder_rel = f"{cloud_slug}/{service.folder}"
        svc_name = service.name
        svc_slug = service.slug
        cat = service.category
    else:
        # Ad-hoc: derive folder from provided category/subpath/slug.
        svc_slug = _slugify(service_slug or service_name or "service")
        svc_name = service_name or service_slug or svc_slug
        cat = normalize_category(category)
        folder_rel = f"{cloud_slug}/{build_folder(cat, subpath, svc_slug)}"

    # Apply the configured author (Cloud Engineering) unless the caller set one explicitly.
    updates: dict = {}
    if content.author in ("", "Cloud Engineering", "ADR Agent"):
        updates["author"] = config_store.author()
    # Auto-fill the IaC hint if the agent didn't supply one.
    if not content.iac.strip():
        updates["iac"] = iac_hint_markdown(
            cloud_slug=cloud_slug,
            service_slug=svc_slug,
            service_name=svc_name,
            category=cat,
        )
    if updates:
        content = content.model_copy(update=updates)

    adr_id = _next_id()
    adr_date = adr_date or date_cls.today().isoformat()
    folder_abs = settings.adr_dir / folder_rel
    folder_abs.mkdir(parents=True, exist_ok=True)

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

    # Auto-generate the Knowledge Transfer doc for Cloud Operations.
    kt_id = kt_rel = ""
    if config_store.effective().get("features", {}).get("kt_docs", True):
        kt_doc = kt.generate(
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
        id=adr_id,
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


def _append_index(saved: SavedADR) -> None:
    """Maintain a flat JSON index of all ADRs for the UI list."""
    index_path = settings.adr_dir / "index.json"
    entries: list[dict] = []
    if index_path.exists():
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
    entry = {k: v for k, v in asdict(saved).items() if k != "markdown"}
    entries = [e for e in entries if e.get("id") != saved.id]
    entries.append(entry)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def list_adrs() -> list[dict]:
    index_path = settings.adr_dir / "index.json"
    if not index_path.exists():
        return []
    try:
        entries = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return sorted(entries, key=lambda e: e.get("id", ""), reverse=True)


def read_adr(adr_id: str) -> dict | None:
    for entry in list_adrs():
        if entry.get("id") == adr_id:
            p = Path(entry["path"])
            if p.exists():
                entry = dict(entry)
                entry["markdown"] = p.read_text(encoding="utf-8")
                return entry
    return None
