import logging
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from ibkr_core.features.zakat.zakat import calculate_zakat, fetch_nisab_usd
from ibkr_core.features.zakat.purification import calculate_purification_amount
from ibkr_core.features.zakat.hawl import get_hawl_status, update_hawl, reset_hawl
from ibkr_core.core.database import get_db
from ibkr_core.core.models import PurificationHistory, TradeHistory, PositionCompliance
from ibkr_core.core.state import TradeState
from typing import Dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/zakat", tags=["zakat"])


class ZakatRequest(BaseModel):
    zakatable_assets_value: float
    rate: float = 0.025
    nisab: Optional[float] = None  # None = fetch live gold price


class ZakatResponse(BaseModel):
    zakatable_assets_value: float
    rate: float
    nisab: float
    zakat_due: float
    below_nisab: bool


class PurificationRequest(BaseModel):
    total_dividend: float
    non_compliant_revenue_pct: float


class PurificationResponse(BaseModel):
    total_dividend: float
    non_compliant_revenue_pct: float
    purification_amount: float


class PurificationRecordRequest(BaseModel):
    symbol: str
    dividend_amount: float
    purification_amount: float
    donation_receipt_link: Optional[str] = None


class PurificationRecordResponse(BaseModel):
    id: int
    symbol: str
    dividend_amount: float
    purification_amount: float
    donation_receipt_link: Optional[str]
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class PurificationLiability(BaseModel):
    symbol: str
    realized_profit: float
    impure_revenue_pct: float
    purification_due: float
    purified_already: float
    remaining_liability: float


@router.get("/purification/liabilities", response_model=List[PurificationLiability])
def get_purification_liabilities(db: Session = Depends(get_db)) -> List[PurificationLiability]:
    """
    Calculates purification due from realized capital gains.
    Formula: Σ(profit * impure_revenue_pct) - already_purified
    """
    # 1. Get realized P&L per symbol
    filled_trades = db.query(TradeHistory).filter(TradeHistory.state == TradeState.FILLED).all()
    realized_by_symbol: Dict[str, float] = {}
    for t in filled_trades:
        sign = 1.0 if t.side == "SELL" else -1.0
        realized_by_symbol[t.symbol] = realized_by_symbol.get(t.symbol, 0.0) + (sign * (t.fill_price or 0) * (t.quantity or 0))

    # 2. Get most recent compliance snapshots (for impure_revenue_pct)
    latest_compliance = db.query(PositionCompliance).order_by(PositionCompliance.timestamp.desc()).all()
    comp_map: Dict[str, float] = {}
    for c in latest_compliance:
        if c.symbol not in comp_map:
            comp_map[c.symbol] = c.metrics.get("impure_revenue_pct", 0.0)

    # 3. Get already purified amounts
    history = db.query(PurificationHistory).all()
    purified_map: Dict[str, float] = {}
    for h in history:
        purified_map[h.symbol] = purified_map.get(h.symbol, 0.0) + h.purification_amount

    # 4. Build liabilities
    liabilities = []
    for symbol, profit in realized_by_symbol.items():
        if profit <= 0:
            continue
            
        impure_pct = comp_map.get(symbol, 0.0)
        total_due = profit * impure_pct
        already_paid = purified_map.get(symbol, 0.0)
        
        liabilities.append(PurificationLiability(
            symbol=symbol,
            realized_profit=profit,
            impure_revenue_pct=impure_pct,
            purification_due=total_due,
            purified_already=already_paid,
            remaining_liability=max(0, total_due - already_paid)
        ))
        
    return liabilities


@router.post("/calculate", response_model=ZakatResponse)
def zakat_calculate(req: ZakatRequest) -> ZakatResponse:
    nisab = req.nisab if req.nisab is not None else fetch_nisab_usd()
    due = calculate_zakat(req.zakatable_assets_value, req.rate, nisab)
    return ZakatResponse(
        zakatable_assets_value=req.zakatable_assets_value,
        rate=req.rate,
        nisab=nisab,
        zakat_due=due,
        below_nisab=req.zakatable_assets_value < nisab,
    )


@router.post("/purification", response_model=PurificationResponse)
def purification_calculate(req: PurificationRequest) -> PurificationResponse:
    amount = calculate_purification_amount(req.total_dividend, req.non_compliant_revenue_pct)
    return PurificationResponse(
        total_dividend=req.total_dividend,
        non_compliant_revenue_pct=req.non_compliant_revenue_pct,
        purification_amount=amount,
    )


@router.post("/purification/record", response_model=PurificationRecordResponse)
def record_purification(
    req: PurificationRecordRequest,
    db: Session = Depends(get_db),
) -> PurificationRecordResponse:
    """Record a completed purification donation. Ref: AUDIT_LOG.md Section 3."""
    entry = PurificationHistory(
        symbol=req.symbol.upper(),
        dividend_amount=req.dividend_amount,
        purification_amount=req.purification_amount,
        donation_receipt_link=req.donation_receipt_link,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/hawl")
def hawl_status(request: Request) -> dict:
    """
    Returns current Hawl (lunar year) status — when Zakat is due.
    Also triggers a hawl update using live portfolio value.
    """
    worker = getattr(request.app.state, "worker", None)
    portfolio_value = 0.0
    try:
        if worker and worker.ib.isConnected():
            portfolio_value = float(worker.get_net_liquidation())
    except Exception:
        # $0 can push the portfolio under nisab and reset the hawl clock.
        logger.warning("Portfolio value unavailable for the hawl update — using $0, "
                       "which may read as below nisab", exc_info=True)
    nisab = fetch_nisab_usd()
    update_hawl(portfolio_value, nisab)
    return get_hawl_status(portfolio_value, nisab)


@router.post("/hawl/reset")
def hawl_reset() -> dict:
    """Reset Hawl after Zakat has been paid — starts new cycle."""
    reset_hawl()
    return {"status": "reset", "message": "Hawl reset. New cycle begins when portfolio exceeds Nisab."}


@router.get("/purification/history", response_model=List[PurificationRecordResponse])
def purification_history(
    symbol: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[PurificationHistory]:
    q = db.query(PurificationHistory)
    if symbol:
        q = q.filter(PurificationHistory.symbol == symbol.upper())
    return q.order_by(PurificationHistory.timestamp.desc()).all()
