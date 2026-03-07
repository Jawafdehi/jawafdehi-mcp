#!/bin/bash
set -e

# Format and lint MCP server project

if [ "$1" = "--check" ]; then
    echo "Checking code formatting..."
    poetry run black --check src/ tests/
    poetry run isort --check-only src/ tests/
    poetry run flake8 src/ tests/
else
    echo "Formatting code..."
    poetry run black src/ tests/
    poetry run isort src/ tests/
    poetry run flake8 src/ tests/
fi
