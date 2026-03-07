# Adding New Tools to Jawafdehi MCP Server

This guide explains how to add new tools to the Jawafdehi MCP server.

## Tool Architecture

The server uses a modular architecture where each tool is a separate class that inherits from `BaseTool`. This makes it easy to add, remove, or modify tools without affecting the core server logic.

## Step-by-Step Guide

### 1. Create a New Tool File

Create a new Python file in `src/jawafdehi_mcp/tools/` with a descriptive name:

```bash
touch src/jawafdehi_mcp/tools/my_new_tool.py
```

### 2. Implement the Tool Class

Your tool must inherit from `BaseTool` and implement all abstract methods:

```python
"""My new tool implementation."""

from typing import Any
from mcp.types import TextContent
from .base import BaseTool


class MyNewTool(BaseTool):
    """Description of what this tool does."""

    @property
    def name(self) -> str:
        """Unique identifier for the tool."""
        return "my_new_tool"

    @property
    def description(self) -> str:
        """Human-readable description shown to users."""
        return "Does something useful with data."

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON schema defining the tool's input parameters."""
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "First parameter",
                },
                "param2": {
                    "type": "number",
                    "description": "Second parameter",
                    "default": 10,
                },
            },
            "required": ["param1"],
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """
        Execute the tool logic.
        
        Args:
            arguments: Dictionary of input parameters
            
        Returns:
            List of TextContent responses
        """
        param1 = arguments.get("param1")
        param2 = arguments.get("param2", 10)
        
        # Your tool logic here
        result = f"Processed {param1} with {param2}"
        
        return [TextContent(type="text", text=result)]
```

### 3. Register the Tool

Add your tool to `src/jawafdehi_mcp/tools/__init__.py`:

```python
"""Tool implementations for Jawafdehi MCP server."""

from .base import BaseTool
from .ngm_judicial import NGMJudicialTool
from .my_new_tool import MyNewTool  # Add this import

__all__ = ["BaseTool", "NGMJudicialTool", "MyNewTool"]  # Add to exports
```

### 4. Add Tool to Server

Update `src/jawafdehi_mcp/server.py` to include your tool:

```python
from .tools import BaseTool, NGMJudicialTool, MyNewTool  # Add import

# Registry of available tools
TOOLS: list[BaseTool] = [
    NGMJudicialTool(),
    MyNewTool(),  # Add your tool instance
]
```

### 5. Test Your Tool

Create tests in `tests/test_my_new_tool.py`:

```python
"""Tests for MyNewTool."""

import pytest
from jawafdehi_mcp.tools.my_new_tool import MyNewTool


@pytest.mark.asyncio
async def test_my_new_tool():
    """Test basic functionality."""
    tool = MyNewTool()
    
    result = await tool.execute({"param1": "test"})
    
    assert len(result) == 1
    assert "test" in result[0].text
```

Run tests:

```bash
poetry run pytest tests/test_my_new_tool.py
```

## Best Practices

### Error Handling

Always handle errors gracefully and return structured error responses:

```python
try:
    # Your logic
    result = do_something()
    return [TextContent(type="text", text=str(result))]
except ValueError as e:
    error_msg = f"Invalid input: {str(e)}"
    return [TextContent(type="text", text=error_msg)]
except Exception as e:
    error_msg = f"Unexpected error: {str(e)}"
    return [TextContent(type="text", text=error_msg)]
```

### Environment Variables

If your tool needs configuration, use environment variables:

```python
import os

def _validate_environment(self) -> str:
    """Validate required environment variables."""
    api_key = os.getenv("MY_API_KEY")
    if not api_key:
        raise ValueError("MY_API_KEY environment variable is required")
    return api_key
```

### Input Validation

Validate inputs before processing:

```python
async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute with validation."""
    param = arguments.get("param")
    
    if not param:
        return [TextContent(type="text", text="Error: param is required")]
    
    if not isinstance(param, str):
        return [TextContent(type="text", text="Error: param must be a string")]
    
    # Process validated input
    ...
```

### Documentation

Document your tool thoroughly:

- Class docstring explaining purpose
- Method docstrings for complex logic
- Clear parameter descriptions in `input_schema`
- Usage examples in comments or separate docs

## Example Tools

See these files for reference:

- `tools/ngm_judicial.py` - Complex database query tool with validation
- `tools/example_tool.py` - Simple template for new tools

## Testing

Always write tests for your tools:

```bash
# Run all tests
poetry run pytest

# Run specific tool tests
poetry run pytest tests/test_my_new_tool.py

# Run with coverage
poetry run pytest --cov=jawafdehi_mcp
```

## Deployment

After adding a tool:

1. Update documentation (README.md, CHANGELOG.md)
2. Run tests and linting
3. Commit changes
4. Update version in `pyproject.toml`
5. Deploy to production

## Need Help?

- Check existing tool implementations in `src/jawafdehi_mcp/tools/`
- Review MCP documentation: https://modelcontextprotocol.io
- Ask in project discussions or issues
