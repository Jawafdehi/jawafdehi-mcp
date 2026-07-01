"""Tests for NES-backed MCP tools."""

import json

import httpx
import pytest

from jawafdehi_mcp.server import TOOL_MAP
from jawafdehi_mcp.tools.nes import GetNESEntityPrefixesTool


class _FakeAsyncClient:
    def __init__(self, get_impl):
        self._get_impl = get_impl

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, timeout=None):
        return await self._get_impl(url, timeout)


class TestGetNESEntityPrefixesTool:
    def setup_method(self):
        self.tool = GetNESEntityPrefixesTool()

    def test_tool_name(self):
        assert self.tool.name == "get_nes_entity_prefixes"

    def test_input_schema_is_empty_object(self):
        assert self.tool.input_schema == {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def test_tool_registered_with_server(self):
        assert "get_nes_entity_prefixes" in TOOL_MAP

    @pytest.mark.asyncio
    async def test_successful_response(self, monkeypatch):
        monkeypatch.setenv("NES_API_BASE_URL", "https://nes.example")

        async def fake_get(url, timeout):
            assert url == "https://nes.example/api/entity_prefixes"
            assert timeout == 30.0
            return httpx.Response(
                200,
                json={
                    "prefixes": [
                        {"prefix": "person", "entity_type": "person"},
                        {
                            "prefix": "organization/political_party",
                            "entity_type": "organization",
                        },
                    ]
                },
            )

        monkeypatch.setattr(
            "jawafdehi_mcp.tools.nes.httpx.AsyncClient",
            lambda: _FakeAsyncClient(fake_get),
        )

        result = await self.tool.execute({})

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed["prefixes"][0]["prefix"] == "person"

    @pytest.mark.asyncio
    async def test_non_200_response_includes_http_code(self, monkeypatch):
        async def fake_get(url, timeout):
            return httpx.Response(503, json={"detail": "NES unavailable"})

        monkeypatch.setattr(
            "jawafdehi_mcp.tools.nes.httpx.AsyncClient",
            lambda: _FakeAsyncClient(fake_get),
        )

        result = await self.tool.execute({})

        assert "HTTP 503" in result[0].text
        assert "NES unavailable" in result[0].text
