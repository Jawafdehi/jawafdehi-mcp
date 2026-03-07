"""Base tool interface for MCP tools."""

from abc import ABC, abstractmethod
from typing import Any

from mcp.types import TextContent, Tool


class BaseTool(ABC):
    """Base class for MCP tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return the tool description."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input."""
        pass

    def to_tool(self) -> Tool:
        """Convert to MCP Tool object."""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema,
        )

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """
        Execute the tool with given arguments.

        Args:
            arguments: Tool input arguments

        Returns:
            List of TextContent responses
        """
        pass
