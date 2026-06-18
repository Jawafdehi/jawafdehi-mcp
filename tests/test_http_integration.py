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
    _protected_resource_metadata,
)
from jawafdehi_mcp.identity import current_user_identity
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
