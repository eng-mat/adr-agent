"""Agent tools: JSON schemas + a dispatcher that executes them.

Tools are intentionally small and composable. `save_adr` is the only one with a side
effect on the ADR tree; publishing is a separate, explicit UI action (not an agent tool)
so the human stays in the loop for outward-facing pushes.
"""
from __future__ import annotations

from typing import Any

from app.services import catalog, knowledge
from app.services.adr_builder import ADRContent
from app.services.storage import save_adr

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_catalog",
        "description": (
            "Search the CSP catalog for a cloud service by name/keyword (e.g. 'gcs "
            "bucket', 'rds postgres', 'bigquery'). Returns matching services with their "
            "canonical cloud_slug, service_slug, and folder path. Use this to resolve "
            "exactly what is being decided and where the ADR is filed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords, e.g. 'gcs bucket'"},
                "cloud": {
                    "type": "string",
                    "enum": ["aws", "gcp", "azure"],
                    "description": "Optional cloud filter.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_knowledge",
        "description": (
            "Read the organization's standards (security, architecture, engineering), "
            "mirrored from Confluence and scoped per cloud. ALWAYS pass `cloud` when "
            "working on an ADR so you get global + that cloud's docs only — never another "
            "cloud's. Call with just `cloud` (and no key) to list what's available, or add "
            "a `key` to read one doc. Ground the ADR's security/standards sections in these; "
            "do not invent controls, and do not use one cloud's specifics in another's ADR."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cloud": {
                    "type": "string",
                    "enum": ["aws", "gcp", "azure"],
                    "description": "Scope docs to global + this cloud. Pass it whenever a cloud is known.",
                },
                "key": {"type": "string", "description": "Doc key to read, or omit to list."},
                "query": {"type": "string", "description": "Optional search term."},
            },
        },
    },
    {
        "name": "save_adr",
        "description": (
            "Persist a fully-authored ADR into the correct CSP folder and assign it an id. "
            "Call this only after the content is complete and security-reviewed.\n"
            "Two ways to target a folder:\n"
            "  1. CATALOG service — pass cloud_slug + service_slug exactly as returned by "
            "search_catalog.\n"
            "  2. ANY service not in the catalog — pass cloud_slug + a service_slug you "
            "choose (kebab-case) + service_name (display) + category (one of the standard "
            "categories) + optional subpath. Never refuse a request because the service "
            "isn't in the catalog; file it this way instead.\n"
            "An Infrastructure-as-Code hint is generated automatically; only pass `iac` to "
            "override it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cloud_slug": {"type": "string", "enum": ["aws", "gcp", "azure"]},
                "service_slug": {"type": "string", "description": "Catalog slug, or a new kebab-case slug for an ad-hoc service."},
                "service_name": {"type": "string", "description": "Display name (required for ad-hoc services not in the catalog)."},
                "category": {
                    "type": "string",
                    "description": (
                        "Category slug for ad-hoc services. One of: compute, storage, "
                        "database, networking, security-identity, containers, serverless, "
                        "analytics, messaging, monitoring, ai-ml, developer-tools, "
                        "management, other."
                    ),
                },
                "subpath": {"type": "string", "description": "Optional nested path under the category, e.g. 'sql' or 'warehouse'."},
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["Proposed", "Accepted", "Deprecated"]},
                "context": {"type": "string"},
                "decision": {"type": "string"},
                "architecture": {"type": "string", "description": "Markdown; concrete automatable settings."},
                "security": {"type": "string", "description": "Markdown; cite specific standard controls."},
                "standards": {"type": "string", "description": "Markdown; naming + mandatory tags."},
                "consequences_positive": {"type": "array", "items": {"type": "string"}},
                "consequences_negative": {"type": "array", "items": {"type": "string"}},
                "alternatives": {"type": "string"},
                "iac": {"type": "string", "description": "Optional IaC hint override (auto-generated if omitted)."},
                "automation_notes": {"type": "string"},
                "references": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "cloud_slug", "service_slug", "title", "context", "decision",
                "architecture", "security", "standards",
            ],
        },
    },
]


def dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool call and return a JSON-serializable result."""
    if name == "search_catalog":
        results = catalog.search(args["query"], args.get("cloud"))
        return {
            "matches": [
                {
                    "cloud_slug": cslug,
                    "cloud_name": catalog.CLOUD_BY_SLUG[cslug].name,
                    "service_slug": svc.slug,
                    "service_name": svc.name,
                    "category": svc.category,
                    "folder": f"{cslug}/{svc.folder}",
                }
                for cslug, svc in results
            ]
        }

    if name == "get_knowledge":
        scope = args.get("cloud")
        if args.get("key"):
            doc = knowledge.get_doc(args["key"])
            return {"key": args["key"], "content": doc or "NOT FOUND"}
        if args.get("query"):
            return {"docs": knowledge.search_docs(args["query"], scope)}
        return {"docs": knowledge.list_docs(scope)}

    if name == "save_adr":
        content = ADRContent(
            title=args["title"],
            status=args.get("status", "Proposed"),
            context=args["context"],
            decision=args["decision"],
            architecture=args["architecture"],
            security=args["security"],
            standards=args["standards"],
            consequences_positive=args.get("consequences_positive", []),
            consequences_negative=args.get("consequences_negative", []),
            alternatives=args.get("alternatives", "N/A"),
            iac=args.get("iac", ""),
            automation_notes=args.get("automation_notes", ""),
            references=args.get("references", []),
            tags=args.get("tags", []),
        )
        saved = save_adr(
            cloud_slug=args["cloud_slug"],
            service_slug=args["service_slug"],
            service_name=args.get("service_name"),
            category=args.get("category"),
            subpath=args.get("subpath", ""),
            content=content,
        )
        return {
            "uid": saved.uid,
            "id": saved.id,
            "title": saved.title,
            "cloud": saved.cloud,
            "service": saved.service,
            "folder": saved.folder,
            "rel_path": saved.rel_path,
            "status": saved.status,
            "kt_id": saved.kt_id,
            "kt_rel_path": saved.kt_rel_path,
            "saved": True,
        }

    return {"error": f"Unknown tool: {name}"}
