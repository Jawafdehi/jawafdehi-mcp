"""Shared helpers for NGM proxy access via Jawafdehi API."""

import json
import os
from typing import Any

import httpx


def get_jawafdehi_api_config() -> tuple[str, str | None]:
    """Return validated Jawafdehi API base URL and optional token."""
    base_url = os.getenv("JAWAFDEHI_API_BASE_URL", "https://portal.jawafdehi.org")
    base_url = base_url.rstrip("/")
    token = os.getenv("JAWAFDEHI_API_TOKEN", "").strip() or None

    if not base_url.startswith(("http://", "https://")):
        raise ValueError(
            "JAWAFDEHI_API_BASE_URL must be an HTTP(S) URL. " f"Got: {base_url[:30]}..."
        )

    return base_url, token


def get_jawafdehi_api_config_strict() -> tuple[str, str]:
    """Return validated Jawafdehi API base URL and token (token required)."""
    base_url, token = get_jawafdehi_api_config()
    if not token:
        raise ValueError("JAWAFDEHI_API_TOKEN environment variable is required.")
    return base_url, token


def rows_to_dicts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert proxy response rows+columns payload into dict records."""
    data = payload.get("data") or {}
    columns = data.get("columns") or []
    rows = data.get("rows") or []
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(columns):
            raise RuntimeError(
                "Malformed proxy payload: "
                f"row {index} has "
                f"{len(row) if isinstance(row, list) else 'non-list'} values "
                f"for {len(columns)} columns"
            )
        records.append(dict(zip(columns, row)))
    return records


def sql_quote(value: str) -> str:
    """Quote a SQL string literal by escaping single quotes."""
    return value.replace("'", "''")


async def execute_ngm_proxy_query(
    client: httpx.AsyncClient,
    base_url: str,
    token: str | None,
    query: str,
    timeout: float = 15,
) -> dict[str, Any]:
    """Execute a query via Jawafdehi's NGM proxy endpoint."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Token {token}"

    response = await client.post(
        f"{base_url}/api/ngm/query_judicial",
        json={"query": query, "timeout": timeout},
        headers=headers,
        timeout=30.0,
    )

    try:
        payload: dict[str, Any] = response.json()
    except ValueError:
        payload = {
            "success": False,
            "error": f"Non-JSON response from proxy ({response.status_code})",
            "raw": response.text,
        }

    if not response.is_success or not payload.get("success"):
        raise RuntimeError(
            f"NGM proxy query failed ({response.status_code}): "
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    return payload
