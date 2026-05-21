"""
Alert dispatcher: routes alerts to configured channels.

Usage:
    from ibkr_core.features.alerts.dispatcher import alert
    await alert("Trade filled", "AAPL 10 shares @ $175.50", settings)

Supported channels (set via settings.alert_channels):
    "telegram"  — Telegram bot (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars)
    "email"     — SMTP email (SMTP_HOST, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL_TO env vars)
    "slack"     — Slack incoming webhook (SLACK_WEBHOOK_URL env var)
"""
import logging
from typing import Sequence

from .telegram import send_telegram
from .email import send_email
from .slack import send_slack

logger = logging.getLogger(__name__)


async def alert(title: str, body: str, channels: Sequence[str] = (),
                reply_markup: dict = None) -> None:
    """Fire-and-forget: send alert to each configured channel. Errors are logged, not raised."""
    if not channels:
        return

    emoji = "ℹ️"
    if "LIQUIDATED" in title or "HARAM" in title or "CRITICAL" in title or "VIOLATION" in title:
        emoji = "🔴"
    elif "OPPORTUNITY" in title or "BUY" in title or "HALAL" in title:
        emoji = "🟢"
    elif "ACTION REQUIRED" in title or "WARNING" in title:
        emoji = "⚠️"
    elif "SELL" in title:
        emoji = "🔵"
    elif "COMPLETE" in title or "SUCCESS" in title:
        emoji = "✅"

    text = f"{emoji} <b>{title}</b>\n\n{body}"
    plain = f"{emoji} {title}\n\n{body}"

    for channel in channels:
        if channel == "telegram":
            await send_telegram(text, reply_markup=reply_markup)
        elif channel == "email":
            await send_email(subject=f"{emoji} {title}", body=text)
        elif channel == "slack":
            await send_slack(plain)
        else:
            logger.warning("Unknown alert channel: %r", channel)
