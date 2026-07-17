"""Load agent skills, scoped per Cloud Service Provider.

Layout:  skills/<scope>/<skill-name>/SKILL.md
  scope ∈ global | aws | gcp | azure

`global` skills always apply. Cloud skills apply only to that cloud's ADRs — this keeps
AWS guidance out of a GCP ADR and vice-versa. Admins add skills via the admin console
(which just writes a new SKILL.md under the chosen scope).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent
SCOPES = ("global", "aws", "gcp", "azure")


@dataclass
class Skill:
    name: str
    scope: str
    description: str
    when_to_use: str
    body: str
    path: str


def _safe_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "skill"


def _parse(md_path: Path, scope: str) -> Skill:
    raw = md_path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    return Skill(
        name=meta.get("name", md_path.parent.name),
        scope=scope,
        description=meta.get("description", ""),
        when_to_use=meta.get("when_to_use", ""),
        body=body.strip(),
        path=str(md_path),
    )


def load_skills(scope: str | None = None) -> list[Skill]:
    """All skills, or `global` + one cloud's skills when scope is a cloud slug."""
    scopes = SCOPES if scope is None else tuple(dict.fromkeys(["global", scope]))
    skills: list[Skill] = []
    for sc in scopes:
        base = SKILLS_DIR / sc
        if not base.exists():
            continue
        for skill_md in sorted(base.glob("*/SKILL.md")):
            skills.append(_parse(skill_md, sc))
    return skills


def skills_as_prompt(scope: str | None = None) -> str:
    blocks = []
    for s in load_skills(scope):
        blocks.append(f"===== SKILL [{s.scope}]: {s.name} =====\n{s.body}")
    return "\n\n".join(blocks)


def add_skill(scope: str, name: str, description: str, when_to_use: str, body: str) -> Skill:
    if scope not in SCOPES:
        raise ValueError(f"Invalid scope '{scope}'. Expected {SCOPES}.")
    slug = _safe_slug(name)
    folder = SKILLS_DIR / scope / slug
    folder.mkdir(parents=True, exist_ok=True)
    md = folder / "SKILL.md"
    front = {
        "name": name,
        "description": description,
        "when_to_use": when_to_use,
    }
    content = "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\n" + body.strip() + "\n"
    md.write_text(content, encoding="utf-8")
    return _parse(md, scope)


def delete_skill(scope: str, name: str) -> bool:
    slug = _safe_slug(name)
    folder = SKILLS_DIR / scope / slug
    md = folder / "SKILL.md"
    if md.exists():
        md.unlink()
        try:
            folder.rmdir()
        except OSError:
            pass
        return True
    return False
