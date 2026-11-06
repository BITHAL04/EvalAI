"""Clerk session verification. Identity comes only from a signature-checked token."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import ConfigurationError, get_settings
from app.core.errors import DomainError

log = logging.getLogger("evalai.auth")


@lru_cache
def _jwks(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=600, timeout=10)


@dataclass
class TokenClaims:
    sub: str
    email: str | None
    email_verified: bool | None
    name: str | None
    raw: dict


def verify_token(token: str) -> TokenClaims:
    s = get_settings()
    if not s.clerk_jwks_url or not s.clerk_issuer:
        raise ConfigurationError("Authentication needs CLERK_JWKS_URL and CLERK_ISSUER. See docs/DEPLOYMENT.md.")
    try:
        key = _jwks(s.clerk_jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=s.clerk_issuer,
                            options={"require": ["exp", "iat", "sub", "iss"], "verify_aud": False})
    except jwt.PyJWKClientConnectionError as exc:
        log.error("JWKS unreachable: %s", exc)
        raise DomainError(503, "auth_unavailable", "Could not verify your session right now") from exc
    except jwt.PyJWTError as exc:
        raise DomainError(401, "invalid_token", "Your session is invalid or has expired") from exc
    allowed = {p.strip() for p in s.clerk_authorized_parties.split(",") if p.strip()}
    if allowed and claims.get("azp") not in allowed:
        raise DomainError(401, "invalid_token", "Token was issued for another application")
    return TokenClaims(sub=claims["sub"], email=claims.get("email"), email_verified=claims.get("email_verified"),
                       name=claims.get("name"), raw=claims)


def fetch_clerk_profile(user_id: str) -> tuple[str | None, bool, str | None]:
    """(primary email, verified, name) from the Clerk Backend API; the default session token has no email."""
    s = get_settings()
    if not s.clerk_secret_key:
        return None, False, None
    r = httpx.get(f"https://api.clerk.com/v1/users/{user_id}", headers={"Authorization": f"Bearer {s.clerk_secret_key}"}, timeout=10)
    r.raise_for_status()
    u = r.json()
    primary = next((e for e in u.get("email_addresses", []) if e["id"] == u.get("primary_email_address_id")), None)
    name = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x) or None
    if not primary:
        return None, False, name
    return primary["email_address"], (primary.get("verification") or {}).get("status") == "verified", name
