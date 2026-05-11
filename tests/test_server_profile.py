"""Tests for public/private MCP profile gating."""

from jawafdehi_mcp.server import (
    PUBLIC_READ_ONLY_TOOL_NAMES,
    TOOL_MAP,
    _get_available_tools,
    _is_public_mode,
)


class TestPublicModeDetection:
    def test_is_public_mode_when_token_unset(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)
        assert _is_public_mode() is True

    def test_is_not_public_mode_when_token_set(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token-123")
        assert _is_public_mode() is False

    def test_is_public_mode_when_token_empty(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "")
        assert _is_public_mode() is True

    def test_is_public_mode_when_token_whitespace(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "   ")
        assert _is_public_mode() is True


class TestAvailableTools:
    def test_public_mode_returns_only_read_only_tools(self, monkeypatch):
        monkeypatch.delenv("JAWAFDEHI_API_TOKEN", raising=False)
        tools = _get_available_tools()
        tool_names = {t.name for t in tools}
        assert tool_names == PUBLIC_READ_ONLY_TOOL_NAMES
        assert len(tools) == 12

    def test_private_mode_returns_all_tools(self, monkeypatch):
        monkeypatch.setenv("JAWAFDEHI_API_TOKEN", "test-token")
        tools = _get_available_tools()
        assert len(tools) == len(TOOL_MAP)

    def test_all_public_tools_exist_in_tool_map(self):
        for name in PUBLIC_READ_ONLY_TOOL_NAMES:
            assert name in TOOL_MAP, f"Public tool '{name}' not found in TOOL_MAP"

    def test_public_tools_are_read_only(self):
        """Verify that public tools don't include write tools."""
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
        """Verify that private-mode-only tools exist."""
        private_tools = set(TOOL_MAP.keys()) - PUBLIC_READ_ONLY_TOOL_NAMES
        assert len(private_tools) > 0
        assert "create_jawafdehi_case" in private_tools
        assert "upload_document_source" in private_tools
