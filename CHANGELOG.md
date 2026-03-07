# Changelog

All notable changes to the Jawafdehi MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-07

### Added
- Initial release of Jawafdehi MCP Server
- `ngm_query_judicial` tool for querying Nepal's judicial database
- Support for SELECT queries against NGM court tables:
  - `courts` - Court information
  - `court_cases` - Case metadata
  - `court_case_hearings` - Hearing records
  - `court_case_entities` - Party information
- Query validation to ensure read-only access
- Environment variable validation for `NGM_DATABASE_URL`
- Comprehensive unit tests for validation logic
- CI/CD pipeline with GitHub Actions
- Linting with black, isort, and flake8
- Documentation: README, USAGE guide, and tool specifications
- MIT License

### Security
- Read-only database access (SELECT queries only)
- Forbidden operations: INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT, REVOKE
- Excluded `scraped_dates` table from queries
- Query timeout protection (default 15 seconds)
- PostgreSQL connection validation

[0.1.0]: https://github.com/NewNepal-org/jawafdehi-mcp/releases/tag/v0.1.0
