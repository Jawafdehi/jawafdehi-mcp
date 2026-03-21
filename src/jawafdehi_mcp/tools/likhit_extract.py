"""Likhit document extraction tool for converting Nepal government PDFs to Markdown."""

from pathlib import Path
from typing import Any

import likhit
from mcp.types import TextContent

from .base import BaseTool


class LikhitExtractTool(BaseTool):
    """Tool for extracting Nepal government documents into structured Markdown.

    Wraps the likhit library to convert PDF documents (e.g. CIAA press releases)
    into clean Markdown with YAML frontmatter containing extracted metadata.
    """

    @property
    def name(self) -> str:
        return "likhit_extract"

    @property
    def description(self) -> str:
        return (
            "Convert a Nepal government PDF document to structured Markdown. "
            "Uses the likhit extraction pipeline to parse PDFs with Nepali text "
            "(including Kalimati font fixing) and produce clean Markdown with "
            "YAML frontmatter.\n\n"
            "The file_path must point to a PDF file accessible on the local filesystem."
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
            convert_fn = getattr(likhit, "convert", None)
            if not convert_fn:
                raise RuntimeError(
                    "Installed likhit package does not expose likhit.convert(file_path)."
                )

            markdown = convert_fn(str(path))

            output_path = arguments.get("output_path")
            if output_path:
                out = Path(output_path)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(markdown, encoding="utf-8")
                return [
                    TextContent(
                        type="text",
                        text=f"Markdown written to {out}\n\n{markdown}",
                    )
                ]

            return [TextContent(type="text", text=markdown)]

        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error extracting document: {e}",
                )
            ]
