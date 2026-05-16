"""Integration tests for the jawafdehi-mcp HTTP server.

Tests identity resolution against a live mock Jawafdehi API server,
ContextVar lifecycle in the HTTP middleware, and end-to-end tool filtering.
"""

import asyncio
import contextlib
import socket

import pytest
import pytest_asyncio
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from jawafdehi_mcp.http_server import JawafdehiMCPServer
from jawafdehi_mcp.identity import current_user_identity
from jawafdehi_mcp.request_context import jawafdehi_user_id

pytestmark = pytest.mark.asyncio(loop_scope="function")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _mock_me_endpoint(request):
    user_id = request.headers.get("x-jawafdehi-user-id", "")
    auth = request.headers.get("authorization", "")

    if not auth or auth != "Token test-integration-token":
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    if user_id == "owui-cw-1":
        return JSONResponse(
            {"user_id": 1, "username": "caseworker1", "roles": ["Contributor"]}
        )
    elif user_id == "owui-admin-1":
        return JSONResponse({"user_id": 2, "username": "admin1", "roles": ["Admin"]})
    elif user_id == "owui-mod-1":
        return JSONResponse({"user_id": 3, "username": "mod1", "roles": ["Moderator"]})
    elif user_id == "owui-pub-1":
        return JSONResponse({"user_id": 4, "username": "public1", "roles": []})
    elif user_id == "owui-error-1":
        return JSONResponse({"error": "not found"}, status_code=404)
    else:
        return JSONResponse({"user_id": 5, "username": user_id, "roles": []})


mock_api_app = Starlette(
    routes=[Route("/api/caseworker/me", _mock_me_endpoint, methods=["GET"])],
)


@pytest_asyncio.fixture
async def mock_api_url():
    port = _find_free_port()
    config = uvicorn.Config(
        mock_api_app, host="127.0.0.1", port=port, log_level="error"
    )
    server = uvicorn.Server(config)
    task = asyncio.ensure_future(server.serve())
    await asyncio.sleep(0.15)
    url = f"http://127.0.0.1:{port}"
    yield url
    server.should_exit = True
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest_asyncio.fixture
async def mcp_server(mock_api_url, monkeypatch):
    monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
    monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)
    mcp = JawafdehiMCPServer()
    ctx = mcp.session_manager.run()
    await ctx.__aenter__()
    yield mcp
    try:
        await ctx.__aexit__(None, None, None)
    except RuntimeError:
        pass


def _make_scope(headers=None):
    return {
        "type": "http",
        "method": "POST",
        "path": "/",
        "http_version": "1.1",
        "headers": headers or [],
        "query_string": b"",
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 12345),
    }


async def _dummy_receive():
    return {"type": "http.disconnect"}


class TestHttpServerMiddleware:
    async def test_caseworker_identity_resolved(self, mcp_server):
        scope = _make_scope([(b"x-jawafdehi-user-id", b"owui-cw-1")])
        await mcp_server._handle_http(scope, _dummy_receive, _noop_send)
        assert jawafdehi_user_id.get() is None
        assert current_user_identity.get() is None

    async def test_public_user_identity_resolved(self, mcp_server):
        scope = _make_scope([(b"x-jawafdehi-user-id", b"owui-pub-1")])
        await mcp_server._handle_http(scope, _dummy_receive, _noop_send)
        assert jawafdehi_user_id.get() is None
        assert current_user_identity.get() is None

    async def test_no_header_no_identity(self, mcp_server):
        scope = _make_scope([])
        await mcp_server._handle_http(scope, _dummy_receive, _noop_send)
        assert jawafdehi_user_id.get() is None
        assert current_user_identity.get() is None

    async def test_identity_cleanup_on_api_error(self, mcp_server):
        scope = _make_scope([(b"x-jawafdehi-user-id", b"owui-error-1")])
        await mcp_server._handle_http(scope, _dummy_receive, _noop_send)
        assert jawafdehi_user_id.get() is None
        assert current_user_identity.get() is None

    async def test_admin_role_resolved(self, mcp_server):
        scope = _make_scope([(b"x-jawafdehi-user-id", b"owui-admin-1")])
        await mcp_server._handle_http(scope, _dummy_receive, _noop_send)
        assert jawafdehi_user_id.get() is None
        assert current_user_identity.get() is None

    async def test_moderator_role_resolved(self, mcp_server):
        scope = _make_scope([(b"x-jawafdehi-user-id", b"owui-mod-1")])
        await mcp_server._handle_http(scope, _dummy_receive, _noop_send)
        assert jawafdehi_user_id.get() is None
        assert current_user_identity.get() is None


