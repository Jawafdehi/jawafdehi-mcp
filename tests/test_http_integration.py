"""Integration tests for the jawafdehi-mcp HTTP server bearer auth.

Exercises the ASGI middleware: bearer extraction, OIDC verification (mocked),
ContextVar lifecycle, 401 on bad tokens, anonymous fallback, and the health /
protected-resource-metadata endpoints.
"""

import json

import pytest

from jawafdehi_mcp import http_server
from jawafdehi_mcp.http_server import (
    JawafdehiMCPServer,
    _bearer_from_headers,
    _canonical_base_url,
    _forwarded_host_scheme,
    _mode_from_headers,
    _protected_resource_metadata,
)
from jawafdehi_mcp.identity import current_request_mode, current_user_identity
from jawafdehi_mcp.oidc import OIDCError
from jawafdehi_mcp.request_context import jawafdehi_bearer_token


def _make_scope(headers=None, path="/"):
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "http_version": "1.1",
        "headers": headers or [],
        "query_string": b"",
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 12345),
    }


async def _dummy_receive():
    return {"type": "http.disconnect"}


class _SendRecorder:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self):
        for m in self.messages:
            if m["type"] == "http.response.start":
                return m["status"]
        return None

    @property
    def body(self):
        for m in self.messages:
            if m["type"] == "http.response.body":
                return m["body"]
        return b""


@pytest.fixture
def mcp_server():
    return JawafdehiMCPServer()


@pytest.fixture
def captured(mcp_server, monkeypatch):
    """Replace handle_request with a recorder of the in-request context."""
    seen = {}

    async def _recorder(scope, receive, send):
        seen["identity"] = current_user_identity.get()
        seen["bearer"] = jawafdehi_bearer_token.get()
        seen["mode"] = current_request_mode.get()

    monkeypatch.setattr(mcp_server.session_manager, "handle_request", _recorder)
    return seen


class TestBearerHelper:
    def test_extracts_bearer(self):
        assert _bearer_from_headers({b"authorization": b"Bearer abc"}) == "abc"

    def test_ignores_non_bearer(self):
        assert _bearer_from_headers({b"authorization": b"Token abc"}) is None

    def test_none_when_absent(self):
        assert _bearer_from_headers({}) is None


class TestMiddleware:
    pytestmark = pytest.mark.asyncio(loop_scope="function")

    async def test_valid_bearer_sets_identity(self, mcp_server, captured, monkeypatch):
        identity = {"sub": "u1", "email": "a@x.org", "roles": ["contributor"]}

        async def _resolve(token):
            assert token == "good-token"
            return identity

        monkeypatch.setattr(http_server, "resolve_bearer_identity", _resolve)

        scope = _make_scope([(b"authorization", b"Bearer good-token")])
        await mcp_server._handle_http(scope, _dummy_receive, _SendRecorder())

        assert captured["identity"] == identity
        assert captured["bearer"] == "good-token"
        # contextvars reset after the request
        assert current_user_identity.get() is None
        assert jawafdehi_bearer_token.get() is None

    async def test_invalid_bearer_returns_401(self, mcp_server, monkeypatch):
        async def _resolve(token):
            raise OIDCError("invalid token or signature")

        monkeypatch.setattr(http_server, "resolve_bearer_identity", _resolve)

        send = _SendRecorder()
        scope = _make_scope([(b"authorization", b"Bearer bad")])
        await mcp_server._handle_http(scope, _dummy_receive, send)

        assert send.status == 401
        assert json.loads(send.body)["error"] == "invalid_token"
        assert current_user_identity.get() is None

    async def test_no_bearer_is_anonymous(self, mcp_server, captured):
        scope = _make_scope([])
        await mcp_server._handle_http(scope, _dummy_receive, _SendRecorder())
        assert captured["identity"] is None
        assert captured["bearer"] is None

    async def test_health_endpoint(self, mcp_server):
        send = _SendRecorder()
        scope = _make_scope([], path="/health")
        await mcp_server._handle_http(scope, _dummy_receive, send)
        assert send.status == 200

    async def test_protected_resource_metadata(self, mcp_server, monkeypatch):
        monkeypatch.setenv("OIDC_ISSUER", "https://auth.x.org")
        monkeypatch.setenv("OIDC_API_AUDIENCE", "proj-1")
        send = _SendRecorder()
        scope = _make_scope([], path="/.well-known/oauth-protected-resource")
        await mcp_server._handle_http(scope, _dummy_receive, send)
        assert send.status == 200
        meta = json.loads(send.body)
        assert meta["resource"] == "proj-1"
        assert meta["authorization_servers"] == ["https://auth.x.org"]


