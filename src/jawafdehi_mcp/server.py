"""MCP server for Jawafdehi and NGM judicial data queries."""

import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .tools import (
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
from .tools.nes import GetNESEntitiesTool, GetNESTagsTool, SearchNESEntitiesTool

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
    "search_nes_entities",
    "get_nes_entities",
    "ngm_query_judicial",
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
        raise ValueError(f"Unknown tool: {name}")

    return await tool.execute(arguments)


def main():
    """Run the MCP server."""
    import asyncio

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream, write_stream, app.create_initialization_options()
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
