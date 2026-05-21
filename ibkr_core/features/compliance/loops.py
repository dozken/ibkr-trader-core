import asyncio
import logging
from datetime import datetime

from ibkr_core.core.websocket import ConnectionManager
from ibkr_core.features.alerts.dispatcher import alert as send_alert
from ibkr_core.features.compliance.corporate_actions import check_corporate_actions
from ibkr_core.features.compliance.service import persist_compliance
from ibkr_core.features.compliance.schemas import ComplianceViolationMessage, ComplianceViolationPayload
from ibkr_core.features.compliance.screening import live_shariah_screen
from ibkr_core.features.compliance.vix import get_current_vix, vix_to_ratio_buffer, vix_to_tier
from ibkr_core.features.settings.service import load_settings
from ibkr_core.features.trading.schemas import TradeCreate
from ibkr_core.features.trading.trader import Trader

logger = logging.getLogger(__name__)


async def _check_vix_tier_change(current_vix: float, health: dict, channels: list) -> str:
    """
    Computes new VIX tier; fires alert when tier changes; updates health dict.
    Returns the new tier string.
    """
    new_tier = vix_to_tier(current_vix)
    prev_tier = health["compliance_audit_loop"].get("vix_tier")
    if prev_tier is not None and prev_tier != new_tier:
        buffer_pct = vix_to_ratio_buffer(current_vix)
        await send_alert(
            f"VIX Tier Change: {prev_tier} → {new_tier}",
            f"VIX={current_vix:.1f}. AAOIFI ratio buffer now {buffer_pct:.0f}%. "
            f"Thresholds tightened for next compliance audit.",
            channels,
        )
        logger.warning("VIX tier changed %s → %s (VIX=%.1f)", prev_tier, new_tier, current_vix)
    health["compliance_audit_loop"]["vix_tier"] = new_tier
    return new_tier


from ibkr_core.core.monitoring import PORTFOLIO_COMPLIANCE_PCT

async def compliance_audit_loop(worker, manager: ConnectionManager, health: dict) -> None:
    logger.info("Starting Compliance Audit Loop...")
    health["compliance_audit_loop"]["status"] = "running"
    trader = Trader(worker)
    first_run = True
    while True:
        try:
            health["compliance_audit_loop"]["last_run"] = datetime.now().isoformat()
            settings = load_settings()
            interval_hours = int(settings.get("compliance_check_interval_hours", 24))
            if not first_run:
                await asyncio.sleep(interval_hours * 3600)
            first_run = False

            settings = load_settings()
            if not settings.get("auto_compliance_check", True):
                logger.info("Compliance audit skipped: auto_compliance_check=False.")
                continue

            logger.info(f"Running portfolio re-screening (interval={interval_hours}h)...")

            if not worker.ib.isConnected():
                # On startup: wait up to 3 min for IBKR to connect before giving up
                for _ in range(18):
                    await asyncio.sleep(10)
                    if worker.ib.isConnected():
                        break
                else:
                    logger.warning("Compliance audit skipped: IBKR not connected after wait.")
                    continue

            loop = asyncio.get_running_loop()
            positions = await loop.run_in_executor(None, worker.get_positions)

            if not positions:
                logger.info("Compliance audit: no positions held.")
                PORTFOLIO_COMPLIANCE_PCT.set(100.0)
                continue

            auto_liquidate = settings.get("critical_auto_sell", False)
            channels = settings.get("alert_channels", [])

            vix = await asyncio.to_thread(get_current_vix)
            vix_buffer = vix_to_ratio_buffer(vix)
            await _check_vix_tier_change(vix, health, channels)
            logger.info(f"VIX={vix:.1f} → dynamic ratio buffer={vix_buffer}%")

            compliant_count = 0
            for pos in positions:
                symbol = str(pos["symbol"])
                qty = int(pos["quantity"])

                ca_alerts = await asyncio.to_thread(check_corporate_actions, symbol)
                for ca in ca_alerts:
                    logger.warning(f"Corporate action detected: {symbol} — {ca.action_type}: {ca.headline}")
                    await send_alert(
                        f"WATCH: {symbol} — {ca.action_type}",
                        f"Corporate action detected: {ca.headline}\n"
                        f"Compliance ratios may change. Manual review recommended.",
                        channels,
                    )

                compliance_status = await loop.run_in_executor(
                    None, live_shariah_screen, symbol, vix_buffer
                )
                await asyncio.to_thread(persist_compliance, symbol, compliance_status)

                if not compliance_status.is_compliant:
                    logger.warning(f"CRITICAL: {symbol} NON-COMPLIANT. Reason: {compliance_status.reason}")
                    await manager.broadcast(ComplianceViolationMessage(payload=ComplianceViolationPayload(
                        symbol=symbol,
                        reason=compliance_status.reason,
                        auto_liquidate=auto_liquidate,
                    )))
                    if qty > 0 and auto_liquidate:
                        logger.info(f"Kill-switch: liquidating {qty} shares of {symbol}...")
                        trade_req = TradeCreate(symbol=symbol, quantity=qty, side="SELL")
                        await trader.execute_trade(trade_req, pre_screened=compliance_status, force_liquidation=True)
                        await send_alert(
                            f"LIQUIDATED: {symbol}",
                            f"Non-compliant. Reason: {compliance_status.reason}\n{qty} shares sold (kill-switch).",
                            channels,
                        )
                    elif qty > 0:
                        logger.warning(f"{symbol} non-compliant but critical_auto_sell=False — manual action required.")
                        await send_alert(
                            f"ACTION REQUIRED: {symbol} Non-Compliant",
                            f"Reason: {compliance_status.reason}\ncritical_auto_sell=False — sell manually.",
                            channels,
                        )
                else:
                    compliant_count += 1
                    logger.info(f"Audit: {symbol} COMPLIANT.")
            
            PORTFOLIO_COMPLIANCE_PCT.set((compliant_count / len(positions)) * 100)
        except Exception as e:
            logger.exception(f"Error in compliance_audit_loop: {e}")
