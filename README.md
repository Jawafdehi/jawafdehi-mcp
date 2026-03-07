# Jawafdehi MCP Server

Model Context Protocol (MCP) server providing tools for querying Nepal's judicial data from the NGM (Nepal Governance Modernization) database.

## Features

- Modular tool architecture for easy extension
- `ngm_query_judicial`: Execute SELECT queries against NGM court and court case tables
- Read-only access with query validation
- Timeout protection (default 15s)
- Comprehensive error handling

## Architecture

The server uses a modular tool architecture:

```
src/jawafdehi_mcp/
├── server.py              # Main MCP server
└── tools/                 # Tool implementations
    ├── __init__.py        # Tool registry
    ├── base.py            # BaseTool abstract class
    ├── ngm_judicial.py    # NGM judicial query tool
    └── example_tool.py    # Example tool template
```

### Adding New Tools

1. Create a new file in `src/jawafdehi_mcp/tools/` (e.g., `my_tool.py`)
2. Subclass `BaseTool` and implement required methods:
   - `name`: Tool identifier
   - `description`: Tool description
   - `input_schema`: JSON schema for inputs
   - `execute()`: Tool execution logic
3. Import your tool in `tools/__init__.py`
4. Add an instance to the `TOOLS` list in `server.py`

See `tools/example_tool.py` for a template.

## Installation

```bash
cd services/jawafdehi-mcp
poetry install
```

## Configuration

Set the required environment variable:

```bash
export NGM_DATABASE_URL="postgresql://user:password@host:5432/database"
```

## Usage

### As MCP Server

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "jawafdehi": {
      "command": "poetry",
      "args": ["run", "jawafdehi-mcp"],
      "cwd": "/path/to/services/jawafdehi-mcp",
      "env": {
        "NGM_DATABASE_URL": "postgresql://user:password@host:5432/database"
      }
    }
  }
}
```

### Available Tables

The following tables from NGM database are accessible:

- `courts` - Court master table (district, high, supreme, special courts)
- `court_cases` - Court case metadata and registration information
- `court_case_hearings` - Hearing records for each case
- `court_case_entities` - Plaintiff and defendant information

Note: The `scraped_dates` table is excluded from queries.

## Documentation

- [Architecture Overview](docs/ARCHITECTURE.md) - System design and structure
- [Adding Tools Guide](docs/ADDING_TOOLS.md) - How to add new tools

## Development

### Adding New Tools

See [docs/ADDING_TOOLS.md](docs/ADDING_TOOLS.md) for a complete guide on adding new tools to the server.

### Running Tests

```bash
poetry run pytest
```

### Linting

```bash
./scripts/format.sh --check
```

### Formatting

```bash
poetry run black src/ tests/
poetry run isort src/ tests/
```

## License

Open source - see LICENSE file for details.
