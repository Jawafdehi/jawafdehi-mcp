import json
import os
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
from mcp.types import TextContent

from .base import BaseTool


def _get_jawafdehi_base_url() -> str:
    return os.getenv("JAWAFDEHI_API_BASE_URL", "https://portal.jawafdehi.org").rstrip(
        "/"
    )


def _get_jawafdehi_api_token() -> str | None:
    token = os.getenv("JAWAFDEHI_API_TOKEN", "").strip()
    return token or None


def _get_auth_headers() -> dict[str, str]:
    """Return Authorization header dict if a token is configured, else empty dict."""
    token = _get_jawafdehi_api_token()
    if token:
        return {"Authorization": f"Token {token}"}
    return {}


def _json_text_content(payload: Any) -> list[TextContent]:
    return [
        TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))
    ]


def _error_text_content(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=message)]


def _build_http_error_payload(response: httpx.Response, prefix: str) -> dict[str, Any]:
    try:
        details: Any = response.json()
    except ValueError:
        details = response.text

    return {
        "error": prefix,
        "status_code": response.status_code,
        "details": details,
    }


def _safe_public_urls(value: Any) -> list[str]:
    urls = value if isinstance(value, list) else [value] if value else []
    safe_urls = []
    for url in urls:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        parsed = urllib.parse.urlparse(url)
        if "/sources/" in parsed.path or "/media/" in parsed.path:
            continue
        if url not in safe_urls:
            safe_urls.append(url)
    return safe_urls


def _sanitize_public_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": source.get("id"),
        "source_id": source.get("source_id"),
        "title": source.get("title") or "",
        "description": source.get("description") or "",
        "source_type": source.get("source_type"),
        "url": _safe_public_urls(source.get("url")),
        "publication_date": source.get("publication_date"),
    }


def _sanitize_public_case(
    case_data: dict[str, Any], include_evidence: bool = False
) -> dict[str, Any]:
    sanitized = {
        "id": case_data.get("id"),
        "case_id": case_data.get("case_id"),
        "slug": case_data.get("slug"),
        "case_type": case_data.get("case_type"),
        "state": case_data.get("state"),
        "title": case_data.get("title") or "",
        "short_description": case_data.get("short_description") or "",
        "description": case_data.get("description") or "",
        "key_allegations": case_data.get("key_allegations") or [],
        "tags": case_data.get("tags") or [],
        "entities": [
            {
                "id": entity.get("id"),
                "nes_id": entity.get("nes_id"),
                "display_name": entity.get("display_name"),
                "type": entity.get("type"),
            }
            for entity in case_data.get("entities") or []
            if isinstance(entity, dict)
        ],
        "case_start_date": case_data.get("case_start_date"),
        "case_end_date": case_data.get("case_end_date"),
        "created_at": case_data.get("created_at"),
        "updated_at": case_data.get("updated_at"),
    }

    if include_evidence:
        evidence = []
        for item in case_data.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            entry = {
                "source_id": item.get("source_id"),
                "description": item.get("description") or "",
            }
            if isinstance(item.get("source"), dict):
                entry["source"] = _sanitize_public_source(item["source"])
            evidence.append(entry)
        sanitized["evidence"] = evidence

    return sanitized


def _sanitize_public_entity(entity: dict[str, Any]) -> dict[str, Any] | None:
    related_cases = []
    for related in entity.get("related_cases") or []:
        if not isinstance(related, dict):
            continue
        if related.get("state") != "PUBLISHED":
            continue
        related_cases.append(
            {
                "case_id": related.get("case_id"),
                "relation_type": related.get("relation_type"),
            }
        )

    if not related_cases:
        return None

    return {
        "id": entity.get("id"),
        "nes_id": entity.get("nes_id"),
        "display_name": entity.get("display_name"),
        "related_cases": related_cases,
    }


class PublicSearchPublishedCasesTool(BaseTool):
    """Public-safe tool for searching only published Jawafdehi cases."""

    @property
    def name(self) -> str:
        return "public_search_published_cases"

    @property
    def description(self) -> str:
        return (
            "Search published public Jawafdehi cases. This tool strips internal "
            "fields, never uses authenticated API access, and supports optional "
            "case_type filtering."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Search across title, description, and allegations.",
                },
                "tags": {
                    "type": "string",
                    "description": "Filter cases containing a specific tag.",
                },
                "case_type": {
                    "type": "string",
                    "enum": ["CORRUPTION", "PROMISES"],
                    "description": "Optional case type filter. Omit to search all published case types.",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination.",
                    "default": 1,
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        query_params: dict[str, str] = {}
        if arguments.get("search"):
            query_params["search"] = arguments["search"]
        if arguments.get("tags"):
            query_params["tags"] = arguments["tags"]
        if arguments.get("case_type"):
            query_params["case_type"] = arguments["case_type"]
        if arguments.get("page"):
            query_params["page"] = str(arguments["page"])

        query_string = urllib.parse.urlencode(query_params)
        url = (
            f"{_get_jawafdehi_base_url()}/api/cases/?{query_string}"
            if query_string
            else f"{_get_jawafdehi_base_url()}/api/cases/"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers={}, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                raw_results = [
                    case for case in data.get("results", []) if isinstance(case, dict)
                ]
                results = [
                    _sanitize_public_case(case)
                    for case in raw_results
                    if case.get("state") == "PUBLISHED"
                ]
                count = data.get("count", len(results))
                if len(raw_results) != len(results):
                    count = len(results)
                return _json_text_content(
                    {
                        "count": count,
                        "next": data.get("next"),
                        "previous": data.get("previous"),
                        "results": results,
                    }
                )
        except httpx.HTTPError as e:
            return _error_text_content(f"Error accessing public cases API: {str(e)}")
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class PublicCountPublishedCasesTool(BaseTool):
    """Public-safe typed count for published Jawafdehi cases."""

    @property
    def name(self) -> str:
        return "public_count_published_cases"

    @property
    def description(self) -> str:
        return (
            "Count published public Jawafdehi cases. Returns an explicit "
            "published-only count contract for public chat and supports optional "
            "case_type filtering."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Search across title, description, and allegations.",
                },
                "tags": {
                    "type": "string",
                    "description": "Filter cases containing a specific tag.",
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        query_params = {"page": "1"}
        filters: dict[str, str] = {}
        if arguments.get("search"):
            query_params["search"] = arguments["search"]
            filters["search"] = arguments["search"]
        if arguments.get("tags"):
            query_params["tags"] = arguments["tags"]
            filters["tags"] = arguments["tags"]

        url = f"{_get_jawafdehi_base_url()}/api/cases/?{urllib.parse.urlencode(query_params)}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers={}, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                raw_results = [
                    case for case in data.get("results", []) if isinstance(case, dict)
                ]
                if any(case.get("state") != "PUBLISHED" for case in raw_results):
                    return _error_text_content(
                        "Public count API returned non-published case data."
                    )
                published_count = data.get("count", len(raw_results))
                if not isinstance(published_count, int) or published_count < 0:
                    return _error_text_content(
                        "Public count API returned an invalid count."
                    )
                return _json_text_content(
                    {
                        "published_count": published_count,
                        "count_scope": "published_only",
                        "filters": filters,
                        "results": [
                            _sanitize_public_case(case) for case in raw_results[:5]
                        ],
                    }
                )
        except httpx.HTTPError as e:
            return _error_text_content(f"Error accessing public cases API: {str(e)}")
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class PublicGetPublishedCaseTool(BaseTool):
    """Public-safe tool for retrieving a single published Jawafdehi case."""

    @property
    def name(self) -> str:
        return "public_get_published_case"

    @property
    def description(self) -> str:
        return (
            "Retrieve one published Jawafdehi case with internal fields stripped. "
            "Rejects draft, in-review, and closed cases."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "case_id": {
                    "type": ["integer", "string"],
                    "description": "Numeric case id or slug.",
                },
                "fetch_sources": {
                    "type": "boolean",
                    "description": "Include sanitized evidence source metadata.",
                    "default": False,
                },
            },
            "required": ["case_id"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        case_id = arguments.get("case_id")
        if not case_id:
            return _error_text_content("Error: case_id is required")

        url = f"{_get_jawafdehi_base_url()}/api/cases/{case_id}/"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers={}, timeout=30.0)
                if response.status_code == 404:
                    return _error_text_content(f"Case {case_id} not found.")
                response.raise_for_status()
                data = response.json()
                if data.get("state") != "PUBLISHED":
                    return _error_text_content(f"Case {case_id} not found.")
                return _json_text_content(
                    _sanitize_public_case(
                        data,
                        include_evidence=bool(arguments.get("fetch_sources", False)),
                    )
                )
        except httpx.HTTPError as e:
            return _error_text_content(f"Error accessing public case API: {str(e)}")
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class PublicSearchJawafEntitiesTool(BaseTool):
    """Public-safe tool for searching Jawafdehi entities tied to published cases."""

    @property
    def name(self) -> str:
        return "public_search_jawaf_entities"

    @property
    def description(self) -> str:
        return "Search public Jawafdehi entities associated with published cases."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Search query matched against display_name and nes_id.",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination.",
                    "default": 1,
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        query_params: dict[str, str] = {}
        if arguments.get("search"):
            query_params["search"] = arguments["search"]
        if arguments.get("page"):
            query_params["page"] = str(arguments["page"])

        query_string = urllib.parse.urlencode(query_params)
        url = (
            f"{_get_jawafdehi_base_url()}/api/entities/?{query_string}"
            if query_string
            else f"{_get_jawafdehi_base_url()}/api/entities/"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers={}, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                results = [
                    sanitized
                    for sanitized in (
                        _sanitize_public_entity(entity)
                        for entity in data.get("results", [])
                        if isinstance(entity, dict)
                    )
                    if sanitized is not None
                ]
                return _json_text_content(
                    {
                        "count": len(results),
                        "next": data.get("next"),
                        "previous": data.get("previous"),
                        "results": results,
                    }
                )
        except httpx.HTTPError as e:
            return _error_text_content(f"Error accessing public entities API: {str(e)}")
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class SearchJawafdehiCasesTool(BaseTool):
    """Tool for searching Jawafdehi accountability cases."""

    @property
    def name(self) -> str:
        return "search_jawafdehi_cases"

    @property
    def description(self) -> str:
        return (
            "Search for published Jawafdehi accountability cases (corruption) "
            "by typing keywords or tags."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": (
                        "Full-text search across title, description, "
                        "and key allegations."
                    ),
                },
                "tags": {
                    "type": "string",
                    "description": "Filter cases containing a specific tag.",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination (defaults to 1).",
                    "default": 1,
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        query_params = {"case_type": "CORRUPTION"}

        if "search" in arguments and arguments["search"]:
            query_params["search"] = arguments["search"]

        if "tags" in arguments and arguments["tags"]:
            query_params["tags"] = arguments["tags"]

        if "page" in arguments:
            query_params["page"] = str(arguments["page"])

        query_string = urllib.parse.urlencode(query_params)
        base_url = _get_jawafdehi_base_url()
        url = f"{base_url.rstrip('/')}/api/cases/?{query_string}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=_get_auth_headers(), timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                return _json_text_content(data)
        except httpx.HTTPError as e:
            return _error_text_content(
                f"Error accessing Jawafdehi cases API: {str(e)}\n\n"
                f"Consider narrowing your search or checking parameters."
            )
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class GetJawafdehiCaseTool(BaseTool):
    """Tool for retrieving detailed info on a specific Jawafdehi case."""

    @property
    def name(self) -> str:
        return "get_jawafdehi_case"

    @property
    def description(self) -> str:
        return (
            "Retrieve detailed information about a specific published Jawafdehi "
            "case, including its allegations, evidence, timeline, and audit history."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "case_id": {
                    "type": "integer",
                    "description": "A unique integer value identifying the case.",
                },
                "fetch_sources": {
                    "type": "boolean",
                    "description": (
                        "If true, the tool will also fetch detailed information "
                        "for each source referenced in the case."
                    ),
                    "default": False,
                },
            },
            "required": ["case_id"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        case_id = arguments.get("case_id")
        if not case_id:
            return _error_text_content("Error: case_id is required")

        fetch_sources = arguments.get("fetch_sources", False)
        base_url = _get_jawafdehi_base_url()
        case_url = f"{base_url.rstrip('/')}/api/cases/{case_id}/"

        try:
            auth_headers = _get_auth_headers()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    case_url, headers=auth_headers, timeout=30.0
                )
                if response.status_code == 404:
                    return _error_text_content(f"Case {case_id} not found.")
                response.raise_for_status()
                case_data = response.json()

                if fetch_sources and "evidence" in case_data:
                    # Resolve sources listed in the evidence property
                    resolved_sources = []
                    source_ids_to_fetch = set()

                    if isinstance(case_data.get("evidence"), list):
                        for ev in case_data["evidence"]:
                            if isinstance(ev, dict):
                                source_id = ev.get("source_id")
                                if source_id:
                                    source_ids_to_fetch.add(source_id)

                    for src_id in source_ids_to_fetch:
                        try:
                            src_url = f"{base_url.rstrip('/')}/api/sources/{src_id}/"
                            src_response = await client.get(
                                src_url, headers=auth_headers, timeout=30.0
                            )
                            if src_response.status_code == 200:
                                resolved_sources.append(src_response.json())
                        except Exception as e:
                            print(f"Failed to fetch source {src_id}: {e}")

                    if resolved_sources:
                        case_data["_resolved_sources"] = resolved_sources

                return _json_text_content(case_data)
        except httpx.HTTPError as e:
            return _error_text_content(
                f"Error accessing Jawafdehi API for case {case_id}: {str(e)}"
            )
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class CreateJawafdehiCaseTool(BaseTool):
    """Tool for creating a draft Jawafdehi case."""

    @property
    def name(self) -> str:
        return "create_jawafdehi_case"

    @property
    def description(self) -> str:
        return (
            "Create a draft Jawafdehi case using a simple authenticated interface. "
            "Requires JAWAFDEHI_API_TOKEN."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Case title.",
                },
                "case_type": {
                    "type": "string",
                    "enum": ["CORRUPTION", "PROMISES"],
                    "description": "Case type.",
                },
                "short_description": {
                    "type": "string",
                    "description": "Optional short description.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional full description.",
                },
            },
            "required": ["title", "case_type"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        title = arguments.get("title")
        case_type = arguments.get("case_type")
        token = _get_jawafdehi_api_token()

        if not token:
            return _error_text_content(
                "Error: JAWAFDEHI_API_TOKEN environment variable is required."
            )

        if not title:
            return _error_text_content("Error: title is required")

        if not case_type:
            return _error_text_content("Error: case_type is required")

        payload = {
            "title": title,
            "case_type": case_type,
        }

        if "short_description" in arguments:
            payload["short_description"] = arguments["short_description"]
        if "description" in arguments:
            payload["description"] = arguments["description"]

        url = f"{_get_jawafdehi_base_url()}/api/cases/"
        headers = {"Authorization": f"Token {token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )

                if response.is_success:
                    return _json_text_content(response.json())

                return _json_text_content(
                    _build_http_error_payload(
                        response, "Error creating Jawafdehi case via API."
                    )
                )
        except httpx.HTTPError as e:
            return _error_text_content(
                f"Error accessing Jawafdehi create API: {str(e)}"
            )
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class PatchJawafdehiCaseTool(BaseTool):
    """Tool for patching a Jawafdehi case with RFC 6902 operations."""

    @property
    def name(self) -> str:
        return "patch_jawafdehi_case"

    @property
    def description(self) -> str:
        return (
            "Patch a Jawafdehi case using raw RFC 6902 JSON Patch operations. "
            "Requires JAWAFDEHI_API_TOKEN."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "case_id": {
                    "type": "integer",
                    "description": "Database id of the case to patch.",
                },
                "operations": {
                    "type": "array",
                    "description": "RFC 6902 JSON Patch operations.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string"},
                            "path": {"type": "string"},
                            "value": {},
                        },
                        "required": ["op", "path"],
                    },
                },
            },
            "required": ["case_id", "operations"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        case_id = arguments.get("case_id")
        operations = arguments.get("operations")
        token = _get_jawafdehi_api_token()

        if not token:
            return _error_text_content(
                "Error: JAWAFDEHI_API_TOKEN environment variable is required."
            )

        if case_id is None:
            return _error_text_content("Error: case_id is required")

        if not isinstance(operations, list):
            return _error_text_content(
                "Error: operations must be a JSON Patch array of operation objects."
            )

        url = f"{_get_jawafdehi_base_url()}/api/cases/{case_id}/"
        headers = {"Authorization": f"Token {token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    url,
                    json=operations,
                    headers=headers,
                    timeout=30.0,
                )

                if response.is_success:
                    return _json_text_content(response.json())

                return _json_text_content(
                    _build_http_error_payload(
                        response, f"Error patching Jawafdehi case {case_id} via API."
                    )
                )
        except httpx.HTTPError as e:
            return _error_text_content(
                f"Error accessing Jawafdehi patch API for case {case_id}: {str(e)}"
            )
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class SubmitNESChangeTool(BaseTool):
    """Tool for submitting authenticated NES queue changes via Jawafdehi API."""

    @property
    def name(self) -> str:
        return "submit_nes_change"

    @property
    def description(self) -> str:
        return (
            "Submit a Jawafdehi NES queue change request for one of the supported "
            "actions: ADD_NAME, CREATE_ENTITY, or UPDATE_ENTITY."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["ADD_NAME", "CREATE_ENTITY", "UPDATE_ENTITY"],
                    "description": "NES queue action type.",
                },
                "payload": {
                    "type": "object",
                    "description": "Action-specific payload accepted by Jawafdehi NESQ.",
                },
                "change_description": {
                    "type": "string",
                    "description": "Human-readable summary of the requested change.",
                },
                "auto_approve": {
                    "type": "boolean",
                    "description": (
                        "Optional privileged flag to request immediate approval. "
                        "The API enforces permission checks."
                    ),
                    "default": False,
                },
            },
            "required": ["action", "payload", "change_description"],
        }

    def _get_api_token(self) -> str:
        token = _get_jawafdehi_api_token()
        if not token:
            raise ValueError(
                "JAWAFDEHI_API_TOKEN environment variable is required for "
                "submit_nes_change."
            )
        return token

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            token = self._get_api_token()
        except ValueError as exc:
            return _error_text_content(f"Error: {exc}")

        request_body = {
            "action": arguments.get("action"),
            "payload": arguments.get("payload"),
            "change_description": arguments.get("change_description"),
        }
        if "auto_approve" in arguments:
            request_body["auto_approve"] = arguments["auto_approve"]

        base_url = _get_jawafdehi_base_url()
        url = f"{base_url}/api/submit_nes_change"
        headers = {"Authorization": f"Token {token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=request_body,
                    headers=headers,
                    timeout=30.0,
                )

            if response.status_code == 201:
                return _json_text_content(response.json())

            try:
                error_body = json.dumps(response.json(), indent=2, ensure_ascii=False)
            except ValueError:
                error_body = response.text
            return _error_text_content(
                f"Error submitting NES change: HTTP {response.status_code}\n\n"
                f"{error_body}"
            )
        except httpx.HTTPError as e:
            return _error_text_content(f"Error submitting NES change: {str(e)}")
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class CreateJawafEntityTool(BaseTool):
    """Tool to create a JawafEntity via the API."""

    @property
    def name(self) -> str:
        return "create_jawaf_entity"

    @property
    def description(self) -> str:
        return "Create a new JawafEntity linking to an NES ID or via a display name."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "nes_id": {
                    "type": "string",
                    "description": "Optional NES ID to link (e.g. 'entity:person/ram-sharma').",
                },
                "display_name": {
                    "type": "string",
                    "description": "Optional custom display name if not linking an NES ID.",
                },
            },
            "required": ["display_name"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        token = _get_jawafdehi_api_token()
        if not token:
            return _error_text_content(
                "JAWAFDEHI_API_TOKEN environment variable is not set."
            )

        base_url = _get_jawafdehi_base_url()
        url = f"{base_url}/api/entities/"

        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=arguments)

            if response.status_code == 201:
                return _json_text_content(response.json())

            return _json_text_content(
                _build_http_error_payload(response, "Error creating JawafEntity")
            )
        except Exception as e:
            return _error_text_content(f"Unexpected error creating entity: {str(e)}")


