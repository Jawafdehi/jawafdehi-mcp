import json
import os
import urllib.parse
from typing import Any

import httpx
import structlog
from mcp.types import TextContent

from ..request_context import get_forwarded_headers
from .base import BaseTool

logger = structlog.get_logger()


def _get_nes_base_url() -> str:
    """Base URL for entity reads.

    Post-unification NES entities are served by the ONE Jawafdehi host under a
    bare ``/api/entities`` (the standalone ``nes.jawafdehi.org`` service + its
    ``/api/nes`` prefix were retired in the 2026-07 hard cut). Honour the legacy
    ``NES_API_BASE_URL`` only if explicitly set, else the unified host.
    """
    base = os.getenv("NES_API_BASE_URL") or os.getenv(
        "JAWAFDEHI_API_BASE_URL", "https://portal.jawafdehi.org"
    )
    return base.rstrip("/")


def _get_nes_headers() -> dict[str, str]:
    """Auth headers for entity reads.

    Forward the caller's OIDC bearer when present (HTTP transport); otherwise
    fall back to the service token as ``Bearer`` (stdio/dev). Mirrors the write
    tools so token-only flows keep working once the unified API requires auth.
    """
    headers = get_forwarded_headers()
    if "Authorization" not in headers:
        token = os.getenv("JAWAFDEHI_API_TOKEN", "").strip()
        if token:
            headers = {"Authorization": f"Bearer {token}"}
    return headers


def _build_text_response(payload: Any) -> list[TextContent]:
    return [
        TextContent(
            type="text",
            text=json.dumps(payload, indent=2, ensure_ascii=False),
        )
    ]


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or response.reason_phrase

    if isinstance(payload, dict):
        return json.dumps(payload, indent=2, ensure_ascii=False)

    return str(payload)


class SearchNESEntitiesTool(BaseTool):
    """Tool for searching NES entities."""

    @property
    def name(self) -> str:
        return "search_nes_entities"

    @property
    def description(self) -> str:
        return "Search for Nepal Entity Service (NES) entities using various filters."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "description": "Filter by primary entity type (e.g., person, organization, location).",
                },
                "query": {
                    "type": "string",
                    "description": "Text query to search in entity names (e.g., 'poudel').",
                },
                "sub_type": {
                    "type": "string",
                    "description": "Filter by entity subtype (e.g., 'political_party').",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags to filter by (uses AND logic, e.g., 'politician,senior-leader').",
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of results to skip (default is 0).",
                    "default": 0,
                },
            },
            "required": ["entity_type"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        entity_type = arguments.get("entity_type")
        if not entity_type:
            return [TextContent(type="text", text="Error: entity_type is required.")]

        query_params = {
            "entity_type": entity_type,
            "limit": "10",
        }

        if arguments.get("query"):
            query_params["query"] = arguments["query"]
        if arguments.get("sub_type"):
            query_params["sub_type"] = arguments["sub_type"]
        if arguments.get("tags"):
            query_params["tags"] = arguments["tags"]
        if "offset" in arguments:
            query_params["offset"] = str(arguments["offset"])

        query_string = urllib.parse.urlencode(query_params)
        url = f"{_get_nes_base_url()}/api/entities?{query_string}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=_get_nes_headers(), timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                return [
                    TextContent(
                        type="text", text=json.dumps(data, indent=2, ensure_ascii=False)
                    )
                ]
        except httpx.HTTPError as e:
            logger.error("nes_search_http_error", error=str(e))
            return [
                TextContent(
                    type="text",
                    text=f"Error accessing NES API: {str(e)}\n\nConsider narrowing your search or checking parameters.",
                )
            ]
        except Exception as e:
            logger.exception("nes_search_unexpected_error", error=str(e))
            return [TextContent(type="text", text=f"Unexpected error: {str(e)}")]


