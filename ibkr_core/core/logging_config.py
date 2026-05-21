"""Central logging configuration. Call setup_logging() once at startup."""
from __future__ import annotations

import contextvars
import json
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Per-request correlation ID; populated by middleware in ibkr_core.core.request_id.
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)

_CONFIGURED = False

_NOISY_LIBS = (
    "httpx",
    "urllib3",
    "apscheduler",
    "ib_insync",
    "sqlalchemy.engine",
)

_RESERVED_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


class _JsonFormatter(logging.Formatter):
    """Hand-rolled JSON log formatter; no extra deps."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        for k, v in record.__dict__.items():
            if k in _RESERVED_RECORD_ATTRS or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        return json.dumps(payload, default=str)


class _ConsoleFormatter(logging.Formatter):
    """Human-readable formatter with optional request_id."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        rid = request_id_var.get()
        if rid:
            return f"[{rid[:8]}] {base}"
        return base


def _level_from_env(name: str, default: str = "INFO") -> int:
    return logging.getLevelName(os.getenv(name, default).upper())


def _maybe_init_sentry(level: int) -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
    except ImportError:
        logging.getLogger("ops").info("Sentry SDK not installed; skipping")
        return
    sentry_sdk.init(
        dsn=dsn,
        integrations=[LoggingIntegration(level=level, event_level=logging.ERROR)],
    )


_log_uncaught = logging.getLogger("ops.uncaught")


def _asyncio_loop_hook(loop, context):
    msg = context.get("message", "asyncio error")
    exc = context.get("exception")
    if exc:
        _log_uncaught.error("asyncio uncaught: %s", msg,
                            exc_info=(type(exc), exc, exc.__traceback__))
    else:
        _log_uncaught.error("asyncio uncaught: %s | ctx=%s", msg, context)


def install_asyncio_excepthook() -> None:
    """Install asyncio loop exception handler. Call from inside a running loop."""
    import asyncio
    try:
        asyncio.get_running_loop().set_exception_handler(_asyncio_loop_hook)
    except RuntimeError:
        pass


def _install_excepthooks() -> None:
    def _sys_hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        _log_uncaught.error("Uncaught exception: %s",
                            "".join(traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = _sys_hook


def setup_logging() -> None:
    """Configure root logger. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = _level_from_env("LOG_LEVEL", "INFO")
    log_format = os.getenv("LOG_FORMAT", "console").lower()
    file_enabled = os.getenv("LOG_FILE_ENABLED", "true").lower() != "false"
    log_dir = Path(os.getenv("LOG_DIR", "data/logs"))

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(level)

    console_fmt: logging.Formatter = (
        _JsonFormatter() if log_format == "json" else _ConsoleFormatter()
    )
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setFormatter(console_fmt)
    stdout_handler.setLevel(level)
    root.addHandler(stdout_handler)

    if file_enabled:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_dir / "app.log",
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(_JsonFormatter())
            file_handler.setLevel(level)
            root.addHandler(file_handler)
        except OSError as exc:
            logging.getLogger("ops").warning("File log disabled (%s): %s", log_dir, exc)

    for lib in _NOISY_LIBS:
        env_key = f"LOG_LEVEL_{lib.replace('.', '_').upper()}"
        lib_level = _level_from_env(env_key, "WARNING")
        logging.getLogger(lib).setLevel(lib_level)

    # Compliance / audit logger never goes below INFO to file.
    logging.getLogger("compliance.audit").setLevel(min(level, logging.INFO))

    _maybe_init_sentry(level)
    _install_excepthooks()

    _CONFIGURED = True
    logging.getLogger("ops").info(
        "logging initialized",
        extra={"level": logging.getLevelName(level), "format": log_format,
               "file": str(log_dir / "app.log") if file_enabled else None},
    )
