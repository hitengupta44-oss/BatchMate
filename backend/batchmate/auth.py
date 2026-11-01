"""Demo sign-in with signed tokens.

DEMO_USERS="priya:pw1,arjun:pw2,coordinator-demo:pw3" turns sign-in on: the API then trusts only
signed tokens from POST /auth/login, never a bare X-User header. Without DEMO_USERS the API runs in
open demo mode (X-User accepted) so local quick start needs no setup.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Header, HTTPException

from . import ratelimit

_SECRET = (os.getenv("AUTH_SECRET") or secrets.token_hex(32)).encode()
TOKEN_TTL_S = 12 * 3600


def _users() -> dict[str, str]:
    raw = os.getenv("DEMO_USERS", "").strip()
    out = {}
    for pair in raw.split(","):
        if ":" in pair:
            u, p = pair.split(":", 1)
            if u.strip():
                out[u.strip()] = p.strip()
    return out


def auth_enabled() -> bool:
    return bool(_users())


def role(user: str) -> str:
    return "coordinator" if user.startswith("coordinator") else "student"


def list_users() -> list[dict]:
    names = list(_users()) or ["priya", "arjun", "coordinator-demo"]
    return [{"id": u, "role": role(u)} for u in names]


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue(user: str) -> str:
    body = _b64(json.dumps({"u": user, "exp": int(time.time()) + TOKEN_TTL_S}).encode())
    sig = _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token: str) -> str | None:
    try:
        body, sig = token.split(".", 1)
        good = _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(_unb64(body))
        return data["u"] if data["exp"] > time.time() else None
    except Exception:
        return None


def login(user: str, password: str) -> str:
    users = _users()
    if users and not hmac.compare_digest(users.get(user, "\0"), password or ""):
        raise HTTPException(401, "Wrong name or password")
    if not users and user not in {u["id"] for u in list_users()}:
        raise HTTPException(401, "Unknown demo user")
    return issue(user)


def current_user(authorization: str = Header(""), x_user: str = Header("")) -> str:
    """FastAPI dependency: the signed-in user id (rate limited)."""
    user = None
    if authorization.lower().startswith("bearer "):
        user = verify(authorization[7:].strip())
        if user is None:
            raise HTTPException(401, "Session expired. Sign in again.")
    elif not auth_enabled() and x_user:
        user = x_user  # open demo mode only
    if not user:
        raise HTTPException(401, "Sign in first")
    if not ratelimit.allow(user):
        raise HTTPException(429, "Slow down: rate limit reached")
    return user
