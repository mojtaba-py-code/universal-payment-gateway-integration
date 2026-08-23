"""Structured logging.

We use :mod:`structlog` to emit machine-parseable JSON logs enriched with a
per-request correlation id. A :class:`contextvars.ContextVar` carries the
correlation id across ``await`` boundaries without threading it through every
call, and a structlog processor injects it into every event.

Sensitive keys are redacted defensively so credentials, tokens, or card data
can never leak into logs even if a caller passes them by mistake.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

import structlog
from structlog.types import EventDict, WrappedLogger

# Correlation id for the in-flight request. Empty string means "no request".
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "apikey",
        "card_number",
        "cvv",
        "cvc",
        "pan",
        "client_secret",
        "secret_encryption_key",
        "jwt_secret_key",
    }
)

_REDACTED = "***redacted***"


def _add_correlation_id(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    cid = correlation_id_var.get()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def _redact_sensitive(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = _REDACTED
    return event_dict


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog + stdlib logging. Idempotent."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_correlation_id,
        _redact_sensitive,
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy) through the same stderr sink so
    # deployment log collectors see a single, uniform stream.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=logging.getLevelNamesMapping().get(level.upper(), logging.INFO),
        force=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
