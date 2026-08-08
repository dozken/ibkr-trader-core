from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
import os
import logging
import asyncio
from typing import Dict, List, Optional, Literal
from datetime import datetime, timedelta
from pydantic import BaseModel, ConfigDict
import yfinance as yf
import pandas as pd

from ibkr_core.core.market_hours import market_status, EXCHANGE_CONFIG
from ibkr_core.core.database import get_db
from ibkr_core.core.models import TradeHistory, PortfolioSnapshot, PositionCompliance, PurificationHistory, AuditLog
from ibkr_core.core.state import TradeState
from ibkr_core.features.portfolio.allocator import PortfolioAllocator
from ibkr_core.features.trading.schemas import TradeSignal, TradeCreate
from ibkr_core.features.trading.order_policy import LIVE_PORTS as _LIVE_PORTS
from ibkr_core.features.settings.service import load_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _resolve_worker(request: Request, account_id: Optional[int] = None):
    if account_id is not None:
        mgr = getattr(request.app.state, "account_manager", None)
        if mgr:
            w = mgr.get_worker_by_id(account_id)
            if w:
                return w
    return getattr(request.app.state, "worker", None)

class SimulationRequest(BaseModel):
    symbol: str
    quantity: float
    price: float
    side: str

class SimulationResponse(BaseModel):
    cash_available_before: float
    cash_available_after: float
    portfolio_purity_before: float
    portfolio_purity_after: float
    sector_concentration_before: float
    sector_concentration_after: float
    warnings: List[str]

class AllocateRequest(BaseModel):
    available_cash: float
    signals: List[TradeSignal]
    current_prices: Dict[str, float]


class PortfolioValue(BaseModel):
    available_funds: float
    connected: bool
    account_type: Literal["PAPER", "LIVE"] = "PAPER"


