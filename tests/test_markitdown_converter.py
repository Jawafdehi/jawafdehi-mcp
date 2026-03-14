"""Tests for the MarkItDownConverterTool."""

from unittest.mock import MagicMock, patch

import pytest

from jawafdehi_mcp.tools.markitdown_converter import MarkItDownConverterTool


class TestMarkItDownConverterTool:
    """Test MarkItDownConverterTool properties and execution."""

    def setup_method(self):
        self.tool = MarkItDownConverterTool()

    def test_tool_name(self):
        assert self.tool.name == "convert_to_markdown"

    def test_tool_has_description(self):
        assert "Convert documents to Markdown" in self.tool.description
        assert "DOCX" in self.tool.description
        assert "WARNING" in self.tool.description
        assert "Nepali" in self.tool.description

    def test_input_schema_required_fields(self):
        schema = self.tool.input_schema
        assert "uri" in schema["properties"]
        assert schema["required"] == ["uri"]

    def test_input_schema_optional_fields(self):
        schema = self.tool.input_schema
        assert "output_path" in schema["properties"]
        assert "enable_plugins" in schema["properties"]

    @pytest.mark.asyncio
    async def test_missing_uri(self):
        result = await self.tool.execute({})
        assert len(result) == 1
        assert "Error" in result[0].text
        assert "required" in result[0].text

    @pytest.mark.asyncio
    async def test_nonexistent_file_uri(self):
        result = await self.tool.execute(
            {"uri": "file:///tmp/nonexistent_markitdown_test.pdf"}
        )
        assert len(result) == 1
        assert "File not found" in result[0].text

    @pytest.mark.asyncio
    async def test_file_uri_is_directory(self, tmp_path):
        result = await self.tool.execute({"uri": f"file://{tmp_path}"})
        assert len(result) == 1
        assert "not a file" in result[0].text

    @pytest.mark.asyncio
    async def test_successful_conversion_without_output(self):
        """Test successful conversion returning markdown directly."""
        fake_markdown = "# Test Document\n\nConverted content\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.markitdown_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute(
                {"uri": "https://example.com/document.docx"}
            )

        assert len(result) == 1
        assert result[0].text == fake_markdown
        mock_converter.convert_uri.assert_called_once_with(
            "https://example.com/document.docx"
        )

    @pytest.mark.asyncio
    async def test_successful_conversion_with_output_path(self, tmp_path):
        """Test that output_path writes the markdown to disk without including content in response."""
        output_file = tmp_path / "output" / "result.md"
        fake_markdown = "# Test Document\n\nConverted content\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.markitdown_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute(
                {
                    "uri": "https://example.com/document.docx",
                    "output_path": str(output_file),
                }
            )

        assert len(result) == 1
        assert "✅ Markdown written to" in result[0].text
        # Verify markdown content is NOT included in the response
        assert fake_markdown not in result[0].text
        # Verify file was written correctly
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == fake_markdown

    @pytest.mark.asyncio
    async def test_enable_plugins_parameter(self):
        """Test that enable_plugins parameter is passed correctly."""
        fake_markdown = "# Test\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.markitdown_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            await self.tool.execute(
                {"uri": "https://example.com/doc.pdf", "enable_plugins": True}
            )

        mock_markitdown.assert_called_once_with(enable_plugins=True)

    @pytest.mark.asyncio
    async def test_file_uri_validation(self, tmp_path):
        """Test that file:// URIs are validated before conversion."""
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        fake_markdown = "# PDF Content\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.markitdown_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute({"uri": f"file://{pdf_file}"})

        assert len(result) == 1
        assert result[0].text == fake_markdown

    @pytest.mark.asyncio
    async def test_markitdown_error_propagation(self):
        """Test that MarkItDown errors are reported as user-friendly messages."""
        with patch(
            "jawafdehi_mcp.tools.markitdown_converter.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.side_effect = Exception(
                "Unsupported file format"
            )
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute(
                {"uri": "https://example.com/unsupported.xyz"}
            )

        assert len(result) == 1
        assert "Error converting document" in result[0].text
        assert "Unsupported file format" in result[0].text
