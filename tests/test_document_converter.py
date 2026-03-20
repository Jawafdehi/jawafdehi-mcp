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
        assert "smart auto-detection" in self.tool.description
        assert "Likhit" in self.tool.description
        assert "MarkItDown" in self.tool.description
        assert "CIAA" in self.tool.description

    def test_input_schema_has_all_fields(self):
        schema = self.tool.input_schema
        expected_fields = [
            "file_path",
            "uri",
            "doc_type",
            "output_path",
            "title",
            "publication_date",
            "source_url",
            "pages",
            "enable_plugins",
        ]
        for field in expected_fields:
            assert field in schema["properties"]

    def test_input_schema_no_required_fields(self):
        """All fields are optional to support both Likhit and MarkItDown."""
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
    async def test_nonexistent_file(self):
        result = await self.tool.execute(
            {"file_path": "/tmp/nonexistent_unified_test.pdf"}
        )
        assert len(result) == 1
        assert "File not found" in result[0].text

    @pytest.mark.asyncio
    async def test_path_is_directory(self, tmp_path):
        result = await self.tool.execute({"file_path": str(tmp_path)})
        assert len(result) == 1
        assert "not a file" in result[0].text

    @pytest.mark.asyncio
    async def test_likhit_conversion_success(self, tmp_path):
        """Test successful Likhit conversion for CIAA press release."""
        pdf_file = tmp_path / "ciaa.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        fake_markdown = "---\ntitle: CIAA Press Release\n---\n\nContent\n"

        with patch(
            "jawafdehi_mcp.tools.document_converter.likhit.convert",
            return_value=fake_markdown,
        ) as mock_convert:
            result = await self.tool.execute(
                {
                    "file_path": str(pdf_file),
                    "doc_type": "ciaa-press-release",
                    "title": "Test Press Release",
                }
            )

        assert len(result) == 1
        assert "Likhit" in result[0].text
        assert fake_markdown in result[0].text
        mock_convert.assert_called_once_with(str(pdf_file))

    @pytest.mark.asyncio
    async def test_likhit_fallback_to_markitdown(self, tmp_path):
        """Test fallback to MarkItDown when Likhit fails."""
        pdf_file = tmp_path / "ciaa.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        markitdown_markdown = "# Fallback Content\n"
        mock_md_result = MagicMock()
        mock_md_result.markdown = markitdown_markdown

        with (
            patch(
                "jawafdehi_mcp.tools.document_converter.likhit.convert",
                side_effect=Exception("Likhit extraction failed"),
            ),
            patch(
                "jawafdehi_mcp.tools.document_converter.MarkItDown"
            ) as mock_markitdown,
        ):
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = mock_md_result
            mock_markitdown.return_value = mock_converter

            result = await self.tool.execute(
                {"file_path": str(pdf_file), "doc_type": "ciaa-press-release"}
            )

        assert len(result) == 1
        assert "fallback" in result[0].text.lower()
        assert "MarkItDown" in result[0].text
        assert markitdown_markdown in result[0].text

    @pytest.mark.asyncio
    async def test_markitdown_direct_with_file_path(self, tmp_path):
        """Test direct MarkItDown usage with file_path (doc_type='auto')."""
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

            result = await self.tool.execute(
                {"file_path": str(docx_file), "doc_type": "auto"}
            )

        assert len(result) == 1
        assert "MarkItDown" in result[0].text
        assert fake_markdown in result[0].text
        mock_converter.convert_uri.assert_called_once()
        call_args = mock_converter.convert_uri.call_args[0][0]
        assert call_args == docx_file.resolve().as_uri()

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
        assert "MarkItDown" in result[0].text
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
    async def test_enable_plugins_parameter(self):
        """Test that enable_plugins is passed to MarkItDown."""
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
                {"uri": "https://example.com/doc.pdf", "enable_plugins": True}
            )

        mock_markitdown.assert_called_once_with(enable_plugins=True)

    @pytest.mark.asyncio
    async def test_file_uri_conversion(self, tmp_path):
        """Test that file:// URIs are properly handled."""
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

            result = await self.tool.execute({"uri": f"file://{pdf_file}"})

        assert len(result) == 1
        assert "MarkItDown" in result[0].text
        assert "Error" not in result[0].text
        mock_converter.convert_uri.assert_called_once_with(pdf_file.resolve().as_uri())

    @pytest.mark.asyncio
    async def test_localhost_file_uri_conversion(self, tmp_path):
        """file://localhost URIs should resolve to local filesystem paths."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        fake_markdown = "# Test\n"
        mock_result = MagicMock()
        mock_result.markdown = fake_markdown
        localhost_uri = f"file://localhost{pdf_file.resolve().as_uri()[7:]}"

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
    async def test_rejects_remote_file_uri_netloc(self):
        """Remote file URIs should be rejected before path validation."""
        result = await self.tool.execute({"uri": "file://example.com/test.pdf"})

        assert len(result) == 1
        assert "Unsupported file URI" in result[0].text

    @pytest.mark.asyncio
    async def test_likhit_parameters_ignored_by_new_api(self, tmp_path):
        """The current public likhit API only accepts a file path."""
        pdf_file = tmp_path / "ciaa.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        with patch(
            "jawafdehi_mcp.tools.document_converter.likhit.convert",
            return_value="# Converted\n",
        ) as mock_convert:
            await self.tool.execute(
                {
                    "file_path": str(pdf_file),
                    "doc_type": "ciaa-press-release",
                    "title": "Custom Title",
                    "publication_date": "2024-01-15",
                    "source_url": "https://ciaa.gov.np/123",
                    "pages": "1-3",
                }
            )

        mock_convert.assert_called_once_with(str(pdf_file))

    @pytest.mark.asyncio
    async def test_default_doc_type_auto(self, tmp_path):
        """Test that omitting doc_type defaults to 'auto' (MarkItDown)."""
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

            result = await self.tool.execute({"file_path": str(pdf_file)})

        assert len(result) == 1
        assert "MarkItDown" in result[0].text
        assert "Likhit" not in result[0].text
