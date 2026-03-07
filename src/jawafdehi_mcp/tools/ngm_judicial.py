"""NGM judicial data query tool."""

import os
import re
import time
from typing import Any

from mcp.types import TextContent
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .base import BaseTool

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
        return (
            "Search judicial cases from Nepal's court system. "
            "Execute SELECT queries against NGM court and court case "
            "tables. Supports: courts, court_cases, court_case_hearings, "
            "court_case_entities. Requires NGM_DATABASE_URL env var."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT query to execute. Must be read-only.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Query timeout in seconds (default: 15)",
                    "default": 15,
                },
            },
            "required": ["query"],
        }

    def _validate_environment(self) -> str:
        """
        Validate required environment variables.

        Returns:
            Database URL from environment

        Raises:
            ValueError: If NGM_DATABASE_URL is not set or invalid
        """
        db_url = os.getenv("NGM_DATABASE_URL")

        if not db_url:
            raise ValueError(
                "NGM_DATABASE_URL environment variable is required. "
                "Example: postgresql://user:password@host:5432/database"
            )

        # Basic validation - must be postgres URL
        if not db_url.startswith(("postgres://", "postgresql://")):
            raise ValueError(
                "NGM_DATABASE_URL must be a PostgreSQL connection string. "
                f"Got: {db_url[:20]}..."
            )

        return db_url

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
        timeout = arguments.get("timeout", 15)

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
            db_url = self._validate_environment()
            engine = create_engine(db_url, pool_pre_ping=True)

            start_time = time.time()

            with engine.connect() as conn:
                # Set statement timeout
                conn.execute(text(f"SET statement_timeout = {int(timeout * 1000)}"))

                # Execute query
                result = conn.execute(text(query))

                # Fetch results
                rows = result.fetchall()
                columns = list(result.keys())

                # Convert rows to list of lists
                data_rows = [list(row) for row in rows]

            query_time_ms = int((time.time() - start_time) * 1000)

            response = {
                "success": True,
                "data": {
                    "columns": columns,
                    "rows": data_rows,
                    "row_count": len(data_rows),
                },
                "error": None,
                "query_time_ms": query_time_ms,
            }

            return [TextContent(type="text", text=str(response))]

        except SQLAlchemyError as e:
            error_msg = str(e).replace('"', '\\"')
            error_response = (
                f'{{"success": false, "data": null, '
                f'"error": "Database error: {error_msg}", "query_time_ms": 0}}'
            )
            return [TextContent(type="text", text=error_response)]
        except Exception as e:
            error_msg = str(e).replace('"', '\\"')
            error_response = (
                f'{{"success": false, "data": null, '
                f'"error": "Unexpected error: {error_msg}", "query_time_ms": 0}}'
            )
            return [TextContent(type="text", text=error_response)]
        finally:
            if "engine" in locals():
                engine.dispose()
