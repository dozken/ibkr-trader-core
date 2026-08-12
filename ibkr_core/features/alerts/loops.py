import asyncio
import logging
from datetime import datetime, time as dtime

from ibkr_core.core.database import SessionLocal
from ibkr_core.core.health_utils import set_loop_error
from ibkr_core.core.market_hours import is_market_open
from ibkr_core.core.models import Account, PositionCompliance, PortfolioSnapshot
from ibkr_core.features.alerts.dispatcher import alert as send_alert
from ibkr_core.features.settings.service import load_settings
from ibkr_core.core.clock import utc_now

logger = logging.getLogger(__name__)


async def purification_reminder_loop(health: dict) -> None:
    """Monthly reminder to calculate and donate impure income. Ref: Phase 3."""
    health["purification_reminder_loop"] = {"status": "running", "last_run": None}
    last_month = None
    
    while True:
        try:
            now = utc_now()
            if now.day == 1 and now.month != last_month:
                settings = load_settings()
                channels = settings.get("alert_channels", [])
                
                await send_alert(
                    "🌙 Purification Reminder",
                    "It's the start of the month. Please review your purification ledger and donate impure income (interest/non-compliant dividends).",
                    channels,
                )
                last_month = now.month
                health["purification_reminder_loop"]["last_run"] = now.isoformat()
            
            await asyncio.sleep(3600 * 12) # Check twice a day
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in purification_reminder_loop: {e}")
            set_loop_error(health["purification_reminder_loop"], 3600, e)
            await asyncio.sleep(3600)


def _resolve_report_targets(worker, account_manager):
    """Return [(account_id, label, worker)] — one entry per account.

    Falls back to a single (None, label, worker) entry when no multi-account
    manager is configured."""
    if account_manager and account_manager.list_account_ids():
        with SessionLocal() as db:
            labels = {a.id: a.label for a in db.query(Account).all()}
        targets = []
        for aid in account_manager.list_account_ids():
            w = account_manager.get_worker_by_id(aid)
            if w:
                targets.append((aid, labels.get(aid, f"Account {aid}"), w))
        if targets:
            return targets
    label = getattr(worker, "ibkr_account_id", None) or "Portfolio"
    return [(None, label, worker)]


async def _benchmark_str() -> str:
    """Daily benchmark returns (HLAL/SPY). Fetched once per digest run."""
    try:
        import yfinance as yf
        bench_lines = []
        for ticker in ("HLAL", "SPY"):
            hist = await asyncio.to_thread(yf.Ticker(ticker).history, period="2d")
            if len(hist) >= 2:
                b_ret = ((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2]) * 100
                bench_lines.append(f"  {ticker}: {b_ret:+.2f}%")
        return "\n".join(bench_lines) if bench_lines else "  (unavailable)"
    except Exception as bench_err:
        logger.warning("Benchmark fetch failed: %s", bench_err)
        return "  (unavailable)"


async def _account_digest_body(worker, account_id, today, comp_map, bench_str) -> str:
    nlv = await asyncio.to_thread(worker.get_net_liquidation)
    funds = await asyncio.to_thread(worker.get_available_funds)
    positions = await asyncio.to_thread(worker.get_positions)

    safe_n = sum(1 for p in positions if comp_map.get(p["symbol"]) == "COMPLIANT")
    total_n = len(positions)

    body = (
        f"📊 <b>Market Close Report</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Total Value: ${nlv:,.2f}\n"
        f"💵 Cash: ${funds:,.2f}\n"
        f"📈 Total Positions: {total_n}\n"
        f"🛡️ Shariah Safe: {safe_n}/{total_n}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>Log in to the dashboard for details.</i>"
    )

    # Daily P&L vs benchmark — opening snapshot scoped to this account
    try:
        today_start = datetime.combine(today, dtime(0, 0))
        with SessionLocal() as db2:
            q = (
                db2.query(PortfolioSnapshot)
                .filter(PortfolioSnapshot.timestamp >= today_start)
            )
            if account_id is not None:
                q = q.filter(PortfolioSnapshot.account_id == account_id)
            open_snap = q.order_by(PortfolioSnapshot.timestamp.asc()).first()
        if open_snap and open_snap.total_value > 0:
            port_return = ((nlv - open_snap.total_value) / open_snap.total_value) * 100
            sign = "📈" if port_return >= 0 else "📉"
            body += (
                f"\n\n{sign} <b>Daily Return: {port_return:+.2f}%</b>\n"
                f"<i>Benchmarks:</i>\n{bench_str}"
            )
    except Exception as bench_err:
        logger.warning("Daily return calc failed: %s", bench_err)

    return body


async def daily_report_loop(worker, health: dict, account_manager=None) -> None:
    health["daily_report_loop"]["status"] = "running"
    last_reported_date = None

    while True:
        try:
            now = utc_now()
            today = now.date()

            if not is_market_open("NMS") and now.hour >= 16 and today != last_reported_date:
                targets = _resolve_report_targets(worker, account_manager)
                if any(w.ib.isConnected() for _, _, w in targets):
                    logger.info("Market closed. Generating per-account daily digests...")

                    # Compliance status is per-symbol (account-independent).
                    with SessionLocal() as db:
                        latest_audits = (
                            db.query(PositionCompliance)
                            .order_by(PositionCompliance.timestamp.desc())
                            .limit(200)
                            .all()
                        )
                        comp_map = {a.symbol: a.shariah_status for a in latest_audits}

                    bench_str = await _benchmark_str()
                    channels = load_settings().get("alert_channels", [])

                    sent_any = False
                    for account_id, label, w in targets:
                        if not w.ib.isConnected():
                            logger.info("Daily digest skipped for %s: not connected.", label)
                            continue
                        body = await _account_digest_body(w, account_id, today, comp_map, bench_str)
                        await send_alert(f"Daily Performance Digest — {label}", body, channels)
                        sent_any = True

                    if sent_any:
                        last_reported_date = today
                        health["daily_report_loop"]["last_run"] = now.isoformat()

            await asyncio.sleep(900)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in daily_report_loop: {e}")
            set_loop_error(health["daily_report_loop"], 300, e)
            await asyncio.sleep(300)
