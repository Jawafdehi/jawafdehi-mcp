"""Unified document conversion tool powered by MarkItDown plugins."""

import logging
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from markitdown import MarkItDown
from mcp.types import TextContent

from .base import BaseTool

logger = logging.getLogger(__name__)


class DocumentConverterTool(BaseTool):
    """Unified tool for converting documents to Markdown with MarkItDown."""

    @property
    def name(self) -> str:
        return "convert_to_markdown"

    @property
    def description(self) -> str:
        return (
            "Convert documents to Markdown through MarkItDown.\n\n"
            "**Default behavior:**\n"
            "- Uses MarkItDown with plugins enabled by default\n"
            "- The `likhit` plugin provides Nepal-specific handling for supported "
            "born-digital PDFs and legacy `.doc` files when installed\n"
            "- Other supported formats continue through MarkItDown's standard "
            "converters\n\n"
            "**Supported inputs:**\n"
            "- Local files via `file_path`\n"
            "- Local files via `file://` URIs\n"
            "- Web pages and remote documents via `http://` and `https://`\n"
            "- Data URIs such as `data:text/plain;base64,...`\n\n"
            "**Output behavior:**\n"
            "- Returns Markdown directly by default\n"
            "- Set `output_path` to save the converted Markdown to a file instead\n\n"
            "Set `enable_plugins=false` only to bypass MarkItDown plugins for "
            "compatibility or troubleshooting."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Absolute path to a local file to convert through MarkItDown. "
                        "When plugins are enabled, plugin converters such as `likhit` "
                        "may intercept supported files. Mutually exclusive with 'uri'."
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
                        "Parent directories are created automatically. "
                        "If not provided, the markdown content is returned directly."
                    ),
                },
                "enable_plugins": {
                    "type": "boolean",
                    "description": (
                        "Optional. Enable MarkItDown plugins. Defaults to True. "
                        "Disable only to bypass plugin-based converters such as "
                        "`likhit`."
                    ),
                    "default": True,
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
            if uri.lower().startswith("file://"):
                parsed = urlparse(uri)
                if parsed.netloc not in ("", "localhost"):
                    raise ValueError(
                        "Unsupported file URI. Netloc must be empty or localhost."
                    )
                return url2pathname(unquote(parsed.path)), True
            return uri, False

        raise ValueError("Must specify either 'file_path' or 'uri'.")

    def _get_output_path(self, arguments: dict[str, Any]) -> Path | None:
        """Resolve an explicitly requested output markdown path."""
        output_path = arguments.get("output_path")
        if output_path:
            return Path(output_path)

        return None

    async def _convert_with_markitdown(
        self, source: str, arguments: dict[str, Any]
    ) -> tuple[str, str | None]:
        """
        Convert document using MarkItDown.

        Returns:
            tuple: (markdown_content, error_message)
        """
        try:
            if not source.lower().startswith(
                ("http://", "https://", "file://", "data:")
            ):
                source = Path(source).resolve().as_uri()

            enable_plugins = arguments.get("enable_plugins", True)
            converter = MarkItDown(enable_plugins=enable_plugins)
            result = converter.convert_uri(source)
            return result.markdown, None
        except Exception as e:
            logger.exception(
                "Unexpected document conversion error (%s)", type(e).__name__
            )
            return "", str(e)

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute document conversion through MarkItDown."""
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

        converter_used = "MarkItDown"
        if arguments.get("enable_plugins", True):
            converter_used += " + plugins"
        markdown, error = await self._convert_with_markitdown(source, arguments)

        # Handle conversion error
        if error:
            return [
                TextContent(
                    type="text",
                    text=f"Error converting document with {converter_used}: {error}",
                )
            ]

        # Write to output file only when explicitly requested
        output_path = self._get_output_path(arguments)
        if output_path:
            try:
                if is_local_file:
                    source_path = Path(source).resolve(strict=False)
                    target_path = output_path.resolve(strict=False)
                    if target_path == source_path:
                        return [
                            TextContent(
                                type="text",
                                text="Error: output_path must differ from the source file.",
                            )
                        ]
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(markdown, encoding="utf-8")
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"✅ Converted with {converter_used}\n"
                            f"📄 Markdown written to {output_path}"
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
