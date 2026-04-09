"""Tests for Jawafdehi MCP create/patch write tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from jawafdehi_mcp.server import TOOL_MAP
from jawafdehi_mcp.tools.jawafdehi_cases import (
    CreateJawafdehiCaseTool,
    CreateJawafEntityTool,
    PatchJawafdehiCaseTool,
    UploadDocumentSourceTool,
)


def _mock_async_client(response):
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.patch = AsyncMock(return_value=response)

    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = client
    context_manager.__aexit__.return_value = False
    return context_manager, client


class TestCreateJawafdehiCaseTool:
    def setup_method(self):
        self.tool = CreateJawafdehiCaseTool()

    def test_tool_metadata(self):
        assert self.tool.name == "create_jawafdehi_case"
        assert "draft Jawafdehi case" in self.tool.description
        assert self.tool.input_schema["required"] == ["title", "case_type"]

    @pytest.mark.asyncio
    async def test_requires_token(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)

        result = await self.tool.execute({"title": "Case", "case_type": "CORRUPTION"})

        assert "JAWAFDEHI_API_TOKEN" in result[0].text

    @pytest.mark.asyncio
    async def test_create_success(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        response = MagicMock()
        response.is_success = True
        response.json.return_value = {"id": 7, "title": "Road contract case"}

        context_manager, client = _mock_async_client(response)

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute(
                {
                    "title": "Road contract case",
                    "case_type": "CORRUPTION",
                    "short_description": "Tender irregularities",
                }
            )

        payload = json.loads(result[0].text)
        assert payload["id"] == 7
        client.post.assert_awaited_once()
        _, kwargs = client.post.await_args
        assert kwargs["headers"]["Authorization"] == "Token test-token"
        assert kwargs["json"]["title"] == "Road contract case"
        assert kwargs["json"]["case_type"] == "CORRUPTION"
        assert kwargs["json"]["short_description"] == "Tender irregularities"

    @pytest.mark.asyncio
    async def test_create_422_passthrough(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        response = MagicMock()
        response.is_success = False
        response.status_code = 422
        response.json.return_value = {
            "title": ["Ensure this field has no more than 200 characters."]
        }

        context_manager, _ = _mock_async_client(response)

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute(
                {"title": "x" * 201, "case_type": "CORRUPTION"}
            )

        payload = json.loads(result[0].text)
        assert payload["status_code"] == 422
        assert payload["details"]["title"] == [
            "Ensure this field has no more than 200 characters."
        ]

    @pytest.mark.asyncio
    async def test_create_403_passthrough(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        response = MagicMock()
        response.is_success = False
        response.status_code = 403
        response.json.return_value = {"detail": "Permission denied."}

        context_manager, _ = _mock_async_client(response)

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute(
                {"title": "Case", "case_type": "CORRUPTION"}
            )

        payload = json.loads(result[0].text)
        assert payload["status_code"] == 403
        assert payload["details"]["detail"] == "Permission denied."


class TestPatchJawafdehiCaseTool:
    def setup_method(self):
        self.tool = PatchJawafdehiCaseTool()

    def test_tool_metadata(self):
        assert self.tool.name == "patch_jawafdehi_case"
        assert "RFC 6902" in self.tool.description
        assert self.tool.input_schema["required"] == ["case_id", "operations"]

    @pytest.mark.asyncio
    async def test_requires_token(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)

        result = await self.tool.execute(
            {
                "case_id": 3,
                "operations": [{"op": "replace", "path": "/title", "value": "Updated"}],
            }
        )

        assert "JAWAFDEHI_API_TOKEN" in result[0].text

    @pytest.mark.asyncio
    async def test_requires_operations_list(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")

        result = await self.tool.execute({"case_id": 3, "operations": {}})

        assert "operations must be a JSON Patch array" in result[0].text

    @pytest.mark.asyncio
    async def test_patch_success(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        response = MagicMock()
        response.is_success = True
        response.json.return_value = {"id": 3, "title": "Updated title"}

        context_manager, client = _mock_async_client(response)

        ops = [{"op": "replace", "path": "/title", "value": "Updated title"}]
        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute({"case_id": 3, "operations": ops})

        payload = json.loads(result[0].text)
        assert payload["title"] == "Updated title"
        client.patch.assert_awaited_once()
        _, kwargs = client.patch.await_args
        assert kwargs["headers"]["Authorization"] == "Token test-token"
        assert kwargs["json"] == ops

    @pytest.mark.asyncio
    async def test_patch_404_passthrough(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        response = MagicMock()
        response.is_success = False
        response.status_code = 404
        response.json.return_value = {"detail": "Not found."}

        context_manager, _ = _mock_async_client(response)

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute(
                {
                    "case_id": 999,
                    "operations": [{"op": "replace", "path": "/title", "value": "x"}],
                }
            )

        payload = json.loads(result[0].text)
        assert payload["status_code"] == 404
        assert payload["details"]["detail"] == "Not found."

    @pytest.mark.asyncio
    async def test_patch_422_passthrough(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        response = MagicMock()
        response.is_success = False
        response.status_code = 422
        response.json.return_value = {
            "detail": "Patching path '/state' is not allowed."
        }

        context_manager, _ = _mock_async_client(response)

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute(
                {
                    "case_id": 3,
                    "operations": [
                        {
                            "op": "replace",
                            "path": "/state",
                            "value": "PUBLISHED",
                        }
                    ],
                }
            )

        payload = json.loads(result[0].text)
        assert payload["status_code"] == 422
        assert "/state" in payload["details"]["detail"]


class TestCreateJawafEntityTool:
    def setup_method(self):
        self.tool = CreateJawafEntityTool()

    def test_tool_metadata(self):
        assert self.tool.name == "create_jawaf_entity"
        assert "JawafEntity" in self.tool.description
        assert self.tool.input_schema["anyOf"] == [
            {"required": ["nes_id"]},
            {"required": ["display_name"]},
        ]

    @pytest.mark.asyncio
    async def test_requires_token(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)

        result = await self.tool.execute({"display_name": "Nepal Rastra Bank"})

        assert "JAWAFDEHI_API_TOKEN" in result[0].text

    @pytest.mark.asyncio
    async def test_create_success(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")

        response = MagicMock()
        response.status_code = 201
        response.json.return_value = {
            "id": 11,
            "nes_id": "entity:organization/ciaa",
            "display_name": "CIAA",
        }

        context_manager, client = _mock_async_client(response)

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute(
                {
                    "nes_id": "entity:organization/ciaa",
                    "display_name": "CIAA",
                }
            )

        payload = json.loads(result[0].text)
        assert payload["id"] == 11
        client.post.assert_awaited_once()
        _, kwargs = client.post.await_args
        assert kwargs["headers"]["Authorization"] == "Token test-token"
        assert kwargs["json"]["nes_id"] == "entity:organization/ciaa"

    @pytest.mark.asyncio
    async def test_create_error_passthrough(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")

        response = MagicMock()
        response.status_code = 422
        response.json.return_value = {
            "nes_id": ["jawaf entity with this nes id already exists."]
        }

        context_manager, _ = _mock_async_client(response)

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute(
                {"nes_id": "entity:person/sher-bahadur-deuba"}
            )

        payload = json.loads(result[0].text)
        assert payload["status_code"] == 422
        assert "already exists" in payload["details"]["nes_id"][0]


class TestUploadDocumentSourceTool:
    def setup_method(self):
        self.tool = UploadDocumentSourceTool()

    def test_tool_metadata(self):
        assert self.tool.name == "upload_document_source"
        assert "DocumentSource" in self.tool.description
        assert self.tool.input_schema["required"] == ["title", "file_path"]

    @pytest.mark.asyncio
    async def test_requires_token(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)

        result = await self.tool.execute(
            {
                "title": "Evidence",
                "file_path": "/tmp/evidence.pdf",
            }
        )

        assert "JAWAFDEHI_API_TOKEN" in result[0].text

    @pytest.mark.asyncio
    async def test_requires_fields(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")

        result = await self.tool.execute({"title": "Missing file_path"})

        assert "Missing required arguments" in result[0].text
        assert "file_path" in result[0].text

    @pytest.mark.asyncio
    async def test_invalid_file_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")

        result = await self.tool.execute(
            {
                "title": "Bad path",
                "file_path": "/nonexistent/path/broken.pdf",
            }
        )

        assert "Could not read file" in result[0].text

    @pytest.mark.asyncio
    async def test_upload_success(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")

        pdf_file = tmp_path / "audit.pdf"
        pdf_file.write_bytes(b"pdf-content")

        response = MagicMock()
        response.status_code = 201
        response.json.return_value = {
            "id": 91,
            "source_id": "source:20820405:abc123ef",
            "title": "Audit Report",
        }

        context_manager, client = _mock_async_client(response)

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute(
                {
                    "title": "Audit Report",
                    "description": "Budget variance report",
                    "source_type": "OTHER_VISUAL",
                    "file_path": str(pdf_file),
                }
            )

        payload = json.loads(result[0].text)
        assert payload["id"] == 91
        client.post.assert_awaited_once()
        _, kwargs = client.post.await_args
        assert kwargs["headers"]["Authorization"] == "Token test-token"
        assert kwargs["data"]["title"] == "Audit Report"
        assert kwargs["data"]["description"] == "Budget variance report"
        assert kwargs["data"]["source_type"] == "OTHER_VISUAL"
        assert kwargs["files"]["uploaded_file"][0] == "audit.pdf"
        assert kwargs["files"]["uploaded_file"][1] == b"pdf-content"

    @pytest.mark.asyncio
    async def test_upload_error_passthrough(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")

        pdf_file = tmp_path / "big.pdf"
        pdf_file.write_bytes(b"small-content")

        response = MagicMock()
        response.status_code = 413
        response.json.return_value = {"detail": "File too large."}

        context_manager, _ = _mock_async_client(response)

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            return_value=context_manager,
        ):
            result = await self.tool.execute(
                {
                    "title": "Oversize",
                    "file_path": str(pdf_file),
                }
            )

        payload = json.loads(result[0].text)
        assert payload["status_code"] == 413
        assert payload["details"]["detail"] == "File too large."

    @pytest.mark.asyncio
    async def test_upload_http_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")

        pdf_file = tmp_path / "evidence.pdf"
        pdf_file.write_bytes(b"file-content")

        with patch(
            "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
            side_effect=httpx.HTTPError("network down"),
        ):
            result = await self.tool.execute(
                {
                    "title": "Network issue",
                    "file_path": str(pdf_file),
                }
            )

        assert "Unexpected error uploading document" in result[0].text


def test_new_tools_registered_in_server_tool_map():
    assert "create_jawaf_entity" in TOOL_MAP
    assert "upload_document_source" in TOOL_MAP
