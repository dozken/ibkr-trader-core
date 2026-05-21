"""Email alert channel — SMTP via env vars."""
import logging
import os
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

_SMTP_HOST = os.getenv("SMTP_HOST", "")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASSWORD", "")
_ALERT_TO  = os.getenv("ALERT_EMAIL_TO", "")


def _send_sync(subject: str, body: str) -> None:
    if not all([_SMTP_HOST, _SMTP_USER, _SMTP_PASS, _ALERT_TO]):
        raise RuntimeError("Email alert misconfigured: set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL_TO")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _SMTP_USER
    msg["To"] = _ALERT_TO
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as s:
        s.ehlo()
        s.starttls()
        s.login(_SMTP_USER, _SMTP_PASS)
        s.sendmail(_SMTP_USER, [_ALERT_TO], msg.as_string())


async def send_email(subject: str, body: str) -> None:
    try:
        await asyncio.get_running_loop().run_in_executor(None, _send_sync, subject, body)
    except Exception as e:
        logger.error("Email alert failed: %s", e)
