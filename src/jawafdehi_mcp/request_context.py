"""Request-scoped context for HTTP transport — user identity forwarding."""

from contextvars import ContextVar

jawafdehi_user_id: ContextVar[str | None] = ContextVar(
    "jawafdehi_user_id", default=None
)


def get_forwarded_headers() -> dict[str, str]:
    """Return headers that should be forwarded to upstream API calls."""
    headers: dict[str, str] = {}
    uid = jawafdehi_user_id.get()
    if uid:
        headers["X-Jawafdehi-User-Id"] = uid
    return headers
