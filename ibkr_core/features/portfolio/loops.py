import asyncio
import logging
from datetime import datetime

from sqlalchemy import func

from ibkr_core.core.database import SessionLocal
from ibkr_core.core.health_utils import set_loop_error
from ibkr_core.core.models import PortfolioSnapshot
from ibkr_core.features.alerts.dispatcher import alert as send_alert
from ibkr_core.features.settings.service import load_settings

logger = logging.getLogger(__name__)


from ibkr_core.core.monitoring import TOTAL_NLV, CASH_AVAILABLE, ACTIVE_POSITIONS, DAILY_PNL_USD, SECTOR_EXPOSURE


def _load_peak_nlv_from_db(account_id: int | None = None) -> float:
    """Seed peak NLV from historical snapshots so drawdown CB survives restarts."""
    try:
        with SessionLocal() as db:
            q = db.query(func.max(PortfolioSnapshot.total_value))
            if account_id is not None:
                q = q.filter(PortfolioSnapshot.account_id == account_id)
            result = q.scalar()
            return float(result) if result else 0.0
    except Exception as e:
        logger.warning("Could not load peak NLV from DB: %s", e)
        return 0.0


async def portfolio_snapshot_loop(worker, health: dict, *, account_id: int | None = None) -> None:
    health["portfolio_snapshot_loop"]["status"] = "running"
    health.setdefault("drawdown_triggered", False)
    health.setdefault("current_drawdown_pct", 0.0)

    # Seed from DB so drawdown CB is accurate immediately after restart
    health["peak_nlv"] = _load_peak_nlv_from_db(account_id)
    if health["peak_nlv"] > 0:
        logger.info("Peak NLV seeded from DB (account=%s): $%.2f", account_id, health["peak_nlv"])

    while True:
        try:
            if worker.ib.isConnected():
                nlv = await asyncio.to_thread(worker.get_net_liquidation)
                cash = await asyncio.to_thread(worker.get_available_funds)
                positions = await asyncio.to_thread(worker.get_positions)
                upnl = sum(p.get("unrealized_pnl", 0.0) for p in positions)

                # Update peak NLV
                if nlv > health["peak_nlv"]:
                    health["peak_nlv"] = nlv

                # Drawdown circuit breaker
                settings = load_settings()
                max_dd = float(settings.get("max_drawdown_pct", 15.0))
                peak = health["peak_nlv"]
                if peak > 0:
                    drawdown_pct = ((peak - nlv) / peak) * 100
                    health["current_drawdown_pct"] = round(drawdown_pct, 2)

                    if drawdown_pct >= max_dd and not health["drawdown_triggered"]:
                        health["drawdown_triggered"] = True
                        logger.error(
                            "DRAWDOWN CIRCUIT BREAKER: %.1f%% >= %.1f%%. Trading halted.",
                            drawdown_pct, max_dd,
                        )
                        channels = settings.get("alert_channels", [])
                        await send_alert(
                            "🛑 DRAWDOWN CIRCUIT BREAKER TRIGGERED",
                            f"Portfolio dropped {drawdown_pct:.1f}% from peak ${peak:,.2f} "
                            f"(now ${nlv:,.2f}). <b>All trading halted.</b> "
                            f"Review positions and reset manually.",
                            channels,
                        )
                    elif drawdown_pct < max_dd / 2 and health["drawdown_triggered"]:
                        health["drawdown_triggered"] = False
                        logger.info("Drawdown recovered to %.1f%%. Trading resumed.", drawdown_pct)

                # Prometheus metrics
                TOTAL_NLV.set(nlv)
                CASH_AVAILABLE.set(cash)
                ACTIVE_POSITIONS.set(len(positions))
                DAILY_PNL_USD.set(upnl)

                # Sector exposure breakdown
                sector_values: dict[str, float] = {}
                for p in positions:
                    sec = (p.get("sector") or "Unknown").split("/")[0].strip()
                    sector_values[sec] = sector_values.get(sec, 0.0) + abs(float(p.get("market_value", 0)))
                total_pos_value = sum(sector_values.values()) or 1.0
                for sec, val in sector_values.items():
                    SECTOR_EXPOSURE.labels(sector=sec).set(round(val / total_pos_value * 100, 1))

                def _save():
                    with SessionLocal() as db:
                        db.add(PortfolioSnapshot(
                            account_id=account_id,
                            total_value=nlv,
                            cash_balance=cash,
                            unrealized_pnl=upnl,
                        ))
                        db.commit()

                await asyncio.to_thread(_save)
                health["portfolio_snapshot_loop"]["last_run"] = datetime.now().isoformat()

            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in portfolio_snapshot_loop: {e}")
            set_loop_error(health["portfolio_snapshot_loop"], 60, e)
            await asyncio.sleep(60)