class UploadDocumentSourceTool(BaseTool):
    """Tool to upload a document source."""

    @property
    def name(self) -> str:
        return "upload_document_source"

    @property
    def description(self) -> str:
        return "Create a new DocumentSource by uploading a file from disk."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {
                    "type": "string",
                    "description": "Source description: what the underlying content *is* (describe the document itself).",
                },
                "source_type": {
                    "type": "string",
                    "description": (
                        "Source category. Supported API enum values: "
                        "LEGAL_COURT_ORDER, LEGAL_PROCEDURAL, OFFICIAL_GOVERNMENT, "
                        "FINANCIAL_FORENSIC, INTERNAL_CORPORATE, MEDIA_NEWS, "
                        "INVESTIGATIVE_REPORT, PUBLIC_COMPLAINT, LEGISLATIVE_DOC, "
                        "SOCIAL_MEDIA, OTHER_VISUAL."
                    ),
                },
                "url": {
                    "type": "array",
                    "items": {"type": "string", "format": "uri"},
                    "description": (
                        "List of external URLs for this source. "
                        "For news articles, include the original article URL here."
                    ),
                },
                "publication_date": {
                    "type": "string",
                    "format": "date",
                    "description": (
                        "Publication date (YYYY-MM-DD). "
                        "Required for MEDIA_NEWS sources."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file on disk to upload.",
                },
            },
            "required": ["title", "file_path"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        token = _get_jawafdehi_api_token()
        if not token:
            return _error_text_content(
                "JAWAFDEHI_API_TOKEN environment variable is not set."
            )

        missing_keys = [k for k in ["title", "file_path"] if k not in arguments]
        if missing_keys:
            return _error_text_content(
                f"Missing required arguments: {', '.join(missing_keys)}"
            )

        file_path = Path(arguments["file_path"])
        try:
            file_bytes = file_path.read_bytes()
        except OSError as e:
            return _error_text_content(f"Could not read file '{file_path}': {e}")

        filename = file_path.name
        base_url = _get_jawafdehi_base_url()
        url = f"{base_url}/api/sources/"

        headers = {
            "Authorization": f"Token {token}",
            "Accept": "application/json",
        }

        data = {
            "title": arguments["title"],
        }
        if "description" in arguments:
            data["description"] = arguments["description"]
        if "source_type" in arguments:
            data["source_type"] = arguments["source_type"]
        if "publication_date" in arguments:
            data["publication_date"] = arguments["publication_date"]

        # url is a JSON list; multipart/form-data requires encoding it as JSON
        import json as _json

        if "url" in arguments and arguments["url"]:
            data["url"] = _json.dumps(arguments["url"])

        files = {"uploaded_file": (filename, file_bytes)}

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    url, headers=headers, data=data, files=files
                )

            if response.status_code == 201:
                return _json_text_content(response.json())

            return _json_text_content(
                _build_http_error_payload(response, "Error uploading document source")
            )
        except Exception as e:
            return _error_text_content(f"Unexpected error uploading document: {str(e)}")


