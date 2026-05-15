"""Tests for the identity resolution module."""

import pytest

from jawafdehi_mcp.identity import (
    CASEWORKER_ROLE_NAMES,
    PUBLIC_READ_ONLY_TOOL_NAMES,
    get_allowed_tool_names,
    resolve_user_identity,
    role_has_write_access,
)


class TestRoleHasWriteAccess:
    def test_contributor_role_has_access(self):
        assert role_has_write_access(["Contributor"]) is True

    def test_multiple_roles_with_contributor(self):
        assert role_has_write_access(["Viewer", "Contributor", "Editor"]) is True

    def test_empty_roles_no_access(self):
        assert role_has_write_access([]) is False

    def test_non_caseworker_roles_no_access(self):
        assert role_has_write_access(["Viewer", "Editor"]) is False

    def test_admin_role_has_access(self):
        assert role_has_write_access(["Admin"]) is True

    def test_moderator_role_has_access(self):
        assert role_has_write_access(["Moderator"]) is True

    def test_nonexistent_role_no_access(self):
        assert role_has_write_access(["Administrator"]) is False

    def test_caseworker_role_names_contains_expected_roles(self):
        assert "Contributor" in CASEWORKER_ROLE_NAMES
        assert "Admin" in CASEWORKER_ROLE_NAMES
        assert "Moderator" in CASEWORKER_ROLE_NAMES
        assert len(CASEWORKER_ROLE_NAMES) == 3


class TestGetAllowedToolNames:
    ALL_TOOLS = {
        "search_jawafdehi_cases",
        "get_jawafdehi_case",
        "create_jawafdehi_case",
        "patch_jawafdehi_case",
        "submit_nes_change",
    }

    def test_none_identity_returns_public_tools(self):
        result = get_allowed_tool_names(None, self.ALL_TOOLS)
        assert result == PUBLIC_READ_ONLY_TOOL_NAMES & self.ALL_TOOLS

    def test_caseworker_identity_returns_all_tools(self):
        identity = {"user_id": "cw-1", "username": "cw", "roles": ["Contributor"]}
        result = get_allowed_tool_names(identity, self.ALL_TOOLS)
        assert result == self.ALL_TOOLS

    def test_public_identity_returns_public_tools(self):
        identity = {"user_id": "pub-1", "username": "pub", "roles": []}
        result = get_allowed_tool_names(identity, self.ALL_TOOLS)
        assert result == PUBLIC_READ_ONLY_TOOL_NAMES & self.ALL_TOOLS
        assert "create_jawafdehi_case" not in result

    def test_identity_with_no_roles_key(self):
        identity = {"user_id": "x-1", "username": "x"}
        result = get_allowed_tool_names(identity, self.ALL_TOOLS)
        assert result == PUBLIC_READ_ONLY_TOOL_NAMES & self.ALL_TOOLS

    def test_respects_all_tool_names_boundary(self):
        """Tools not in all_tool_names are never returned."""
        limited_tools = {"search_jawafdehi_cases", "get_jawafdehi_case"}
        identity = {"user_id": "cw-2", "username": "cw2", "roles": ["Contributor"]}
        result = get_allowed_tool_names(identity, limited_tools)
        assert result == limited_tools

    def test_public_tools_set_does_not_include_write_tools(self):
        write_tools = {
            "create_jawafdehi_case",
            "patch_jawafdehi_case",
            "submit_nes_change",
            "create_jawaf_entity",
            "upload_document_source",
            "ngm_extract_case_data",
        }
        assert PUBLIC_READ_ONLY_TOOL_NAMES.isdisjoint(write_tools)


@pytest.mark.asyncio
class TestResolveUserIdentity:
    async def test_returns_none_when_no_token(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)
        result = await resolve_user_identity("test-user")
        assert result is None

    async def test_returns_none_when_token_empty(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "")
        result = await resolve_user_identity("test-user")
        assert result is None

    async def test_returns_none_on_http_error(self, monkeypatch):
        from unittest.mock import AsyncMock, patch

        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        with patch("jawafdehi_mcp.identity.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("connection refused")
            )
            result = await resolve_user_identity("test-user")
        assert result is None

    async def test_returns_identity_on_success(self, monkeypatch):
        from unittest.mock import patch

        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        expected = {
            "user_id": "42",
            "username": "caseworker1",
            "roles": ["Contributor"],
        }

        class MockResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return expected

        async def mock_get(*args, **kwargs):
            return MockResponse()

        with patch("jawafdehi_mcp.identity.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get
            result = await resolve_user_identity("owui-user-1")
        assert result == expected
