"""Streamable HTTP transport for jawafdehi-mcp.

Wraps the MCP server with a Streamable HTTP transport using
mcp's built-in StreamableHTTPSessionManager.

Usage:
    jawafdehi-mcp-http
    # or
    HTTP_HOST=127.0.0.1 HTTP_PORT=9090 jawafdehi-mcp-http
"""

import os

import jwt
import structlog
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from .identity import current_user_identity, resolve_user_identity
from .request_context import jawafdehi_user_id, jawafdehi_user_name
from .server import app as mcp_app

logger = structlog.get_logger()

OWUI_JWT_HEADER = b"x-openwebui-user-jwt"
OWUI_JWT_ISSUER = "open-webui"


def _decode_owui_jwt(token: str, secret: str) -> dict | None:
    """Verify Open WebUI's HS256 user-info JWT; return its claims or None."""
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=OWUI_JWT_ISSUER,
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None


def extract_identity(headers: dict[bytes, bytes]) -> tuple[str | None, str | None]:
    """Resolve (user_id, user_name) for the request.

    When OWUI_USER_JWT_SECRET is set, trust ONLY the signed X-OpenWebUI-User-Jwt
    that stock Open WebUI mints (sub = OWUI user id); the legacy plaintext
    X-Jawafdehi-User-* headers are spoofable and ignored. Without the secret
    (local dev), fall back to the legacy plaintext headers.
    """
    secret = (os.getenv("OWUI_USER_JWT_SECRET") or "").strip()
    if secret:
        raw = headers.get(OWUI_JWT_HEADER, b"").decode().strip()
        if not raw:
            return None, None
        payload = _decode_owui_jwt(raw, secret)
        if payload is None:
            logger.warning("owui_jwt_verification_failed")
            return None, None
        uid = str(payload.get("sub") or "").strip() or None
        uname = str(payload.get("name") or "").strip() or None
        return uid, uname

    raw_id = headers.get(b"x-jawafdehi-user-id", b"").decode().strip()
    raw_name = headers.get(b"x-jawafdehi-user-name", b"").decode().strip()
    return (raw_id or None), (raw_name or None)


class JawafdehiMCPServer:
    """Minimal ASGI app wrapping StreamableHTTPSessionManager with
    per-request user identity capture (see extract_identity)."""

    def __init__(self) -> None:
        self.session_manager = StreamableHTTPSessionManager(
            app=mcp_app,
            json_response=True,
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        elif scope["type"] == "http":
            await self._handle_http(scope, receive, send)

    @staticmethod
    async def _send_response(send, status_code, headers):
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [(k.encode(), v.encode()) for k, v in headers],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"",
            }
        )

    async def _handle_lifespan(self, scope, receive, send):
        """Handle ASGI lifespan protocol."""
        message = await receive()
        if message["type"] == "lifespan.startup":
            logger.info("http_server_starting")
            self._lifespan_ctx = self.session_manager.run()
            await self._lifespan_ctx.__aenter__()
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            if hasattr(self, "_lifespan_ctx"):
                await self._lifespan_ctx.__aexit__(None, None, None)
            logger.info("http_server_stopped")
            await send({"type": "lifespan.shutdown.complete"})

    async def _handle_http(self, scope, receive, send):
        """Resolve the request's user identity, resolve roles, then delegate."""
        path = scope.get("path", "")
        if path == "/health":
            await receive()
            await self._send_response(send, 200, [("content-type", "text/plain")])
            return
        headers = dict(scope.get("headers", []))
        uid, uname = extract_identity(headers)
        id_token = None
        name_token = None
        identity_token = None
        if uid:
            id_token = jawafdehi_user_id.set(uid)
        if uname:
            name_token = jawafdehi_user_name.set(uname)
        if uid:
            identity = await resolve_user_identity(uid)
            if identity:
                identity_token = current_user_identity.set(identity)
        try:
            await self.session_manager.handle_request(scope, receive, send)
        finally:
            if name_token is not None:
                jawafdehi_user_name.reset(name_token)
            if identity_token is not None:
                current_user_identity.reset(identity_token)
            if id_token is not None:
                jawafdehi_user_id.reset(id_token)


app = JawafdehiMCPServer()


def main() -> None:
    import uvicorn

    host = os.getenv("HTTP_HOST", "0.0.0.0")
    port = int(os.getenv("HTTP_PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    logger.info("http_server_binding", host=host, port=port)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )
