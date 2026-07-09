"""Request-scoped context for MCP transports and bearer-token forwarding."""

from contextvars import ContextVar

current_transport: ContextVar[str | None] = ContextVar(
    "current_transport", default=None
)

jawafdehi_bearer_token: ContextVar[str | None] = ContextVar(
    "jawafdehi_bearer_token", default=None
)


def get_forwarded_headers() -> dict[str, str]:
    """Headers forwarded to upstream jawafdehi-api calls.

    Forwards the caller's verified OIDC bearer so the API authenticates as the
    same user (OIDCJWTAuthentication). Empty in stdio/dev, where tools fall back
    to a service token.
    """
    token = jawafdehi_bearer_token.get()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
