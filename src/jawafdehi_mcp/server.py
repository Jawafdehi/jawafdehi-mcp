"""MCP server for Jawafdehi and NGM judicial data queries."""

from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .tools import BaseTool, NGMJudicialTool

# Initialize MCP server
app = Server("jawafdehi-mcp")

# Registry of available tools
TOOLS: list[BaseTool] = [
    NGMJudicialTool(),
]

# Create tool name to instance mapping
TOOL_MAP = {tool.name: tool for tool in TOOLS}


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [tool.to_tool() for tool in TOOLS]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool execution requests."""
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
