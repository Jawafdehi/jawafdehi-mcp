# Jawafdehi MCP Server - Usage Guide

## Quick Start

### 1. Install Dependencies

```bash
cd services/jawafdehi-mcp
poetry install
```

Document conversion is handled by MarkItDown. Nepal-specific PDF and legacy `.doc`
support comes from the installed `markitdown-likhit` plugin dependency.
By default, `convert_to_markdown` returns Markdown directly in the tool response.
Provide `output_path` when you want the converted Markdown saved as a file.

### 2. Set Environment Variables

```bash
export JAWAFDEHI_API_BASE_URL="https://portal.jawafdehi.org"
export JAWAFDEHI_API_TOKEN="your-jawafdehi-api-token"
```

### 3. Run the Server

```bash
poetry run jawafdehi-mcp
```

## MCP Client Configuration

Add to your MCP client's configuration file (e.g., `.kiro/settings/mcp.json`):

```json
{
  "mcpServers": {
    "jawafdehi": {
      "command": "poetry",
      "args": ["run", "jawafdehi-mcp"],
      "cwd": "/absolute/path/to/services/jawafdehi-mcp",
      "env": {
        "JAWAFDEHI_API_BASE_URL": "https://portal.jawafdehi.org",
        "JAWAFDEHI_API_TOKEN": "your-jawafdehi-api-token"
      }
    }
  }
}
```

## Available Tools

### ngm_query_judicial

Execute SELECT queries against Nepal's court data through the platform's gated SQL plane (`POST /api/query/`).

**Parameters:**
- `query` (string, required): SQL SELECT query
- `timeout` (number, optional): Query timeout in seconds (default: 15)

**Example Queries:**

#### 1. Get all courts

```sql
SELECT identifier, court_type, full_name_nepali, full_name_english
FROM courts
ORDER BY court_type, identifier
```

#### 2. Search corruption cases

```sql
SELECT
  case_number,
  case_type,
  plaintiff,
  defendant,
  registration_date_bs
FROM court_cases
WHERE case_type LIKE '%भ्रष्टाचार%'
ORDER BY registration_date_ad DESC
LIMIT 20
```

#### 3. Get case hearing history

```sql
SELECT
  cc.case_number,
  cc.case_type,
  co.full_name_nepali as court_name,
  COUNT(cch.id) as total_hearings,
  MIN(cch.hearing_date_ad) as first_hearing,
  MAX(cch.hearing_date_ad) as last_hearing
FROM court_cases cc
JOIN courts co ON cc.court_identifier = co.identifier
LEFT JOIN court_case_hearings cch
  ON cc.case_number = cch.case_number
  AND cc.court_identifier = cch.court_identifier
WHERE cc.case_type LIKE '%भ्रष्टाचार%'
GROUP BY cc.case_number, cc.case_type, co.full_name_nepali
HAVING COUNT(cch.id) > 5
ORDER BY total_hearings DESC
LIMIT 10
```

#### 4. Search cases by party name

```sql
SELECT
  case_number,
  case_type,
  plaintiff,
  defendant,
  registration_date_bs
FROM court_cases
WHERE plaintiff ILIKE '%नेपाल सरकार%'
   OR defendant ILIKE '%नेपाल सरकार%'
ORDER BY registration_date_ad DESC
LIMIT 20
```

#### 5. Get judge statistics

```sql
SELECT
  judge_names,
  COUNT(*) as hearing_count,
  COUNT(DISTINCT case_number) as unique_cases
FROM court_case_hearings
WHERE judge_names IS NOT NULL
  AND hearing_date_ad >= '2024-01-01'
GROUP BY judge_names
ORDER BY hearing_count DESC
LIMIT 20
```

### submit_nes_change

Write an NES entity directly on the unified entity plane. There is no NES *queue*
— `CREATE` posts a JSON-LD document, `UPDATE` applies RFC 6902 patch ops.

**Parameters:**
- `action` (string, required): `CREATE` or `UPDATE`
- `change_description` (string, required): Human-readable summary of the change
- `document` (object, CREATE only): the JSON-LD / authoring entity document
- `ref` (string, UPDATE only): entity `@id` IRI or `prefix/slug`
- `patch_ops` (array, UPDATE only): RFC 6902 JSON Patch operations

