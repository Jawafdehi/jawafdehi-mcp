# Jawafdehi MCP Server

Model Context Protocol (MCP) server providing tools for integrating LLM workflows with Jawafdehi products, including Jawafdehi.org, Nepal Entity Service (NES), Nepal Government Modernization (NGM), and the `likhit` Markdown conversion tool.

## Available MCP Tools

- Modular tool architecture for easy extension
- **Unified document converter** with smart auto-detection (Likhit + MarkItDown)
- Read-only access with query validation
- Timeout protection (default 15s)
- Comprehensive error handling

### Jawafdehi.org

- `search_jawafdehi_cases`: Search published Jawafdehi accountability cases
- `get_jawafdehi_case`: Retrieve detailed case information
- `create_jawafdehi_case`: Create a draft Jawafdehi case
- `patch_jawafdehi_case`: Patch an existing case with RFC 6902 JSON Patch operations

### Nepal Entity Service (NES)

- `submit_nes_change`: Submit NES queue changes through Jawafdehi API
- `search_nes_entities`: Search Nepal Entity Service for persons and organizations
- `get_nes_entities`: Retrieve complete entity profiles
- `get_nes_entity_prefixes`: Fetch valid NES entity prefixes for creation/classification
- `get_nes_entity_prefix_schema`: Fetch the JSON schema for a specific NES entity prefix
- `get_nes_tags`: Fetch all available entity tags

### Nepal Government Modernization (NGM)

- `ngm_query_judicial`: Execute SELECT queries against NGM court and court case tables
- `ngm_extract_case_data`: Extract complete judicial case information to Markdown

### Likhit and Document Conversion

- `convert_to_markdown`: Convert documents with smart auto-detection (Likhit for Nepal government PDFs, MarkItDown for Office documents/web pages/general PDFs, with automatic fallback)
- `convert_date`: Convert dates between AD and BS calendars

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

Install via PyPI (recommended):

```bash
uv tool install jawafdehi-mcp
```

If you want the latest unreleased changes, install from GitHub instead:

```bash
uv tool install git+https://github.com/NewNepal-org/jawafdehi-mcp.git
```

## Configuration

Set the required environment variables:

```bash
export JAWAFDEHI_API_BASE_URL="https://portal.jawafdehi.org"
export JAWAFDEHI_API_TOKEN="your-jawafdehi-api-token"
```

To request a Jawafdehi API token, contact `inquiry@jawafdehi.org` or WhatsApp: `+1 206-530-9098`.

## Usage

### As MCP Server

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "jawafdehi": {
      "command": "uvx",
      "args": ["jawafdehi-mcp"],
      "env": {
        "JAWAFDEHI_API_BASE_URL": "https://portal.jawafdehi.org",
        "JAWAFDEHI_API_TOKEN": "your-jawafdehi-api-token"
      }
    }
  }
}
```

### Jawafdehi Case Drafting and Patching

Use `create_jawafdehi_case` to create draft cases and `patch_jawafdehi_case` to apply
JSON Patch updates to existing cases by `case_id`.

Both tools require `JAWAFDEHI_API_TOKEN`.

### NES Queue Submissions

The `submit_nes_change` tool sends authenticated POST requests to Jawafdehi API's
NES queue endpoint. Supported action values are:

- `ADD_NAME`
- `CREATE_ENTITY`
- `UPDATE_ENTITY`

The tool uses `JAWAFDEHI_API_BASE_URL` for the API host and requires
`JAWAFDEHI_API_TOKEN` for authentication.

### NES Schema Discovery

Use `get_nes_entity_prefixes` to fetch the currently valid NES entity prefixes,
and `get_nes_entity_prefix_schema` to fetch the JSON schema for one prefix such
as `person` or `organization/political_party`. Prefixes containing slashes
(e.g. `organization/political_party`) are automatically URL-encoded by the tool
before being sent in the request path.

These tools read from `NES_API_BASE_URL`, which defaults to
`https://nes.newnepal.org`.

### Available Tables

The following NGM judicial tables are accessible through the Jawafdehi API proxy endpoint (`/api/ngm/query_judicial`):

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
