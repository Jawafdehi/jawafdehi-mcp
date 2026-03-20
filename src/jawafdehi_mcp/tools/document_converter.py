"""Unified document conversion tool with smart auto-detection.

This tool intelligently chooses between Likhit (for Nepal government documents)
and MarkItDown (for general documents) based on the input parameters.
"""

from pathlib import Path
from typing import Any

from likhit import extractors
from likhit.core import render_markdown
from markitdown import MarkItDown
from mcp.types import TextContent

from .base import BaseTool

# Supported Likhit document types
LIKHIT_SUPPORTED_TYPES = ["ciaa-press-release"]


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
            "**Likhit (for Nepal government documents):**\n"
            "- CIAA press releases (अख्तियार दुरुपयोग अनुसन्धान आयोग)\n"
            "- Excellent Nepali text support with Kalimati font fixing\n"
            "- Extracts metadata (title, date, etc.) into YAML frontmatter\n"
            "- Requires: file_path (local PDF) + doc_type\n\n"
            "**MarkItDown (for general documents):**\n"
            "- Office documents: DOCX, PPTX, XLSX\n"
            "- PDFs (⚠️ limited Nepali text support)\n"
            "- Web pages: http://, https:// URLs\n"
            "- Local files: file:///absolute/path\n"
            "- Data URIs: data:text/plain;base64,...\n"
            "- Requires: uri\n\n"
            "**Auto-detection logic:**\n"
            "1. If doc_type is provided and supported by Likhit → Use Likhit\n"
            "2. If doc_type='auto' or not provided → Use MarkItDown\n"
            "3. If Likhit fails → Automatically fall back to MarkItDown\n\n"
            "⚠️ **Important**: MarkItDown may not accurately convert Nepali text in PDFs. "
            "For Nepal government documents, always specify doc_type for best results."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Absolute path to a local file. Used for Likhit extraction "
                        "or converted to file:// URI for MarkItDown. "
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
                "doc_type": {
                    "type": "string",
                    "enum": ["auto", "ciaa-press-release"],
                    "description": (
                        "Document type for specialized extraction:\n"
                        "- 'ciaa-press-release': CIAA press release (uses Likhit)\n"
                        "- 'auto': Auto-detect or use MarkItDown (default)\n"
                        "If not specified, defaults to 'auto'."
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Optional. Absolute path to write the converted Markdown file. "
                        "Parent directories are created automatically."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Optional. Override the title (Likhit only). "
                        "Only used when doc_type is a Likhit-supported type."
                    ),
                },
                "publication_date": {
                    "type": "string",
                    "description": (
                        "Optional. Override publication date in YYYY-MM-DD format (Likhit only). "
                        "Only used when doc_type is a Likhit-supported type."
                    ),
                },
                "source_url": {
                    "type": "string",
                    "description": (
                        "Optional. Source URL for metadata (Likhit only). "
                        "Only used when doc_type is a Likhit-supported type."
                    ),
                },
                "pages": {
                    "type": "string",
                    "description": (
                        "Optional. Page range to extract, e.g. '1-3' or '5' (Likhit only). "
                        "Only used when doc_type is a Likhit-supported type."
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

    def _should_use_likhit(self, arguments: dict[str, Any]) -> bool:
        """Determine if we should use Likhit based on arguments."""
        doc_type = arguments.get("doc_type", "auto")
        return doc_type in LIKHIT_SUPPORTED_TYPES

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
            # Check if it's a file:// URI
            if uri.startswith("file://"):
                return uri.replace("file://", ""), True
            return uri, False

        raise ValueError("Must specify either 'file_path' or 'uri'.")

    async def _convert_with_likhit(
        self, file_path: str, arguments: dict[str, Any]
    ) -> tuple[str, str | None]:
        """
        Convert document using Likhit.

        Returns:
            tuple: (markdown_content, error_message)
        """
        doc_type = arguments.get("doc_type")

        try:
            result = extract(
                file_path,
                doc_type,
                title=arguments.get("title"),
                publication_date=arguments.get("publication_date"),
                source_url=arguments.get("source_url"),
                pages=arguments.get("pages"),
            )
            markdown = render_markdown(result)
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
            # If source is a local file path, convert to file:// URI
            if not source.startswith(("http://", "https://", "file://", "data:")):
                source = f"file://{source}"

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
        use_likhit = self._should_use_likhit(arguments)
        converter_used = None
        markdown = None
        error = None

        # Try Likhit first if applicable
        if use_likhit and is_local_file:
            converter_used = "Likhit"
            markdown, error = await self._convert_with_likhit(source, arguments)

            # Fall back to MarkItDown if Likhit fails
            if error:
                fallback_msg = (
                    f"⚠️ Likhit conversion failed: {error}\n"
                    f"Falling back to MarkItDown (Nepali text may not be accurate)...\n\n"
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
