"""MCP server for Jawafdehi and NGM judicial data queries."""

import os
import uuid
from typing import Any

import structlog
import structlog.contextvars
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .identity import (
    PUBLIC_READ_ONLY_TOOL_NAMES,
    current_user_identity,
    get_allowed_tool_names,
)
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

app = Server("jawafdehi-mcp")

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

TOOL_MAP = {tool.name: tool for tool in TOOLS}
ALL_TOOL_NAMES: set[str] = set(TOOL_MAP.keys())


def _has_api_token() -> bool:
    return bool(os.getenv("JAWAFDEHI_API_TOKEN", "").strip())


def _get_allowed_tools() -> list[BaseTool]:
    identity = current_user_identity.get()
    if identity is not None:
        allowed = get_allowed_tool_names(identity, ALL_TOOL_NAMES)
        return [tool for tool in TOOLS if tool.name in allowed]

    if _has_api_token():
        return TOOLS

    return [tool for tool in TOOLS if tool.name in PUBLIC_READ_ONLY_TOOL_NAMES]


def _is_tool_allowed(name: str) -> bool:
    identity = current_user_identity.get()
    if identity is not None:
        allowed = get_allowed_tool_names(identity, ALL_TOOL_NAMES)
        return name in allowed

    if _has_api_token():
        return True

    return name in PUBLIC_READ_ONLY_TOOL_NAMES


def _bind_audit_context(identity: dict | None) -> None:
    if identity:
        structlog.contextvars.bind_contextvars(
            jawafdehi_user_id=str(identity.get("user_id", "")),
            jawafdehi_username=identity.get("username", ""),
            jawafdehi_roles=identity.get("roles", []),
        )


def _unbind_audit_context() -> None:
    structlog.contextvars.unbind_contextvars(
        "jawafdehi_user_id",
        "jawafdehi_username",
        "jawafdehi_roles",
    )


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools based on the current user's identity."""
    return [tool.to_tool() for tool in _get_allowed_tools()]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool execution requests with per-user authorization."""
    if not _is_tool_allowed(name):
        identity = current_user_identity.get()
        user_info = ""
        if identity:
            user_info = (
                f" (user_id={identity.get('user_id')}, roles={identity.get('roles')})"
            )
        raise ValueError(
            f"Tool '{name}' is not available for the current user{user_info}. "
            "Contact a caseworker for elevated access."
        )

    tool = TOOL_MAP.get(name)
    if not tool:
        logger.error("unknown_tool_requested", tool_name=name)
        raise ValueError(f"Unknown tool: {name}")

    identity = current_user_identity.get()
    request_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
    _bind_audit_context(identity)
    logger.info("tool_call_started", tool_name=name)
    try:
        result = await tool.execute(arguments)
        return result
    except Exception:
        logger.exception("tool_execution_failed", tool_name=name)
        raise
    finally:
        _unbind_audit_context()
        structlog.contextvars.unbind_contextvars("request_id")


def main():
    """Run the MCP server via stdio."""
    logger.info("server_starting")

    import asyncio

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream, write_stream, app.create_initialization_options()
            )

    asyncio.run(run())


def main_http():
    """Run the MCP server via Streamable HTTP."""
    from .http_server import main as _http_main

    _http_main()


if __name__ == "__main__":
    main()
