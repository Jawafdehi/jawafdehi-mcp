"""Unified document conversion tool with smart auto-detection.

This tool intelligently chooses between Likhit (for Nepal government documents)
and MarkItDown (for general documents) based on the input parameters.
"""

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import likhit
from markitdown import MarkItDown
from mcp.types import TextContent

from .base import BaseTool


class DocumentConverterTool(BaseTool):
    """Unified tool for converting documents to Markdown with smart auto-detection.

    This tool automatically chooses the best conversion method:
    - For Nepal government documents with Nepali text: Uses Likhit (specialized extraction)
    - For other documents: Uses MarkItDown (general-purpose conversion)

    Supports:
    - Nepal government PDFs (CIAA press releases, etc.) via Likhit
    - Office documents (DOCX, PPTX, XLSX) via MarkItDown
    - General PDFs via MarkItDown
    - Web pages (http://, https://) via MarkItDown
    - Data URIs via MarkItDown
    """

    @property
    def name(self) -> str:
        return "convert_to_markdown"

    @property
    def description(self) -> str:
        return (
            "Convert documents to Markdown with smart auto-detection. "
            "Automatically chooses the best conversion method:\n\n"
            "**Likhit (for local PDF files):**\n"
            "- Used automatically for local `.pdf` files\n"
            "- Better Nepali/Kalimati text handling for supported documents\n"
            "- Auto-detects supported structure from the PDF itself\n\n"
            "**MarkItDown (for general documents):**\n"
            "- Office documents: DOCX, PPTX, XLSX\n"
            "- Web pages: http://, https:// URLs\n"
            "- Local files via `file://` URIs and non-PDF local files\n"
            "- Data URIs: data:text/plain;base64,...\n\n"
            "**Auto-detection logic:**\n"
            "1. If the source is a local PDF file → Use Likhit\n"
            "2. Otherwise → Use MarkItDown based on file extension or URI scheme\n"
            "3. If Likhit fails → Automatically fall back to MarkItDown\n\n"
            "⚠️ **Important**: MarkItDown may not accurately convert Nepali text in PDFs. "
            "For Nepali PDFs, Likhit is preferred when the input is a local PDF file."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Absolute path to a local file. Local PDFs are processed with "
                        "Likhit; other local files are converted with MarkItDown. "
                        "Mutually exclusive with 'uri'."
                    ),
                },
                "uri": {
                    "type": "string",
                    "description": (
                        "URI of the resource to convert (for MarkItDown). Supports:\n"
                        "- file:///absolute/path/to/document\n"
                        "- http://example.com/document\n"
                        "- https://example.com/document\n"
                        "- data:text/plain;base64,...\n"
                        "Mutually exclusive with 'file_path'."
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Optional. Absolute path to write the converted Markdown file. "
                        "Parent directories are created automatically."
                    ),
                },
                "enable_plugins": {
                    "type": "boolean",
                    "description": (
                        "Optional. Enable MarkItDown plugins (MarkItDown only). "
                        "Defaults to False. Only used when using MarkItDown converter."
                    ),
                    "default": False,
                },
            },
            "required": [],
        }

    def _get_source_path(self, arguments: dict[str, Any]) -> tuple[str, bool]:
        """
        Get the source path/URI and determine if it's a local file.

        Returns:
            tuple: (path_or_uri, is_local_file)
        """
        file_path = arguments.get("file_path")
        uri = arguments.get("uri")

        if file_path and uri:
            raise ValueError(
                "Cannot specify both 'file_path' and 'uri'. Use one or the other."
            )

        if file_path:
            return file_path, True

        if uri:
            if uri.startswith("file://"):
                parsed = urlparse(uri)
                if parsed.netloc not in ("", "localhost"):
                    raise ValueError(
                        "Unsupported file URI. Netloc must be empty or localhost."
                    )
                return url2pathname(unquote(parsed.path)), True
            return uri, False

        raise ValueError("Must specify either 'file_path' or 'uri'.")

    def _should_use_likhit(self, source: str, is_local_file: bool) -> bool:
        """Use likhit for local PDF files only."""
        return is_local_file and Path(source).suffix.lower() == ".pdf"

    async def _convert_with_likhit(self, file_path: str) -> tuple[str, str | None]:
        """
        Convert a local PDF with Likhit.

        Returns:
            tuple: (markdown_content, error_message)
        """
        try:
            convert_fn = getattr(likhit, "convert", None)
            if not convert_fn:
                raise RuntimeError(
                    "Installed likhit package does not expose likhit.convert(file_path)."
                )
            markdown = convert_fn(file_path)
            return markdown, None
        except Exception as e:
            return "", str(e)

    async def _convert_with_markitdown(
        self, source: str, arguments: dict[str, Any]
    ) -> tuple[str, str | None]:
        """
        Convert document using MarkItDown.

        Returns:
            tuple: (markdown_content, error_message)
        """
        try:
            if not source.startswith(("http://", "https://", "file://", "data:")):
                source = Path(source).resolve().as_uri()

            enable_plugins = arguments.get("enable_plugins", False)
            converter = MarkItDown(enable_plugins=enable_plugins)
            result = converter.convert_uri(source)
            return result.markdown, None
        except Exception as e:
            return "", str(e)

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute document conversion with smart auto-detection."""
        # Get source path/URI
        try:
            source, is_local_file = self._get_source_path(arguments)
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]

        # Validate local file exists
        if is_local_file:
            path = Path(source)
            if not path.exists():
                return [
                    TextContent(
                        type="text",
                        text=f"Error: File not found: {source}",
                    )
                ]
            if not path.is_file():
                return [
                    TextContent(
                        type="text",
                        text=f"Error: Path is not a file: {source}",
                    )
                ]

        # Determine conversion method
        use_likhit = self._should_use_likhit(source, is_local_file)
        converter_used = None
        markdown = None
        error = None

        # Try Likhit first if applicable
        if use_likhit:
            converter_used = "Likhit"
            markdown, error = await self._convert_with_likhit(source)

            # Fall back to MarkItDown if Likhit fails
            if error:
                fallback_msg = (
                    f"⚠️ Likhit conversion failed: {error}\n"
                    "Falling back to MarkItDown...\n\n"
                )
                converter_used = "MarkItDown (fallback)"
                markdown, error = await self._convert_with_markitdown(source, arguments)
                if not error:
                    markdown = fallback_msg + markdown
        # Use MarkItDown directly
        else:
            converter_used = "MarkItDown"
            markdown, error = await self._convert_with_markitdown(source, arguments)

        # Handle conversion error
        if error:
            return [
                TextContent(
                    type="text",
                    text=f"Error converting document with {converter_used}: {error}",
                )
            ]

        # Write to output file if specified
        output_path = arguments.get("output_path")
        if output_path:
            try:
                out = Path(output_path)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(markdown, encoding="utf-8")
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"✅ Converted with {converter_used}\n"
                            f"📄 Markdown written to {out}"
                        ),
                    )
                ]
            except Exception as e:
                return [
                    TextContent(
                        type="text",
                        text=f"Error writing to {output_path}: {e}",
                    )
                ]

        # Return markdown directly
        return [
            TextContent(
                type="text",
                text=f"✅ Converted with {converter_used}\n\n{markdown}",
            )
        ]
