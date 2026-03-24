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


def _get_jawafdehi_api_token() -> str | None:
    token = os.getenv("JAWAFDEHI_API_TOKEN", "").strip()
    return token or None


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
                response = await client.get(url, timeout=30.0)
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
            async with httpx.AsyncClient() as client:
                response = await client.get(case_url, timeout=30.0)
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
                            src_response = await client.get(src_url, timeout=30.0)
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
