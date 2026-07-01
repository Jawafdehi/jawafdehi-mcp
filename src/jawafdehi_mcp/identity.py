"""Per-request user identity helpers for jawafdehi-mcp.

Identity is built from the caller's verified OIDC bearer token (see
``oidc.py`` and ``http_server.py``) and stored in a request-scoped ContextVar.
This module maps the resolved roles to the set of allowed MCP tool names.
"""

import os
from contextvars import ContextVar

import structlog

logger = structlog.get_logger()

current_user_identity: ContextVar[dict | None] = ContextVar(
    "current_user_identity", default=None
)

PUBLIC_READ_ONLY_TOOL_NAMES: set[str] = {
    "get_current_user",
    "search_jawafdehi_cases",
    "get_jawafdehi_case",
    "search_nes_entities",
    "get_nes_entities",
    "get_nes_tags",
    "get_nes_entity_prefixes",
    "ngm_query_judicial",
    "convert_date",
    "convert_to_markdown",
}

# Zitadel role keys are lowercase (admin, contributor, moderator, ...); matching
# is case-insensitive so legacy capitalized names also work.
_DEFAULT_WRITE_ROLES = ("contributor", "admin", "moderator")


def _write_role_names() -> set[str]:
    """Roles that grant write-tool access (lowercased).

    Configurable via MCP_WRITE_ROLES (comma-separated) so new roles can be
    granted write access without a code change. Falls back to the default
    caseworker roles when unset.
    """
    raw = (os.getenv("MCP_WRITE_ROLES") or "").strip()
    names = (
        [role.strip() for role in raw.split(",") if role.strip()]
        if raw
        else list(_DEFAULT_WRITE_ROLES)
    )
    return {name.lower() for name in names}


CASEWORKER_ROLE_NAMES: set[str] = _write_role_names()


def role_has_write_access(roles: list[str]) -> bool:
    """Return True if any of the given roles grants write-tool access.

    Reads MCP_WRITE_ROLES at call time so configuration changes take effect
    without re-importing the module. Case-insensitive.
    """
    write_roles = _write_role_names()
    return any(str(role).lower() in write_roles for role in roles)


def get_allowed_tool_names(identity: dict | None, all_tool_names: set[str]) -> set[str]:
    """Return the set of tool names allowed for the given identity.

    - No identity → public read-only tools only.
    - Identity with a write-granting role → all tools.
    - Identity without a write-granting role → public read-only tools.
    """
    if identity is None:
        return PUBLIC_READ_ONLY_TOOL_NAMES & all_tool_names

    roles: list[str] = identity.get("roles", [])
    if role_has_write_access(roles):
        return all_tool_names

    return PUBLIC_READ_ONLY_TOOL_NAMES & all_tool_names
