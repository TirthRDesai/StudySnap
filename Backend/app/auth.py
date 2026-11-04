"""Authenticate requests by asking Supabase Auth who owns the bearer token."""
import time
from dataclasses import dataclass

import httpx
from fastapi import Header, HTTPException

from .config import settings

_CACHE_TTL = 30.0
_cache: dict[str, tuple[float, "AuthUser"]] = {}


@dataclass(frozen=True)
class AuthUser:
    id: str


def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token.")

    now = time.monotonic()
    hit = _cache.get(token)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]

    try:
        resp = httpx.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": settings.supabase_anon_key},
            timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Auth service unreachable.")

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user_id = resp.json().get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    user = AuthUser(id=user_id)
    if len(_cache) > 1000:
        _cache.clear()
    _cache[token] = (now, user)
    return user
