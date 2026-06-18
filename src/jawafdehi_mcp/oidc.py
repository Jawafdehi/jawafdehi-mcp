"""OIDC bearer-token verification for jawafdehi-mcp.

Verifies Zitadel-issued RS256 access tokens via JWKS and resolves the caller's
identity (email, name, roles) from the OIDC userinfo endpoint. Mirrors
jawafdehi-api's OIDCJWTAuthentication so both services trust the same tokens.
"""

import asyncio
import os
import time

import httpx
import jwt
import structlog

logger = structlog.get_logger()

# A non-default User-Agent is required: the Cloudflare WAF in front of
# auth.jawafdehi.org 403s the stock ``Python-urllib``/client agents.
_USER_AGENT = "jawafdehi-mcp/1.0"

_jwks_client: jwt.PyJWKClient | None = None

# Userinfo cached by token id so we call the userinfo endpoint at most once per
# access token (not on every request).
_userinfo_cache: dict[str, tuple[float, dict]] = {}


class OIDCError(Exception):
    """Raised when a bearer token cannot be verified or its identity resolved."""


def _env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise OIDCError(f"{name} is not configured")
    return value


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            _env("OIDC_JWKS_URL"),
            headers={"User-Agent": _USER_AGENT},
        )
    return _jwks_client


def verify_bearer_token(token: str) -> dict:
    """Validate a Zitadel RS256 access token and return its claims.

    Raises OIDCError on any failure: a JWE rather than a JWS, bad signature,
    wrong audience/issuer, or expiry.
    """
    # A JWS has 3 segments (2 dots); a JWE has 5. We only accept JWS.
    if token.count(".") != 2:
        raise OIDCError("encrypted (JWE) tokens are not accepted")

    issuer = _env("OIDC_ISSUER")
    audience = _env("OIDC_API_AUDIENCE")
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("oidc_token_validation_failed", error=str(exc))
        raise OIDCError("invalid token or signature") from exc


async def fetch_userinfo(token: str, claims: dict) -> dict:
    """Return userinfo claims (email/name/roles) for this access token.

    The access token carries only sub/aud/iss; email and the flattened ``roles``
    array live in userinfo, so we fetch them here and cache per token (until the
    token's ``exp``) to avoid a call per request.
    """
    key = claims.get("jti") or claims.get("sub") or token
    now = time.time()
    cached = _userinfo_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    endpoint = _env("OIDC_OP_USER_ENDPOINT")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                endpoint,
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json",
                },
                timeout=10,
            )
            response.raise_for_status()
            info: dict = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("oidc_userinfo_fetch_failed", error=str(exc))
        raise OIDCError("could not resolve user identity") from exc

    # Prune expired entries so the per-token cache can't grow unbounded.
    for stale in [k for k, (exp, _) in _userinfo_cache.items() if exp <= now]:
        del _userinfo_cache[stale]
    _userinfo_cache[key] = (float(claims.get("exp", now + 300)), info)
    return info


def build_identity(claims: dict, info: dict) -> dict:
    """Assemble the request-scoped identity dict from token + userinfo claims."""
    roles = info.get("roles")
    if not isinstance(roles, list):
        roles = []
    name = (
        info.get("name")
        or " ".join(
            part for part in (info.get("given_name"), info.get("family_name")) if part
        ).strip()
    )
    return {
        "sub": claims.get("sub"),
        "email": (info.get("email") or "").lower() or None,
        "name": name or None,
        "roles": [str(role) for role in roles],
    }


async def resolve_bearer_identity(token: str) -> dict:
    """Verify a bearer token and resolve the full identity. Raises OIDCError."""
    # verify_bearer_token may do a blocking JWKS fetch (first call / key
    # rotation); run it off the event loop.
    claims = await asyncio.to_thread(verify_bearer_token, token)
    info = await fetch_userinfo(token, claims)
    return build_identity(claims, info)
