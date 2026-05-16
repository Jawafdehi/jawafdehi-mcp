"""Tests for per-user tool gating in jawafdehi-mcp."""

from jawafdehi_mcp.identity import (
    PUBLIC_READ_ONLY_TOOL_NAMES,
    current_user_identity,
    get_allowed_tool_names,
    role_has_write_access,
)
from jawafdehi_mcp.server import (
    ALL_TOOL_NAMES,
    TOOL_MAP,
    _get_allowed_tools,
    _has_api_token,
    _is_tool_allowed,
)


class TestHasApiToken:
    def test_has_token_when_set(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token-123")
        assert _has_api_token() is True

    def test_has_no_token_when_unset(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)
        assert _has_api_token() is False

    def test_has_no_token_when_empty(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "")
        assert _has_api_token() is False

    def test_has_no_token_when_whitespace(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "   ")
        assert _has_api_token() is False


class TestRoleHasWriteAccess:
    def test_contributor_has_write_access(self):
        assert role_has_write_access(["Contributor"]) is True

    def test_empty_roles_no_write_access(self):
        assert role_has_write_access([]) is False

    def test_unknown_role_no_write_access(self):
        assert role_has_write_access(["SomeOtherRole"]) is False

    def test_contributor_with_extra_roles(self):
        assert role_has_write_access(["Contributor", "Editor"]) is True


class TestGetAllowedToolNames:
    def test_no_identity_returns_only_public(self):
        all_names = set(TOOL_MAP.keys())
        result = get_allowed_tool_names(None, all_names)
        assert result == PUBLIC_READ_ONLY_TOOL_NAMES

    def test_caseworker_identity_returns_all(self):
        all_names = set(TOOL_MAP.keys())
        identity = {"user_id": 1, "username": "test", "roles": ["Contributor"]}
        result = get_allowed_tool_names(identity, all_names)
        assert result == all_names

    def test_non_caseworker_identity_returns_public(self):
        all_names = set(TOOL_MAP.keys())
        identity = {"user_id": 2, "username": "public", "roles": []}
        result = get_allowed_tool_names(identity, all_names)
        assert result == PUBLIC_READ_ONLY_TOOL_NAMES

    def test_identity_no_roles_returns_public(self):
        all_names = set(TOOL_MAP.keys())
        identity = {"user_id": 3, "username": "noroles"}
        result = get_allowed_tool_names(identity, all_names)
        assert result == PUBLIC_READ_ONLY_TOOL_NAMES


class TestAllowedTools:
    def test_no_identity_no_token_returns_public(self, monkeypatch):
        """No identity, no token: only public tools."""
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)
        current_user_identity.set(None)
        tools = _get_allowed_tools()
        tool_names = {t.name for t in tools}
        assert tool_names == PUBLIC_READ_ONLY_TOOL_NAMES
        assert len(tools) == 12

    def test_token_mode_no_user_returns_all(self, monkeypatch):
        """Token present but no identity: all tools."""
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        current_user_identity.set(None)
        tools = _get_allowed_tools()
        assert len(tools) == len(TOOL_MAP)

    def test_token_only_no_identity_returns_all(self, monkeypatch):
        """Token present but no identity (API down): falls to token branch → all tools."""
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        current_user_identity.set(None)
        tools = _get_allowed_tools()
        assert len(tools) == len(TOOL_MAP)

    def test_caseworker_identity_returns_all(self, monkeypatch):
        """Caseworker with Contributor role gets all tools."""
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        identity = {"user_id": 1, "username": "worker", "roles": ["Contributor"]}
        current_user_identity.set(identity)
        try:
            tools = _get_allowed_tools()
            assert len(tools) == len(TOOL_MAP)
        finally:
            current_user_identity.set(None)

    def test_public_user_identity_returns_public(self, monkeypatch):
        """Non-caseworker gets public tools only."""
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        identity = {"user_id": 2, "username": "public", "roles": []}
        current_user_identity.set(identity)
        try:
            tools = _get_allowed_tools()
            tool_names = {t.name for t in tools}
            assert tool_names == PUBLIC_READ_ONLY_TOOL_NAMES
        finally:
            current_user_identity.set(None)


class TestIsToolAllowed:
    def test_public_tool_allowed_without_token(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)
        current_user_identity.set(None)
        assert _is_tool_allowed("search_jawafdehi_cases") is True

    def test_write_tool_blocked_without_token(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)
        current_user_identity.set(None)
        assert _is_tool_allowed("create_jawafdehi_case") is False

    def test_write_tool_allowed_for_caseworker(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        identity = {"user_id": 1, "username": "cw", "roles": ["Contributor"]}
        current_user_identity.set(identity)
        try:
            assert _is_tool_allowed("create_jawafdehi_case") is True
        finally:
            current_user_identity.set(None)

    def test_write_tool_blocked_for_public_identity(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        identity = {"user_id": 2, "username": "pub", "roles": []}
        current_user_identity.set(identity)
        try:
            assert _is_tool_allowed("create_jawafdehi_case") is False
        finally:
            current_user_identity.set(None)

    def test_write_tool_allowed_with_token_only(self, monkeypatch):
        """Token present + no forwarded identity: all tools allowed."""
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        current_user_identity.set(None)
        assert _is_tool_allowed("create_jawafdehi_case") is True


class TestPublicToolSetIntegrity:
    def test_all_public_tools_exist_in_tool_map(self):
        for name in PUBLIC_READ_ONLY_TOOL_NAMES:
            assert name in TOOL_MAP, f"Public tool '{name}' not found in TOOL_MAP"

    def test_public_tools_are_read_only(self):
        write_tool_names = {
            "create_jawafdehi_case",
            "patch_jawafdehi_case",
            "submit_nes_change",
            "create_jawaf_entity",
            "upload_document_source",
            "ngm_extract_case_data",
        }
        assert PUBLIC_READ_ONLY_TOOL_NAMES.isdisjoint(write_tool_names)

    def test_private_tools_not_in_public_set(self):
        private_tools = set(TOOL_MAP.keys()) - PUBLIC_READ_ONLY_TOOL_NAMES
        assert len(private_tools) > 0
        assert "create_jawafdehi_case" in private_tools
        assert "upload_document_source" in private_tools

    def test_all_tool_names_count(self):
        assert len(ALL_TOOL_NAMES) == len(set(TOOL_MAP.keys()))

    def test_public_tools_count(self):
        assert len(PUBLIC_READ_ONLY_TOOL_NAMES) == 12
