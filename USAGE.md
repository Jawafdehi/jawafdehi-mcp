# Jawafdehi MCP Server - Usage Guide

## Quick Start

### 1. Install Dependencies

```bash
cd services/jawafdehi-mcp
poetry install
```

### 2. Set Environment Variable

```bash
export NGM_DATABASE_URL="postgresql://user:password@host:5432/ngm_database"
export JAWAFDEHI_API_TOKEN="your-drf-token"
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
        "NGM_DATABASE_URL": "postgresql://user:password@host:5432/database",
        "JAWAFDEHI_API_TOKEN": "your-drf-token"
      }
    }
  }
}
```

## Available Tools

### create_jawafdehi_case

Create a draft Jawafdehi case using a simplified authenticated payload.

**Parameters:**
- `title` (string, required)
- `case_type` (string, required): `CORRUPTION` or `PROMISES`
- `short_description` (string, optional)
- `description` (string, optional)

### patch_jawafdehi_case

Patch an existing Jawafdehi case using raw RFC 6902 JSON Patch operations.

**Parameters:**
- `case_id` (integer, required)
- `operations` (array, required)

### ngm_query_judicial

Execute SELECT queries against Nepal's judicial database.

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

### "NGM_DATABASE_URL environment variable is required"

Make sure you've set the environment variable:

```bash
export NGM_DATABASE_URL="postgresql://user:password@host:5432/database"
```

### "Only SELECT queries are allowed"

The server only accepts read-only SELECT queries. Remove any INSERT, UPDATE, DELETE, or other write operations.

### "Access to 'scraped_dates' table is not allowed"

The `scraped_dates` table is excluded from queries. Use only the allowed tables listed above.

### Query timeout

If your query takes too long, increase the timeout parameter:

```json
{
  "query": "SELECT * FROM court_cases LIMIT 1000",
  "timeout": 30
}
```

## Support

For issues or questions, please open an issue on the NewNepal.org GitHub repository.
