"""Tests for public-safe Jawafdehi MCP tools."""

import json

import httpx
import pytest

from jawafdehi_mcp.server import TOOL_MAP
from jawafdehi_mcp.tools.jawafdehi_cases import (
    PublicCountPublishedCasesTool,
    PublicGetPublishedCaseTool,
    PublicSearchJawafEntitiesTool,
    PublicSearchPublishedCasesTool,
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


def _published_case(**overrides):
    payload = {
        "id": 7,
        "case_id": "case-7",
        "slug": "published-case",
        "case_type": "CORRUPTION",
        "state": "PUBLISHED",
        "title": "Published case",
        "short_description": "Public short description",
        "description": "Public description",
        "notes": "private notes",
        "contributors": ["private-user"],
        "versionInfo": {"moderation": "private"},
        "missing_details": ["private"],
    }
    payload.update(overrides)
    return payload


def test_public_tools_are_registered():
    assert "public_count_published_cases" in TOOL_MAP
    assert "public_search_published_cases" in TOOL_MAP
    assert "public_get_published_case" in TOOL_MAP
    assert "public_search_jawaf_entities" in TOOL_MAP


@pytest.mark.asyncio
async def test_public_count_returns_published_only_contract(monkeypatch):
    monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")
    monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", "https://jawafdehi.example")
    calls = []

    async def fake_get(url, headers, timeout):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return _response(
            url,
            json_payload={
                "count": 12,
                "results": [_published_case()],
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await PublicCountPublishedCasesTool().execute({"search": "procurement"})
    parsed = _text_json(result)

    assert calls[0]["headers"] == {}
    assert "search=procurement" in calls[0]["url"]
    assert parsed["published_count"] == 12
    assert parsed["count_scope"] == "published_only"
    assert parsed["filters"] == {"search": "procurement"}
    assert parsed["results"][0]["state"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_public_count_rejects_non_published_rows(monkeypatch):
    async def fake_get(url, headers, timeout):
        return _response(
            url,
            json_payload={
                "count": 2,
                "results": [
                    _published_case(),
                    _published_case(id=8, state="IN_REVIEW"),
                ],
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await PublicCountPublishedCasesTool().execute({"search": "procurement"})

    assert result[0].text == "Public count API returned non-published case data."


@pytest.mark.asyncio
async def test_public_search_uses_no_auth_and_filters_non_published(monkeypatch):
    monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "secret-token")
    monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", "https://jawafdehi.example")
    calls = []

    async def fake_get(url, headers, timeout):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return _response(
            url,
            json_payload={
                "count": 2,
                "results": [
                    _published_case(),
                    _published_case(id=8, state="IN_REVIEW", title="Private case"),
                ],
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await PublicSearchPublishedCasesTool().execute({"search": "procurement"})
    parsed = _text_json(result)

    assert calls[0]["headers"] == {}
    assert calls[0]["url"].startswith("https://jawafdehi.example/api/cases/?")
    assert "case_type=" not in calls[0]["url"]
    assert parsed["count"] == 1
    assert len(parsed["results"]) == 1
    assert parsed["results"][0]["state"] == "PUBLISHED"
    assert "notes" not in parsed["results"][0]
    assert "contributors" not in parsed["results"][0]
    assert "versionInfo" not in parsed["results"][0]


@pytest.mark.asyncio
async def test_public_search_accepts_optional_case_type_filter(monkeypatch):
    monkeypatch.setenv("JAWAFDEHI_API_BASE_URL", "https://jawafdehi.example")
    calls = []

    async def fake_get(url, headers, timeout):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return _response(
            url,
            json_payload={
                "count": 1,
                "results": [_published_case(case_type="PROMISES")],
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await PublicSearchPublishedCasesTool().execute({"case_type": "PROMISES"})
    parsed = _text_json(result)

    assert "case_type=PROMISES" in calls[0]["url"]
    assert parsed["results"][0]["case_type"] == "PROMISES"


@pytest.mark.asyncio
async def test_public_get_treats_non_published_as_not_found(monkeypatch):
    async def fake_get(url, headers, timeout):
        return _response(url, json_payload=_published_case(state="DRAFT"))

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await PublicGetPublishedCaseTool().execute({"case_id": 7})

    assert result[0].text == "Case 7 not found."


@pytest.mark.asyncio
async def test_public_get_strips_private_fields_and_private_source_urls(monkeypatch):
    async def fake_get(url, headers, timeout):
        return _response(
            url,
            json_payload=_published_case(
                evidence=[
                    {
                        "source_id": "source-1",
                        "description": "Public evidence description",
                        "notes": "private evidence note",
                        "source": {
                            "id": 99,
                            "source_id": "doc-99",
                            "title": "Public document",
                            "description": "Public document description",
                            "source_type": "pdf",
                            "url": [
                                "https://safe.example/doc.pdf",
                                "https://portal.jawafdehi.org/media/private.pdf",
                                "ftp://unsafe.example/doc.pdf",
                            ],
                        },
                    }
                ],
            ),
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await PublicGetPublishedCaseTool().execute(
        {"case_id": 7, "fetch_sources": True}
    )
    parsed = _text_json(result)

    assert "notes" not in parsed
    assert "contributors" not in parsed
    assert "versionInfo" not in parsed
    assert parsed["evidence"][0]["source"]["url"] == ["https://safe.example/doc.pdf"]
    assert "notes" not in parsed["evidence"][0]


@pytest.mark.asyncio
async def test_public_entity_search_filters_non_published_related_cases(monkeypatch):
    async def fake_get(url, headers, timeout):
        return _response(
            url,
            json_payload={
                "count": 1,
                "results": [
                    {
                        "id": 1,
                        "nes_id": "entity:person/example",
                        "display_name": "Example Person",
                        "notes": "private notes",
                        "related_cases": [
                            {"case_id": "case-1", "state": "PUBLISHED"},
                            {"case_id": "case-2", "state": "IN_REVIEW"},
                        ],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        "jawafdehi_mcp.tools.jawafdehi_cases.httpx.AsyncClient",
        lambda: _FakeAsyncClient(fake_get),
    )

    result = await PublicSearchJawafEntitiesTool().execute({"search": "example"})
    parsed = _text_json(result)

    assert parsed["results"][0]["related_cases"] == [
        {"case_id": "case-1", "relation_type": None}
    ]
    assert "notes" not in parsed["results"][0]
