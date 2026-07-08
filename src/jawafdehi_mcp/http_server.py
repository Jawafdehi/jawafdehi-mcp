"""Streamable HTTP transport for jawafdehi-mcp.

Wraps the MCP server with a Streamable HTTP transport using mcp's built-in
StreamableHTTPSessionManager, and authenticates each request as an OIDC
resource server: a verified ``Authorization: Bearer`` token resolves the
caller's identity and roles, which the MCP server uses to gate tools and which
is forwarded upstream to jawafdehi-api.

Usage:
    jawafdehi-mcp-http
    # or
    HTTP_HOST=127.0.0.1 HTTP_PORT=9090 jawafdehi-mcp-http
"""

import json
import os

import structlog
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from .identity import current_request_mode, current_user_identity
from .oidc import OIDCError, resolve_bearer_identity
from .request_context import jawafdehi_bearer_token
from .server import app as mcp_app

logger = structlog.get_logger()

WELL_KNOWN_PROTECTED_RESOURCE = "/.well-known/oauth-protected-resource"
# Injected by the ingress (never client-trusted — Traefik overwrites it):
#   "internal" -> OAuth-gated door; unauthenticated requests get a 401 challenge
#   "public"   -> anonymous door; restricted tools, OAuth never advertised
#   absent     -> legacy/OWUI-facing in-cluster behavior (unchanged)
MODE_HEADER = b"x-mcp-mode"


def _bearer_from_headers(headers: dict[bytes, bytes]) -> str | None:
    raw = headers.get(b"authorization", b"").decode(errors="replace").strip()
    if not raw:
        return None
    # Split on any run of whitespace (HTTP allows multiple spaces / tabs).
    parts = raw.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return None
    return parts[1].strip()


def _mode_from_headers(headers: dict[bytes, bytes]) -> str | None:
    raw = headers.get(MODE_HEADER, b"").decode(errors="replace").strip().lower()
    return raw or None


def _forwarded_host_scheme(headers: dict[bytes, bytes]) -> tuple[str | None, str]:
    """The public host + scheme this request was addressed to, from the edge
    proxy headers. Used to build absolute RFC 9728 URLs so the metadata is
    correct on whichever hostname (mcp / mcp-internal) served the request."""
    raw_host = headers.get(b"x-forwarded-host") or headers.get(b"host")
    host = raw_host.decode(errors="replace").split(",")[0].strip() if raw_host else None
    raw_proto = headers.get(b"x-forwarded-proto", b"https")
    scheme = raw_proto.decode(errors="replace").split(",")[0].strip() or "https"
    return host, scheme


def _resource_metadata_url(host: str | None, scheme: str) -> str:
    return f"{scheme}://{host}{WELL_KNOWN_PROTECTED_RESOURCE}" if host else ""


def _protected_resource_metadata(resource_url: str | None = None) -> dict:
    """RFC 9728 Protected Resource Metadata so OAuth clients discover the
    authorization server (Zitadel, Design 1a) and the scopes to request.

    ``resource_url`` is the absolute canonical URL of this MCP server, derived
    from the request Host; falls back to OIDC_RESOURCE/OIDC_API_AUDIENCE for
    stdio / hostless callers."""
    audience = (os.getenv("OIDC_API_AUDIENCE") or "").strip()
    issuer = (os.getenv("OIDC_ISSUER") or "").strip()
    resource = resource_url or (os.getenv("OIDC_RESOURCE") or audience or "").strip()
    # offline_access must be advertised for clients (e.g. Claude Code) to request
    # a refresh token; the project-aud urn puts our project id in the token
    # audience so the API + this server accept the bearer.
    scopes = ["openid", "email", "profile", "offline_access"]
    if audience:
        scopes.append(f"urn:zitadel:iam:org:project:id:{audience}:aud")
    return {
        "resource": resource,
        "authorization_servers": [issuer] if issuer else [],
        "bearer_methods_supported": ["header"],
        "scopes_supported": scopes,
    }


class JawafdehiMCPServer:
    """Minimal ASGI app wrapping StreamableHTTPSessionManager with per-request
    OIDC bearer authentication (see resolve_bearer_identity)."""

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
    async def _send_response(send, status_code, headers, body: bytes = b""):
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [(k.encode(), v.encode()) for k, v in headers],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def _send_json(self, send, status_code, payload, extra_headers=None):
        body = json.dumps(payload).encode()
        headers = [("content-type", "application/json")]
        if extra_headers:
            headers.extend(extra_headers)
        await self._send_response(send, status_code, headers, body)

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
        """Authenticate the request's bearer token, then delegate to MCP.

        Behavior varies by the ingress-injected mode (see MODE_HEADER):
        ``internal`` challenges anonymous callers with a 401 so MCP clients
        start OAuth; ``public`` serves anonymous callers a restricted tool set
        and never advertises OAuth; absent = legacy behavior.
        """
        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))
        mode = _mode_from_headers(headers)

        if path == "/health":
            await receive()
            await self._send_response(send, 200, [("content-type", "text/plain")])
            return
        if path == WELL_KNOWN_PROTECTED_RESOURCE:
            await receive()
            if mode == "public":
                # The public door does not advertise OAuth.
                await self._send_response(
                    send, 404, [("content-type", "text/plain")], b"not found"
                )
                return
            host, scheme = _forwarded_host_scheme(headers)
            resource_url = f"{scheme}://{host}" if host else None
            await self._send_json(send, 200, _protected_resource_metadata(resource_url))
            return

        token = _bearer_from_headers(headers)

        # Internal door: an anonymous request is challenged so the MCP client
        # begins the OAuth flow (clients only start auth on a 401/403).
        if not token and mode == "internal":
            await receive()
            host, scheme = _forwarded_host_scheme(headers)
            rm_url = _resource_metadata_url(host, scheme)
            challenge = f'Bearer resource_metadata="{rm_url}"' if rm_url else "Bearer"
            await self._send_json(
                send,
                401,
                {"error": "unauthorized", "detail": "authentication required"},
                extra_headers=[("www-authenticate", challenge)],
            )
            return

        token_ctx = None
        identity_ctx = None

        if token:
            try:
                identity = await resolve_bearer_identity(token)
            except OIDCError as exc:
                await receive()
                challenge = 'Bearer error="invalid_token"'
                if mode == "internal":
                    host, scheme = _forwarded_host_scheme(headers)
                    rm_url = _resource_metadata_url(host, scheme)
                    if rm_url:
                        challenge += f', resource_metadata="{rm_url}"'
                await self._send_json(
                    send,
                    401,
                    {"error": "invalid_token", "detail": str(exc)},
                    extra_headers=[("www-authenticate", challenge)],
                )
                return
            token_ctx = jawafdehi_bearer_token.set(token)
            identity_ctx = current_user_identity.set(identity)

        mode_ctx = current_request_mode.set(mode)
        try:
            await self.session_manager.handle_request(scope, receive, send)
        finally:
            current_request_mode.reset(mode_ctx)
            if identity_ctx is not None:
                current_user_identity.reset(identity_ctx)
            if token_ctx is not None:
                jawafdehi_bearer_token.reset(token_ctx)


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
