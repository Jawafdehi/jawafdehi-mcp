"""Streamable HTTP transport for jawafdehi-mcp.

Wraps the MCP server with a Streamable HTTP transport using
mcp's built-in StreamableHTTPSessionManager.

Usage:
    jawafdehi-mcp-http
    # or
    HTTP_HOST=127.0.0.1 HTTP_PORT=9090 jawafdehi-mcp-http
"""

import os

import structlog
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from .request_context import jawafdehi_user_id
from .server import app as mcp_app

logger = structlog.get_logger()


class JawafdehiMCPServer:
    """Minimal ASGI app wrapping StreamableHTTPSessionManager with
    X-Jawafdehi-User-Id header capture."""

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
        """Extract user ID header, then delegate to the session manager."""
        headers = dict(scope.get("headers", []))
        raw = headers.get(b"x-jawafdehi-user-id", b"").decode()
        uid = raw.strip()
        token = None
        if uid:
            token = jawafdehi_user_id.set(uid)
        try:
            await self.session_manager.handle_request(scope, receive, send)
        finally:
            if token is not None:
                jawafdehi_user_id.reset(token)


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
