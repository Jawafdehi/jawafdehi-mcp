"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set up mock environment variables for all tests."""
    monkeypatch.setenv(
        "NGM_DATABASE_URL", "postgresql://test:test@localhost:5432/test_ngm"
    )
