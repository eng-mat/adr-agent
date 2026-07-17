"""Authentication & role resolution.

**Stub / free-login for now.** There are no passwords: a user provides an email + name and
a requested role, and we issue an opaque session token. This is deliberately a placeholder
for the eventual **SSO + group mapping** (on GKE, the identity provider's groups map to the
`admin` / `user` roles here — Admin group => admin, everyone else => user).

Role rules today:
  * if the email is in the admin allowlist (admin console → General), role = admin
  * otherwise the requested role is honored (free login)

Admin-only API routes depend on `require_admin`, which reads the caller's identity from
request headers set by the frontend session. Not secure by itself — SSO/JWT replaces it.
"""
from __future__ import annotations

import base64
import json

from fastapi import Header, HTTPException

from app.services import config_store

ROLES = ("admin", "user")


def resolve_role(email: str, requested: str | None) -> str:
    email = (email or "").strip().lower()
    if email and email in config_store.admin_emails():
        return "admin"
    return requested if requested in ROLES else "user"


def issue_token(email: str, name: str, role: str) -> str:
    """Opaque, non-secret session token (base64 JSON). Replaced by a real IdP token later."""
    payload = {"email": email, "name": name, "role": role}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_token(token: str) -> dict | None:
    try:
        return json.loads(base64.urlsafe_b64decode(token.encode()).decode())
    except (ValueError, json.JSONDecodeError):
        return None


def current_user(
    x_user_email: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
    x_user_name: str | None = Header(default=None),
) -> dict:
    """Identity from session headers the frontend attaches to each request."""
    role = x_user_role if x_user_role in ROLES else "user"
    # An email in the admin allowlist always resolves to admin, regardless of the header.
    if x_user_email and x_user_email.strip().lower() in config_store.admin_emails():
        role = "admin"
    return {"email": x_user_email or "", "name": x_user_name or "", "role": role}


def require_admin(
    x_user_email: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
    x_user_name: str | None = Header(default=None),
) -> dict:
    user = current_user(x_user_email, x_user_role, x_user_name)
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required.")
    return user
