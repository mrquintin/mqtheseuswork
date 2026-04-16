"""
Structured JSON logging for Noosphere.

All library modules should use `get_logger(__name__)` from this module.
Configure once at process entry (CLI or orchestrator) via `configure_logging`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

_FILE_LOGGER_NAME = "theseus_noosphere_jsonl"


def configure_logging(
    level: str | None = None,
    *,
    json_format: bool = True,
    log_to_file: bool | None = None,
) -> None:
    """
    Configure structlog for stdout JSON (or console) output.

    When ``log_to_file`` is true (default unless ``THESEUS_LOG_FILE=0``), also
    append the same JSON lines to a rotating file under ``~/.theseus/logs/`` or
    ``THESEUS_LOG_DIR``.
    """
    lvl = (level or os.environ.get("THESEUS_LOG_LEVEL", "INFO")).upper()
    levelno = getattr(logging, lvl, logging.INFO)

    if log_to_file is None:
        log_to_file = os.environ.get("THESEUS_LOG_FILE", "1").strip().lower() not in {
            "0",
            "false",
            "no",
        }

    tee_processor: Any | None = None
    if log_to_file and json_format:
        log_dir = Path(
            os.environ.get("THESEUS_LOG_DIR", Path.home() / ".theseus" / "logs")
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "noosphere.jsonl"
        file_log = logging.getLogger(_FILE_LOGGER_NAME)
        file_log.handlers.clear()
        file_log.setLevel(levelno)
        file_log.propagate = False
        rh = RotatingFileHandler(
            log_path,
            maxBytes=int(os.environ.get("THESEUS_LOG_MAX_BYTES", str(10 * 1024 * 1024))),
            backupCount=int(os.environ.get("THESEUS_LOG_BACKUP_COUNT", "5")),
            encoding="utf-8",
        )
        rh.setFormatter(logging.Formatter("%(message)s"))
        file_log.addHandler(rh)

        def _tee_file(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
            file_log.info(json.dumps(event_dict, default=str, ensure_ascii=False))
            return event_dict

        tee_processor = _tee_file

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if tee_processor is not None:
        processors.append(tee_processor)
    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(levelno),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a structlog bound logger."""
    return structlog.get_logger(name)
