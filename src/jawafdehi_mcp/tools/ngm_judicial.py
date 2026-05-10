"""NGM judicial data query tool."""

import json
import re
from typing import Any

import httpx
from mcp.types import TextContent

from .base import BaseTool
from .ngm_proxy import execute_ngm_proxy_query, get_jawafdehi_api_config

# Allowed tables (excluding scraped_dates)
ALLOWED_TABLES = {
    "courts",
    "court_cases",
    "court_case_hearings",
    "court_case_entities",
}


class NGMJudicialTool(BaseTool):
    """Tool for querying Nepal's judicial data from NGM database."""

    @property
    def name(self) -> str:
        return "ngm_query_judicial"

    @property
    def description(self) -> str:
        return """Search judicial cases from Nepal's court system. Execute SELECT queries against NGM court and court case tables. By default, we should fetch only a few results (e.g. 5) to avoid eating up the context window.

Table Schemas:
- courts: identifier (PK), court_type, full_name_nepali, full_name_english, created_at, updated_at
- court_cases: case_number (PK), court_identifier (PK), registration_date_bs, registration_date_ad, case_type, division, category, section, plaintiff, defendant, original_case_number, case_id, priority, registration_number, case_status, verdict_date_bs, verdict_date_ad, verdict_judge, status, extra_data
- court_case_hearings: id (PK), case_number, court_identifier, hearing_date_bs, hearing_date_ad, bench, bench_type, judge_names, lawyer_names, serial_no, case_status, decision_type, remarks, extra_data
- court_case_entities: id (PK), case_number, court_identifier, side, name, address, nes_id

Court IDs (court_identifier):
- Supreme & Special: supreme, special
- High Courts: biratnagarhc, illamhc, dhankutahc, okhaldhungahc, janakpurhc, rajbirajhc, birganjhc, patanhc, hetaudahc, pokharahc, baglunghc, tulsipurhc, butwalhc, nepalgunjhc, surkhethc, jumlahc, dipayalhc, mahendranagarhc
- District Courts: achhamdc, argakhanchidc, etc."""

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT query to execute. Must be read-only. By default, we should fetch only a few results (e.g. 5) to avoid eating up the context window.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Query timeout in seconds (default: 15)",
                    "default": 15,
                },
            },
            "required": ["query"],
        }

    def _validate_environment(self) -> tuple[str, str | None]:
        """
        Validate required environment variables.

        Returns:
            Tuple of (base_url, optional token)

        Raises:
            ValueError: If required API configuration is missing or invalid
        """
        return get_jawafdehi_api_config()

    def _validate_query(self, query: str) -> tuple[bool, str | None]:
        """
        Validate that query is a SELECT statement and uses only allowed tables.

        Args:
            query: SQL query string

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if valid
            - (False, error_message) if invalid
        """
        # Normalize query for validation
        normalized = query.strip().lower()

        # Must be SELECT query
        if not normalized.startswith("select"):
            return False, "Only SELECT queries are allowed"

        # Check for forbidden keywords (write operations)
        forbidden_keywords = [
            "insert",
            "update",
            "delete",
            "drop",
            "create",
            "alter",
            "truncate",
            "grant",
            "revoke",
        ]

        for keyword in forbidden_keywords:
            if re.search(rf"\b{keyword}\b", normalized):
                return False, f"Forbidden keyword detected: {keyword.upper()}"

        # Extract table names from FROM and JOIN clauses
        table_pattern = r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)"
        referenced_tables = set(re.findall(table_pattern, normalized))

        # Check if scraped_dates is referenced
        if "scraped_dates" in referenced_tables:
            return False, "Access to 'scraped_dates' table is not allowed"

        # Check if all referenced tables are in allowed list
        invalid_tables = referenced_tables - ALLOWED_TABLES
        if invalid_tables:
            return (
                False,
                f"Invalid table(s): {', '.join(invalid_tables)}. "
                f"Allowed tables: {', '.join(sorted(ALLOWED_TABLES))}",
            )

        return True, None

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute the NGM judicial query tool."""
        # Extract arguments
        query = arguments.get("query")
        raw_timeout = arguments.get("timeout", 15)

        # Validate and clamp timeout
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            error_response = (
                '{"success": false, "data": null, '
                '"error": "timeout must be a number", "query_time_ms": 0}'
            )
            return [TextContent(type="text", text=error_response)]
        if timeout <= 0:
            error_response = (
                '{"success": false, "data": null, '
                '"error": "timeout must be greater than 0", "query_time_ms": 0}'
            )
            return [TextContent(type="text", text=error_response)]
        timeout = min(timeout, 15.0)

        if not query:
            error_response = (
                '{"success": false, "data": null, '
                '"error": "Query parameter is required", "query_time_ms": 0}'
            )
            return [TextContent(type="text", text=error_response)]

        # Validate query
        is_valid, error_msg = self._validate_query(query)
        if not is_valid:
            error_response = (
                f'{{"success": false, "data": null, '
                f'"error": "{error_msg}", "query_time_ms": 0}}'
            )
            return [TextContent(type="text", text=error_response)]

        # Execute query
        try:
            base_url, token = self._validate_environment()

            async with httpx.AsyncClient() as client:
                payload = await execute_ngm_proxy_query(
                    client,
                    base_url,
                    token,
                    query,
                    timeout=timeout,
                )

            # Wrap in stable tool-owned envelope
            proxy_data = payload.get("data") or {}
            response = {
                "success": True,
                "data": {
                    "columns": proxy_data.get("columns", []),
                    "rows": proxy_data.get("rows", []),
                    "row_count": proxy_data.get(
                        "row_count", len(proxy_data.get("rows", []))
                    ),
                },
                "error": None,
                "query_time_ms": payload.get("query_time_ms", 0),
            }
            return [
                TextContent(
                    type="text",
                    text=json.dumps(response, ensure_ascii=False),
                )
            ]
        except RuntimeError as e:
            error_msg = str(e).replace('"', '\\"')
            error_response = (
                f'{{"success": false, "data": null, '
                f'"error": "Proxy API error: {error_msg}", "query_time_ms": 0}}'
            )
            return [TextContent(type="text", text=error_response)]
        except httpx.HTTPError as e:
            error_msg = str(e).replace('"', '\\"')
            error_response = (
                f'{{"success": false, "data": null, '
                f'"error": "HTTP error: {error_msg}", "query_time_ms": 0}}'
            )
            return [TextContent(type="text", text=error_response)]
        except Exception as e:
            error_msg = str(e).replace('"', '\\"')
            error_response = (
                f'{{"success": false, "data": null, '
                f'"error": "Unexpected error: {error_msg}", "query_time_ms": 0}}'
            )
            return [TextContent(type="text", text=error_response)]
