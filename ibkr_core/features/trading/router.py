import asyncio
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from ibkr_core.core.database import get_db, SessionLocal
from ibkr_core.core.models import TradeHistory, TwapExecution, PendingSignal, SignalLog
from ibkr_core.features.trading.schemas import TradeCreate, Trade
from ibkr_core.core.state import TradeState
from ibkr_core.core.auth import require_api_key
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trades", tags=["trading"])

_LIVE_PORTS = {7496, 4001}


class TradeResponse(BaseModel):
    id: int
    symbol: str
    quantity: float
    side: str
    order_type: str
    state: str
    ibkr_order_id: int | None
    fill_price: float | None
    commission: float | None
    signal_price: float | None
    slippage_delta: float | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TwapExecutionResponse(BaseModel):
    id: int
    symbol: str
    slice_qty: float
    n_slices: int
    slices_submitted: int
    interval_secs: int
    stop_price: float | None
    tp_price: float | None
    exchange: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PendingSignalResponse(BaseModel):
    id: int
    symbol: str
    action: str
    confidence: float
    sentiment_score: float | None
    reasoning: str | None
    exchange: str | None
    source: str | None
    account_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApproveRequest(BaseModel):
    symbol: str
    side: str
    account_id: Optional[int] = None


@router.get("", response_model=List[TradeResponse])
def list_trades(limit: int = 50, account_id: Optional[int] = None,
                db: Session = Depends(get_db)) -> List[TradeHistory]:
    q = db.query(TradeHistory)
    if account_id is not None:
        q = q.filter(TradeHistory.account_id == account_id)
    return q.order_by(TradeHistory.created_at.desc()).limit(limit).all()


@router.get("/twap", response_model=List[TwapExecutionResponse])
def list_twap(status: Optional[str] = None, db: Session = Depends(get_db)):
    """List TWAP executions. Filter by status=RUNNING|COMPLETED|FAILED."""
    q = db.query(TwapExecution)
    if status:
        q = q.filter(TwapExecution.status == status)
    return q.order_by(TwapExecution.created_at.desc()).limit(50).all()


