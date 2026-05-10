"""MCP server for Jawafdehi and NGM judicial data queries."""

import os
from typing import Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .logging_setup import setup_logging

setup_logging()

from .tools import (  # noqa: E402
    BaseTool,
    CreateJawafdehiCaseTool,
    CreateJawafEntityTool,
    DateConverterTool,
    DocumentConverterTool,
    GetJawafdehiCaseTool,
    GetJawafEntityTool,
    GetNESEntityPrefixesTool,
    GetNESEntityPrefixSchemaTool,
    NGMExtractCaseDataTool,
    NGMJudicialTool,
    PatchJawafdehiCaseTool,
    SearchJawafdehiCasesTool,
    SearchJawafEntitiesTool,
    SubmitNESChangeTool,
    UploadDocumentSourceTool,
)
from .tools.nes import (  # noqa: E402
    GetNESEntitiesTool,
    GetNESTagsTool,
    SearchNESEntitiesTool,
)

logger = structlog.get_logger()

logger = structlog.get_logger()

# Initialize MCP server
app = Server("jawafdehi-mcp")

# Registry of available tools
TOOLS: list[BaseTool] = [
    NGMJudicialTool(),
    NGMExtractCaseDataTool(),
    SearchJawafdehiCasesTool(),
    GetJawafdehiCaseTool(),
    CreateJawafdehiCaseTool(),
    PatchJawafdehiCaseTool(),
    SubmitNESChangeTool(),
    CreateJawafEntityTool(),
    SearchJawafEntitiesTool(),
    GetJawafEntityTool(),
    UploadDocumentSourceTool(),
    SearchNESEntitiesTool(),
    GetNESEntitiesTool(),
    GetNESEntityPrefixesTool(),
    GetNESEntityPrefixSchemaTool(),
    GetNESTagsTool(),
    DateConverterTool(),
    DocumentConverterTool(),
]

# Create tool name to instance mapping
TOOL_MAP = {tool.name: tool for tool in TOOLS}

# Public read-only tools available without JAWAFDEHI_API_TOKEN
PUBLIC_READ_ONLY_TOOL_NAMES = {
    "search_jawafdehi_cases",
    "get_jawafdehi_case",
    "search_jawaf_entities",
    "get_jawaf_entity",
    "search_nes_entities",
    "get_nes_entities",
    "get_nes_tags",
    "get_nes_entity_prefixes",
    "get_nes_entity_prefix_schema",
    "ngm_query_judicial",
    "convert_date",
    "convert_to_markdown",
}


def _is_public_mode() -> bool:
    """Return True if JAWAFDEHI_API_TOKEN is not set (public read-only mode)."""
    return not os.getenv("JAWAFDEHI_API_TOKEN", "").strip()


def _get_available_tools() -> list[BaseTool]:
    """Return the list of tools available based on current profile."""
    if _is_public_mode():
        return [tool for tool in TOOLS if tool.name in PUBLIC_READ_ONLY_TOOL_NAMES]
    return TOOLS


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools based on public/private profile."""
    return [tool.to_tool() for tool in _get_available_tools()]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool execution requests."""
    if _is_public_mode() and name not in PUBLIC_READ_ONLY_TOOL_NAMES:
        raise ValueError(
            f"Tool '{name}' is not available in public read-only mode. "
            "Set JAWAFDEHI_API_TOKEN for full access."
        )

    tool = TOOL_MAP.get(name)
    if not tool:
        logger.error("unknown_tool_requested", tool_name=name)
        raise ValueError(f"Unknown tool: {name}")

    logger.info("tool_call_started", tool_name=name)
    try:
        result = await tool.execute(arguments)
        return result
    except Exception:
        logger.exception("tool_execution_failed", tool_name=name)
        raise


def main():
    """Run the MCP server."""
    import asyncio

    logger.info("server_starting")

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream, write_stream, app.create_initialization_options()
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
