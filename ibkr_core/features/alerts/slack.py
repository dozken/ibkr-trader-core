"""Slack alert channel — incoming webhook."""
import logging
import os
import httpx

logger = logging.getLogger(__name__)

_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


async def send_slack(text: str) -> None:
    if not _WEBHOOK_URL:
        logger.error("Slack alert misconfigured: set SLACK_WEBHOOK_URL")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(_WEBHOOK_URL, json={"text": text})
            if resp.status_code != 200:
                logger.error("Slack webhook returned %s: %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("Slack alert failed: %s", e)
