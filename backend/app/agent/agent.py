"""The ADR agent: a tool-use loop over the LLM provider.

The agent is stateless across HTTP requests; the frontend passes back the running
`messages` history each turn. Each `run_turn` call advances the conversation, executing
any tool calls until the model produces a final text answer.
"""
from __future__ import annotations

from typing import Any

from app.agent.tools import TOOLS, dispatch
from app.llm.provider import get_provider
from app.services import config_store
from app.skills.loader import skills_as_prompt

BASE_SYSTEM = """You are the **ADR Agent** for the **Cloud Engineering** team. You turn a
short request (e.g. "I need an ADR for a GCS bucket") into a standards-compliant
Architecture Decision Record (an automation document) that the Automation team builds from
and that is handed to Cloud Operations via a Knowledge Transfer (KT) doc.

Operating rules:
- Work across AWS, GCP, and Azure. Prefer the catalog for known services and their folders.
  If a requested service is NOT in the catalog, still create the ADR: pick the best-fit
  standard category, choose a clean kebab-case service slug and display name, and pass them
  to save_adr (with an optional subpath). Never refuse because a service isn't pre-registered
  — you can author an ADR for ANY service on any of the three clouds.
- **NEVER MIX CLOUDS.** Each ADR targets exactly one cloud. When authoring for a cloud,
  call get_knowledge with that `cloud` so you only see global + that cloud's docs, and apply
  ONLY that cloud's conventions/skills. Do not put AWS services, resource names, or
  terminology in a GCP or Azure ADR (or any other cross-cloud mix). If unsure which cloud,
  ask before proceeding.
- Ground every ADR's security and standards sections in the knowledge base via get_knowledge
  (scoped to the cloud). Do not fabricate controls or links.
- Keep the conversation efficient: propose sensible defaults, ask only for decision-critical
  details you cannot reasonably assume (environment, data classification, region), and say
  which defaults you applied.
- Enforce the security guardrails from the security-review skill. If a request would cross a
  boundary, explain it and propose the compliant option before proceeding.
- The author of every ADR is **Cloud Engineering** (leave the author field default).
- When the content is complete and reviewed, call save_adr. Saving also auto-generates the
  KT document for Cloud Operations. Afterward, tell the user the ADR id, its folder path,
  that a KT doc was created, and that they can review, download (Markdown/Word), and publish
  to GitHub/Confluence from the UI (publishing is a deliberate, separate action).
- Be concise and prescriptive. You are writing for engineers.

Skills below are tagged by scope: [global] always apply; [aws]/[gcp]/[azure] apply ONLY when
that is the target cloud. Never apply one cloud's skill to another cloud's ADR.
"""


def _references_block() -> str:
    refs = config_store.references()
    if not refs:
        return ""
    lines = ["===== CANONICAL REFERENCE SOURCES ====="]
    lines.append(
        "These are the org's authoritative source-of-truth links (kept updated by the "
        "Security / Architecture / Engineering teams). In an ADR's References section, "
        "cite the ones whose scope is 'global' or matches the ADR's cloud — never another "
        "cloud's link."
    )
    for r in refs:
        scope = (r.get("scope") or "global").lower()
        cat = r.get("category", "other")
        title = r.get("title") or r.get("url")
        lines.append(f"- [{scope}/{cat}] {title}: {r.get('url')}")
    return "\n".join(lines)


def system_prompt() -> str:
    parts = [BASE_SYSTEM, skills_as_prompt()]
    refs = _references_block()
    if refs:
        parts.append(refs)
    return "\n\n".join(parts)


def run_turn(messages: list[dict[str, Any]], max_steps: int = 8) -> dict[str, Any]:
    """Advance the conversation by one user turn.

    `messages` is the full Anthropic-style history (user/assistant turns). Returns the
    updated message list, the final assistant text, and any tool activity for the UI.
    """
    provider = get_provider()
    system = system_prompt()
    tool_events: list[dict[str, Any]] = []
    saved_adrs: list[dict[str, Any]] = []

    for _ in range(max_steps):
        resp = provider.complete(
            system=system, messages=messages, tools=TOOLS, max_tokens=4096
        )
        # Record the assistant turn (content blocks) verbatim.
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.get("type") == "tool_use"]
        if not tool_uses:
            final_text = "".join(
                b.get("text", "") for b in resp.content if b.get("type") == "text"
            )
            return {
                "messages": messages,
                "reply": final_text.strip(),
                "tool_events": tool_events,
                "saved_adrs": saved_adrs,
                "done": True,
            }

        # Execute each tool call and feed results back.
        tool_results = []
        for tu in tool_uses:
            name, args, tid = tu["name"], tu.get("input", {}), tu["id"]
            try:
                result = dispatch(name, args)
            except Exception as exc:  # surface tool errors to the model
                result = {"error": str(exc)}
            tool_events.append({"tool": name, "input": args, "result": result})
            if name == "save_adr" and result.get("saved"):
                saved_adrs.append(result)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tid,
                "content": _json(result),
            })
        messages.append({"role": "user", "content": tool_results})

    return {
        "messages": messages,
        "reply": "I wasn't able to finish within the step limit — please refine the request.",
        "tool_events": tool_events,
        "saved_adrs": saved_adrs,
        "done": False,
    }


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
