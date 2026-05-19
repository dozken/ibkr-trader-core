"""Append-only JSONL audit trail for Telegram traffic."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_MAX_TEXT = 2000
_DEFAULT_PATH = Path(os.getenv("LOG_DIR", "data/logs")) / "telegram.jsonl"
_ENABLED = os.getenv("LOG_TELEGRAM_AUDIT", "true").lower() != "false"


def _truncate(text: str | None) -> str | None:
    if text is None:
        return None
    if len(text) <= _MAX_TEXT:
        return text
    return text[:_MAX_TEXT] + f"…[truncated {len(text) - _MAX_TEXT} chars]"


def log_telegram(direction: str, chat_id: str | int | None, text: str | None = None, **extra: Any) -> None:
    """Append one JSONL record. Direction: in|out. Status (in extra): ok|fail|unauthorized."""
    if not _ENABLED:
        return
    record = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "direction": direction,
        "chat_id": str(chat_id) if chat_id is not None else None,
        "text": _truncate(text),
    }
    record.update(extra)
    try:
        _DEFAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, default=str, ensure_ascii=False)
        with _LOCK:
            with _DEFAULT_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError as exc:
        logger.warning("telegram audit write failed: %s", exc)
