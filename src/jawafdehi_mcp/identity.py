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

# Which "door" the request came through, tagged by the ingress (X-MCP-Mode):
#   "public"   -> anonymous, restricted tool set (mcp.jawafdehi.org)
#   "internal" -> OAuth-gated (mcp-internal.jawafdehi.org); anonymous requests
#                 are challenged with 401 upstream in http_server, so an
#                 anonymous request should not normally reach tool gating here.
#   None       -> legacy/unset (OWUI-facing in-cluster deploy, stdio) — keep the
#                 historical anonymous behavior (full read-only set).
current_request_mode: ContextVar[str | None] = ContextVar(
    "current_request_mode", default=None
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

# Anonymous tool set for the public internet door. Drops the two tools that
# burn real resources for unauthenticated callers: convert_to_markdown (OCR /
# LLM credits) and ngm_query_judicial (arbitrary SQL over the judicial lake).
PUBLIC_HOST_TOOL_NAMES: set[str] = PUBLIC_READ_ONLY_TOOL_NAMES - {
    "convert_to_markdown",
    "ngm_query_judicial",
}


def anonymous_tool_names(mode: str | None) -> set[str]:
    """Tool set for an unauthenticated caller, by request mode.

    Only the public internet door restricts the set; the legacy/unset and
    internal doors keep the full read-only set (the internal door 401s
    anonymous callers before this anyway).
    """
    if mode == "public":
        return PUBLIC_HOST_TOOL_NAMES
    return PUBLIC_READ_ONLY_TOOL_NAMES


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


def get_allowed_tool_names(
    identity: dict | None,
    all_tool_names: set[str],
    mode: str | None = None,
) -> set[str]:
    """Return the set of tool names allowed for the given identity + mode.

    - No identity → anonymous tools for the request mode (restricted on the
      public internet door, full read-only otherwise).
    - Identity with a write-granting role → all tools.
    - Identity without a write-granting role → full read-only set (an
      authenticated caller is not restricted by the public-door set).
    """
    if identity is None:
        return anonymous_tool_names(mode) & all_tool_names

    roles: list[str] = identity.get("roles", [])
    if role_has_write_access(roles):
        return all_tool_names

    return PUBLIC_READ_ONLY_TOOL_NAMES & all_tool_names
