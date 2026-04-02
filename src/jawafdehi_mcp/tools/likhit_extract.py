"""Deprecated compatibility wrapper for plugin-backed Nepali document extraction."""

from pathlib import Path
from typing import Any

from markitdown import MarkItDown
from mcp.types import TextContent

from .base import BaseTool


class LikhitExtractTool(BaseTool):
    """Compatibility tool for local plugin-backed extraction."""

    @property
    def name(self) -> str:
        return "likhit_extract"

    @property
    def description(self) -> str:
        return (
            "Deprecated compatibility wrapper around MarkItDown with plugins enabled. "
            "This keeps the legacy `likhit_extract` tool shape for local PDF files, "
            "but conversion now flows through MarkItDown and the installed `likhit` "
            "plugin rather than `likhit.convert(...)`.\n\n"
            "The file_path must point to a PDF file accessible on the local filesystem. "
            "By default the extracted Markdown is saved beside the PDF as a `.md` file, "
            "or you can provide `output_path` to choose where it is written."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the PDF file on the local filesystem.",
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Optional. Absolute path to write the converted Markdown file. "
                        "Parent directories are created automatically."
                    ),
                },
            },
            "required": ["file_path"],
        }

    def _get_output_path(self, arguments: dict[str, Any], path: Path) -> Path:
        """Write a sibling markdown file by default for local PDFs."""
        output_path = arguments.get("output_path")
        if output_path:
            return Path(output_path)
        return path.with_suffix(".md")

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        file_path = arguments.get("file_path")

        if not file_path:
            return [
                TextContent(
                    type="text",
                    text="Error: 'file_path' is a required parameter.",
                )
            ]

        path = Path(file_path)
        if not path.exists():
            return [
                TextContent(
                    type="text",
                    text=f"Error: File not found: {file_path}",
                )
            ]

        if not path.is_file():
            return [
                TextContent(
                    type="text",
                    text=f"Error: Path is not a file: {file_path}",
                )
            ]

        if path.suffix.lower() != ".pdf":
            return [
                TextContent(
                    type="text",
                    text="Error extracting document: likhit only supports local PDF files.",
                )
            ]

        try:
            converter = MarkItDown(enable_plugins=True)
            markdown = converter.convert_uri(path.resolve().as_uri()).markdown

            out = self._get_output_path(arguments, path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(markdown, encoding="utf-8")
            return [
                TextContent(
                    type="text",
                    text=(
                        "✅ Converted with MarkItDown + plugins\n"
                        f"📄 Markdown written to {out}"
                    ),
                )
            ]

        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error extracting document: {e}",
                )
            ]
