"""Logging setup for jawafdehi-mcp — structlog + optional Sentry + optional GCP Cloud Logging."""

import logging
import os
import sys

import structlog

SERVICE_NAME = "jawafdehi-mcp"


def _get_version() -> str:
    try:
        from . import __version__

        return __version__
    except ImportError:
        return "0.0.0"


def _sentry_processor(logger, method_name, event_dict):
    """Forward structlog context to Sentry scope (replaces removed StructlogIntegration)."""
    try:
        import sentry_sdk

        scope = sentry_sdk.get_current_scope()
        if scope:
            exclude = {
                "event",
                "level",
                "timestamp",
                "logger",
                "exception",
                "stack_info",
            }
            for key, value in event_dict.items():
                if key not in exclude:
                    scope.set_context(
                        "structlog", {**scope.contexts.get("structlog", {}), key: value}
                    )
    except Exception:
        pass
    return event_dict


# Benign SSE / streamable-http transport artifacts that surface out of the mcp
# session manager's anyio TaskGroup (not our code): the client hanging up
# mid-stream, and the cancel-scope teardown-ordering RuntimeError that anyio
# raises when a streamed request is cancelled. These are unactionable noise, so we
# drop them before they reach Sentry — matched on the exception type/message so a
# genuinely different RuntimeError is still reported.
_IGNORED_ERROR_SIGNATURES = (
    "ClientDisconnect",
    "Attempted to exit cancel scope in a different task",
)


def _drop_transport_noise(event, hint):
    """Sentry ``before_send``: drop benign SSE-transport teardown artifacts."""
    exc_info = hint.get("exc_info") if hint else None
    if exc_info and exc_info[0] is not None:
        text = f"{exc_info[0].__name__}: {exc_info[1]}"
        if any(sig in text for sig in _IGNORED_ERROR_SIGNATURES):
            return None
    for value in (event.get("exception") or {}).get("values") or []:
        signature = f"{value.get('type', '')}: {value.get('value', '')}"
        if any(sig in signature for sig in _IGNORED_ERROR_SIGNATURES):
            return None
    return event


def _init_sentry() -> None:
    # Opt-in error reporting: only initialize when a DSN is explicitly provided
    # (prod injects SENTRY_DSN via the jawafdehi-mcp-env secret). Local and
    # stdio-bridge dev runs leave it unset and stay silent — no events are
    # shipped from developer machines.
    sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
    if not sentry_dsn:
        return

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
            release=os.getenv("SENTRY_RELEASE", f"{SERVICE_NAME}@{_get_version()}"),
            before_send=_drop_transport_noise,
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
        _sentry_processor,
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
