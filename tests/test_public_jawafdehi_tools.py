"""Tests for the public-chat MCP read-tool surface."""

import json

import httpx
import pytest

from jawafdehi_mcp.server import TOOL_MAP
from jawafdehi_mcp.tools.jawafdehi_cases import (
    GetJawafdehiCaseTool,
    SearchJawafdehiCasesTool,
)
from jawafdehi_mcp.tools.knowledge import (
    GetJawafdehiKnowledgeSourceTool,
    SearchJawafdehiKnowledgeTool,
)


class _FakeAsyncClient:
    def __init__(self, get_impl):
        self._get_impl = get_impl

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers, timeout):
        return await self._get_impl(url, headers, timeout)


def _text_json(result):
    return json.loads(result[0].text)


def _response(url, status_code=200, json_payload=None):
    return httpx.Response(
        status_code,
        json=json_payload,
        request=httpx.Request("GET", url),
    )


def test_public_chat_uses_generic_read_tools():
    assert "search_jawafdehi_cases" in TOOL_MAP
    assert "get_jawafdehi_case" in TOOL_MAP
    assert "search_jawafdehi_knowledge" in TOOL_MAP
    assert "get_jawafdehi_knowledge_source" in TOOL_MAP
    assert "convert_to_markdown" in TOOL_MAP


@pytest.mark.asyncio
async def test_generic_case_search_works_without_token_and_case_type(monkeypatch):
    monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)
    monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", "https://jawafdehi.example")
    calls = []

    async def fake_get(url, headers, timeout):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return _response(
            url,
            json_payload={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [{"id": 7, "title": "Published procurement case"}],
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await SearchJawafdehiCasesTool().execute(
        {"search": "procurement", "case_type": "PROMISES", "page": 2}
    )
    parsed = _text_json(result)

    assert calls[0]["headers"] == {}
    assert calls[0]["url"].startswith("https://jawafdehi.example/api/cases/?")
    assert "search=procurement" in calls[0]["url"]
    assert "case_type=PROMISES" in calls[0]["url"]
    assert "page=2" in calls[0]["url"]
    assert parsed["count"] == 1
    assert parsed["results"][0]["title"] == "Published procurement case"


@pytest.mark.asyncio
async def test_generic_case_search_sends_token_only_when_configured(monkeypatch):
    monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")
    calls = []

    async def fake_get(url, headers, timeout):
        calls.append({"headers": headers})
        return _response(url, json_payload={"count": 0, "results": []})

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    await SearchJawafdehiCasesTool().execute({})

    assert calls[0]["headers"] == {"Authorization": "Token secret-token"}


@pytest.mark.asyncio
async def test_generic_get_case_accepts_slug_and_fetch_sources(monkeypatch):
    monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)
    monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", "https://jawafdehi.example")
    calls = []

    async def fake_get(url, headers, timeout):
        calls.append({"url": url, "headers": headers})
        if url.endswith("/api/cases/example-case/"):
            return _response(
                url,
                json_payload={
                    "id": 7,
                    "slug": "example-case",
                    "title": "Example case",
                    "evidence": [{"source_id": 42}],
                },
            )
        return _response(
            url,
            json_payload={"id": 42, "title": "Evidence source"},
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await GetJawafdehiCaseTool().execute(
        {"case_id": "example-case", "fetch_sources": True}
    )
    parsed = _text_json(result)

    assert calls[0]["url"] == "https://jawafdehi.example/api/cases/example-case/"
    assert calls[0]["headers"] == {}
    assert calls[1]["url"] == "https://jawafdehi.example/api/sources/42/"
    assert parsed["_resolved_sources"][0]["title"] == "Evidence source"


@pytest.mark.asyncio
async def test_generic_get_case_returns_public_safe_payload_even_with_token(
    monkeypatch,
):
    monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")
    monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", "https://jawafdehi.example")

    async def fake_get(url, headers, timeout):
        return _response(
            url,
            json_payload={
                "id": 7,
                "slug": "published-case",
                "state": "PUBLISHED",
                "title": "Published case",
                "storage_path": "/private/source.pdf",
                "internal_notes": "do not expose",
                "evidence": [
                    {
                        "source_id": 42,
                        "description": "Public source",
                        "source": {
                            "id": 42,
                            "title": "Evidence source",
                            "url": [
                                "https://example.org/public.pdf",
                                "https://jawafdehi.example/media/private.pdf",
                            ],
                            "storage_path": "/private/path.pdf",
                        },
                    }
                ],
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await GetJawafdehiCaseTool().execute(
        {"case_id": "published-case", "fetch_sources": True}
    )
    parsed = _text_json(result)

    assert parsed["title"] == "Published case"
    assert "storage_path" not in parsed
    assert "internal_notes" not in parsed
    assert parsed["evidence"][0]["source"]["url"] == ["https://example.org/public.pdf"]


@pytest.mark.asyncio
async def test_generic_get_case_hides_unpublished_token_response(monkeypatch):
    monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")

    async def fake_get(url, headers, timeout):
        return _response(
            url,
            json_payload={
                "id": 7,
                "state": "DRAFT",
                "title": "Private draft",
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await GetJawafdehiCaseTool().execute({"case_id": 7})

    assert result[0].text == "Case 7 not found."


@pytest.mark.asyncio
async def test_knowledge_search_is_public_and_returns_source_metadata(monkeypatch):
    monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")
    monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", "https://jawafdehi.example")
    calls = []

    async def fake_get(url, headers, timeout):
        calls.append({"url": url, "headers": headers})
        return _response(
            url,
            json_payload={
                "query": "2079 cases",
                "results": [
                    {
                        "chunk_id": "c1",
                        "source_id": 3,
                        "source_title": "Annual Report 2079",
                        "source_url": "https://example.org/report.pdf",
                        "metadata": {"toc_pages": "3-5"},
                    }
                ],
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.knowledge.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await SearchJawafdehiKnowledgeTool().execute(
        {"query": "2079 cases", "year": "2079", "max_results": 4}
    )
    parsed = _text_json(result)

    assert calls[0]["headers"] == {}
    assert "query=2079+cases" in calls[0]["url"]
    assert "year=2079" in calls[0]["url"]
    assert "max_results=4" in calls[0]["url"]
    assert parsed["results"][0]["metadata"]["toc_pages"] == "3-5"


@pytest.mark.asyncio
async def test_get_knowledge_source_uses_public_endpoint(monkeypatch):
    monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", "https://jawafdehi.example")
    calls = []

    async def fake_get(url, headers, timeout):
        calls.append({"url": url, "headers": headers})
        return _response(
            url,
            json_payload={
                "source_id": 3,
                "title": "Annual Report 2079",
                "source_url": "https://example.org/report.pdf",
                "metadata": {"toc_pages": "3-5"},
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.knowledge.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await GetJawafdehiKnowledgeSourceTool().execute({"source_id": 3})
    parsed = _text_json(result)

    assert (
        calls[0]["url"] == "https://jawafdehi.example/api/knowledge/public-sources/3/"
    )
    assert calls[0]["headers"] == {}
    assert parsed["metadata"]["toc_pages"] == "3-5"
