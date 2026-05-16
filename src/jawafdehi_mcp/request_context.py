"""Request-scoped context for HTTP transport — user identity forwarding."""

from contextvars import ContextVar

jawafdehi_user_id: ContextVar[str | None] = ContextVar(
    "jawafdehi_user_id", default=None
)

jawafdehi_user_name: ContextVar[str | None] = ContextVar(
    "jawafdehi_user_name", default=None
)


def get_forwarded_headers() -> dict[str, str]:
    """Return headers that should be forwarded to upstream API calls."""
    headers: dict[str, str] = {}
    uid = jawafdehi_user_id.get()
    if uid:
        headers["X-Jawafdehi-User-Id"] = uid
    uname = jawafdehi_user_name.get()
    if uname:
        headers["X-Jawafdehi-User-Name"] = uname
    return headers
