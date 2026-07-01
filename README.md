# Jawafdehi MCP Server

Model Context Protocol (MCP) server providing tools for integrating LLM workflows with Jawafdehi products, including Jawafdehi.org, Nepal Entity Service (NES), Nepal Government Modernization (NGM), and MarkItDown-based document conversion with the `likhit` plugin.

## Available MCP Tools

- Modular tool architecture for easy extension
- **Unified document converter** powered by MarkItDown with plugin support
- Read-only access with query validation
- Timeout protection (default 15s)
- Comprehensive error handling

### Jawafdehi.org

- `search_jawafdehi_cases`: Search published Jawafdehi accountability cases
- `get_jawafdehi_case`: Retrieve detailed case information
- `create_jawafdehi_case`: Create a draft Jawafdehi case
- `patch_jawafdehi_case`: Patch an existing case with RFC 6902 JSON Patch operations

### Nepal Entity Service (NES)

- `submit_nes_change`: Write an NES entity directly — `CREATE` (POST a JSON-LD document) or `UPDATE` (PATCH by ref with RFC 6902 ops)
- `search_nes_entities`: Search Nepal Entity Service for persons and organizations
- `get_nes_entities`: Retrieve complete entity profiles
- `get_nes_entity_prefixes`: Fetch valid NES entity prefixes for creation/classification
- `get_nes_tags`: Fetch all available entity tags

### Materials

- `upload_material_file`: Attach a file to a Material (`/material/{source}/{ident}`), uploading it to storage as a roled MediaObject

### Nepal Government Modernization (NGM)

- `ngm_query_judicial`: Execute SELECT queries against the court tables via the gated SQL plane
- `ngm_extract_case_data`: Extract complete judicial case information to Markdown

### Likhit and Document Conversion

- `convert_to_markdown`: Convert documents through MarkItDown with plugins enabled by default; the `likhit` plugin adds Nepal-specific handling for supported PDFs and legacy `.doc` files. **Legacy `.doc` files require `antiword` installed on the host** (see [System Requirements](#system-requirements)). Markdown is returned directly by default, or written to a file when `output_path` is provided
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

## System Requirements

Most functionality requires only the Python dependencies managed by `uv`/`poetry`.

**Legacy `.doc` file conversion** (when `convert_to_markdown` is called on a `.doc` file) additionally requires `antiword` installed on the host:

```bash
# Ubuntu / Debian
sudo apt install antiword

# macOS
brew install antiword
```

Without a system `antiword` binary, the bundled binary inside `pyantiword` (MarkItDown's `.doc` converter) may fail with an `Exec format error` if it was compiled for a different CPU architecture. `.docx`, `.pdf`, and all other formats are unaffected.

## Installation

Install via PyPI (recommended):

```bash
uv tool install jawafdehi-mcp
```


If you want the latest unreleased changes, install from GitHub instead:

```bash
uv tool install git+https://github.com/Jawafdehi/jawafdehi-mcp.git
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

### NES Entity Writes

The `submit_nes_change` tool writes NES entities directly on the unified entity
plane (the old NES *queue* endpoint and its `ADD_NAME`/`CREATE_ENTITY`/
`UPDATE_ENTITY` actions are gone):

- `action=CREATE` → `POST /api/entities` with a JSON-LD `document`.
- `action=UPDATE` → `PATCH /api/entities/{ref}` with RFC 6902 `patch_ops`
  (adding a name is just an `add` op to `/name`).

The tool uses `JAWAFDEHI_API_BASE_URL` for the API host and requires
`JAWAFDEHI_API_TOKEN` (or a forwarded OIDC bearer) for authentication.

### NES Schema Discovery

Use `get_nes_entity_prefixes` to fetch the currently valid NES entity prefixes.
All entity reads (`search_nes_entities`, `get_nes_entities` → `/api/entities`,
`get_nes_tags` → `/api/entities/tags`, `get_nes_entity_prefixes` →
`/api/entity_prefixes`) now hit the ONE unified Jawafdehi host — the standalone
`nes.jawafdehi.org` service and its `/api/nes` prefix were retired.

### Available Tables

The following court tables are accessible through the gated SQL plane (`/api/query/`):

- `courts` - Court master table (district, high, supreme, special courts)
- `court_cases` - Court case metadata and registration information
- `court_case_hearings` - Hearing records for each case
- `court_case_entities` - Plaintiff and defendant information

Note: The `scraped_dates` table is excluded from queries.

## Documentation

- [Architecture Overview](docs/ARCHITECTURE.md) - System design and structure
- [Adding Tools Guide](docs/ADDING_TOOLS.md) - How to add new tools
- [Publishing Guide](docs/PUBLISHING.md) - How to release a new version to PyPI

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

Licensed under the [Hippocratic License 3.0](./LICENSE), an [Ethical Source](https://ethicalsource.dev) license. See [LICENSING.md](./LICENSING.md) for details.