class GetNESEntitiesTool(BaseTool):
    """Tool for retrieving detailed info on one or more NES entities by ID."""

    @property
    def name(self) -> str:
        return "get_nes_entities"

    @property
    def description(self) -> str:
        return "Retrieve the complete profiles of one or more NES entities by their unique IDs."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of unique entity identifiers to retrieve (e.g., ['entity:person/ram-chandra-poudel']).",
                },
            },
            "required": ["entity_ids"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        entity_ids = arguments.get("entity_ids")
        if not entity_ids or not isinstance(entity_ids, list):
            return [
                TextContent(
                    type="text",
                    text="Error: entity_ids must be a non-empty list of strings.",
                )
            ]

        all_entities = []
        errors = []

        chunk_size = 25
        base_url = _get_nes_base_url()

        async with httpx.AsyncClient() as client:
            for i in range(0, len(entity_ids), chunk_size):
                chunk = entity_ids[i : i + chunk_size]
                ids_str = ",".join(chunk)
                url = f"{base_url}/api/entities?ids={urllib.parse.quote(ids_str)}"

                try:
                    response = await client.get(
                        url, headers=_get_nes_headers(), timeout=30.0
                    )
                    response.raise_for_status()
                    data = response.json()

                    if "entities" in data:
                        all_entities.extend(data["entities"])
                    else:
                        errors.append(
                            f"Unexpected response format for chunk {i//chunk_size + 1}"
                        )

                except httpx.HTTPError as e:
                    logger.error(
                        "nes_get_entities_http_error",
                        chunk=i // chunk_size + 1,
                        error=str(e),
                    )
                    errors.append(f"HTTP Error for chunk {i//chunk_size + 1}: {str(e)}")
                except Exception as e:
                    logger.exception(
                        "nes_get_entities_unexpected_error",
                        chunk=i // chunk_size + 1,
                        error=str(e),
                    )
                    errors.append(
                        f"Unexpected error for chunk {i//chunk_size + 1}: {str(e)}"
                    )

        result = {
            "entities": all_entities,
            "total_requested": len(entity_ids),
            "total_found": len(all_entities),
        }

        if errors:
            result["errors"] = errors

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]


class GetNESTagsTool(BaseTool):
    """Tool for fetching the complete list of unique entity tags."""

    @property
    def name(self) -> str:
        return "get_nes_tags"

    @property
    def description(self) -> str:
        return "Fetch the complete list of all unique entity tag values present in the NES database."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        url = f"{_get_nes_base_url()}/api/entities/tags"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=_get_nes_headers(), timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                return [
                    TextContent(
                        type="text", text=json.dumps(data, indent=2, ensure_ascii=False)
                    )
                ]
        except httpx.HTTPError as e:
            logger.error("nes_tags_http_error", error=str(e))
            return [
                TextContent(type="text", text=f"Error accessing NES Tags API: {str(e)}")
            ]
        except Exception as e:
            logger.exception("nes_tags_unexpected_error", error=str(e))
            return [TextContent(type="text", text=f"Unexpected error: {str(e)}")]


class GetNESEntityPrefixesTool(BaseTool):
    """Tool for fetching available NES entity prefixes."""

    @property
    def name(self) -> str:
        return "get_nes_entity_prefixes"

    @property
    def description(self) -> str:
        return "Fetch the available NES entity prefixes and related metadata."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        url = f"{_get_nes_base_url()}/api/entity_prefixes"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=_get_nes_headers(), timeout=30.0
                )

            if response.status_code == 200:
                return _build_text_response(response.json())

            error_message = _extract_error_message(response)
            return [
                TextContent(
                    type="text",
                    text=(
                        "Error fetching NES entity prefixes: "
                        f"HTTP {response.status_code}\n\n{error_message}"
                    ),
                )
            ]
        except httpx.TimeoutException:
            logger.warning("nes_prefixes_timeout")
            return [
                TextContent(
                    type="text",
                    text="Error fetching NES entity prefixes: request timed out.",
                )
            ]
        except httpx.HTTPError as exc:
            logger.error("nes_prefixes_http_error", error=str(exc))
            return [
                TextContent(
                    type="text",
                    text=f"Error fetching NES entity prefixes: {str(exc)}",
                )
            ]
        except Exception as exc:
            logger.exception("nes_prefixes_unexpected_error", error=str(exc))
            return [TextContent(type="text", text=f"Unexpected error: {str(exc)}")]
