"""GitHub and Confluence publishers.

Both run in **local stub mode** until credentials are supplied in .env. In stub mode the
ADR is copied into `backend/.local-mirror/<target>/...` and a descriptive result is
returned, so the whole flow is exercisable end-to-end without external services.

When credentials are present, the real code paths (marked TODO) take over. The public
functions never change signature, so the UI/agent are agnostic to the mode.
"""
from __future__ import annotations

import base64
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import settings
from app.services import config_store
from app.services.storage import read_adr


@dataclass
class PublishResult:
    target: str          # "github" | "confluence"
    mode: str            # "live" | "stub"
    ok: bool
    message: str
    url: str | None = None


def publish_github(adr_key: str) -> PublishResult:
    """`adr_key` is the ADR's uid (e.g. gcp-gcs-0001); display ids repeat per service."""
    adr = read_adr(adr_key)
    if not adr:
        return PublishResult("github", "stub", False, f"ADR {adr_key} not found")

    gh = config_store.effective()["github"]
    branch = gh.get("branch") or "main"
    if not config_store.github_configured():
        dest = settings.local_mirror_dir / "github" / adr["rel_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(adr["path"], dest)
        return PublishResult(
            target="github",
            mode="stub",
            ok=True,
            message=(
                f"[stub] Would commit {adr['rel_path']} to "
                f"{gh.get('repo') or '<GITHUB_REPO>'}@{branch}. "
                f"Configure GitHub in the Admin Console to push for real. "
                f"Mirrored locally to {dest}."
            ),
            url=None,
        )

    # --- live path (GitHub Contents API) ---
    owner_repo = gh["repo"]
    path = adr["rel_path"]
    api = f"https://api.github.com/repos/{owner_repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {gh['token']}",
        "Accept": "application/vnd.github+json",
    }
    content_b64 = base64.b64encode(
        Path(adr["path"]).read_bytes()
    ).decode("ascii")
    # Check for existing file to obtain its sha (required for updates).
    sha = None
    with httpx.Client(timeout=30) as client:
        existing = client.get(api, headers=headers, params={"ref": branch})
        if existing.status_code == 200:
            sha = existing.json().get("sha")
        body = {
            "message": f"Add {adr['id']} ({adr['cloud']}/{adr['service']}): {adr['title']}",
            "content": content_b64,
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        resp = client.put(api, headers=headers, json=body)
    if resp.status_code in (200, 201):
        html_url = resp.json().get("content", {}).get("html_url")
        return PublishResult("github", "live", True, f"Committed {path}", html_url)
    return PublishResult(
        "github", "live", False, f"GitHub error {resp.status_code}: {resp.text[:200]}"
    )


def publish_confluence(adr_key: str) -> PublishResult:
    """`adr_key` is the ADR's uid (e.g. gcp-gcs-0001); display ids repeat per service."""
    adr = read_adr(adr_key)
    if not adr:
        return PublishResult("confluence", "stub", False, f"ADR {adr_key} not found")

    conf = config_store.effective()["confluence"]
    if not config_store.confluence_configured():
        dest = settings.local_mirror_dir / "confluence" / f"{adr.get('uid', adr_key)}.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        html = _markdown_to_storage_html(adr["markdown"])
        dest.write_text(html, encoding="utf-8")
        return PublishResult(
            target="confluence",
            mode="stub",
            ok=True,
            message=(
                f"[stub] Would create Confluence page '{adr['title']}' in space "
                f"{conf.get('space_key') or '<SPACE_KEY>'}. "
                f"Configure Confluence in the Admin Console to publish for real. "
                f"Rendered locally to {dest}."
            ),
            url=None,
        )

    # --- live path (Confluence Cloud REST API v2) ---
    base = conf["base_url"].rstrip("/")
    auth = (conf["user"], conf["api_token"])
    html = _markdown_to_storage_html(adr["markdown"])
    payload = {
        "spaceKey": conf["space_key"],
        # Confluence page titles must be unique in a space, and display ids now repeat
        # across services — qualify with cloud/service.
        "title": f"{adr['id']} · {adr['cloud']}/{adr['service']} — {adr['title']}",
        "type": "page",
        "body": {"storage": {"value": html, "representation": "storage"}},
    }
    with httpx.Client(timeout=30, auth=auth) as client:
        resp = client.post(f"{base}/rest/api/content", json=payload)
    if resp.status_code in (200, 201):
        data = resp.json()
        page_url = base + data.get("_links", {}).get("webui", "")
        return PublishResult("confluence", "live", True, "Page created", page_url)
    return PublishResult(
        "confluence", "live", False,
        f"Confluence error {resp.status_code}: {resp.text[:200]}",
    )


def _markdown_to_storage_html(markdown: str) -> str:
    """Minimal Markdown -> HTML for the stub/preview.

    Deliberately dependency-free. The live path can swap in a full renderer or use
    Confluence's markdown macro; this keeps the stub self-contained.
    """
    lines = markdown.splitlines()
    html: list[str] = []
    in_code = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            html.append("<pre>" if in_code else "</pre>")
            continue
        if in_code:
            html.append(_esc(line))
        elif line.startswith("# "):
            html.append(f"<h1>{_esc(line[2:])}</h1>")
        elif line.startswith("## "):
            html.append(f"<h2>{_esc(line[3:])}</h2>")
        elif line.startswith("### "):
            html.append(f"<h3>{_esc(line[4:])}</h3>")
        elif line.startswith("- "):
            html.append(f"<ul><li>{_esc(line[2:])}</li></ul>")
        elif line.strip() == "":
            html.append("")
        else:
            html.append(f"<p>{_esc(line)}</p>")
    return "\n".join(html)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