class TestProtectedResourceMetadata:
    def test_resource_defaults_to_audience(self, monkeypatch):
        monkeypatch.delenv("OIDC_RESOURCE", raising=False)
        monkeypatch.setenv("OIDC_API_AUDIENCE", "aud-1")
        monkeypatch.setenv("OIDC_ISSUER", "https://iss.x.org")
        meta = _protected_resource_metadata()
        assert meta["resource"] == "aud-1"
        assert meta["bearer_methods_supported"] == ["header"]

    def test_host_aware_resource_and_scopes(self, monkeypatch):
        monkeypatch.setenv("OIDC_API_AUDIENCE", "proj-9")
        monkeypatch.setenv("OIDC_ISSUER", "https://auth.x.org")
        meta = _protected_resource_metadata("https://mcp-internal.x.org")
        assert meta["resource"] == "https://mcp-internal.x.org"
        # Design 1a: point at Zitadel directly.
        assert meta["authorization_servers"] == ["https://auth.x.org"]
        # Refresh + project-audience scopes advertised.
        assert "offline_access" in meta["scopes_supported"]
        assert "urn:zitadel:iam:org:project:id:proj-9:aud" in meta["scopes_supported"]


class TestHeaderHelpers:
    def test_mode_from_headers(self):
        assert _mode_from_headers({b"x-mcp-mode": b"internal"}) == "internal"
        assert _mode_from_headers({b"x-mcp-mode": b"Public"}) == "public"
        assert _mode_from_headers({}) is None

    def test_forwarded_host_scheme_prefers_forwarded(self):
        host, scheme = _forwarded_host_scheme(
            {
                b"x-forwarded-host": b"mcp.x.org",
                b"host": b"internal",
                b"x-forwarded-proto": b"https",
            }
        )
        assert host == "mcp.x.org"
        assert scheme == "https"

    def test_forwarded_host_scheme_falls_back_to_host(self):
        host, scheme = _forwarded_host_scheme({b"host": b"mcp-internal.x.org"})
        assert host == "mcp-internal.x.org"
        assert scheme == "https"

    def test_mode_defaults_to_env_floor(self, monkeypatch):
        monkeypatch.setenv("MCP_DEFAULT_MODE", "public")
        # Missing header falls back to the deployment floor...
        assert _mode_from_headers({}) == "public"
        # ...but an explicit ingress-injected header still wins.
        assert _mode_from_headers({b"x-mcp-mode": b"internal"}) == "internal"

    def test_canonical_base_prefers_configured_over_client_host(self, monkeypatch):
        monkeypatch.setenv("OIDC_RESOURCE", "https://mcp-internal.jawafdehi.org")
        # A spoofed X-Forwarded-Host / Host must NOT steer the advertised URL.
        base = _canonical_base_url(
            {b"x-forwarded-host": b"evil.example", b"host": b"evil.example"}
        )
        assert base == "https://mcp-internal.jawafdehi.org"

    def test_canonical_base_falls_back_to_host_when_unset(self, monkeypatch):
        monkeypatch.delenv("OIDC_RESOURCE", raising=False)
        base = _canonical_base_url({b"host": b"mcp-internal.x.org"})
        assert base == "https://mcp-internal.x.org"