class SearchJawafEntitiesTool(BaseTool):
    """Tool for searching Jawafdehi entities."""

    @property
    def name(self) -> str:
        return "search_jawaf_entities"

    @property
    def description(self) -> str:
        return (
            "Search for Jawafdehi entities (persons, organizations) by name or NES ID. "
            "Returns entities associated with published cases."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": (
                        "Search query matched against display_name and nes_id."
                    ),
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination (defaults to 1).",
                    "default": 1,
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        query_params: dict[str, str] = {}

        if arguments.get("search"):
            query_params["search"] = arguments["search"]

        if "page" in arguments:
            query_params["page"] = str(arguments["page"])

        base_url = _get_jawafdehi_base_url()
        query_string = urllib.parse.urlencode(query_params)
        url = (
            f"{base_url}/api/entities/?{query_string}"
            if query_string
            else f"{base_url}/api/entities/"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=_get_auth_headers(), timeout=30.0
                )
                response.raise_for_status()
                return _json_text_content(response.json())
        except httpx.HTTPError as e:
            return _error_text_content(
                f"Error accessing Jawafdehi entities API: {str(e)}"
            )
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")


class GetJawafEntityTool(BaseTool):
    """Tool for retrieving a single Jawafdehi entity by ID."""

    @property
    def name(self) -> str:
        return "get_jawaf_entity"

    @property
    def description(self) -> str:
        return (
            "Retrieve a specific Jawafdehi entity by its integer ID, including "
            "its NES ID, display name, and related published cases."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "integer",
                    "description": "The integer ID of the Jawafdehi entity.",
                },
            },
            "required": ["entity_id"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        entity_id = arguments.get("entity_id")
        if not entity_id:
            return _error_text_content("Error: entity_id is required")

        base_url = _get_jawafdehi_base_url()
        url = f"{base_url}/api/entities/{entity_id}/"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=_get_auth_headers(), timeout=30.0
                )
                if response.status_code == 404:
                    return _error_text_content(f"Entity {entity_id} not found.")
                response.raise_for_status()
                return _json_text_content(response.json())
        except httpx.HTTPError as e:
            return _error_text_content(
                f"Error accessing Jawafdehi entities API for entity {entity_id}: {str(e)}"
            )
        except Exception as e:
            return _error_text_content(f"Unexpected error: {str(e)}")
