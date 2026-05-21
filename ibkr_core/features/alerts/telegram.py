"""
Telegram alert sender. Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from env.
No-op when either var is unset.
"""
import os
import logging
import httpx

from ibkr_core.features.alerts.audit import log_telegram

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


async def send_telegram(text: str, reply_markup: dict = None) -> bool:
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log_telegram("out", chat_id or None, text, status="skipped", reason="env_unset")
        return False
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_API_URL.format(token=token), json=payload)
            resp.raise_for_status()
            log_telegram("out", chat_id, text, status="ok")
            return True
    except Exception as exc:
        logger.warning(f"Telegram alert failed: {exc}")
        log_telegram("out", chat_id, text, status="fail", error=str(exc))
        return False