**Example: `CREATE`** → `POST /api/entities`

```json
{
  "action": "CREATE",
  "document": {
    "prefix": "person",
    "slug": "pushpa-kamal-dahal",
    "type": "Person",
    "name": { "en": "Pushpa Kamal Dahal", "ne": "पुष्पकमल दाहाल" }
  },
  "change_description": "Create missing person entity for case linkage"
}
```

**Example: `UPDATE` (add a name)** → `PATCH /api/entities/person/sher-bahadur-deuba`

```json
{
  "action": "UPDATE",
  "ref": "person/sher-bahadur-deuba",
  "patch_ops": [
    { "op": "add", "path": "/name/en", "value": "S. B. Deuba" }
  ],
  "change_description": "Add common English alias used in reporting"
}
```

The tool returns the created (201) or updated (200) entity JSON-LD document.
Immutable paths (`@id`/`@type`/`@context`/version) are rejected by the API.

### upload_material_file

Attach a local file to a Material at `@id = /material/{source}/{ident}`. Streams
the file to object storage and appends a roled schema.org `MediaObject`; creates
the material if it does not yet exist (then `material_type` is required).

**Parameters:**
- `source` (string, required): material source segment of the IRI (e.g. `nkp`, `court`)
- `ident` (string, required): material ident segment of the IRI
- `file_path` (string, required): absolute path to the file on disk
- `role` (string, optional): `RAW` (default), `ALTERNATE`, or `PERMALINK`
- `material_type` (string, optional): required only when creating a new material

Returns the material JSON-LD (201 created / 200 updated).

### get_nes_entity_prefixes

Fetch the current list of valid NES entity prefixes.

**Parameters:**
- None

**Example response shape:**

```json
{
  "prefixes": [
    "person",
    "organization/political_party",
    "organization/nepal_govt/moha"
  ]
}
```

## Response Format

All queries return a JSON response:

```json
{
  "success": true,
  "data": {
    "columns": ["case_number", "case_type", "plaintiff"],
    "rows": [
      ["082-OA-0503", "भ्रष्टाचार", "नेपाल सरकार"],
      ["081-C4-3088", "चेक अनादर", "राम बहादुर"]
    ],
    "row_count": 2
  },
  "error": null,
  "query_time_ms": 45
}
```

Error response:

```json
{
  "success": false,
  "data": null,
  "error": "Only SELECT queries are allowed",
  "query_time_ms": 0
}
```

## Security & Limitations

### Allowed Operations
- ✅ SELECT queries only
- ✅ JOIN operations across allowed tables
- ✅ WHERE, GROUP BY, ORDER BY, LIMIT clauses
- ✅ Aggregate functions (COUNT, SUM, AVG, etc.)

### Forbidden Operations
- ❌ INSERT, UPDATE, DELETE
- ❌ DROP, CREATE, ALTER
- ❌ TRUNCATE, GRANT, REVOKE
- ❌ Access to `scraped_dates` table

### Allowed Tables
- `courts` - Court information
- `court_cases` - Case metadata
- `court_case_hearings` - Hearing records
- `court_case_entities` - Party information

## Development

### Running Tests

```bash
poetry run pytest -v
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

## Troubleshooting

### "JAWAFDEHI_API_TOKEN environment variable is required"

Make sure you've set the API token:

```bash
export JAWAFDEHI_API_TOKEN="your-jawafdehi-api-token"
```

### "Only SELECT queries are allowed"

The server only accepts read-only SELECT queries. Remove any INSERT, UPDATE, DELETE, or other write operations.

### "Access to 'scraped_dates' table is not allowed"

The `scraped_dates` table is excluded from queries. Use only the allowed tables listed above.

### Query timeout

The upstream proxy API currently enforces a maximum timeout of 15 seconds.
Keep `timeout` between 1 and 15:

```json
{
  "query": "SELECT * FROM court_cases LIMIT 1000",
  "timeout": 15
}
```

## Support

For issues or questions, please open an issue on the Jawafdehi.org GitHub repository.