class TestModeDoors:
    pytestmark = pytest.mark.asyncio(loop_scope="function")

    async def test_internal_anonymous_gets_401_challenge(self, mcp_server):
        send = _SendRecorder()
        scope = _make_scope(
            [(b"x-mcp-mode", b"internal"), (b"host", b"mcp-internal.x.org")]
        )
        await mcp_server._handle_http(scope, _dummy_receive, send)
        assert send.status == 401
        wa = dict(
            (k.decode(), v.decode())
            for k, v in next(
                m["headers"]
                for m in send.messages
                if m["type"] == "http.response.start"
            )
        )
        assert "resource_metadata=" in wa["www-authenticate"]
        assert "mcp-internal.x.org" in wa["www-authenticate"]

    async def test_public_anonymous_proceeds(self, mcp_server, captured):
        scope = _make_scope([(b"x-mcp-mode", b"public")])
        await mcp_server._handle_http(scope, _dummy_receive, _SendRecorder())
        assert captured["identity"] is None
        assert captured["mode"] == "public"
        # contextvar reset after request
        assert current_request_mode.get() is None

    async def test_legacy_anonymous_proceeds(self, mcp_server, captured):
        scope = _make_scope([])
        await mcp_server._handle_http(scope, _dummy_receive, _SendRecorder())
        assert captured["identity"] is None
        assert captured["mode"] is None

    async def test_metadata_ignores_spoofed_host_when_configured(
        self, mcp_server, monkeypatch
    ):
        monkeypatch.setenv("OIDC_RESOURCE", "https://mcp-internal.jawafdehi.org")
        monkeypatch.setenv("OIDC_ISSUER", "https://auth.x.org")
        monkeypatch.setenv("OIDC_API_AUDIENCE", "proj-1")
        send = _SendRecorder()
        scope = _make_scope(
            [
                (b"x-mcp-mode", b"internal"),
                (b"x-forwarded-host", b"evil.example"),
            ],
            path="/.well-known/oauth-protected-resource",
        )
        await mcp_server._handle_http(scope, _dummy_receive, send)
        meta = json.loads(send.body)
        assert meta["resource"] == "https://mcp-internal.jawafdehi.org"

    async def test_public_hides_oauth_metadata(self, mcp_server):
        send = _SendRecorder()
        scope = _make_scope(
            [(b"x-mcp-mode", b"public")],
            path="/.well-known/oauth-protected-resource",
        )
        await mcp_server._handle_http(scope, _dummy_receive, send)
        assert send.status == 404

    async def test_internal_serves_host_aware_metadata(self, mcp_server, monkeypatch):
        monkeypatch.setenv("OIDC_API_AUDIENCE", "proj-1")
        monkeypatch.setenv("OIDC_ISSUER", "https://auth.x.org")
        send = _SendRecorder()
        scope = _make_scope(
            [(b"x-mcp-mode", b"internal"), (b"host", b"mcp-internal.x.org")],
            path="/.well-known/oauth-protected-resource",
        )
        await mcp_server._handle_http(scope, _dummy_receive, send)
        assert send.status == 200
        meta = json.loads(send.body)
        assert meta["resource"] == "https://mcp-internal.x.org"
        assert meta["authorization_servers"] == ["https://auth.x.org"]

    async def test_internal_valid_token_proceeds(
        self, mcp_server, captured, monkeypatch
    ):
        identity = {"sub": "u1", "email": "cw@x.org", "roles": ["contributor"]}

        async def _resolve(token):
            return identity

        monkeypatch.setattr(http_server, "resolve_bearer_identity", _resolve)
        scope = _make_scope(
            [(b"x-mcp-mode", b"internal"), (b"authorization", b"Bearer good")]
        )
        await mcp_server._handle_http(scope, _dummy_receive, _SendRecorder())
        assert captured["identity"] == identity
        assert captured["mode"] == "internal"
