import logging
from datetime import datetime, UTC
from backend.core.database import SessionLocal
from backend.core.models import TradeHistory, PositionCompliance
from backend.core.state import TradeState

logger = logging.getLogger(__name__)

async def reconcile_with_ibkr(worker) -> None:
    """
    Syncs local DB with IBKR reality on startup and after reconnect.
    Uses openTrades() (all open orders, not session-scoped) so bracket
    children and post-reconnect fills are captured.
    Ref: DISASTER_RECOVERY.md Section 2 - State Recovery.
    """
    if not worker.ib.isConnected():
        logger.error("Reconciliation failed: IBKR not connected.")
        return

    logger.info("🔄 Starting IBKR-to-Database reconciliation...")

    # 1. Live positions (offloaded — sync IBKR call must not block event loop)
    import asyncio
    positions = await asyncio.to_thread(worker.get_positions)
    logger.info("Detected %d live positions in IBKR.", len(positions))

    # 2. Build map from ALL open IBKR orders
    open_ib_trades = {t.order.orderId: t for t in worker.ib.openTrades()}
    logger.info("Detected %d open orders in IBKR.", len(open_ib_trades))

    with SessionLocal() as db:
        # 3. Reconcile every SUBMITTED/PRE_ORDER record in our DB
        pending_trades = db.query(TradeHistory).filter(
            TradeHistory.state.in_([TradeState.SUBMITTED, TradeState.PRE_ORDER])
        ).all()

        position_symbols = {p["symbol"] for p in positions}

        for trade in pending_trades:
            # PRE_ORDER with no ibkr_order_id: app crashed before IBKR call — never submitted
            if not trade.ibkr_order_id:
                trade.state = TradeState.IBKR_ERROR
                trade.updated_at = datetime.now(UTC)
                logger.warning(
                    "PRE_ORDER %d (%s %s) has no ibkr_order_id — never reached IBKR, marking IBKR_ERROR",
                    trade.id, trade.symbol, trade.side,
                )
                continue

            oid = int(trade.ibkr_order_id)

            if oid in open_ib_trades:
                ib_t = open_ib_trades[oid]
                ib_status = ib_t.orderStatus.status
                if ib_status == "Filled":
                    trade.state = TradeState.FILLED
                    trade.fill_price = ib_t.orderStatus.avgFillPrice
                    trade.updated_at = datetime.now(UTC)
                    logger.info("Reconciled order %d → FILLED", oid)
                elif ib_status in ("Cancelled", "Inactive"):
                    trade.state = TradeState.IBKR_ERROR
                    trade.updated_at = datetime.now(UTC)
                    logger.warning("Reconciled order %d → IBKR_ERROR (status: %s)", oid, ib_status)
            else:
                # Not in openTrades: order completed (filled or cancelled) while app was down.
                if trade.side == "BUY" and trade.symbol in position_symbols:
                    # BUY filled: we hold the position
                    trade.state = TradeState.FILLED
                    trade.updated_at = datetime.now(UTC)
                    logger.info(
                        "Reconciled order %d (%s BUY) → FILLED (position exists in IBKR)",
                        oid, trade.symbol,
                    )
                elif trade.side == "SELL" and trade.symbol not in position_symbols:
                    # SELL filled: we no longer hold the position
                    trade.state = TradeState.FILLED
                    trade.updated_at = datetime.now(UTC)
                    logger.info(
                        "Reconciled order %d (%s SELL) → FILLED (position gone from IBKR)",
                        oid, trade.symbol,
                    )
                elif trade.side == "SELL" and trade.symbol in position_symbols:
                    # SELL cancelled/rejected: we still hold the position
                    trade.state = TradeState.IBKR_ERROR
                    trade.updated_at = datetime.now(UTC)
                    logger.warning(
                        "Reconciled order %d (%s SELL) → IBKR_ERROR (position still in IBKR — likely cancelled)",
                        oid, trade.symbol,
                    )
                else:
                    # BUY not in positions and not in openTrades — cancelled before fill
                    trade.state = TradeState.IBKR_ERROR
                    trade.updated_at = datetime.now(UTC)
                    logger.warning(
                        "Reconciled order %d (%s BUY) → IBKR_ERROR (not in openTrades, not in positions)",
                        oid, trade.symbol,
                    )

        db.commit()

    logger.info("✅ Reconciliation complete.")
