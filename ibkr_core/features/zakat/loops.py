import asyncio
import logging
from datetime import datetime

from ibkr_core.core.database import SessionLocal
from ibkr_core.core.health_utils import set_loop_error
from ibkr_core.features.zakat.zakat import calculate_zakat, fetch_nisab_usd
from ibkr_core.features.zakat.hawl import update_hawl, get_hawl_status
from ibkr_core.core.monitoring import PURIFICATION_PENDING, ZAKAT_LIABILITY
from ibkr_core.features.zakat.router import get_purification_liabilities
from ibkr_core.features.alerts.telegram import send_telegram

logger = logging.getLogger(__name__)

_hawl_alerted_due = False          # prevent repeat alerts once already notified
_hawl_alerted_7day = False


async def zakat_monitoring_loop(worker, health: dict) -> None:
    """Updates Zakat/Purification metrics and sends Hawl due-date alerts."""
    global _hawl_alerted_due, _hawl_alerted_7day
    health["zakat_monitoring_loop"] = {"status": "running", "last_run": None}

    while True:
        try:
            if worker.ib.isConnected():
                nlv = await asyncio.to_thread(worker.get_net_liquidation)
                nisab = await asyncio.to_thread(fetch_nisab_usd)
                zakat_due = calculate_zakat(nlv, nisab=nisab)
                ZAKAT_LIABILITY.set(zakat_due)
                await asyncio.to_thread(update_hawl, nlv, nisab)
                hawl = await asyncio.to_thread(get_hawl_status, nlv, nisab)

                # ── Hawl Telegram alerts ──────────────────────────────────────
                if hawl["is_due"] and not _hawl_alerted_due:
                    await send_telegram(
                        f"🕌 <b>ZAKAT IS DUE</b>\n\n"
                        f"Your Hawl completed on <b>{hawl['hawl_end']}</b>.\n"
                        f"Portfolio: <b>${nlv:,.0f}</b> | "
                        f"Zakat due (2.5%): <b>${zakat_due:,.2f}</b>\n\n"
                        f"Please calculate and pay your Zakat. Go to the Zakat page to record payment."
                    )
                    _hawl_alerted_due = True
                elif not hawl["is_due"]:
                    _hawl_alerted_due = False  # reset when new cycle starts

                if hawl["hawl_end"] and hawl["days_remaining"] <= 7 and hawl["days_remaining"] > 0 and not _hawl_alerted_7day:
                    await send_telegram(
                        f"⏳ <b>Zakat due in {hawl['days_remaining']} days</b>\n\n"
                        f"Hawl ends: <b>{hawl['hawl_end']}</b>\n"
                        f"Estimated Zakat: <b>${zakat_due:,.2f}</b> (2.5% of ${nlv:,.0f})\n\n"
                        f"Prepare your payment — Nisab threshold: ${nisab:,.0f}"
                    )
                    _hawl_alerted_7day = True
                elif hawl["days_remaining"] > 7:
                    _hawl_alerted_7day = False

                def _get_purification():
                    with SessionLocal() as db:
                        return get_purification_liabilities(db)

                liabilities = await asyncio.to_thread(_get_purification)
                total_pending = sum(liab.remaining_liability for liab in liabilities)
                PURIFICATION_PENDING.set(total_pending)

                health["zakat_monitoring_loop"]["last_run"] = datetime.now().isoformat()

            await asyncio.sleep(3600 * 12)  # twice a day

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in zakat_monitoring_loop: {e}")
            set_loop_error(health["zakat_monitoring_loop"], 3600, e)
            await asyncio.sleep(3600)