class TestLiveApiIntegration:
    async def test_resolve_caseworker(self, mock_api_url, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)

        from jawafdehi_mcp.identity import resolve_user_identity

        identity = await resolve_user_identity("owui-cw-1")
        assert identity is not None
        assert identity["user_id"] == 1
        assert identity["username"] == "caseworker1"
        assert "Contributor" in identity["roles"]

    async def test_resolve_public_user(self, mock_api_url, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)

        from jawafdehi_mcp.identity import resolve_user_identity

        identity = await resolve_user_identity("owui-pub-1")
        assert identity is not None
        assert identity["user_id"] == 4
        assert identity["roles"] == []

    async def test_resolve_admin_user(self, mock_api_url, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)

        from jawafdehi_mcp.identity import resolve_user_identity

        identity = await resolve_user_identity("owui-admin-1")
        assert identity is not None
        assert "Admin" in identity["roles"]

    async def test_resolve_moderator_user(self, mock_api_url, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)

        from jawafdehi_mcp.identity import resolve_user_identity

        identity = await resolve_user_identity("owui-mod-1")
        assert identity is not None
        assert "Moderator" in identity["roles"]

    async def test_resolve_returns_none_on_api_error(self, mock_api_url, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)

        from jawafdehi_mcp.identity import resolve_user_identity

        identity = await resolve_user_identity("owui-error-1")
        assert identity is None


class TestToolFilteringEndToEnd:
    async def test_caseworker_gets_all_tools(self, mock_api_url, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)

        from jawafdehi_mcp.identity import current_user_identity as cid
        from jawafdehi_mcp.server import TOOL_MAP, _get_allowed_tools

        cid.set({"user_id": 1, "username": "cw", "roles": ["Contributor"]})
        try:
            tools = _get_allowed_tools()
            assert len(tools) == len(TOOL_MAP)
        finally:
            cid.set(None)

    async def test_public_user_gets_read_only_tools(self, mock_api_url, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)

        from jawafdehi_mcp.identity import PUBLIC_READ_ONLY_TOOL_NAMES
        from jawafdehi_mcp.identity import current_user_identity as cid
        from jawafdehi_mcp.server import _get_allowed_tools

        cid.set({"user_id": 2, "username": "pub", "roles": []})
        try:
            tools = _get_allowed_tools()
            tool_names = {t.name for t in tools}
            assert tool_names == PUBLIC_READ_ONLY_TOOL_NAMES
        finally:
            cid.set(None)

    async def test_admin_user_gets_all_tools(self, mock_api_url, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)

        from jawafdehi_mcp.identity import current_user_identity as cid
        from jawafdehi_mcp.server import TOOL_MAP, _get_allowed_tools

        cid.set({"user_id": 3, "username": "admin", "roles": ["Admin"]})
        try:
            tools = _get_allowed_tools()
            assert len(tools) == len(TOOL_MAP)
        finally:
            cid.set(None)

    async def test_moderator_user_gets_all_tools(self, mock_api_url, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-integration-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", mock_api_url)

        from jawafdehi_mcp.identity import current_user_identity as cid
        from jawafdehi_mcp.server import TOOL_MAP, _get_allowed_tools

        cid.set({"user_id": 4, "username": "mod", "roles": ["Moderator"]})
        try:
            tools = _get_allowed_tools()
            assert len(tools) == len(TOOL_MAP)
        finally:
            cid.set(None)


async def _noop_send(message):
    pass
