"""Tests for the legacy LikhitExtractTool compatibility wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from jawafdehi_mcp.tools.likhit_extract import LikhitExtractTool


class TestLikhitExtractTool:
    """Test LikhitExtractTool properties and execution."""

    def setup_method(self):
        self.tool = LikhitExtractTool()

    def test_tool_name(self):
        assert self.tool.name == "likhit_extract"

    def test_tool_has_description(self):
        assert "Deprecated compatibility wrapper" in self.tool.description

    def test_input_schema_required_fields(self):
        schema = self.tool.input_schema
        assert "file_path" in schema["properties"]
        assert schema["required"] == ["file_path"]

    def test_input_schema_optional_fields(self):
        schema = self.tool.input_schema
        assert "output_path" in schema["properties"]
        assert "doc_type" not in schema["properties"]

    @pytest.mark.asyncio
    async def test_missing_file_path(self):
        result = await self.tool.execute({})
        assert len(result) == 1
        assert "Error" in result[0].text
        assert "required" in result[0].text

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tmp_path):
        result = await self.tool.execute(
            {"file_path": str(tmp_path / "nonexistent_likhit_test.pdf")}
        )
        assert len(result) == 1
        assert "File not found" in result[0].text

    @pytest.mark.asyncio
    async def test_path_is_directory(self, tmp_path):
        result = await self.tool.execute({"file_path": str(tmp_path)})
        assert len(result) == 1
        assert "not a file" in result[0].text

    @pytest.mark.asyncio
    async def test_rejects_non_pdf_file(self, tmp_path):
        docx_file = tmp_path / "sample.docx"
        docx_file.write_bytes(b"fake docx content")

        result = await self.tool.execute({"file_path": str(docx_file)})

        assert len(result) == 1
        assert "only supports local PDF files" in result[0].text

    @pytest.mark.asyncio
    async def test_successful_conversion(self, tmp_path):
        """Test successful conversion writes a sibling markdown file."""
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")
        output_file = tmp_path / "sample.md"

        fake_markdown = "# Converted\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.likhit_extract.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter
            result = await self.tool.execute({"file_path": str(pdf_file)})

        assert len(result) == 1
        assert "Markdown written to" in result[0].text
        assert fake_markdown in result[0].text
        mock_markitdown.assert_called_once_with(enable_plugins=True)
        mock_converter.convert_uri.assert_called_once_with(pdf_file.resolve().as_uri())
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == fake_markdown

    @pytest.mark.asyncio
    async def test_successful_conversion_with_output_path(self, tmp_path):
        """Test that output_path writes the markdown to disk."""
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")
        output_file = tmp_path / "output" / "result.md"

        fake_markdown = "# Converted\n"

        mock_result = MagicMock()
        mock_result.markdown = fake_markdown

        with patch(
            "jawafdehi_mcp.tools.likhit_extract.MarkItDown"
        ) as mock_markitdown:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_result
            mock_markitdown.return_value = mock_converter
            result = await self.tool.execute(
                {"file_path": str(pdf_file), "output_path": str(output_file)}
            )

        assert len(result) == 1
        assert "Markdown written to" in result[0].text
        assert fake_markdown in result[0].text
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == fake_markdown

    @pytest.mark.asyncio
    async def test_likhit_error_propagation(self, tmp_path):
        """Test that MarkItDown errors are reported as user-friendly messages."""
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"not a real pdf")

        with patch(
            "jawafdehi_mcp.tools.likhit_extract.MarkItDown",
            side_effect=Exception("Unsupported input format"),
        ):
            result = await self.tool.execute({"file_path": str(pdf_file)})

        assert len(result) == 1
        assert "Error extracting document" in result[0].text
        assert "Unsupported input format" in result[0].text