@router.get("/pending", response_model=List[PendingSignalResponse])
def list_pending_signals(account_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List signals awaiting human approval (unresolved). Optionally filter by account."""
    q = db.query(PendingSignal).filter(PendingSignal.resolved == False)  # noqa: E712
    if account_id is not None:
        q = q.filter(PendingSignal.account_id == account_id)
    return q.order_by(PendingSignal.created_at.desc()).all()


@router.post("/pending/{signal_id}/resolve", dependencies=[Depends(require_api_key)])
def resolve_pending_signal(signal_id: int, db: Session = Depends(get_db)):
    """Mark a pending signal as resolved (dismissed without executing)."""
    sig = db.query(PendingSignal).filter(PendingSignal.id == signal_id).first()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    sig.resolved = True
    db.commit()
    return {"status": "resolved", "id": signal_id}


@router.post("/twap/{twap_id}/cancel", dependencies=[Depends(require_api_key)])
def cancel_twap(twap_id: int, db: Session = Depends(get_db)):
    """
    Stop future TWAP slices. Already-submitted slices remain active in IBKR.
    Cancel those separately via /cancel-order if needed.
    """
    twap = db.query(TwapExecution).filter(TwapExecution.id == twap_id).first()
    if not twap:
        raise HTTPException(status_code=404, detail="TWAP execution not found")
    if twap.status != "RUNNING":
        raise HTTPException(status_code=400, detail=f"Cannot cancel — status is {twap.status}")
    twap.status = "CANCELLED"
    db.commit()
    return {"status": "cancelled", "id": twap_id, "slices_submitted": twap.slices_submitted, "n_slices": twap.n_slices}


def _resolve_worker(request: Request, account_id: Optional[int]):
    """Return the IBKRWorker for the given account, falling back to the primary worker."""
    mgr = getattr(request.app.state, "account_manager", None)
    if mgr and account_id is not None:
        from ibkr_core.core.database import SessionLocal
        from ibkr_core.core.models import Account as AccountModel
        db = SessionLocal()
        try:
            acc = db.query(AccountModel).filter(AccountModel.id == account_id, AccountModel.is_active == True).first()
            if acc:
                return mgr.get_worker(acc.id, acc.host, acc.port, acc.client_id)
        finally:
            db.close()
    return getattr(request.app.state, "worker", None)


@router.post("/approve", dependencies=[Depends(require_api_key)])
async def approve_trade(body: ApproveRequest, request: Request):
    """
    User-initiated trade execution from a signal recommendation.
    Runs a fresh Shariah compliance check before executing.
    Ref: AGENT.md AI Autonomy constraint — AI recommends, human approves.
    """
    from ibkr_core.features.compliance.screening import live_shariah_screen
    from ibkr_core.features.trading.trader import Trader

    logger.info(f"Approve request received for {body.symbol} ({body.side}) account={body.account_id}")
    try:
        worker = _resolve_worker(request, body.account_id)
        if worker is None:
            logger.warning("Approve failed: worker not connected")
            raise HTTPException(status_code=503, detail="IBKR worker not connected")

        loop = asyncio.get_running_loop()
        compliance = await loop.run_in_executor(None, live_shariah_screen, body.symbol)

        trade_req = TradeCreate(symbol=body.symbol, quantity=0, side=body.side)
        trader = Trader(worker, account_id=body.account_id)
        exchange = getattr(compliance, "exchange", None) or "NMS"

        trade = await trader.execute_trade(
            trade_req,
            exchange=exchange,
            pre_screened=compliance,
        )

        return {"state": trade.state, "symbol": trade.symbol, "quantity": trade.quantity,
                "ibkr_order_id": trade.ibkr_order_id, "compliance_snapshot": compliance.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"CRITICAL: approve_trade failed for {body.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ibkr/health")
def ibkr_health(request: Request) -> dict:
    """
    Phase 6 live audit: connectivity, port type (LIVE/PAPER), and account safety check.
    Returns warnings if margin or live port detected.
    """
    host = os.getenv("IBKR_HOST", "127.0.0.1")
    port = int(os.getenv("IBKR_PORT", "7497"))
    port_type = "LIVE" if port in _LIVE_PORTS else "PAPER"

    worker = getattr(request.app.state, "worker", None)
    if worker is None or not worker.ib.isConnected():
        return {
            "connected": False,
            "host": host,
            "port": port,
            "port_type": port_type,
            "account_id": None,
            "account_type": None,
            "warnings": [],
        }

    summary = worker.get_account_summary()
    effective_port_type = "LIVE" if worker.port in _LIVE_PORTS else "PAPER"
    warnings = list(summary["warnings"])
    if effective_port_type == "LIVE":
        warnings.append("LIVE port connected — real capital at risk")

    return {
        "connected": True,
        "host": worker.host,
        "port": worker.port,
        "port_type": effective_port_type,
        "account_id": summary["account_id"],
        "account_type": summary["account_type"],
        "warnings": warnings,
    }


@router.get("/open-orders", dependencies=[Depends(require_api_key)])
def get_open_orders(request: Request):
    """Returns all working orders from IBKR."""
    worker = getattr(request.app.state, "worker", None)
    if worker is None or not worker.ib.isConnected():
        raise HTTPException(status_code=503, detail="IBKR not connected")
    return {"open_orders": worker.get_open_orders()}


@router.post("/cancel-all-orders", dependencies=[Depends(require_api_key)])
def cancel_all_orders(request: Request):
    """Broadcasts global cancel to IBKR — cancels every open order."""
    worker = getattr(request.app.state, "worker", None)
    if worker is None or not worker.ib.isConnected():
        raise HTTPException(status_code=503, detail="IBKR not connected")
    worker.cancel_all_orders()
    return {"status": "cancel sent"}


@router.post("/cancel-order/{order_id}", dependencies=[Depends(require_api_key)])
def cancel_order(order_id: int, request: Request):
    """Cancels a single IBKR order by order ID."""
    worker = getattr(request.app.state, "worker", None)
    if worker is None or not worker.ib.isConnected():
        raise HTTPException(status_code=503, detail="IBKR not connected")
    ok = worker.cancel_order(order_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found in open orders")
    return {"status": "cancel sent", "order_id": order_id}


# ── Position Trimmer ──────────────────────────────────────────────────────────

class TrimSuggestion(BaseModel):
    symbol: str
    score: float
    reason: str
    quantity: float


class TrimResponse(BaseModel):
    over_limit: int
    max_positions: int
    suggested_sells: List[TrimSuggestion]
    executed: bool


def _quick_t_score(symbol: str) -> float:
    """
    Fallback score computed from yfinance: SMA20 cross + 5-day momentum.
    Returns a float in [0, 100].  Higher = stronger signal.
    """
    try:
        import yfinance as yf
        import numpy as np

        hist = yf.Ticker(symbol).history(period="30d", interval="1d", auto_adjust=True)
        if len(hist) < 20:
            return 50.0
        close = hist["Close"].values
        sma20 = close[-20:].mean()
        momentum_5d = (close[-1] - close[-6]) / close[-6] if close[-6] != 0 else 0.0
        # Price above SMA20 → above-average score; 5-day momentum adds ±30 pts
        base = 50.0 + (10.0 if close[-1] > sma20 else -10.0)
        score = base + float(np.clip(momentum_5d * 100, -30.0, 30.0))
        return float(np.clip(score, 0.0, 100.0))
    except Exception:
        return 50.0


def _get_signal_score(symbol: str) -> float:
    """Return the latest t_score from SignalLog, falling back to _quick_t_score."""
    try:
        with SessionLocal() as db:
            row = (
                db.query(SignalLog)
                .filter(SignalLog.symbol == symbol)
                .order_by(SignalLog.created_at.desc())
                .first()
            )
        if row is not None and row.t_score is not None:
            return float(row.t_score)
    except Exception:
        pass
    return _quick_t_score(symbol)


@router.post("/trim", response_model=TrimResponse, dependencies=[Depends(require_api_key)])
async def trim_positions(
    request: Request,
    execute: bool = Query(default=False, description="Set true to auto-sell the weakest positions"),
):
    """
    Identify positions over max_positions limit and surface the weakest ones
    (by signal score) as suggested SELLs.

    Pass ?execute=true to dispatch the SELLs immediately via the trader.
    """
    from ibkr_core.features.settings.service import load_settings
    from ibkr_core.features.trading.trader import Trader

    worker = _resolve_worker(request, None)
    if worker is None:
        raise HTTPException(status_code=503, detail="IBKR worker not connected")

    settings = await asyncio.to_thread(load_settings)
    max_positions = int(settings.get("max_positions", 15))

    positions = await asyncio.to_thread(worker.get_positions)
    n_positions = len(positions)
    over_limit = max(0, n_positions - max_positions)

    if over_limit == 0:
        return TrimResponse(
            over_limit=0,
            max_positions=max_positions,
            suggested_sells=[],
            executed=False,
        )

    # Score every position (blocking yfinance calls offloaded to thread pool)
    scored: list[tuple[float, dict]] = []
    for pos in positions:
        symbol = pos.get("symbol", "")
        score = await asyncio.to_thread(_get_signal_score, symbol)
        scored.append((score, pos))

    # Sort ascending — weakest first
    scored.sort(key=lambda x: x[0])
    weakest = scored[:over_limit]

    suggestions = [
        TrimSuggestion(
            symbol=pos.get("symbol", ""),
            score=round(score, 2),
            reason="Weakest signal",
            quantity=float(pos.get("quantity", 0)),
        )
        for score, pos in weakest
    ]

    executed = False
    if execute:
        from ibkr_core.features.compliance.screening import live_shariah_screen

        trader = Trader(worker)
        for suggestion in suggestions:
            try:
                compliance = await asyncio.to_thread(live_shariah_screen, suggestion.symbol)
                trade_req = TradeCreate(
                    symbol=suggestion.symbol,
                    quantity=suggestion.quantity,
                    side="SELL",
                )
                await trader.execute_trade(trade_req, exchange=compliance.exchange or "NMS", pre_screened=compliance)
                logger.info("Trim: sold %s (score=%.1f)", suggestion.symbol, suggestion.score)
            except Exception as exc:
                logger.warning("Trim: failed to sell %s: %s", suggestion.symbol, exc)
        executed = True

    return TrimResponse(
        over_limit=over_limit,
        max_positions=max_positions,
        suggested_sells=suggestions,
        executed=executed,
    )


class EmergencyLiquidateRequest(BaseModel):
    emergency_pin: str
    account_id: Optional[int] = None


@router.post("/emergency-liquidate", dependencies=[Depends(require_api_key)])
async def emergency_liquidate(body: EmergencyLiquidateRequest, request: Request):
    """
    Sell every open position immediately at market price.
    Requires EMERGENCY_PIN env var to be set and matched.
    Protected by X-Api-Key header AND pin — two independent secrets.
    """
    import os
    from ibkr_core.features.compliance.screening import live_shariah_screen
    from ibkr_core.features.trading.trader import Trader

    required_pin = os.getenv("EMERGENCY_PIN", "")
    if not required_pin:
        raise HTTPException(status_code=503, detail="EMERGENCY_PIN env var not configured on server")
    if body.emergency_pin != required_pin:
        raise HTTPException(status_code=403, detail="Invalid emergency PIN")

    worker = _resolve_worker(request, body.account_id)
    if worker is None or not worker.ib.isConnected():
        raise HTTPException(status_code=503, detail="IBKR worker not connected")

    positions = await asyncio.to_thread(worker.get_positions)
    if not positions:
        return {"liquidated": [], "skipped": [], "total": 0}

    trader = Trader(worker, account_id=body.account_id)
    liquidated, skipped = [], []

    for pos in positions:
        symbol = pos.get("symbol", "")
        qty = float(pos.get("quantity", 0))
        if not symbol or qty <= 0:
            continue
        try:
            compliance = await asyncio.to_thread(live_shariah_screen, symbol)
            trade_req = TradeCreate(symbol=symbol, quantity=qty, side="SELL")
            await trader.execute_trade(
                trade_req,
                exchange=compliance.exchange or "NMS",
                pre_screened=compliance,
                force_liquidation=True,
            )
            logger.warning("EMERGENCY LIQUIDATE: sold %s qty=%.4f", symbol, qty)
            liquidated.append(symbol)
        except Exception as exc:
            logger.error("EMERGENCY LIQUIDATE: failed %s: %s", symbol, exc)
            skipped.append({"symbol": symbol, "error": str(exc)})

    return {"liquidated": liquidated, "skipped": skipped, "total": len(liquidated)}


class BatchSellRequest(BaseModel):
    symbols: List[str]
    account_id: Optional[int] = None


@router.post("/batch-sell", dependencies=[Depends(require_api_key)])
async def batch_sell(body: BatchSellRequest, request: Request):
    """Sell specific positions by symbol at market price."""
    from ibkr_core.features.compliance.screening import live_shariah_screen
    from ibkr_core.features.trading.trader import Trader

    if not body.symbols:
        raise HTTPException(status_code=400, detail="No symbols provided")

    worker = _resolve_worker(request, body.account_id)
    if worker is None or not worker.ib.isConnected():
        raise HTTPException(status_code=503, detail="IBKR worker not connected")

    positions = await asyncio.to_thread(worker.get_positions)
    pos_map = {p["symbol"]: float(p.get("quantity", 0)) for p in positions if p.get("symbol")}

    trader = Trader(worker, account_id=body.account_id)
    sold, skipped = [], []

    for symbol in body.symbols:
        qty = pos_map.get(symbol, 0)
        if qty <= 0:
            skipped.append({"symbol": symbol, "error": "no position"})
            continue
        try:
            compliance = await asyncio.to_thread(live_shariah_screen, symbol)
            trade_req = TradeCreate(symbol=symbol, quantity=qty, side="SELL")
            await trader.execute_trade(
                trade_req,
                exchange=compliance.exchange or "NMS",
                pre_screened=compliance,
            )
            logger.info("BATCH SELL: sold %s qty=%.4f", symbol, qty)
            sold.append(symbol)
        except Exception as exc:
            logger.error("BATCH SELL: failed %s: %s", symbol, exc)
            skipped.append({"symbol": symbol, "error": str(exc)})

    return {"sold": sold, "skipped": skipped, "total": len(sold)}
