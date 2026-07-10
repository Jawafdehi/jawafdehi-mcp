import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
import structlog
from mcp.types import TextContent

from ..request_context import get_forwarded_headers, jawafdehi_bearer_token
from .base import BaseTool

logger = structlog.get_logger()


def _get_jawafdehi_base_url() -> str:
    return os.getenv("JAWAFDEHI_API_BASE_URL", "https://api.jawafdehi.org").rstrip("/")


def _get_jawafdehi_api_token() -> str | None:
    token = os.getenv("JAWAFDEHI_API_TOKEN", "").strip()
    return token or None


def _has_upstream_auth() -> bool:
    """True if the request can authenticate to jawafdehi-api: a forwarded OIDC
    bearer (HTTP transport) or a service token (stdio/dev fallback)."""
    return bool(jawafdehi_bearer_token.get()) or bool(_get_jawafdehi_api_token())


def _get_auth_headers() -> dict[str, str]:
    """Return Authorization headers for upstream calls.

    Prefer the caller's forwarded OIDC bearer; fall back to the service token
    (stdio/dev), also sent as ``Bearer``. The unified platform is OIDC-only —
    the legacy DRF ``Token`` scheme is no longer honoured (2026-07 hard cut).
    get_forwarded_headers() wins because it overwrites Authorization.
    """
    headers: dict[str, str] = {}
    token = _get_jawafdehi_api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(get_forwarded_headers())
    return headers


_NO_AUTH_MESSAGE = (
    "Authentication required: sign in (OIDC bearer) or set JAWAFDEHI_API_TOKEN."
)


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


def _flatten_lang_map(value: Any) -> str:
    """Flatten a unified-search language map ({en, ne}) to a single string.

    Prefers English, then Nepali, then any non-empty value. A plain string is
    returned as-is; anything else becomes "".
    """
    if isinstance(value, dict):
        for lang in ("en", "ne"):
            text = value.get(lang)
            if isinstance(text, str) and text:
                return text
        for text in value.values():
            if isinstance(text, str) and text:
                return text
        return ""
    return value if isinstance(value, str) else ""


def _slug_from_search_hit(hit: dict[str, Any]) -> str:
    """Extract a case slug from a unified-search hit.

    The /api/search/ result carries the slug inside ``api_url``
    (``/api/cases/<slug>/``) or ``url`` (``/case/<slug>``) — it has no bare
    ``slug`` field. get_jawafdehi_case needs the slug, so derive it here.
    """
    for key, pattern in (
        ("api_url", r"/api/cases/([^/]+)/?$"),
        ("url", r"/case/([^/]+)/?$"),
    ):
        value = hit.get(key)
        if isinstance(value, str):
            match = re.search(pattern, value)
            if match:
                return match.group(1)
    return ""


def _shape_case_search_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """Map a raw /api/search/ case hit to the case shape the tool returns.

    Keeps a ``slug`` (for get_jawafdehi_case), a flattened title/snippet, and
    the case_type/date/url/score so the assistant can present and link results.
    """
    extra = hit.get("extra")
    if not isinstance(extra, dict):
        extra = {}
    return {
        "slug": _slug_from_search_hit(hit),
        "title": _flatten_lang_map(hit.get("title")),
        "snippet": _flatten_lang_map(hit.get("snippet")),
        "case_type": extra.get("case_type"),
        "date": extra.get("date"),
        "url": hit.get("url"),
        "score": hit.get("score"),
    }