class Position(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    market_value: float = 0.0
    unrealized_pnl: float = 0.0

@router.post("/simulate", response_model=SimulationResponse)
async def simulate_trade(req: SimulationRequest, request: Request, db: Session = Depends(get_db)):
    worker = getattr(request.app.state, "worker", None)
    if not worker or not worker.ib.isConnected():
        raise HTTPException(status_code=503, detail="IBKR not connected")

    settings = load_settings()
    max_concentration_pct = settings.get("max_position_size_pct", 10.0)

    try:
        available_funds = float(worker.get_available_funds())
        net_liq = float(worker.get_net_liquidation())
        positions = worker.get_positions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch IBKR data: {e}")

    symbols = [p["symbol"] for p in positions]
    if req.symbol not in symbols:
        symbols.append(req.symbol)
    
    comp_records = (
        db.query(AuditLog)
        .filter(AuditLog.symbol.in_(symbols))
        .order_by(AuditLog.timestamp.desc())
        .all()
    )
    
    # Take the latest audit log for each symbol
    comp_map = {}
    for c in comp_records:
        if c.symbol not in comp_map:
            comp_map[c.symbol] = {
                "sector": c.business_activity or "Unknown",
                "impure_pct": c.metrics.get("impure_revenue_ratio", 0.0) if isinstance(c.metrics, dict) else 0.0
            }
    
    target_sector = comp_map.get(req.symbol, {}).get("sector", "Unknown")

    total_value = sum(float(p.get("market_value", 0)) for p in positions)
    
    weighted_purity = sum(float(p.get("market_value", 0)) * comp_map.get(p["symbol"], {}).get("impure_pct", 0.0) for p in positions)
    purity_before = (weighted_purity / total_value) if total_value > 0 else 0.0

    sector_value = sum(float(p.get("market_value", 0)) for p in positions if comp_map.get(p["symbol"], {}).get("sector") == target_sector)
    sector_before = (sector_value / total_value) if total_value > 0 else 0.0

    if req.price <= 0:
        try:
            req.price = await worker.get_last_price(req.symbol)
        except Exception:
            req.price = 100.0  # Fallback

    if req.quantity <= 0:
        reserve = net_liq * (settings.get("cash_reserve_pct", 5.0) / 100)
        investable = max(available_funds - reserve, 0.0)
        max_position = net_liq * (settings.get("max_position_size_pct", 10.0) / 100)
        dollars = min(investable, max_position)
        if dollars < settings.get("min_trade_size", 10.0):
            req.quantity = 0.0
        else:
            req.quantity = dollars / req.price

    trade_value = req.quantity * req.price
    target_sym_val_before = sum(float(p.get("market_value", 0)) for p in positions if p["symbol"] == req.symbol)
    
    if req.side.upper() == "BUY":
        cash_after = available_funds - trade_value
        total_value_after = total_value + trade_value
        new_sector_value = sector_value + trade_value
        new_weighted_purity = weighted_purity + (trade_value * comp_map.get(req.symbol, {}).get("impure_pct", 0.0))
        target_sym_val_after = target_sym_val_before + trade_value
    else:
        cash_after = available_funds + trade_value
        total_value_after = total_value - trade_value
        new_sector_value = max(0, sector_value - trade_value)
        new_weighted_purity = max(0, weighted_purity - (trade_value * comp_map.get(req.symbol, {}).get("impure_pct", 0.0)))
        target_sym_val_after = max(0, target_sym_val_before - trade_value)

    if total_value_after > 0:
        purity_after = new_weighted_purity / total_value_after
        sector_after = new_sector_value / total_value_after
    else:
        purity_after = 0.0
        sector_after = 0.0

    warnings = []
    if cash_after < 0:
        warnings.append(f"Trade exceeds available cash (shortfall: ${abs(cash_after):.2f})")
    
    if net_liq > 0 and (target_sym_val_after / net_liq) > (max_concentration_pct / 100.0):
         warnings.append(f"Exceeds {max_concentration_pct}% max position size limit")

    return SimulationResponse(
        cash_available_before=available_funds,
        cash_available_after=cash_after,
        portfolio_purity_before=purity_before,
        portfolio_purity_after=purity_after,
        sector_concentration_before=sector_before,
        sector_concentration_after=sector_after,
        warnings=warnings
    )

@router.get("/rebalance/preview", response_model=List[TradeCreate])
async def get_rebalance_preview(request: Request) -> List[TradeCreate]:
    """
    Previews trades required to align portfolio with target weights.
    Ref: Phase 1 - Portfolio Autopilot.
    """
    settings = load_settings()
    target_weights = settings.get("target_weights", {})
    if not target_weights:
        return []
        
    worker = getattr(request.app.state, "worker", None)
    if not worker or not worker.ib.isConnected():
        return []
        
    positions = worker.get_positions()
    total_val = worker.get_net_liquidation()
    
    # Fetch current prices for all symbols in targets or holdings
    symbols = list(set(target_weights.keys()) | {p["symbol"] for p in positions})
    
    price_map: Dict[str, float] = {}
    async def _fetch(s):
        try:
            price_map[s] = await worker.get_last_price(s)
        except Exception:
            pass
            
    await asyncio.gather(*[_fetch(s) for s in symbols])
    
    allocator = PortfolioAllocator(
        min_trade_size=settings.get("min_trade_size", 100.0),
        max_commission_pct=settings.get("max_commission_pct", 0.005)
    )
    
    trades = allocator.rebalance(
        total_value=total_val,
        current_positions=positions,
        target_weights=target_weights,
        current_prices=price_map
    )
    
    return trades


@router.get("/value", response_model=PortfolioValue)
def get_portfolio_value(request: Request, account_id: Optional[int] = None) -> PortfolioValue:
    worker = _resolve_worker(request, account_id)

    worker_port = worker.port if worker else int(os.environ.get("IBKR_PORT", "7497"))
    account_type = "LIVE" if worker_port in _LIVE_PORTS else "PAPER"
    
    try:
        if worker and worker.ib.isConnected():
            return PortfolioValue(
                available_funds=worker.get_available_funds(), 
                connected=True,
                account_type=account_type
            )
    except Exception:
        pass
    return PortfolioValue(available_funds=0.0, connected=False, account_type=account_type)


@router.get("/markets")
def get_market_status():
    return [market_status(ex) for ex in EXCHANGE_CONFIG]


@router.get("/positions", response_model=List[Position])
def get_positions(request: Request, account_id: Optional[int] = None) -> List[Position]:
    worker = _resolve_worker(request, account_id)
    try:
        if worker and worker.ib.isConnected():
            return [Position(**p) for p in worker.get_positions()]
    except Exception:
        pass
    return []


@router.post("/allocate", response_model=List[TradeCreate])
def allocate(req: AllocateRequest) -> List[TradeCreate]:
    allocator = PortfolioAllocator()
    return allocator.allocate(req.available_cash, req.signals, req.current_prices)


class DividendData(BaseModel):
    symbol: str
    past12_per_share: Optional[float]
    quantity: float
    total_received: Optional[float]


@router.get("/dividends", response_model=List[DividendData])
async def get_dividends(request: Request) -> List[DividendData]:
    """Past-12-month dividends for all positions via IBKR tick 456."""
    worker = getattr(request.app.state, "worker", None)
    if not worker or not worker.ib.isConnected():
        return []
    try:
        positions = worker.get_positions()
        return [DividendData(**r) for r in await worker.get_dividends_batch(positions)]
    except Exception:
        return []


class PositionPnL(BaseModel):
    symbol: str
    unrealized_pnl: float
    realized_pnl: float
    quantity: float
    avg_cost: float
    market_value: float
    purification_cost: float = 0.0
    halal_pnl: float = 0.0
    days_held: Optional[int] = None      # days since first BUY
    stop_price: Optional[float] = None   # avg_cost × (1 − stop_loss_pct)
    target_price: Optional[float] = None # avg_cost × (1 + take_profit_pct)
    partial_price: Optional[float] = None  # avg_cost × (1 + partial_profit_pct)


class PnLSummary(BaseModel):
    total_unrealized_pnl: float
    total_realized_pnl: float
    total_purification_cost: float = 0.0
    positions: List[PositionPnL]


class PortfolioSnapshotResponse(BaseModel):
    timestamp: datetime
    total_value: float
    cash_balance: float
    unrealized_pnl: float
    benchmark_value: Optional[float] = None  # legacy single (SPUS)
    benchmarks: Dict[str, float] = {}  # SPUS, SPY, VTI, BRK-B all normalized to 100 at start
    net_purified_value: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/history", response_model=List[PortfolioSnapshotResponse])
async def get_portfolio_history(db: Session = Depends(get_db),
                                account_id: Optional[int] = None) -> List[Dict]:
    """
    Returns historical portfolio snapshots aligned with SPUS benchmark.
    Now includes Purification-Adjusted Returns (Phase 5.3).
    """
    snaps_q = db.query(PortfolioSnapshot)
    if account_id is not None:
        snaps_q = snaps_q.filter(PortfolioSnapshot.account_id == account_id)
    snaps = snaps_q.order_by(PortfolioSnapshot.timestamp.asc()).all()
    if not snaps:
        return []

    # 1. Fetch benchmark (SPUS) for the range
    start_date = snaps[0].timestamp.date()
    end_date = (snaps[-1].timestamp + timedelta(days=1)).date()
    
    # 2. Pre-calculate realized gains over time for Zakat estimation
    trades_q = db.query(TradeHistory).filter(TradeHistory.state == TradeState.FILLED)
    if account_id is not None:
        trades_q = trades_q.filter(TradeHistory.account_id == account_id)
    filled_trades = trades_q.order_by(TradeHistory.updated_at.asc()).all()
    
    realized_series = []
    cum_realized = 0.0
    inventory = {} # symbol -> list of [qty, price]
    for t in filled_trades:
        sym = t.symbol
        qty = t.quantity or 0
        price = t.fill_price or 0.0
        if t.side == "BUY":
            if sym not in inventory:
                inventory[sym] = []
            inventory[sym].append([qty, price])
        else:
            # SELL - FIFO realized gain
            while qty > 0 and sym in inventory and inventory[sym]:
                iqty, iprice = inventory[sym][0]
                if iqty <= qty:
                    cum_realized += iqty * (price - iprice)
                    qty -= iqty
                    inventory[sym].pop(0)
                else:
                    cum_realized += qty * (price - iprice)
                    inventory[sym][0][0] -= qty
                    qty = 0
            realized_series.append((t.updated_at, cum_realized))

    # 3. Estimate purification liability (impure revenue pct)
    # We use latest known compliance ratios as a proxy for history
    compliance_rows = (
        db.query(PositionCompliance)
        .order_by(PositionCompliance.timestamp.desc())
        .all()
    )
    comp_map = {}
    for r in compliance_rows:
        if r.symbol not in comp_map:
            comp_map[r.symbol] = float((r.metrics or {}).get("impure_revenue_pct", 0.0) or 0.0)
    
    avg_impure_pct = sum(comp_map.values()) / len(comp_map) if comp_map else 0.03 # 3% default fallback

    try:
        from datetime import timedelta as _td, date as _date

        today = _date.today()
        fetch_end = min(end_date + _td(days=1), today + _td(days=1))

        # Skip date-range fetch if window has no past weekdays (yfinance logs a
        # misleading "possibly delisted" warning for empty weekend/future ranges).
        cur = start_date
        has_weekday = False
        while cur < fetch_end:
            if cur.weekday() < 5 and cur <= today:
                has_weekday = True
                break
            cur += _td(days=1)

        # Multi-benchmark: SPUS (halal), SPY (S&P 500), VTI (Vanguard total market), BRK-B (Berkshire)
        _BENCHMARKS = ["SPUS", "SPY", "VTI", "BRK-B"]

        def _fetch_one(ticker: str):
            if has_weekday:
                df = yf.download(ticker, start=start_date, end=fetch_end,
                                 interval="1d", progress=False, auto_adjust=True)
            else:
                df = pd.DataFrame()
            if df is None or df.empty:
                df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
            if df.empty:
                return {}
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df["Close"].to_dict()

        # Fetch all benchmarks in parallel
        bench_maps = {}
        bench_results = await asyncio.gather(
            *(asyncio.to_thread(_fetch_one, t) for t in _BENCHMARKS),
            return_exceptions=True,
        )
        for ticker, result in zip(_BENCHMARKS, bench_results):
            if isinstance(result, Exception):
                logger.debug("Benchmark fetch %s failed: %s", ticker, result)
                bench_maps[ticker] = {}
            else:
                bench_maps[ticker] = result

        # First-day value per benchmark (for normalization to 100)
        first_bench_per: dict = {}
        for ticker, bmap in bench_maps.items():
            for d in sorted(bmap.keys()):
                first_bench_per[ticker] = float(bmap[d])
                break

        # Backwards compat: SPUS map for legacy benchmark_value field
        bench_map = bench_maps.get("SPUS", {})
        first_bench = first_bench_per.get("SPUS")

        first_total = snaps[0].total_value if snaps[0].total_value > 0 else 1.0

        results = []
        for s in snaps:
            s_date = pd.Timestamp(s.timestamp.date())

            def _val_at(bmap):
                if not bmap:
                    return None
                if s_date in bmap:
                    return float(bmap[s_date])
                past = [d for d in bmap.keys() if d <= s_date]
                return float(bmap[max(past)]) if past else None

            b_val = _val_at(bench_map)
            bench_norm = (b_val / first_bench * 100.0) if (b_val and first_bench) else 100.0

            # Per-benchmark normalized values
            benchmarks_norm = {}
            for ticker in _BENCHMARKS:
                v = _val_at(bench_maps[ticker])
                first_v = first_bench_per.get(ticker)
                if v and first_v:
                    benchmarks_norm[ticker] = round(v / first_v * 100.0, 4)
            
            # --- Purification Adjustment (Phase 5.3) ---
            # Realized gains up to this snapshot
            z_realized = 0.0
            for ts, val in realized_series:
                if ts <= s.timestamp:
                    z_realized = val
                else:
                    break
            
            # Zakat: 2.5% of realized gains
            zakat = max(0, z_realized) * 0.025
            
            # Purification: Market Value of positions * impure pct
            pos_val = max(0, s.total_value - s.cash_balance)
            accrued_purify = pos_val * avg_impure_pct
            
            net_val = s.total_value - zakat - accrued_purify
            
            results.append({
                "timestamp": s.timestamp,
                "total_value": (s.total_value / first_total * 100.0),
                "cash_balance": s.cash_balance,
                "unrealized_pnl": s.unrealized_pnl,
                "benchmark_value": bench_norm,
                "benchmarks": benchmarks_norm,
                "net_purified_value": (net_val / first_total * 100.0)
            })
        return results
    except Exception as e:
        logger.warning(f"Benchmark fetch failed: {e}")
        first_val = snaps[0].total_value if snaps[0].total_value > 0 else 1.0
        return [{
            "timestamp": s.timestamp,
            "total_value": (s.total_value / first_val * 100.0),
            "cash_balance": s.cash_balance,
            "unrealized_pnl": s.unrealized_pnl,
            "benchmark_value": 100.0,
            "benchmarks": {},
            "net_purified_value": (s.total_value / first_val * 100.0)
        } for s in snaps]


@router.get("/pnl", response_model=PnLSummary)
def get_pnl(request: Request, db: Session = Depends(get_db),
            account_id: Optional[int] = None) -> PnLSummary:
    # 1. Fetch live positions from IBKR (graceful fallback on disconnect)
    live_positions: List[Position] = []
    worker = _resolve_worker(request, account_id)
    try:
        if worker and worker.ib.isConnected():
            live_positions = [Position(**p) for p in worker.get_positions()]
    except Exception:
        pass

    # 2. Build a map of live position data keyed by symbol
    live_map: Dict[str, Position] = {p.symbol: p for p in live_positions}

    # 3. Query filled trades, optionally scoped to account
    trades_q = db.query(TradeHistory).filter(TradeHistory.state == TradeState.FILLED)
    if account_id is not None:
        trades_q = trades_q.filter(TradeHistory.account_id == account_id)
    filled_trades = trades_q.all()

    # 4. Compute realized P&L per symbol using net cash-flow:
    #    BUY  → negative cash flow (cost)
    #    SELL → positive cash flow (proceeds)
    #    For currently-held positions: zero out — unrealized covers the open leg.
    #    Realized is only meaningful once a position is fully (or partially) closed.
    raw_realized: Dict[str, float] = {}
    for trade in filled_trades:
        fill_price = trade.fill_price or 0.0
        qty = trade.quantity or 0
        sign = 1.0 if trade.side == "SELL" else -1.0
        raw_realized[trade.symbol] = (
            raw_realized.get(trade.symbol, 0.0) + sign * fill_price * qty
        )
    # For symbols still held: raw net cash-flow spans ALL history and includes the
    # cost basis of remaining shares as a negative.  Add back qty × avg_cost so that
    # only the gain/loss on *sold* shares remains.
    #   realized = raw_net + remaining_cost_basis
    #            = (sell_proceeds − total_buy_cost) + (held_qty × avg_cost)
    #            = sell_proceeds − cost_of_sold_shares          ← correct FIFO P&L
    # Fully-closed symbols (not in live_map) need no adjustment.
    realized_by_symbol: Dict[str, float] = {}
    for sym, raw in raw_realized.items():
        if sym in live_map:
            pos = live_map[sym]
            cost_basis = float(pos.avg_cost) * float(pos.quantity)
            realized_by_symbol[sym] = raw + cost_basis
        else:
            realized_by_symbol[sym] = raw

    # 5. Settings for stop/target price levels
    settings = load_settings()
    _stop_pct = settings.get("stop_loss_pct") or settings.get("risk_profile") and {
        "CONSERVATIVE": 3.0, "BALANCED": 5.0, "AGGRESSIVE": 8.0
    }.get(settings.get("risk_profile", "BALANCED"), 5.0) or 5.0
    _take_pct = settings.get("take_profit_pct") or {"CONSERVATIVE": 6.0, "BALANCED": 10.0, "AGGRESSIVE": 16.0}.get(settings.get("risk_profile", "BALANCED"), 10.0)
    _partial_pct = float(settings.get("partial_profit_pct", 10.0))

    # 5b. First BUY date per symbol for days_held
    first_buy: Dict[str, datetime] = {}
    today = datetime.now()
    for trade in filled_trades:
        if trade.side == "BUY" and trade.symbol in live_map:
            prev = first_buy.get(trade.symbol)
            created = trade.created_at if hasattr(trade, "created_at") and trade.created_at else None
            if created and (prev is None or created < prev):
                first_buy[trade.symbol] = created

    # 6. Merge live positions with realized P&L; include symbols only in DB too
    all_symbols = set(live_map.keys()) | set(realized_by_symbol.keys())

    # 8. Fetch latest PositionCompliance per symbol for purification calculation
    compliance_rows = (
        db.query(PositionCompliance)
        .filter(PositionCompliance.symbol.in_(all_symbols))
        .order_by(PositionCompliance.timestamp.desc())
        .all()
    )
    compliance_map: Dict[str, float] = {}
    seen_compliance: set = set()
    for row in compliance_rows:
        if row.symbol not in seen_compliance:
            impure_pct = float((row.metrics or {}).get("impure_revenue_pct", 0.0) or 0.0)
            compliance_map[row.symbol] = impure_pct
            seen_compliance.add(row.symbol)

    position_pnls: List[PositionPnL] = []
    for symbol in sorted(all_symbols):
        live = live_map.get(symbol)
        mkt_val = live.market_value if live else 0.0
        unrealized = live.unrealized_pnl if live else 0.0
        purification_cost = mkt_val * compliance_map.get(symbol, 0.0)
        halal_pnl = unrealized - purification_cost
        avg_cost = live.avg_cost if live else 0.0
        stop_price = round(avg_cost * (1 - float(_stop_pct) / 100), 2) if avg_cost > 0 else None
        target_price = round(avg_cost * (1 + float(_take_pct) / 100), 2) if avg_cost > 0 else None
        partial_price = round(avg_cost * (1 + _partial_pct / 100), 2) if avg_cost > 0 else None
        entry = first_buy.get(symbol)
        days_held = (today - entry).days if entry else None

        position_pnls.append(
            PositionPnL(
                symbol=symbol,
                unrealized_pnl=unrealized,
                realized_pnl=realized_by_symbol.get(symbol, 0.0),
                quantity=live.quantity if live else 0.0,
                avg_cost=avg_cost,
                market_value=mkt_val,
                purification_cost=purification_cost,
                halal_pnl=halal_pnl,
                days_held=days_held,
                stop_price=stop_price if live else None,
                target_price=target_price if live else None,
                partial_price=partial_price if live else None,
            )
        )

    total_unrealized = sum(p.unrealized_pnl for p in position_pnls)
    total_realized = sum(p.realized_pnl for p in position_pnls)
    total_purification = sum(p.purification_cost for p in position_pnls)

    return PnLSummary(
        total_unrealized_pnl=total_unrealized,
        total_realized_pnl=total_realized,
        total_purification_cost=total_purification,
        positions=position_pnls,
    )


# ── Purification helpers & endpoints ─────────────────────────────────────────

def _compute_pending_purification(
    positions: list,
    dividends_map: Dict[str, float],
    compliance_map: Dict[str, float],
    purified_map: Dict[str, float],
) -> List[Dict]:
    """Computes pending Tazkiyah per symbol: dividends × impure_pct minus already donated."""
    result = []
    for p in positions:
        sym = p["symbol"] if isinstance(p, dict) else p.symbol
        div = dividends_map.get(sym, 0.0) or 0.0
        impure = compliance_map.get(sym, 0.0)
        needed = div * impure
        purified = purified_map.get(sym, 0.0)
        pending = max(0.0, needed - purified)
        result.append({
            "symbol": sym,
            "dividend_total": div if div > 0 else None,
            "impure_pct": impure,
            "purification_needed": needed,
            "already_purified": purified,
            "pending": pending,
        })
    return result


class PurificationPending(BaseModel):
    symbol: str
    dividend_total: Optional[float]
    impure_pct: float
    purification_needed: float
    already_purified: float
    pending: float


class PurificationRecordRequest(BaseModel):
    symbol: str
    purification_amount: float
    dividend_amount: float
    donation_receipt_link: Optional[str] = None


@router.get("/purification/pending", response_model=List[PurificationPending])
async def get_pending_purification(request: Request, db: Session = Depends(get_db),
                                   account_id: Optional[int] = None) -> List[PurificationPending]:
    """
    Returns pending Tazkiyah (purification) amounts per held position.
    Computed as: past-12m dividends × impure_revenue_pct − already recorded donations.
    """
    worker = _resolve_worker(request, account_id)
    if not worker or not worker.ib.isConnected():
        return []

    positions = worker.get_positions()
    if not positions:
        return []

    symbols = [p["symbol"] for p in positions]

    try:
        dividends_raw = await worker.get_dividends_batch(positions)
        dividends_map = {d["symbol"]: (d["total_received"] or 0.0) for d in dividends_raw}
    except Exception:
        dividends_map = {}

    comp_q = (
        db.query(PositionCompliance)
        .filter(PositionCompliance.symbol.in_(symbols))
    )
    if account_id is not None:
        comp_q = comp_q.filter(PositionCompliance.account_id == account_id)
    compliance_rows = comp_q.order_by(PositionCompliance.timestamp.desc()).all()
    compliance_map: Dict[str, float] = {}
    seen: set = set()
    for row in compliance_rows:
        if row.symbol not in seen:
            impure_pct = float((row.metrics or {}).get("impure_revenue_pct", 0.0) or 0.0)
            compliance_map[row.symbol] = impure_pct
            seen.add(row.symbol)

    purified_rows = (
        db.query(PurificationHistory.symbol, func.sum(PurificationHistory.purification_amount).label("total"))
        .filter(PurificationHistory.symbol.in_(symbols))
        .group_by(PurificationHistory.symbol)
        .all()
    )
    purified_map = {row.symbol: float(row.total) for row in purified_rows}

    raw = _compute_pending_purification(positions, dividends_map, compliance_map, purified_map)
    return [PurificationPending(**r) for r in raw]


@router.post("/purification/record", status_code=201)
def record_purification(req: PurificationRecordRequest, db: Session = Depends(get_db)):
    """Records a completed Tazkiyah donation for audit trail."""
    entry = PurificationHistory(
        symbol=req.symbol,
        dividend_amount=req.dividend_amount,
        purification_amount=req.purification_amount,
        donation_receipt_link=req.donation_receipt_link,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "symbol": entry.symbol, "purification_amount": entry.purification_amount}


class PortfolioSummaryResponse(BaseModel):
    connected: bool
    account_type: Literal["PAPER", "LIVE"] = "PAPER"
    total_value: Optional[float] = None
    cost_basis: Optional[float] = None
    cash_available: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    return_pct: Optional[float] = None
    total_invested: Optional[float] = None
    total_pnl: Optional[float] = None
    total_return_pct: Optional[float] = None
    purity: Optional[float] = None
    purification_due: Optional[float] = None
    compliance_pct: Optional[float] = None
    zakat_estimate: Optional[float] = None
    sector_count: Optional[int] = None
    max_impure_revenue_pct: Optional[float] = None
    halal_label: Optional[str] = None
    compliance_label: Optional[str] = None
    sector_label: Optional[str] = None
    purify_label: Optional[str] = None


@router.get("/summary", response_model=PortfolioSummaryResponse)
def get_portfolio_summary(request: Request, db: Session = Depends(get_db),
                          account_id: Optional[int] = None) -> PortfolioSummaryResponse:
    worker = _resolve_worker(request, account_id)

    worker_port = worker.port if worker else int(os.environ.get("IBKR_PORT", "7497"))
    account_type: Literal["PAPER", "LIVE"] = "LIVE" if worker_port in _LIVE_PORTS else "PAPER"
    connected = False
    total_cash = 0.0
    positions: list = []

    try:
        if worker and worker.ib.isConnected():
            connected = True
            # Settled cash, NOT AvailableFunds: the latter is NetLiquidation minus
            # margin requirement, so adding it to position value double-counts the
            # margin cushion and overstates NAV (measured +$70,033 on DUN514226,
            # 2026-08-08). It would also report borrowing capacity as if it were
            # the user's money, which a no-margin account must never do.
            total_cash = float(worker.get_total_cash())
            positions = worker.get_positions()
    except Exception:
        pass

    if not connected or not positions:
        return PortfolioSummaryResponse(connected=connected, account_type=account_type)

    symbols = [p["symbol"] for p in positions]
    total_market_value = sum(float(p.get("market_value", 0)) for p in positions)
    total_cost_basis = sum(float(p.get("avg_cost", 0)) * float(p.get("quantity", 0)) for p in positions)
    total_unrealized = sum(float(p.get("unrealized_pnl", 0)) for p in positions)
    total_value = total_market_value + total_cash
    return_pct = (total_unrealized / total_cost_basis * 100) if total_cost_basis > 0 else 0.0

    # True total return — money in (all BUY fills) vs money now (open market value
    # + SELL proceeds). Unlike return_pct, this captures realized losses from
    # closed/sold positions, so a losing account no longer shows green.
    trades_q = db.query(TradeHistory).filter(TradeHistory.state == TradeState.FILLED)
    if account_id is not None:
        trades_q = trades_q.filter(TradeHistory.account_id == account_id)
    total_buys = 0.0
    total_sells = 0.0
    for t in trades_q.all():
        amt = (t.fill_price or 0.0) * (t.quantity or 0)
        if t.side == "SELL":
            total_sells += amt
        else:
            total_buys += amt
    if total_buys > 0:
        total_pnl = total_market_value + total_sells - total_buys
        total_return_pct = total_pnl / total_buys * 100
    else:
        # No trade history (e.g. positions transferred in) — fall back to unrealized.
        total_buys = total_cost_basis
        total_pnl = total_unrealized
        total_return_pct = return_pct

    comp_q = db.query(PositionCompliance).filter(PositionCompliance.symbol.in_(symbols))
    if account_id is not None:
        comp_q = comp_q.filter(PositionCompliance.account_id == account_id)
    comp_rows = comp_q.order_by(PositionCompliance.timestamp.desc()).all()

    compliance_map: Dict[str, dict] = {}
    for row in comp_rows:
        if row.symbol not in compliance_map:
            metrics = row.metrics or {}
            compliance_map[row.symbol] = {
                "status": row.shariah_status,
                "impure_pct": float(metrics.get("impure_revenue_pct", 0) or 0),
                "sector": metrics.get("sector", "Unknown"),
            }

    compliant_count = sum(1 for s in symbols if compliance_map.get(s, {}).get("status") == "COMPLIANT")
    screened_count = sum(1 for s in symbols if s in compliance_map)
    compliance_pct = (compliant_count / screened_count * 100) if screened_count > 0 else None

    sectors = set()
    max_impure = 0.0
    total_impure_weighted = 0.0
    for p in positions:
        sym = p["symbol"]
        info = compliance_map.get(sym, {})
        sector = info.get("sector", "Unknown")
        if sector and sector != "Unknown":
            sectors.add(sector.split("/")[0].strip())
        impure = info.get("impure_pct", 0.0)
        mkt_val = float(p.get("market_value", 0))
        max_impure = max(max_impure, impure)
        total_impure_weighted += impure * mkt_val

    purity = 1.0 - (total_impure_weighted / total_market_value) if total_market_value > 0 else None
    purification_due = total_impure_weighted if total_impure_weighted > 0 else 0.0
    zakat_estimate = total_value * 0.025

    n_pos = len(positions)
    halal_label = (
        "all clear" if purity and purity >= 0.98 else
        f"purify {n_pos - compliant_count}" if screened_count > 0 else
        None
    )
    compliance_label = (
        f"{compliant_count}/{screened_count} pass" if screened_count > 0 else "no data"
    )
    sector_count = len(sectors) if sectors else None
    sector_label = (
        f"{len(sectors)} sectors" if len(sectors) > 1 else
        "1 sector" if len(sectors) == 1 else
        "no data"
    )
    purify_label = (
        f"max {max_impure*100:.1f}% impure" if max_impure > 0 else
        "all clean" if screened_count > 0 else
        "no data"
    )

    return PortfolioSummaryResponse(
        connected=connected,
        account_type=account_type,
        total_value=round(total_value, 2),
        cost_basis=round(total_cost_basis, 2),
        cash_available=round(total_cash, 2),
        unrealized_pnl=round(total_unrealized, 2),
        return_pct=round(return_pct, 2),
        total_invested=round(total_buys, 2),
        total_pnl=round(total_pnl, 2),
        total_return_pct=round(total_return_pct, 2),
        purity=round(purity, 4) if purity is not None else None,
        purification_due=round(purification_due, 2),
        compliance_pct=round(compliance_pct, 2) if compliance_pct is not None else None,
        zakat_estimate=round(zakat_estimate, 2),
        sector_count=sector_count,
        max_impure_revenue_pct=round(max_impure, 4) if max_impure > 0 else 0.0,
        halal_label=halal_label,
        compliance_label=compliance_label,
        sector_label=sector_label,
        purify_label=purify_label,
    )


@router.post("/rerate")
async def manual_rerate(request: Request):
    """
    Re-scores all held positions immediately (bypasses 4h loop cadence).
    Returns per-symbol scores. Positions below rerate_sell_threshold get a
    PendingSignal queued for approval — does NOT auto-execute.

    Requires the private AI module to be installed (provides get_multi_factor_score).
    Returns 501 in the public build.
    """
    from ibkr_core.core.strategy import get_active_strategy
    from ibkr_core.features.compliance.vix import get_current_vix, vix_to_ratio_buffer
    from ibkr_core.core.models import PendingSignal
    from ibkr_core.core.database import SessionLocal

    strategy = get_active_strategy()

    worker = getattr(request.app.state, "worker", None)
    settings = load_settings()
    threshold = int(settings.get("rerate_sell_threshold") or 35)

    positions = []
    if worker:
        try:
            positions = await asyncio.to_thread(worker.get_positions)
        except Exception:
            pass

    if not positions:
        return {"scored": [], "sell_queued": [], "threshold": threshold, "note": "No positions (IBKR disconnected?)"}

    vix = await asyncio.to_thread(get_current_vix)
    buf = vix_to_ratio_buffer(vix)

    scored, sell_queued = [], []
    for pos in positions:
        symbol = pos.get("symbol", "")
        qty = float(pos.get("quantity", 0))
        if not symbol or qty <= 0:
            continue
        try:
            res = await strategy.get_multi_factor_score(symbol, vix_buffer=buf)
            if res is None:
                scored.append({"symbol": symbol, "score": None, "error": "strategy does not support scoring"})
                continue
            score = res["total_score"]
            action = res.get("action", "HOLD")
            entry = {"symbol": symbol, "score": score, "action": action,
                     "f": res.get("f_score"), "t": res.get("t_score"), "s": res.get("s_score")}
            scored.append(entry)
            if score <= threshold:
                with SessionLocal() as db:
                    existing = db.query(PendingSignal).filter(
                        PendingSignal.symbol == symbol,
                        PendingSignal.action == "SELL",
                    ).first()
                    if not existing:
                        db.add(PendingSignal(
                            symbol=symbol, action="SELL", confidence=80,
                            sentiment_score=0.0,
                            reasoning=f"Manual rerate: score {score} ≤ threshold {threshold}.",
                        ))
                        db.commit()
                        sell_queued.append(symbol)
                    else:
                        sell_queued.append(f"{symbol}(already pending)")
        except Exception as e:
            scored.append({"symbol": symbol, "score": None, "error": str(e)})

    scored.sort(key=lambda x: x.get("score") or 999)
    return {"scored": scored, "sell_queued": sell_queued, "threshold": threshold, "vix": round(vix, 1)}
