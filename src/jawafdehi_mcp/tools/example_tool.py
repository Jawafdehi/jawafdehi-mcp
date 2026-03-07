"""Example tool implementation - template for adding new tools."""

from typing import Any

from mcp.types import TextContent

from .base import BaseTool


class ExampleTool(BaseTool):
    """
    Example tool demonstrating the structure for new tools.

    To add a new tool:
    1. Create a new file in this directory (e.g., my_tool.py)
    2. Subclass BaseTool
    3. Implement all abstract methods
    4. Import and register in __init__.py
    5. Add to TOOLS list in server.py
    """

    @property
    def name(self) -> str:
        return "example_tool"

    @property
    def description(self) -> str:
        return "Example tool for demonstration purposes."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "A message to echo back",
                },
            },
            "required": ["message"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute the example tool."""
        message = arguments.get("message", "")

        response = f"Echo: {message}"
        return [TextContent(type="text", text=response)]
