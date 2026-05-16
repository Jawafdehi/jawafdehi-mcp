"""Per-request user identity resolution for jawafdehi-mcp.

Resolves user identity via jawafdehi-api's /api/caseworker/me endpoint,
stores the result in a request-scoped ContextVar, and maps resolved
roles to allowed MCP tool names.
"""

import os
from contextvars import ContextVar

import httpx
import structlog

from .request_context import get_forwarded_headers

logger = structlog.get_logger()

current_user_identity: ContextVar[dict | None] = ContextVar(
    "current_user_identity", default=None
)

PUBLIC_READ_ONLY_TOOL_NAMES: set[str] = {
    "search_jawafdehi_cases",
    "get_jawafdehi_case",
    "search_jawaf_entities",
    "get_jawaf_entity",
    "search_nes_entities",
    "get_nes_entities",
    "get_nes_tags",
    "get_nes_entity_prefixes",
    "get_nes_entity_prefix_schema",
    "ngm_query_judicial",
    "convert_date",
    "convert_to_markdown",
}

CASEWORKER_ROLE_NAMES: set[str] = {"Contributor", "Admin", "Moderator"}


def _get_jawafdehi_base_url() -> str:
    return os.getenv("JAWAFDEHI_API_BASE_URL", "https://portal.jawafdehi.org").rstrip(
        "/"
    )


def _get_jawafdehi_api_token() -> str | None:
    token = os.getenv("JAWAFDEHI_API_TOKEN", "").strip()
    return token or None


async def resolve_user_identity(user_id: str) -> dict | None:
    """Resolve user identity via jawafdehi-api GET /api/caseworker/me.

    Returns the parsed JSON identity dict on success, or None if resolution
    is unavailable or fails (public-access fallback).
    """
    token = _get_jawafdehi_api_token()
    if not token:
        return None

    base_url = _get_jawafdehi_base_url()
    url = f"{base_url}/api/caseworker/me"

    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Token {token}",
            }
            headers.update(get_forwarded_headers())
            response = await client.get(
                url,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            identity: dict = response.json()
            logger.info(
                "user_identity_resolved",
                user_id=identity.get("user_id"),
                username=identity.get("username"),
                roles=identity.get("roles"),
            )
            return identity
    except Exception:
        logger.exception("user_identity_resolution_failed", forwarded_user_id=user_id)
        return None


def role_has_write_access(roles: list[str]) -> bool:
    """Return True if any of the given roles grants write-tool access."""
    return any(role in CASEWORKER_ROLE_NAMES for role in roles)


def get_allowed_tool_names(identity: dict | None, all_tool_names: set[str]) -> set[str]:
    """Return the set of tool names allowed for the given identity.

    - No identity → public read-only tools only.
    - Identity with a caseworker role → all tools.
    - Identity without a caseworker role → public read-only tools.
    """
    if identity is None:
        return PUBLIC_READ_ONLY_TOOL_NAMES & all_tool_names

    roles: list[str] = identity.get("roles", [])
    if role_has_write_access(roles):
        return all_tool_names

    return PUBLIC_READ_ONLY_TOOL_NAMES & all_tool_names
