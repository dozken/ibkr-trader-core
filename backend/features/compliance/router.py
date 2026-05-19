import csv
import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.features.compliance.schemas import ComplianceStatus
from backend.features.compliance.screening import check_shariah_compliance, live_shariah_screen
from backend.features.compliance.service import persist_compliance
from backend.features.compliance.data_fetcher import normalize_ticker, search_symbol
from backend.core.database import get_db
from backend.core.models import AuditLog, PositionCompliance
from backend.core.audit import verify_audit_chain

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


class AuditEntry(BaseModel):
    id: int
    timestamp: datetime
    symbol: str
    action: str
    shariah_status: str
    data_source: Optional[str]
    metrics: dict
    business_activity: Optional[str]
    ibkr_order_id: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ManualScreenRequest(BaseModel):
    symbol: str
    debt: float
    cash: float
    revenue: float
    prohibited_income: float
    mkt_cap: float
    sector: str


class ScreenPositionsRequest(BaseModel):
    symbols: List[str]


class PositionComplianceRecord(BaseModel):
    symbol: str
    shariah_status: str
    metrics: dict
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)



@router.post("/screen-positions", response_model=List[ComplianceStatus])
async def screen_positions(req: ScreenPositionsRequest) -> List[ComplianceStatus]:
    import asyncio
    from backend.features.compliance.screening import screen_many
    results = await screen_many([s.upper() for s in req.symbols if s.strip()])
    loop = asyncio.get_running_loop()
    for r in results:
        await loop.run_in_executor(None, persist_compliance, r.symbol, r)
    return results


@router.get("/positions", response_model=List[PositionComplianceRecord])
def get_position_compliance(db: Session = Depends(get_db)) -> List[PositionCompliance]:
    """Latest compliance record per symbol from DB."""
    subq = (
        db.query(PositionCompliance.symbol, func.max(PositionCompliance.timestamp).label("max_ts"))
        .group_by(PositionCompliance.symbol)
        .subquery()
    )
    return (
        db.query(PositionCompliance)
        .join(subq, (PositionCompliance.symbol == subq.c.symbol) & (PositionCompliance.timestamp == subq.c.max_ts))
        .all()
    )


@router.get("/search")
def search_symbols(q: str) -> list:
    """Lookup tickers by company name or partial symbol. Returns [{symbol, company_name, exchange, type}]."""
    if len(q.strip()) < 2:
        return []
    return search_symbol(q.strip(), max_results=8)


@router.post("/screen/cache/clear")
def clear_screen_cache(symbol: str | None = None):
    from backend.features.compliance.screening import invalidate_screen_cache
    invalidate_screen_cache(symbol)
    return {"cleared": symbol or "all"}


@router.get("/screen/{symbol:path}", response_model=ComplianceStatus)
def screen_symbol(symbol: str) -> ComplianceStatus:
    return live_shariah_screen(normalize_ticker(symbol))


@router.post("/screen", response_model=ComplianceStatus)
def screen_manual(req: ManualScreenRequest) -> ComplianceStatus:
    return check_shariah_compliance(
        symbol=normalize_ticker(req.symbol),
        debt=req.debt,
        cash=req.cash,
        revenue=req.revenue,
        prohibited_income=req.prohibited_income,
        mkt_cap=req.mkt_cap,
        sector=req.sector,
    )


@router.get("/audit", response_model=List[AuditEntry])
def get_audit_log(limit: int = 100, db: Session = Depends(get_db)) -> List[AuditLog]:
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()


@router.get("/audit/verify")
def verify_audit_integrity(db: Session = Depends(get_db)) -> dict:
    """
    Validates the cryptographic hash chain of the entire AuditLog table.
    Returns {valid: bool, entry_count: int, message: str}.
    """
    count = db.query(func.count(AuditLog.id)).scalar() or 0
    valid = verify_audit_chain(db)
    return {
        "valid": valid,
        "entry_count": count,
        "message": "Chain intact." if valid else "TAMPER DETECTED — hash chain broken. Check server logs.",
    }


@router.get("/audit/export/csv")
def export_audit_csv(db: Session = Depends(get_db)) -> StreamingResponse:
    """Export full AuditLog as CSV. Ref: AUDIT_LOG.md Section 4."""
    entries = db.query(AuditLog).order_by(AuditLog.timestamp.asc()).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "timestamp", "symbol", "action", "shariah_status",
        "data_source", "business_activity", "ibkr_order_id",
        "debt_to_mkt_cap", "cash_to_mkt_cap", "impure_revenue_ratio",
    ])
    for e in entries:
        m = e.metrics or {}
        writer.writerow([
            e.id, e.timestamp.isoformat(), e.symbol, e.action,
            e.shariah_status, e.data_source, e.business_activity, e.ibkr_order_id,
            m.get("debt_to_market_cap"), m.get("cash_to_market_cap"),
            m.get("impure_revenue_ratio"),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=shariah_audit_log.csv"},
    )
