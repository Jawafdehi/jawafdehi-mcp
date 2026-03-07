"""Tests for query validation logic."""

import pytest

from jawafdehi_mcp.tools.ngm_judicial import NGMJudicialTool


class TestQueryValidation:
    """Test query validation rules."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = NGMJudicialTool()

    def test_valid_select_query(self):
        """Test that valid SELECT queries pass validation."""
        query = "SELECT * FROM courts"
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is True
        assert error is None

    def test_valid_join_query(self):
        """Test that valid JOIN queries pass validation."""
        query = """
            SELECT c.case_number, co.full_name_nepali
            FROM court_cases c
            JOIN courts co ON c.court_identifier = co.identifier
        """
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is True
        assert error is None

    def test_reject_insert_query(self):
        """Test that INSERT queries are rejected."""
        query = "INSERT INTO courts (identifier) VALUES ('test')"
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is False
        assert "only select" in error.lower()

    def test_reject_update_query(self):
        """Test that UPDATE queries are rejected."""
        query = "UPDATE courts SET full_name_nepali = 'test'"
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is False
        assert "only select" in error.lower()

    def test_reject_delete_query(self):
        """Test that DELETE queries are rejected."""
        query = "DELETE FROM courts WHERE identifier = 'test'"
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is False
        assert "only select" in error.lower()

    def test_reject_drop_query(self):
        """Test that DROP queries are rejected."""
        query = "DROP TABLE courts"
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is False
        assert "only select" in error.lower()

    def test_reject_scraped_dates_table(self):
        """Test that queries to scraped_dates table are rejected."""
        query = "SELECT * FROM scraped_dates"
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is False
        assert "scraped_dates" in error.lower()

    def test_reject_invalid_table(self):
        """Test that queries to non-allowed tables are rejected."""
        query = "SELECT * FROM users"
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is False
        assert "invalid table" in error.lower()

    def test_case_insensitive_validation(self):
        """Test that validation is case-insensitive."""
        query = "SELECT * FROM COURTS"
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is True
        assert error is None

    def test_complex_valid_query(self):
        """Test complex but valid query."""
        query = """
            SELECT
                cc.case_number,
                cc.case_type,
                co.full_name_nepali,
                COUNT(cch.id) as hearing_count
            FROM court_cases cc
            JOIN courts co ON cc.court_identifier = co.identifier
            LEFT JOIN court_case_hearings cch
                ON cc.case_number = cch.case_number
            WHERE cc.case_type LIKE '%भ्रष्टाचार%'
            GROUP BY cc.case_number, cc.case_type, co.full_name_nepali
            ORDER BY hearing_count DESC
            LIMIT 10
        """
        is_valid, error = self.tool._validate_query(query)
        assert is_valid is True
        assert error is None


class TestEnvironmentValidation:
    """Test environment variable validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = NGMJudicialTool()

    def test_missing_database_url(self, monkeypatch):
        """Test that missing NGM_DATABASE_URL raises error."""
        monkeypatch.delenv("NGM_DATABASE_URL", raising=False)

        with pytest.raises(ValueError, match="NGM_DATABASE_URL.*required"):
            self.tool._validate_environment()

    def test_invalid_database_url(self, monkeypatch):
        """Test that non-PostgreSQL URL raises error."""
        monkeypatch.setenv("NGM_DATABASE_URL", "mysql://user:pass@host/db")

        with pytest.raises(ValueError, match="must be a PostgreSQL"):
            self.tool._validate_environment()

    def test_valid_postgres_url(self, monkeypatch):
        """Test that valid PostgreSQL URL passes validation."""
        url = "postgresql://user:pass@localhost:5432/ngm"
        monkeypatch.setenv("NGM_DATABASE_URL", url)

        result = self.tool._validate_environment()
        assert result == url

    def test_valid_postgres_url_short_form(self, monkeypatch):
        """Test that postgres:// (short form) passes validation."""
        url = "postgres://user:pass@localhost:5432/ngm"
        monkeypatch.setenv("NGM_DATABASE_URL", url)

        result = self.tool._validate_environment()
        assert result == url