class SearchJawafdehiCasesTool(BaseTool):
    """Tool for searching Jawafdehi accountability cases."""

    @property
    def name(self) -> str:
        return "search_jawafdehi_cases"

    @property
    def description(self) -> str:
        return (
            "Search published Jawafdehi accountability cases by keywords or tags. "
            "Covers every case type (corruption, tax evasion, and others); pass "
            "case_type only to narrow the results to a single type."
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
                "case_type": {
                    "type": "string",
                    "description": (
                        "Optional. Restrict results to one case type "
                        "(e.g. CORRUPTION, TAX_EVASION, PROMISES). Omit to search "
                        "across all case types."
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
        # Query the unified OpenSearch plane (/api/search/), NOT the legacy
        # /api/cases/ list filter. That list filter is a plain ORM icontains
        # over title/description that misses Nepali-script titles — English
        # queries returned 0 results — and DRF 404s on an out-of-range page
        # (BB-03). /api/search/ is the bilingual, ranked search and returns an
        # empty page instead of a 404.
        query_params: dict[str, str] = {"type": "case"}

        search = arguments.get("search")
        if search:
            query_params["q"] = str(search)

        tags = arguments.get("tags")
        if tags:
            query_params["tags"] = str(tags)

        # Optional case-type filter — default is NO filter so every case type is
        # searchable. A previously hard-coded case_type=CORRUPTION silently hid
        # tax-evasion and other non-corruption cases from search and chat (BB-03).
        case_type = arguments.get("case_type")
        if case_type:
            query_params["case_type"] = str(case_type)

        if "page" in arguments:
            query_params["page"] = str(arguments["page"])

        query_string = urllib.parse.urlencode(query_params)
        base_url = _get_jawafdehi_base_url()
        url = f"{base_url.rstrip('/')}/api/search/?{query_string}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=_get_auth_headers(), timeout=30.0
                )
                if not response.is_success:
                    # Surface the API's own error body (status + detail) instead of
                    # a bare status string, so failures like an expired forwarded
                    # token ({"detail": "Token has expired."}) are diagnosable.
                    error_payload = _build_http_error_payload(
                        response, "Error accessing Jawafdehi search API."
                    )
                    logger.error(
                        "jawafdehi_search_http_error",
                        status_code=response.status_code,
                        details=error_payload.get("details"),
                    )
                    return _json_text_content(error_payload)
                data = response.json()

            # Defensive: a well-behaved /api/search/ returns a JSON object with a
            # list of dict hits, but never trust the shape blindly.
            if not isinstance(data, dict):
                data = {}
            raw_results = data.get("results")
            results = raw_results if isinstance(raw_results, list) else []
            payload = {
                "count": data.get("count"),
                "page": data.get("page"),
                "results": [
                    _shape_case_search_hit(hit)
                    for hit in results
                    if isinstance(hit, dict)
                ],
            }
            return _json_text_content(payload)
        except httpx.HTTPError as e:
            logger.error("jawafdehi_search_http_error", error=str(e))
            return _error_text_content(
                f"Error accessing Jawafdehi cases API: {str(e)}\n\n"
                f"Consider narrowing your search or checking parameters."
            )
        except Exception as e:
            logger.exception("jawafdehi_search_unexpected_error", error=str(e))
            return _error_text_content(f"Unexpected error: {str(e)}")


class GetJawafdehiCaseTool(BaseTool):
    """Tool for retrieving detailed info on a specific Jawafdehi case."""

    @property
    def name(self) -> str:
        return "get_jawafdehi_case"

    @property
    def description(self) -> str:
        return (
            "Retrieve detailed information about a specific Jawafdehi case "
            "(published or draft), including its allegations, evidence, timeline, "
            "and audit history. Each evidence entry is a reference into the "
            "Materials store — ``{material_iri, additional_details, material}`` — "
            "where ``material`` is the resolved material (display name, type, "
            "roled URLs), embedded by the API. All cases (including drafts) have "
            "auto-generated slugs. Use the 'slug' from search results for direct "
            "lookup. The 'slug' field also accepts a court case reference of the "
            "form '{court_identifier}:{case_number}' (e.g. 'supreme:081-CR-0081') "
            "to look up the Jawafdehi case that cites that CIAA court case; the "
            "case number is normalized automatically (casing, zero-padding, "
            "Devanagari digits)."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": (
                        "The URL slug of the case (e.g. from search results), the "
                        "canonical identifier for API lookup. Alternatively, a "
                        "court case reference '{court_identifier}:{case_number}' "
                        "(e.g. 'supreme:081-CR-0081') to look up the case by the "
                        "CIAA court case it cites."
                    ),
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        base_url = _get_jawafdehi_base_url()
        auth_headers = _get_auth_headers()

        slug = arguments.get("slug")

        if slug and isinstance(slug, str) and slug.strip():
            case_url = f"{base_url.rstrip('/')}/api/cases/{slug.strip()}/"
            lookup_label = f"slug={slug.strip()}"
        else:
            return _error_text_content(
                "Error: 'slug' (string) is required. "
                "Use the 'slug' field from search_jawafdehi_cases results."
            )

        # The case detail already embeds each evidence entry's resolved material
        # (cases own no documents — evidence is a CaseMaterialReference join, and
        # CaseDetailSerializer resolves the material inline). No separate
        # source-fetch loop is needed; the old /api/sources endpoint is gone.
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    case_url, headers=auth_headers, timeout=30.0
                )
                if response.status_code == 404:
                    return _error_text_content(f"Case not found ({lookup_label}).")
                if not response.is_success:
                    # Surface the API's error body (e.g. an expired forwarded token
                    # → {"detail": "Token has expired."}) rather than a bare status.
                    error_payload = _build_http_error_payload(
                        response,
                        f"Error accessing Jawafdehi case API ({lookup_label}).",
                    )
                    logger.error(
                        "jawafdehi_get_case_http_error",
                        lookup_label=lookup_label,
                        status_code=response.status_code,
                        details=error_payload.get("details"),
                    )
                    return _json_text_content(error_payload)
                return _json_text_content(response.json())
        except httpx.HTTPError as e:
            logger.error(
                "jawafdehi_get_case_http_error",
                lookup_label=lookup_label,
                error=str(e),
            )
            return _error_text_content(
                f"Error accessing Jawafdehi API ({lookup_label}): {str(e)}"
            )
        except Exception as e:
            logger.exception(
                "jawafdehi_get_case_unexpected_error",
                lookup_label=lookup_label,
                error=str(e),
            )
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
            "Requires a signed-in user with write access."
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
                    "description": "Optional full description (Markdown).",
                },
            },
            "required": ["title", "case_type"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        title = arguments.get("title")
        case_type = arguments.get("case_type")

        if not _has_upstream_auth():
            return _error_text_content(f"Error: {_NO_AUTH_MESSAGE}")

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
        headers = _get_auth_headers()

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
            logger.error("jawafdehi_create_case_http_error", error=str(e))
            return _error_text_content(
                f"Error accessing Jawafdehi create API: {str(e)}"
            )
        except Exception as e:
            logger.exception("jawafdehi_create_case_unexpected_error", error=str(e))
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
            "Requires a signed-in user with write access. Use a slug (from "
            "search results) for direct lookup."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": (
                        "The URL slug of the case to patch. "
                        "Use the 'slug' field from search_jawafdehi_cases results."
                    ),
                },
                "operations": {
                    "type": "array",
                    "description": "RFC 6902 JSON Patch operations. Use Markdown for /description values.",
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
            "required": ["slug", "operations"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        operations = arguments.get("operations")
        slug = arguments.get("slug")

        if not _has_upstream_auth():
            return _error_text_content(f"Error: {_NO_AUTH_MESSAGE}")

        if not slug or not isinstance(slug, str) or not slug.strip():
            return _error_text_content(
                "Error: 'slug' (string) is required. "
                "Use the 'slug' field from search_jawafdehi_cases results."
            )

        if not isinstance(operations, list):
            return _error_text_content(
                "Error: operations must be a JSON Patch array of operation objects."
            )

        base_url = _get_jawafdehi_base_url()

        url = f"{base_url.rstrip('/')}/api/cases/{slug.strip()}/"
        lookup_label = f"slug={slug.strip()}"

        headers = _get_auth_headers()

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
                        response,
                        f"Error patching Jawafdehi case ({lookup_label}) via API.",
                    )
                )
        except httpx.HTTPError as e:
            logger.error(
                "jawafdehi_patch_case_http_error",
                lookup_label=lookup_label,
                error=str(e),
            )
            return _error_text_content(
                f"Error accessing Jawafdehi patch API ({lookup_label}): {str(e)}"
            )
        except Exception as e:
            logger.exception(
                "jawafdehi_patch_case_unexpected_error",
                lookup_label=lookup_label,
                error=str(e),
            )
            return _error_text_content(f"Unexpected error: {str(e)}")


