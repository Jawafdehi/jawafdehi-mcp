# Jawafdehi MCP Server Architecture

## Overview

The Jawafdehi MCP server uses a modular architecture that makes it easy to add, remove, or modify tools without affecting the core server logic.

## Directory Structure

```
src/jawafdehi_mcp/
├── __init__.py           # Package initialization
├── server.py             # Main MCP server with tool registry
└── tools/                # Tool implementations
    ├── __init__.py       # Tool exports
    ├── base.py           # BaseTool abstract class
    ├── ngm_judicial.py   # NGM judicial query tool
    └── example_tool.py   # Example tool template
```

## Core Components

### 1. Server (`server.py`)

The main MCP server that:
- Initializes the MCP server instance
- Maintains a registry of available tools (`TOOLS` list)
- Creates a tool name-to-instance mapping (`TOOL_MAP`)
- Handles tool listing requests (`list_tools()`)
- Dispatches tool execution requests (`call_tool()`)

```python
# Tool registry
TOOLS: list[BaseTool] = [
    NGMJudicialTool(),
    # Add new tools here
]
```

### 2. Base Tool (`tools/base.py`)

Abstract base class that defines the tool interface:

```python
class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool identifier (must be unique)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON schema for tool inputs."""
        pass

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute the tool logic."""
        pass

    def to_tool(self) -> Tool:
        """Convert to MCP Tool object."""
        pass
```

### 3. Tool Implementations (`tools/`)

Each tool is a separate module that:
- Inherits from `BaseTool`
- Implements all abstract methods
- Contains its own validation and execution logic
- Manages its own dependencies and configuration

## Tool Lifecycle

```
1. Server Initialization
   ├── Import tool classes
   ├── Instantiate tools
   └── Build tool registry

2. Tool Discovery (list_tools)
   ├── Client requests available tools
   ├── Server iterates TOOLS list
   └── Returns tool metadata (name, description, schema)

3. Tool Execution (call_tool)
   ├── Client sends tool name + arguments
   ├── Server looks up tool in TOOL_MAP
   ├── Dispatches to tool.execute()
   └── Returns tool response
```

## Adding a New Tool

### Step 1: Create Tool Class

Create `src/jawafdehi_mcp/tools/my_tool.py`:

```python
from typing import Any
from mcp.types import TextContent
from .base import BaseTool

class MyTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Description of what this tool does."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "Parameter description"}
            },
            "required": ["param"]
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        param = arguments.get("param")
        result = f"Processed: {param}"
        return [TextContent(type="text", text=result)]
```

### Step 2: Register Tool

Update `src/jawafdehi_mcp/tools/__init__.py`:

```python
from .base import BaseTool
from .ngm_judicial import NGMJudicialTool
from .my_tool import MyTool  # Add import

__all__ = ["BaseTool", "NGMJudicialTool", "MyTool"]  # Add to exports
```

### Step 3: Add to Server

Update `src/jawafdehi_mcp/server.py`:

```python
from .tools import BaseTool, NGMJudicialTool, MyTool  # Add import

TOOLS: list[BaseTool] = [
    NGMJudicialTool(),
    MyTool(),  # Add instance
]
```

### Step 4: Test

Create `tests/test_my_tool.py` and run:

```bash
poetry run pytest tests/test_my_tool.py
```

## Design Principles

### 1. Separation of Concerns
- Server handles MCP protocol and routing
- Tools handle business logic and validation
- Each tool is self-contained

### 2. Open/Closed Principle
- Open for extension (add new tools easily)
- Closed for modification (no server changes needed)

### 3. Single Responsibility
- Each tool has one clear purpose
- Tools manage their own dependencies
- Tools handle their own errors

### 4. Dependency Injection
- Tools are instantiated and injected into server
- Easy to mock for testing
- Clear dependency graph

## Benefits

### For Developers
- **Easy to add tools** - Just create a new class and register it
- **Easy to test** - Each tool can be tested independently
- **Easy to maintain** - Changes to one tool don't affect others
- **Clear structure** - Consistent pattern across all tools

### For Users
- **Discoverable** - All tools listed via MCP protocol
- **Consistent** - All tools follow same interface
- **Reliable** - Each tool handles its own errors
- **Extensible** - New capabilities added without breaking changes

## Example: NGM Judicial Tool

The NGM judicial query tool demonstrates the architecture:

```python
class NGMJudicialTool(BaseTool):
    # Tool metadata
    name = "ngm_query_judicial"
    description = "Query Nepal's judicial data..."
    input_schema = {...}

    # Private validation methods
    def _validate_environment(self) -> str: ...
    def _validate_query(self, query: str) -> tuple[bool, str | None]: ...

    # Public execution method
    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        # 1. Extract arguments
        # 2. Validate inputs
        # 3. Execute logic
        # 4. Return results
        ...
```

## Future Enhancements

Potential improvements to the architecture:

1. **Tool Categories** - Group related tools
2. **Tool Dependencies** - Tools that depend on other tools
3. **Tool Middleware** - Common pre/post processing
4. **Tool Configuration** - Per-tool config files
5. **Tool Versioning** - Support multiple versions of same tool
6. **Tool Metrics** - Usage tracking and performance monitoring

## References

- [MCP Protocol Specification](https://modelcontextprotocol.io)
- [Adding Tools Guide](ADDING_TOOLS.md)
- [Example Tool Implementation](../src/jawafdehi_mcp/tools/example_tool.py)
