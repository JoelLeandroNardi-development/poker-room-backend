"""Structured logging configuration for game-service.

Provides a pre-configured logger with JSON-style structured fields and
a middleware that attaches correlation IDs to every request.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

# ── Correlation ID propagation ───────────────────────────────────
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    return correlation_id_ctx.get()


# ── Structured logger ───────────────────────────────────────────

class StructuredLogger:
    """Thin wrapper around stdlib logging that adds structured context."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _extra(self, **fields: object) -> dict:
        cid = get_correlation_id()
        base = {"correlation_id": cid} if cid else {}
        base.update(fields)
        return base

    def info(self, msg: str, **fields: object) -> None:
        self._logger.info(msg, extra={"structured": self._extra(**fields)})

    def warning(self, msg: str, **fields: object) -> None:
        self._logger.warning(msg, extra={"structured": self._extra(**fields)})

    def error(self, msg: str, **fields: object) -> None:
        self._logger.error(msg, extra={"structured": self._extra(**fields)})

    def debug(self, msg: str, **fields: object) -> None:
        self._logger.debug(msg, extra={"structured": self._extra(**fields)})


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)


# ── JSON-ish formatter ───────────────────────────────────────────

class StructuredFormatter(logging.Formatter):
    """Formatter that appends structured fields to the log line."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        structured = getattr(record, "structured", None)
        if structured:
            fields = " ".join(f"{k}={v}" for k, v in structured.items() if v is not None)
            return f"{base} | {fields}" if fields else base
        return base


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging with structured formatter."""
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
