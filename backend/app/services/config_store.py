"""Runtime, admin-editable configuration.

`.env` holds developer/bootstrap defaults (LLM keys, initial integration values). The
**admin console** writes operational config here (GitHub/Confluence credentials, author,
admin emails, feature flags) to a local JSON file, which overlays the .env defaults.

Secrets are masked when read back over the API and preserved when an update omits them.
For local/dev use this plain-JSON store is fine; on GKE these move to Secrets later.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import BACKEND_DIR, settings

DATA_DIR = BACKEND_DIR / "data"
CONFIG_PATH = DATA_DIR / "app_config.json"
MASK = "••••••••"
_SECRET_PATHS = (("github", "token"), ("confluence", "api_token"))


def _defaults() -> dict[str, Any]:
    return {
        "author": "Cloud Engineering",
        "admin_emails": [],
        # Canonical source-of-truth links (Confluence & others) that the
        # Security / Architecture / Engineering teams keep updated. Each:
        #   {"title": str, "category": security|architecture|engineering|other,
        #    "scope": global|aws|gcp|azure, "url": str}
        "references": [],
        "github": {
            "token": settings.github_token,
            "repo": settings.github_repo,
            "branch": settings.github_branch or "main",
        },
        "confluence": {
            "base_url": settings.confluence_base_url,
            "user": settings.confluence_user,
            "api_token": settings.confluence_api_token,
            "space_key": settings.confluence_space_key,
        },
        "features": {"docx_export": True, "kt_docs": True, "auto_publish": False},
    }


def _load() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def effective() -> dict[str, Any]:
    """Full config with real secret values (server-side use only)."""
    return _deep_merge(_defaults(), _load())


def github_configured() -> bool:
    g = effective()["github"]
    return bool(g.get("token") and g.get("repo"))


def confluence_configured() -> bool:
    c = effective()["confluence"]
    return bool(c.get("base_url") and c.get("user") and c.get("api_token") and c.get("space_key"))


def author() -> str:
    return effective().get("author") or "Cloud Engineering"


def admin_emails() -> list[str]:
    return [e.strip().lower() for e in effective().get("admin_emails", []) if e.strip()]


def references() -> list[dict]:
    return [r for r in effective().get("references", []) if r.get("url")]


def references_for(cloud: str | None) -> list[dict]:
    """Reference links that apply to a given cloud: global + that cloud's."""
    out = []
    for r in references():
        scope = (r.get("scope") or "global").lower()
        if scope in ("global", cloud):
            out.append(r)
    return out


def references_as_lines(cloud: str | None) -> list[str]:
    """Formatted 'Title (category) — url' lines for an ADR/KT References section."""
    lines = []
    for r in references_for(cloud):
        cat = r.get("category", "other")
        title = r.get("title") or r["url"]
        lines.append(f"{title} ({cat}) — {r['url']}")
    return lines


def public() -> dict[str, Any]:
    """Config for the admin UI: secrets masked, plus computed status flags."""
    cfg = effective()
    masked = json.loads(json.dumps(cfg))  # deep copy
    for section, key in _SECRET_PATHS:
        if masked.get(section, {}).get(key):
            masked[section][key] = MASK
    masked["github"]["configured"] = github_configured()
    masked["confluence"]["configured"] = confluence_configured()
    return masked


def update(patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a patch into the stored config. Masked secret values are ignored so an
    admin can save the form without re-entering tokens."""
    stored = _load()
    # Drop masked secrets from the patch so they don't overwrite real stored values.
    clean = json.loads(json.dumps(patch))
    for section, key in _SECRET_PATHS:
        if clean.get(section, {}).get(key) == MASK:
            clean[section].pop(key, None)
    merged = _deep_merge(stored, clean)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return public()
