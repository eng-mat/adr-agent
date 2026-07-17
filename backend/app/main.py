"""FastAPI entrypoint for the ADR Agent."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from app.agent.agent import run_turn
from app.config import settings
from app.services import config_store, knowledge, kt, storage
from app.services.auth import current_user, issue_token, require_admin, resolve_role
from app.services.catalog import catalog_as_dict
from app.services.docx_export import markdown_to_docx_bytes
from app.services.publishers import publish_confluence, publish_github
from app.skills.loader import add_skill, delete_skill, load_skills

app = FastAPI(title="ADR Agent", version="0.3.0")
knowledge.ensure_dirs()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ---------- schemas ----------
class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = []


class PublishRequest(BaseModel):
    adr_id: str
    targets: list[str] = ["github", "confluence"]


class LoginRequest(BaseModel):
    email: str
    name: str = ""
    role: str | None = None


class KnowledgeUpload(BaseModel):
    scope: str
    category: str
    title: str
    content: str


class SkillUpload(BaseModel):
    scope: str
    name: str
    description: str = ""
    when_to_use: str = ""
    body: str


# ---------- meta ----------
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "model": settings.active_model,
        "llm_ready": settings.llm_ready,
        "llm_key_env": settings.llm_key_env,
        "author": config_store.author(),
        "github": "live" if config_store.github_configured() else "stub",
        "confluence": "live" if config_store.confluence_configured() else "stub",
        "features": config_store.effective().get("features", {}),
    }


@app.get("/api/catalog")
def get_catalog() -> dict:
    return {"clouds": catalog_as_dict()}


@app.get("/api/skills")
def get_skills(scope: str | None = None) -> dict:
    return {
        "skills": [
            {"name": s.name, "scope": s.scope, "description": s.description, "when_to_use": s.when_to_use}
            for s in load_skills(scope)
        ]
    }


@app.get("/api/references")
def get_references() -> dict:
    return {"references": config_store.references()}


@app.get("/api/knowledge")
def get_knowledge_list(scope: str | None = None) -> dict:
    return {"docs": knowledge.list_docs(scope)}


@app.get("/api/knowledge/{key:path}")
def get_knowledge_doc(key: str) -> dict:
    content = knowledge.get_doc(key)
    if content is None:
        raise HTTPException(404, f"Doc not found: {key}")
    return {"key": key, "content": content}


# ---------- auth (stub / free login) ----------
@app.post("/api/auth/login")
def login(req: LoginRequest) -> dict:
    role = resolve_role(req.email, req.role)
    user = {"email": req.email, "name": req.name or req.email, "role": role}
    return {"token": issue_token(req.email, user["name"], role), "user": user}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": user}


# ---------- ADRs ----------
@app.get("/api/adrs")
def list_adrs() -> dict:
    return {"adrs": storage.list_adrs()}


@app.get("/api/adrs/{adr_id}")
def get_adr(adr_id: str) -> dict:
    adr = storage.read_adr(adr_id)
    if not adr:
        raise HTTPException(404, f"ADR not found: {adr_id}")
    return adr


@app.get("/api/adrs/{adr_id}/export.docx")
def export_adr_docx(adr_id: str):
    adr = storage.read_adr(adr_id)
    if not adr:
        raise HTTPException(404, f"ADR not found: {adr_id}")
    data = markdown_to_docx_bytes(adr["markdown"], adr["title"])
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{adr_id}.docx"'},
    )


# ---------- KT documents ----------
@app.get("/api/kt")
def list_kt() -> dict:
    return {"kt": kt.list_kt()}


@app.get("/api/kt/{kt_id}")
def get_kt(kt_id: str) -> dict:
    doc = kt.read_kt(kt_id)
    if not doc:
        raise HTTPException(404, f"KT not found: {kt_id}")
    return doc


@app.get("/api/adrs/{adr_id}/kt")
def get_adr_kt(adr_id: str) -> dict:
    doc = kt.read_kt_for_adr(adr_id)
    if not doc:
        raise HTTPException(404, f"No KT for {adr_id}")
    return doc


@app.get("/api/kt/{kt_id}/export.docx")
def export_kt_docx(kt_id: str):
    doc = kt.read_kt(kt_id)
    if not doc:
        raise HTTPException(404, f"KT not found: {kt_id}")
    data = markdown_to_docx_bytes(doc["markdown"], doc["title"])
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{kt_id}.docx"'},
    )


# ---------- agent ----------
@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    messages = list(req.history)
    messages.append({"role": "user", "content": req.message})
    try:
        result = run_turn(messages)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"Agent error: {exc}")
    return result


# ---------- publishing (explicit, human-triggered) ----------
@app.post("/api/publish")
def publish(req: PublishRequest) -> dict:
    results = []
    if "github" in req.targets:
        results.append(publish_github(req.adr_id).__dict__)
    if "confluence" in req.targets:
        results.append(publish_confluence(req.adr_id).__dict__)
    if not results:
        raise HTTPException(400, "No valid targets specified.")
    return {"results": results}


# ================= ADMIN (require admin role) =================
@app.get("/api/admin/config")
def admin_get_config(_: dict = Depends(require_admin)) -> dict:
    return config_store.public()


@app.put("/api/admin/config")
def admin_update_config(patch: dict, _: dict = Depends(require_admin)) -> dict:
    return config_store.update(patch)


@app.get("/api/admin/knowledge")
def admin_list_knowledge(_: dict = Depends(require_admin)) -> dict:
    return {
        "docs": knowledge.list_docs(),
        "scopes": list(knowledge.SCOPES),
        "categories": list(knowledge.CATEGORIES),
    }


@app.post("/api/admin/knowledge")
def admin_add_knowledge(req: KnowledgeUpload, _: dict = Depends(require_admin)) -> dict:
    try:
        return knowledge.add_doc(req.scope, req.category, req.title, req.content)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/admin/knowledge")
def admin_delete_knowledge(key: str, _: dict = Depends(require_admin)) -> dict:
    if not knowledge.delete_doc(key):
        raise HTTPException(404, f"Doc not found: {key}")
    return {"deleted": key}


@app.get("/api/admin/skills")
def admin_list_skills(_: dict = Depends(require_admin)) -> dict:
    return {
        "skills": [
            {"name": s.name, "scope": s.scope, "description": s.description,
             "when_to_use": s.when_to_use, "body": s.body}
            for s in load_skills()
        ],
        "scopes": ["global", "aws", "gcp", "azure"],
    }


@app.post("/api/admin/skills")
def admin_add_skill(req: SkillUpload, _: dict = Depends(require_admin)) -> dict:
    try:
        s = add_skill(req.scope, req.name, req.description, req.when_to_use, req.body)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"name": s.name, "scope": s.scope}


@app.delete("/api/admin/skills")
def admin_delete_skill(scope: str, name: str, _: dict = Depends(require_admin)) -> dict:
    if not delete_skill(scope, name):
        raise HTTPException(404, f"Skill not found: {scope}/{name}")
    return {"deleted": f"{scope}/{name}"}
