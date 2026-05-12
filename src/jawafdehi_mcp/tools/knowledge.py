"""Public knowledge index tools for Jawafdehi agentic retrieval."""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

import httpx
from mcp.types import TextContent

from .base import BaseTool


def _get_jawafdehi_base_url() -> str:
    return os.getenv("JAWAFDEHI_API_BASE_URL", "https://portal.jawafdehi.org").rstrip(
        "/"
    )


def _json_text_content(payload: Any) -> list[TextContent]:
    return [
        TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))
    ]


def _error_text_content(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=message)]


class SearchJawafdehiKnowledgeTool(BaseTool):
    """Search the public Jawafdehi knowledge index."""

    @property
    def name(self) -> str:
        return "search_jawafdehi_knowledge"

    @property
    def description(self) -> str:
        return (
            "Search public Jawafdehi knowledgebase chunks such as annual reports, "
            "methodology docs, FAQs, and indexed public source documents. Use this "
            "before converting full PDFs when the user asks report, year, statistic, "
            "or knowledgebase questions."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query preserving years, names, and Nepali terms.",
                },
                "collection": {
                    "type": "string",
                    "description": "Optional public collection slug to restrict search.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum chunks to return, capped by the API.",
                    "default": 5,
                },
                "year": {
                    "type": "string",
                    "description": "Optional AD or BS year mentioned by the user.",
                },
                "source_type": {
                    "type": "string",
                    "description": "Optional source type such as annual_report or faq.",
                },
            },
            "required": ["query"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return _error_text_content("Error: query is required")

        query_params = {"query": query}
        for key in ("collection", "max_results", "year", "source_type"):
            value = arguments.get(key)
            if value not in (None, ""):
                query_params[key] = str(value)

        url = (
            f"{_get_jawafdehi_base_url()}/api/knowledge/public-search/?"
            f"{urllib.parse.urlencode(query_params)}"
        )
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers={}, timeout=30.0)
                response.raise_for_status()
                return _json_text_content(response.json())
        except httpx.HTTPError as exc:
            return _error_text_content(
                f"Error searching Jawafdehi public knowledge API: {exc}"
            )
        except Exception as exc:
            return _error_text_content(f"Unexpected error: {exc}")


class GetJawafdehiKnowledgeSourceTool(BaseTool):
    """Fetch public metadata for one indexed knowledge source."""

    @property
    def name(self) -> str:
        return "get_jawafdehi_knowledge_source"

    @property
    def description(self) -> str:
        return (
            "Fetch public metadata for an indexed Jawafdehi knowledge source, "
            "including source URL, citation metadata, and page/TOC hints."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_id": {
                    "type": ["integer", "string"],
                    "description": "Public knowledge source id from search results.",
                }
            },
            "required": ["source_id"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        source_id = str(arguments.get("source_id") or "").strip()
        if not source_id:
            return _error_text_content("Error: source_id is required")
        if not source_id.isdigit():
            return _error_text_content("Error: source_id must be a numeric id")

        url = f"{_get_jawafdehi_base_url()}/api/knowledge/public-sources/{source_id}/"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers={}, timeout=30.0)
                if response.status_code == 404:
                    return _error_text_content(
                        f"Public knowledge source {source_id} not found."
                    )
                response.raise_for_status()
                return _json_text_content(response.json())
        except httpx.HTTPError as exc:
            return _error_text_content(
                f"Error fetching Jawafdehi public knowledge source: {exc}"
            )
        except Exception as exc:
            return _error_text_content(f"Unexpected error: {exc}")