class SubmitNESChangeTool(BaseTool):
    """Write an NES entity directly via the unified entity write plane.

    Post-unification (2026-07 hard cut) there is no NES *queue* endpoint
    (``/api/submit_nes_change`` and the ADD_NAME/CREATE_ENTITY/UPDATE_ENTITY
    NESQ actions are gone). Writes go straight to the entity store:
      * CREATE → ``POST /api/entities`` with a JSON-LD / authoring ``document``.
      * UPDATE → ``PATCH /api/entities/{ref}`` with RFC-6902 ``patch_ops``
        (add-a-name is just an ``add`` op to ``/name`` — no dedicated action).
    NES-contributor gated; the API enforces permissions and the ≥2-source held
    /published gate does NOT apply to direct API writes (they publish).
    """

    @property
    def name(self) -> str:
        return "submit_nes_change"

    @property
    def description(self) -> str:
        return (
            "Write an NES entity directly. Use action=CREATE with a JSON-LD "
            "'document' to create an entity, or action=UPDATE with 'ref' "
            "(the entity @id or prefix/slug) and RFC-6902 'patch_ops' to modify "
            "one (e.g. add a name: [{'op':'add','path':'/name/en','value':'...'}])."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["CREATE", "UPDATE"],
                    "description": "CREATE a new entity or UPDATE an existing one.",
                },
                "ref": {
                    "type": "string",
                    "description": (
                        "UPDATE only: the entity @id IRI or 'prefix/slug' path "
                        "(e.g. 'person/ram-chandra-poudel')."
                    ),
                },
                "document": {
                    "type": "object",
                    "description": (
                        "CREATE only: the JSON-LD / authoring entity document "
                        "(must carry @id or prefix+slug + @type)."
                    ),
                },
                "patch_ops": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "UPDATE only: RFC-6902 JSON Patch operations. Immutable "
                        "paths (@id/@type/@context/version) are rejected by the API."
                    ),
                },
                "change_description": {
                    "type": "string",
                    "description": "Human-readable summary of the change.",
                },
            },
            "required": ["action", "change_description"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        if not _has_upstream_auth():
            return _error_text_content(f"Error: {_NO_AUTH_MESSAGE}")

        action = arguments.get("action")
        change_description = arguments.get("change_description")
        base_url = _get_jawafdehi_base_url()
        headers = _get_auth_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        if action == "CREATE":
            document = arguments.get("document")
            if not isinstance(document, dict):
                return _error_text_content(
                    "Error: 'document' (object) is required for action=CREATE."
                )
            url = f"{base_url}/api/entities"
            body = {**document, "change_description": change_description}
            method = "POST"
        elif action == "UPDATE":
            ref = arguments.get("ref")
            patch_ops = arguments.get("patch_ops")
            if not ref or not isinstance(patch_ops, list):
                return _error_text_content(
                    "Error: 'ref' and 'patch_ops' (array) are required for "
                    "action=UPDATE."
                )
            # The detail route accepts either a bare ``prefix/slug`` path (slashes
            # are path separators) or a FULLY url-encoded ``@id`` IRI (one opaque
            # segment). Encode a full IRI with safe='' so its scheme ``//`` and
            # path slashes don't collapse into route separators; keep slashes for
            # the prefix/slug form.
            ref = str(ref)
            if ref.startswith(("http://", "https://")):
                ref_path = urllib.parse.quote(ref, safe="")
            else:
                ref_path = urllib.parse.quote(ref, safe="/")
            url = f"{base_url}/api/entities/{ref_path}"
            body = {"patch_ops": patch_ops, "change_description": change_description}
            method = "PATCH"
        else:
            return _error_text_content(
                f"Error: unsupported action {action!r} (use CREATE or UPDATE)."
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method, url, json=body, headers=headers, timeout=30.0
                )

            if response.status_code in (200, 201):
                return _json_text_content(response.json())

            return _json_text_content(
                _build_http_error_payload(response, "Error writing NES entity")
            )
        except httpx.HTTPError as e:
            logger.error("jawafdehi_submit_nes_change_http_error", error=str(e))
            return _error_text_content(f"Error writing NES entity: {str(e)}")
        except Exception as e:
            logger.exception(
                "jawafdehi_submit_nes_change_unexpected_error", error=str(e)
            )
            return _error_text_content(f"Unexpected error: {str(e)}")


class UploadMaterialFileTool(BaseTool):
    """Attach a file to a Material via the unified material upload endpoint.

    Post-unification the document/evidence store is Materials: this streams a
    local file to ``POST /api/materials/{source}/{ident}/file`` (multipart),
    which places it in object storage and appends a roled schema.org
    ``MediaObject`` to the material's ``associatedMedia`` (creating the material
    if it does not yet exist). Replaces the retired ``/api/sources`` upload.
    NGM-role gated.
    """

    @property
    def name(self) -> str:
        return "upload_material_file"

    @property
    def description(self) -> str:
        return (
            "Attach a file (from disk) to a Material at @id "
            "/material/{source}/{ident}, uploading it to storage as a roled "
            "MediaObject. Creates the material if it does not exist (then "
            "material_type is required)."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": (
                        "Material source segment of the IRI "
                        "(e.g. 'nkp', 'court'), i.e. /material/{source}/{ident}."
                    ),
                },
                "ident": {
                    "type": "string",
                    "description": "Material ident segment of the IRI.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file on disk to upload.",
                },
                "role": {
                    "type": "string",
                    "enum": ["RAW", "ALTERNATE", "PERMALINK"],
                    "description": "Link role for the uploaded file (default RAW).",
                    "default": "RAW",
                },
                "material_type": {
                    "type": "string",
                    "description": (
                        "Required only when CREATING a new material "
                        "(e.g. court_order). Ignored when the material exists."
                    ),
                },
            },
            "required": ["source", "ident", "file_path"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        if not _has_upstream_auth():
            return _error_text_content(_NO_AUTH_MESSAGE)

        missing_keys = [
            k for k in ["source", "ident", "file_path"] if not arguments.get(k)
        ]
        if missing_keys:
            return _error_text_content(
                f"Missing required arguments: {', '.join(missing_keys)}"
            )

        file_path = Path(arguments["file_path"])
        try:
            file_bytes = file_path.read_bytes()
        except OSError as e:
            return _error_text_content(f"Could not read file '{file_path}': {e}")

        source = urllib.parse.quote(str(arguments["source"]), safe="")
        ident = urllib.parse.quote(str(arguments["ident"]), safe="")
        base_url = _get_jawafdehi_base_url()
        url = f"{base_url}/api/materials/{source}/{ident}/file"

        headers = _get_auth_headers()
        headers["Accept"] = "application/json"

        data: dict[str, str] = {}
        # input_schema "default" is metadata only (BaseTool doesn't inject it), so
        # apply the advertised RAW default here rather than sending no role.
        data["role"] = str(arguments.get("role") or "RAW")
        if arguments.get("material_type"):
            data["material_type"] = arguments["material_type"]

        files = {"file": (file_path.name, file_bytes)}

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    url, headers=headers, data=data, files=files
                )

            if response.status_code in (200, 201):
                return _json_text_content(response.json())

            return _json_text_content(
                _build_http_error_payload(response, "Error uploading material file")
            )
        except Exception as e:
            logger.exception("jawafdehi_upload_material_unexpected_error", error=str(e))
            return _error_text_content(f"Unexpected error uploading material: {str(e)}")
