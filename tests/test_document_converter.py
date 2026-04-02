"""Tests for the unified DocumentConverterTool."""

from unittest.mock import MagicMock, patch

import pytest

from jawafdehi_mcp.tools.document_converter import DocumentConverterTool


class TestDocumentConverterTool:
    """Test DocumentConverterTool properties and execution."""

    def setup_method(self):
        self.tool = DocumentConverterTool()

    def test_tool_name(self):
        assert self.tool.name == "convert_to_markdown"

    def test_tool_has_description(self):
        assert "MarkItDown" in self.tool.description
        assert "plugins enabled by default" in self.tool.description
        assert "`likhit` plugin" in self.tool.description

    def test_input_schema_has_all_fields(self):
        schema = self.tool.input_schema
        expected_fields = [
            "file_path",
            "uri",
            "output_path",
            "enable_plugins",
        ]
        for field in expected_fields:
            assert field in schema["properties"]

        assert "doc_type" not in schema["properties"]
        assert "title" not in schema["properties"]

    def test_input_schema_no_required_fields(self):
        """All fields are optional to support both file paths and URIs."""
        schema = self.tool.input_schema
        assert schema["required"] == []

    @pytest.mark.asyncio
    async def test_missing_both_file_path_and_uri(self):
        result = await self.tool.execute({})
        assert len(result) == 1
        assert "Error" in result[0].text
        assert "file_path" in result[0].text or "uri" in result[0].text

    @pytest.mark.asyncio
    async def test_both_file_path_and_uri_provided(self):
        result = await self.tool.execute(
            {"file_path": "/tmp/test.pdf", "uri": "https://example.com/doc.pdf"}
        )
        assert len(result) == 1
        assert "Error" in result[0].text
        assert "both" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tmp_path):
        result = await self.tool.execute(
            {"file_path": str(tmp_path / "nonexistent_unified_test.pdf")}
        )
        assert len(result) == 1
        assert "File not found" in result[0].text

    @pytest.mark.asyncio
    async def test_path_is_directory(self, tmp_path):
        result = await self.tool.execute({"file_path": str(tmp_path)})
        assert len(result) == 1
        assert "not a file" in result[0].text

    @pytest.mark.asyncio
    async def test_local_pdf_uses_markitdown_with_plugins_by_default(self, tmp_path):
        """Local PDFs should route through MarkItDown and return markdown by default."""
        pdf_file = tmp_path / "ciaa.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        fake_markdown = "# Converted with plugin\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter
            result = await self.tool.execute({"file_path": str(pdf_file)})

        assert len(result) == 1
        assert "MarkItDown + plugins" in result[0].text
        assert fake_markdown in result[0].text
        mock_markitdown.assert_called_once_with(enable_plugins=True)
        mock_converter.convert_uri.assert_called_once_with(pdf_file.resolve().as_uri())

    @pytest.mark.asyncio
    async def test_markitdown_direct_with_file_path(self, tmp_path):
        """Non-PDF local files should still use MarkItDown and return markdown."""
        docx_file = tmp_path / "document.docx"
        docx_file.write_bytes(b"fake docx content")

        fake_markdown = "# Document Title\n\nContent\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute({"file_path": str(docx_file)})

        assert len(result) == 1
        assert "MarkItDown + plugins" in result[0].text
        assert fake_markdown in result[0].text
        mock_converter.convert_uri.assert_called_once()
        call_args = mock_converter.convert_uri.call_args[0][0]
        assert call_args == docx_file.resolve().as_uri()

    @pytest.mark.asyncio
    async def test_legacy_doc_uses_unified_plugin_enabled_path(self, tmp_path):
        """Legacy DOC files should be accepted by the unified MarkItDown path."""
        doc_file = tmp_path / "legacy.doc"
        doc_file.write_bytes(b"fake doc content")

        fake_markdown = "# Legacy Doc\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute({"file_path": str(doc_file)})

        assert len(result) == 1
        assert fake_markdown in result[0].text
        mock_markitdown.assert_called_once_with(enable_plugins=True)
        mock_converter.convert_uri.assert_called_once_with(doc_file.resolve().as_uri())

    @pytest.mark.asyncio
    async def test_markitdown_with_uri(self):
        """Test MarkItDown with web URI."""
        fake_markdown = "# Web Document\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute(
                {"uri": "https://example.com/document.pdf"}
            )

        assert len(result) == 1
        assert "MarkItDown + plugins" in result[0].text
        assert fake_markdown in result[0].text
        mock_converter.convert_uri.assert_called_once_with(
            "https://example.com/document.pdf"
        )

    @pytest.mark.asyncio
    async def test_output_path_writing(self, tmp_path):
        """Test that output_path writes markdown to disk without including content in response."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")
        output_file = tmp_path / "output" / "result.md"

        fake_markdown = "# Test\n"

        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter
            result = await self.tool.execute(
                {"file_path": str(pdf_file), "output_path": str(output_file)}
            )

        assert len(result) == 1
        assert "written to" in result[0].text.lower()
        assert fake_markdown not in result[0].text
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == fake_markdown

    @pytest.mark.asyncio
    async def test_enable_plugins_defaults_to_true(self):
        """Plugin-backed conversion is enabled by default."""
        fake_markdown = "# Test\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            await self.tool.execute({"uri": "https://example.com/doc.pdf"})

        mock_markitdown.assert_called_once_with(enable_plugins=True)

    @pytest.mark.asyncio
    async def test_enable_plugins_false_bypasses_plugins(self):
        """Explicitly disabling plugins should be passed through."""
        fake_markdown = "# Test\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            await self.tool.execute(
                {"uri": "https://example.com/doc.pdf", "enable_plugins": False}
            )

        mock_markitdown.assert_called_once_with(enable_plugins=False)

    @pytest.mark.asyncio
    async def test_file_uri_conversion(self, tmp_path):
        """Test that file:// URIs are converted and returned directly."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        fake_markdown = "# Test\n"

        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter
            result = await self.tool.execute({"uri": pdf_file.resolve().as_uri()})

        assert len(result) == 1
        assert "MarkItDown + plugins" in result[0].text
        assert "Error" not in result[0].text
        assert fake_markdown in result[0].text
        mock_converter.convert_uri.assert_called_once_with(pdf_file.resolve().as_uri())

    @pytest.mark.asyncio
    async def test_rejects_output_path_matching_source_file(self, tmp_path):
        """Explicit output_path must not overwrite the source file."""
        markdown_file = tmp_path / "already.md"
        markdown_file.write_text("# Existing\n", encoding="utf-8")

        fake_markdown = "# Converted\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute(
                {
                    "file_path": str(markdown_file),
                    "output_path": str(markdown_file),
                }
            )

        assert len(result) == 1
        assert "output_path must differ from the source file" in result[0].text
        assert markdown_file.read_text(encoding="utf-8") == "# Existing\n"

    @pytest.mark.asyncio
    async def test_localhost_file_uri_conversion(self, tmp_path):
        """file://localhost URIs should resolve to local filesystem paths."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")
        localhost_uri = f"file://localhost{pdf_file.resolve().as_uri()[7:]}"

        mock_result = MagicMock()
        mock_result.markdown = "# Test\n"

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter
            result = await self.tool.execute({"uri": localhost_uri})

        assert len(result) == 1
        assert "Error" not in result[0].text
        mock_converter.convert_uri.assert_called_once_with(pdf_file.resolve().as_uri())

    @pytest.mark.asyncio
    async def test_uppercase_file_uri_conversion(self, tmp_path):
        """FILE:// URIs should be treated as file URIs."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")
        uppercase_uri = pdf_file.resolve().as_uri().replace("file://", "FILE://", 1)

        mock_result = MagicMock()
        mock_result.markdown = "# Test\n"

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter
            result = await self.tool.execute({"uri": uppercase_uri})

        assert len(result) == 1
        assert "Error" not in result[0].text
        mock_converter.convert_uri.assert_called_once_with(pdf_file.resolve().as_uri())

    @pytest.mark.asyncio
    async def test_uppercase_https_uri_uses_markitdown(self):
        """HTTPS:// URIs should still be treated as web URIs."""
        fake_markdown = "# Web Document\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.document_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute(
                {"uri": "HTTPS://example.com/document.pdf"}
            )

        assert len(result) == 1
        assert "MarkItDown" in result[0].text
        mock_converter.convert_uri.assert_called_once_with(
            "HTTPS://example.com/document.pdf"
        )

    @pytest.mark.asyncio
    async def test_rejects_remote_file_uri_netloc(self):
        """Remote file URIs should be rejected before path validation."""
        result = await self.tool.execute({"uri": "file://example.com/test.pdf"})

        assert len(result) == 1
        assert "Unsupported file URI" in result[0].text
