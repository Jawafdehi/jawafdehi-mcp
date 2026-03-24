"""Tests for Jawafdehi API-backed MCP tools."""

import json

import httpx
import pytest

from jawafdehi_mcp.server import TOOL_MAP
from jawafdehi_mcp.tools.jawafdehi_cases import SubmitNESChangeTool


class _FakeAsyncClient:
    def __init__(self, post_impl):
        self._post_impl = post_impl

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json, headers, timeout):
        return await self._post_impl(url, json, headers, timeout)


class TestSubmitNESChangeTool:
    def setup_method(self):
        self.tool = SubmitNESChangeTool()

    def test_tool_name(self):
        assert self.tool.name == "submit_nes_change"

    def test_input_schema_required_fields(self):
        schema = self.tool.input_schema
        assert schema["required"] == ["action", "payload", "change_description"]
        assert "auto_approve" in schema["properties"]

    def test_tool_registered_with_server(self):
        assert "submit_nes_change" in TOOL_MAP

    @pytest.mark.asyncio
    async def test_missing_api_token(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)

        result = await self.tool.execute(
            {
                "action": "ADD_NAME",
                "payload": {"entity_id": "entity:person/test"},
                "change_description": "Add alias",
            }
        )

        assert len(result) == 1
        assert "JAWAFDEHI_API_TOKEN" in result[0].text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action", "payload"),
        [
            (
                "ADD_NAME",
                {
                    "entity_id": "entity:person/sher-bahadur-deuba",
                    "name": {"kind": "ALIAS", "en": {"full": "S. B. Deuba"}},
                    "author_id": "jawafdehi-queue",
                },
            ),
            (
                "CREATE_ENTITY",
                {
                    "entity_type": "person",
                    "entity_data": {
                        "slug": "pushpa-kamal-dahal",
                        "names": [
                            {
                                "kind": "PRIMARY",
                                "en": {"full": "Pushpa Kamal Dahal"},
                                "ne": {"full": "पुष्पकमल दाहाल"},
                            }
                        ],
                    },
                    "author_id": "jawafdehi-queue",
                },
            ),
            (
                "UPDATE_ENTITY",
                {
                    "entity_id": "entity:person/sher-bahadur-deuba",
                    "updates": {"tags": ["politician", "prime-minister"]},
                    "author_id": "jawafdehi-queue",
                },
            ),
        ],
    )
    async def test_submit_success_for_supported_actions(
        self, monkeypatch, action, payload
    ):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")
        monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", "https://jawafdehi.example")

        calls = []

        async def fake_post(url, json, headers, timeout):
            calls.append(
                {
                    "url": url,
                    "json": json,
                    "headers": headers,
                    "timeout": timeout,
                }
            )
            return httpx.Response(
                201,
                json={
                    "id": 42,
                    "action": json["action"],
                    "status": "PENDING",
                    "submitted_by": "caseworker",
                },
            )

        monkeypatch.setattr(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            lambda: _FakeAsyncClient(fake_post),
        )

        result = await self.tool.execute(
            {
                "action": action,
                "payload": payload,
                "change_description": "Queue NES change",
            }
        )

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed["id"] == 42
        assert parsed["action"] == action
        assert parsed["status"] == "PENDING"

        assert calls == [
            {
                "url": "https://jawafdehi.example/api/submit_nes_change",
                "json": {
                    "action": action,
                    "payload": payload,
                    "change_description": "Queue NES change",
                },
                "headers": {"Authorization": "Token secret-token"},
                "timeout": 30.0,
            }
        ]

    @pytest.mark.asyncio
    async def test_auto_approve_is_forwarded(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")

        captured = {}

        async def fake_post(url, json, headers, timeout):
            captured.update({"url": url, "json": json, "headers": headers})
            return httpx.Response(201, json={"id": 7, "action": "ADD_NAME"})

        monkeypatch.setattr(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            lambda: _FakeAsyncClient(fake_post),
        )

        await self.tool.execute(
            {
                "action": "ADD_NAME",
                "payload": {
                    "entity_id": "entity:person/sher-bahadur-deuba",
                    "name": {"kind": "ALIAS", "en": {"full": "S. B. Deuba"}},
                    "author_id": "jawafdehi-queue",
                },
                "change_description": "Queue NES change",
                "auto_approve": True,
            }
        )

        assert captured["url"] == "https://portal.jawafdehi.org/api/submit_nes_change"
        assert captured["headers"] == {"Authorization": "Token secret-token"}
        assert captured["json"]["auto_approve"] is True

    @pytest.mark.asyncio
    async def test_validation_error_response(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")

        async def fake_post(url, json, headers, timeout):
            return httpx.Response(
                400,
                json={"payload": [{"loc": ["name"], "msg": "Field required"}]},
            )

        monkeypatch.setattr(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            lambda: _FakeAsyncClient(fake_post),
        )

        result = await self.tool.execute(
            {
                "action": "ADD_NAME",
                "payload": {"entity_id": "entity:person/test"},
                "change_description": "Queue NES change",
            }
        )

        assert "HTTP 400" in result[0].text
        assert "Field required" in result[0].text

    @pytest.mark.asyncio
    async def test_auto_approve_permission_error(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")

        async def fake_post(url, json, headers, timeout):
            return httpx.Response(
                403,
                json={
                    "auto_approve": (
                        "Only Admin and Moderator users can set auto_approve=true."
                    )
                },
            )

        monkeypatch.setattr(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            lambda: _FakeAsyncClient(fake_post),
        )

        result = await self.tool.execute(
            {
                "action": "ADD_NAME",
                "payload": {"entity_id": "entity:person/test"},
                "change_description": "Queue NES change",
                "auto_approve": True,
            }
        )

        assert "HTTP 403" in result[0].text
        assert "auto_approve=true" in result[0].text

    @pytest.mark.asyncio
    async def test_timeout_error(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")

        async def fake_post(url, json, headers, timeout):
            raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            lambda: _FakeAsyncClient(fake_post),
        )

        result = await self.tool.execute(
            {
                "action": "ADD_NAME",
                "payload": {"entity_id": "entity:person/test"},
                "change_description": "Queue NES change",
            }
        )

        assert "timed out" in result[0].text.lower()
