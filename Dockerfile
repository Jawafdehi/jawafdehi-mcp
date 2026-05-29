# SPDX-License-Identifier: Hippocratic-3.0
# jawafdehi-mcp — MCP HTTP server for Jawafdehi data
# Ref: https://github.com/Jawafdehi/jawafdehi-mcp
#
# Build:  docker build -t ghcr.io/jawafdehi/jawafdehi-mcp:latest .
# Push:   docker push ghcr.io/jawafdehi/jawafdehi-mcp:latest

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ARG UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# uv sync needs git for git dependencies (likhit)
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

RUN groupadd --system --gid 1000 mcp && \
    useradd --system --uid 1000 --gid mcp --create-home mcp

COPY --from=builder --chown=mcp:mcp /app/.venv /app/.venv
COPY --chown=mcp:mcp src /app/src
COPY --chown=mcp:mcp pyproject.toml /app/

ENV PATH="/app/.venv/bin:$PATH" \
    HTTP_HOST="0.0.0.0" \
    HTTP_PORT="8000" \
    LOG_LEVEL="info"

USER mcp
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.getenv('HTTP_PORT', '8000'); urllib.request.urlopen(f'http://localhost:{port}/health')" || exit 1

CMD ["jawafdehi-mcp-http"]
