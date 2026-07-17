"""Render an ADR data structure into standards-compliant Markdown."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "adr_template.md"


class ADRContent(BaseModel):
    """The fields the agent fills in to author an ADR.

    Free-text sections accept Markdown. Bullet sections accept a list of strings.
    """
    title: str
    status: str = "Proposed"
    author: str = "Cloud Engineering"
    context: str
    decision: str
    architecture: str
    security: str
    standards: str
    consequences_positive: list[str] = Field(default_factory=list)
    consequences_negative: list[str] = Field(default_factory=list)
    alternatives: str = "N/A"
    iac: str = ""  # Infrastructure-as-Code hint; auto-filled if left blank.
    automation_notes: str = ""
    references: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


def _bullets(items: list[str]) -> str:
    if not items:
        return "- _None recorded._"
    return "\n".join(f"- {item}" for item in items)


def render_markdown(
    *,
    adr_id: str,
    date: str,
    cloud_name: str,
    service_name: str,
    category: str,
    content: ADRContent,
) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    references = content.references or [
        "Cloud Security Standard — <CONFLUENCE_LINK_PLACEHOLDER>",
        "Cloud Architecture Standard — <CONFLUENCE_LINK_PLACEHOLDER>",
    ]
    return template.format(
        id=adr_id,
        title=content.title,
        status=content.status,
        date=date,
        author=content.author,
        cloud_name=cloud_name,
        service_name=service_name,
        category=category,
        tags=", ".join(content.tags),
        context=content.context.strip(),
        decision=content.decision.strip(),
        architecture=content.architecture.strip(),
        security=content.security.strip(),
        standards=content.standards.strip(),
        consequences_positive=_bullets(content.consequences_positive),
        consequences_negative=_bullets(content.consequences_negative),
        alternatives=content.alternatives.strip() or "N/A",
        iac=content.iac.strip() or "_No IaC hint generated._",
        automation_notes=content.automation_notes.strip()
        or "_To be completed by the automation team._",
        references="\n".join(f"- {r}" for r in references),
    )
