"""Logging setup for jawafdehi-mcp — structlog + optional Sentry + optional GCP Cloud Logging."""

import logging
import os
import sys

import structlog

SERVICE_NAME = "jawafdehi-mcp"
SENTRY_DSN = "https://f56afa3cccf0b71c8a09b1dc5a596d4a@o4511364048027648.ingest.de.sentry.io/4511366946553936"


def _get_version() -> str:
    try:
        from . import __version__

        return __version__
    except ImportError:
        return "0.0.0"


def _init_sentry() -> None:
    sentry_dsn = os.getenv("SENTRY_DSN", SENTRY_DSN).strip()

    try:
        import sentry_sdk
        from sentry_sdk.integrations.structlog import StructlogIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
            release=os.getenv("SENTRY_RELEASE", f"{SERVICE_NAME}@{_get_version()}"),
            integrations=[
                StructlogIntegration(),
            ],
        )
    except Exception:
        print("Failed to initialize Sentry SDK", file=sys.stderr)


def _init_gcp_logging() -> None:
    gcp_project = os.getenv("GCP_LOG_PROJECT", "").strip()
    if not gcp_project:
        return

    try:
        import google.cloud.logging

        client = google.cloud.logging.Client(project=gcp_project)
        client.setup_logging(
            log_level=_resolve_log_level(os.getenv("LOG_LEVEL", "INFO")),
        )
    except Exception:
        print("Failed to initialize GCP Cloud Logging", file=sys.stderr)


def _resolve_log_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


def setup_logging() -> None:
    """Configure structlog logging and optionally initialize Sentry."""
    _init_sentry()

    structlog.contextvars.bind_contextvars(service=SERVICE_NAME)

    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        timestamper,
    ]

    debug = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    if debug:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(_resolve_log_level(os.getenv("LOG_LEVEL", "INFO")))

    _init_gcp_logging()
