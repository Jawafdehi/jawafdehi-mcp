"""Tests for the LikhitExtractTool."""

from unittest.mock import patch

import pytest

from jawafdehi_mcp.tools.likhit_extract import LikhitExtractTool


class TestLikhitExtractTool:
    """Test LikhitExtractTool properties and execution."""

    def setup_method(self):
        self.tool = LikhitExtractTool()

    def test_tool_name(self):
        assert self.tool.name == "likhit_extract"

    def test_tool_has_description(self):
        assert "Nepal government PDF" in self.tool.description
        assert "ciaa-press-release" in self.tool.description

    def test_input_schema_required_fields(self):
        schema = self.tool.input_schema
        assert "file_path" in schema["properties"]
        assert "doc_type" in schema["properties"]
        assert schema["required"] == ["file_path", "doc_type"]

    def test_input_schema_optional_fields(self):
        schema = self.tool.input_schema
        for field in (
            "title",
            "publication_date",
            "source_url",
            "pages",
            "output_path",
        ):
            assert field in schema["properties"]

    @pytest.mark.asyncio
    async def test_missing_file_path(self):
        result = await self.tool.execute({"doc_type": "ciaa-press-release"})
        assert len(result) == 1
        assert "Error" in result[0].text
        assert "required" in result[0].text

    @pytest.mark.asyncio
    async def test_missing_doc_type(self):
        result = await self.tool.execute({"file_path": "/tmp/test.pdf"})
        assert len(result) == 1
        assert "Error" in result[0].text
        assert "required" in result[0].text

    @pytest.mark.asyncio
    async def test_nonexistent_file(self):
        result = await self.tool.execute(
            {
                "file_path": "/tmp/nonexistent_likhit_test.pdf",
                "doc_type": "ciaa-press-release",
            }
        )
        assert len(result) == 1
        assert "File not found" in result[0].text

    @pytest.mark.asyncio
    async def test_path_is_directory(self, tmp_path):
        result = await self.tool.execute(
            {"file_path": str(tmp_path), "doc_type": "ciaa-press-release"}
        )
        assert len(result) == 1
        assert "not a file" in result[0].text

    @pytest.mark.asyncio
    async def test_successful_extraction(self, tmp_path):
        """Test successful extraction with mocked likhit."""
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        fake_markdown = "---\ntitle: Test\n---\n\nExtracted content\n"
        fake_extraction = object()

        with (
            patch(
                "jawafdehi_mcp.tools.likhit_extract.likhit.extract",
                return_value=fake_extraction,
            ) as mock_extract,
            patch(
                "jawafdehi_mcp.tools.likhit_extract.likhit_render_markdown",
                return_value=fake_markdown,
            ) as mock_render,
        ):
            result = await self.tool.execute(
                {
                    "file_path": str(pdf_file),
                    "doc_type": "ciaa-press-release",
                    "title": "Press Release",
                    "source_url": "https://ciaa.gov.np/press/123",
                }
            )

        assert len(result) == 1
        assert result[0].text == fake_markdown
        mock_extract.assert_called_once_with(
            str(pdf_file),
            "ciaa-press-release",
            title="Press Release",
            publication_date=None,
            source_url="https://ciaa.gov.np/press/123",
            pages=None,
        )
        mock_render.assert_called_once_with(fake_extraction)

    @pytest.mark.asyncio
    async def test_successful_extraction_with_output_path(self, tmp_path):
        """Test that output_path writes the markdown to disk."""
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")
        output_file = tmp_path / "output" / "result.md"

        fake_markdown = "---\ntitle: Test\n---\n\nExtracted content\n"

        with (
            patch(
                "jawafdehi_mcp.tools.likhit_extract.likhit.extract",
                return_value=object(),
            ),
            patch(
                "jawafdehi_mcp.tools.likhit_extract.likhit_render_markdown",
                return_value=fake_markdown,
            ),
        ):
            result = await self.tool.execute(
                {
                    "file_path": str(pdf_file),
                    "doc_type": "ciaa-press-release",
                    "output_path": str(output_file),
                }
            )

        assert len(result) == 1
        assert "Markdown written to" in result[0].text
        assert fake_markdown in result[0].text
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == fake_markdown

    @pytest.mark.asyncio
    async def test_likhit_error_propagation(self, tmp_path):
        """Test that likhit errors are reported as user-friendly messages."""
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"not a real pdf")

        with patch(
            "jawafdehi_mcp.tools.likhit_extract.likhit.extract",
            side_effect=Exception("Unsupported document type 'invalid'"),
        ):
            result = await self.tool.execute(
                {"file_path": str(pdf_file), "doc_type": "ciaa-press-release"}
            )

        assert len(result) == 1
        assert "Error extracting document" in result[0].text
        assert "Unsupported document type" in result[0].text
