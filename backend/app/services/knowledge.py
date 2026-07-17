"""Knowledge base, scoped per Cloud Service Provider.

Layout:  knowledge/<scope>/<category>/<file>.md
  scope    ∈ global | aws | gcp | azure   (global applies to every cloud)
  category ∈ security | architecture | engineering | general

The scoping is what stops the agent from mixing clouds: when authoring an ADR for AWS it
is given only `global` + `aws` docs, never `gcp`/`azure`. Admins upload/remove docs here
via the admin console. Mirrors Confluence today; swap `get_doc` for a live fetch later.
"""
from __future__ import annotations

import re
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
SCOPES = ("global", "aws", "gcp", "azure")
CATEGORIES = ("security", "architecture", "engineering", "general")


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (stem or "doc") + ".md"


def ensure_dirs() -> None:
    for scope in SCOPES:
        for cat in CATEGORIES:
            (KNOWLEDGE_DIR / scope / cat).mkdir(parents=True, exist_ok=True)


def _title_of(md_path: Path) -> str:
    try:
        first = md_path.read_text(encoding="utf-8").splitlines()[0]
        return first.lstrip("# ").strip() or md_path.stem
    except (OSError, IndexError):
        return md_path.stem


def list_docs(scope: str | None = None) -> list[dict]:
    """All docs, or docs for a scope. `scope='aws'` returns global + aws (what the agent
    sees when working on AWS)."""
    scopes = SCOPES if scope is None else tuple(dict.fromkeys(["global", scope]))
    docs: list[dict] = []
    for sc in scopes:
        base = KNOWLEDGE_DIR / sc
        if not base.exists():
            continue
        for md in sorted(base.rglob("*.md")):
            rel = md.relative_to(KNOWLEDGE_DIR).as_posix()
            parts = rel.split("/")
            docs.append({
                "key": rel,
                "scope": parts[0],
                "category": parts[1] if len(parts) > 2 else "general",
                "title": _title_of(md),
            })
    return docs


def get_doc(key: str) -> str | None:
    target = (KNOWLEDGE_DIR / key).resolve()
    if KNOWLEDGE_DIR.resolve() not in target.parents:
        return None  # path traversal guard
    if target.exists() and target.suffix == ".md":
        return target.read_text(encoding="utf-8")
    return None


def search_docs(query: str, scope: str | None = None) -> list[dict]:
    q = query.lower()
    hits = []
    for doc in list_docs(scope):
        text = (get_doc(doc["key"]) or "").lower()
        if q in text or q in doc["title"].lower() or q in doc["category"]:
            hits.append(doc)
    return hits or list_docs(scope)


def add_doc(scope: str, category: str, title: str, content: str) -> dict:
    if scope not in SCOPES:
        raise ValueError(f"Invalid scope '{scope}'. Expected {SCOPES}.")
    if category not in CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Expected {CATEGORIES}.")
    folder = KNOWLEDGE_DIR / scope / category
    folder.mkdir(parents=True, exist_ok=True)
    filename = _safe_name(title)
    path = folder / filename
    body = content if content.lstrip().startswith("#") else f"# {title}\n\n{content}"
    path.write_text(body, encoding="utf-8")
    key = path.relative_to(KNOWLEDGE_DIR).as_posix()
    return {"key": key, "scope": scope, "category": category, "title": title}


def delete_doc(key: str) -> bool:
    target = (KNOWLEDGE_DIR / key).resolve()
    if KNOWLEDGE_DIR.resolve() not in target.parents:
        return False
    if target.exists() and target.suffix == ".md":
        target.unlink()
        return True
    return False
