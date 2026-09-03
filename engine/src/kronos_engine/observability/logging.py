# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured local logging. Secrets are redacted before any handler writes."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from kronos_engine.observability.redaction import redact_text

_LOGGER_NAME = "kronos"
_DEFAULT_MAX_BYTES = 5_000_000
_DEFAULT_BACKUP_COUNT = 5


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    redact_text(arg) if isinstance(arg, str) else arg for arg in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    key: redact_text(value) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
        return True


def configure_logging(
    log_dir: Path,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "engine.log"
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = RotatingFileHandler(
        path,
        maxBytes=max(1024, max_bytes),
        backupCount=max(1, backup_count),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.propagate = False
    get_logger("kronos.engine")


def get_logger(name: str) -> logging.Logger:
    if name == "kronos.test":
        logger = logging.getLogger(_LOGGER_NAME)
        if not logger.handlers:
            configure_logging(Path("."))
        child = logger
    else:
        child = logging.getLogger(name)
        root = logging.getLogger(_LOGGER_NAME)
        if root.handlers and not child.handlers:
            child.handlers = list(root.handlers)
            child.setLevel(root.level)
            child.propagate = False
        child.addFilter(RedactingFilter())
    child.addFilter(RedactingFilter())
    return child
