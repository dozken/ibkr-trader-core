import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime

from backend.core.logging_config import setup_logging, install_asyncio_excepthook

setup_logging()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from backend.core.database import init_db
from backend.core.request_id import RequestIDMiddleware
from backend.features.alerts.telegram import send_telegram
from backend.core.monitoring import IBKR_CONNECTED
from backend.features.trading.reconciliation import reconcile_with_ibkr
from backend.core.websocket import ConnectionManager, TickerUpdate, WS_TICKERS
from backend.features.alerts.loops import daily_report_loop, purification_reminder_loop
from backend.features.alerts.telegram_bot import telegram_bot_loop
from backend.features.compliance.loops import compliance_audit_loop
from backend.features.compliance.router import router as compliance_router
from backend.features.portfolio.loops import portfolio_snapshot_loop
from backend.features.portfolio.router import router as portfolio_router
from backend.features.settings.router import router as settings_router
from backend.features.trading.loops import cash_sweep_loop, main_loop, halal_drip_loop, discovery_loop, position_rerating_loop
from backend.features.trading.trader import resume_pending_twap
from backend.features.trading.accounts_router import router as accounts_router
from backend.features.trading.router import router as trading_router
from backend.features.trading.worker import IBKRWorker
from backend.features.trading.account_manager import get_account_manager
from backend.features.zakat.router import router as zakat_router
from backend.features.zakat.loops import zakat_monitoring_loop
from backend.core.audit import verify_audit_chain
from backend.core.database import SessionLocal

# Optional AI/ML module — present only in the private fork. Public installs
# fall back to the bundled reference Strategy (SMA crossover).
try:
    from backend.features.ai.router import router as ai_router  # type: ignore
    from backend.features.ai.halal_universe import halal_universe_refresh_loop  # type: ignore
    from backend.features.ai.loops import ml_retraining_loop  # type: ignore
    from backend.features.ai.signal_outcome_checker import signal_outcome_loop  # type: ignore
    HAS_AI_MODULE = True
except ImportError:
    HAS_AI_MODULE = False
    ai_router = None
    halal_universe_refresh_loop = None
    ml_retraining_loop = None
    signal_outcome_loop = None

logger = logging.getLogger(__name__)

async def audit_integrity_loop(worker, health: dict) -> None:
    """Hourly verification of the cryptographic AuditLog chain. Ref: Polish & Guard #3."""
    health["audit_integrity_loop"] = {"status": "running", "last_run": None}
    
    while True:
        try:
            with SessionLocal() as db:
                is_valid = await asyncio.to_thread(verify_audit_chain, db)
                
            if not is_valid:
                logger.error("🛑 CRYPTOGRAPHIC TAMPER DETECTED! Entering SAFE MODE.")
                await send_telegram("🚨 <b>EMERGENCY: AUDIT LOG TAMPER DETECTED</b>\nThe compliance ledger hash chain is broken. Entering <b>SAFE MODE</b>. Cancelling all orders.")
                
                if worker.ib.isConnected():
                    worker.ib.reqGlobalCancel()
                    logger.info("SAFE MODE: Global order cancellation sent.")
                
                health["audit_integrity_loop"]["status"] = "CRITICAL_ERROR"
                # Keep loop alive but stop trading if possible (handled via status check in main_loop)
                while True:
                    try:
                        await asyncio.sleep(60)
                    except asyncio.CancelledError:
                        return

            health["audit_integrity_loop"]["last_run"] = datetime.now().isoformat()
            await asyncio.sleep(3600) # Verify every hour
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in audit_integrity_loop: {e}")
            health["audit_integrity_loop"]["status"] = "error"
            await asyncio.sleep(300)

manager = ConnectionManager()


async def price_push_loop(worker, health: dict) -> None:
    """Subscribe to IBKR ticks for all held positions; broadcast to WS clients."""
    health["price_push_loop"] = {"status": "running", "last_run": None}
    subscribed: set = set()

    while True:
        try:
            if worker.ib.isConnected():
                current = {p["symbol"] for p in await asyncio.to_thread(worker.get_positions)}

                for sym in current - subscribed:
                    def make_cb(s: str):
                        def cb(update):
                            asyncio.create_task(manager.broadcast(TickerUpdate(data=update)))
                        return cb
                    await worker.subscribe_ticker(sym, make_cb(sym))
                    subscribed.add(sym)

                for sym in subscribed - current:
                    worker.unsubscribe_ticker(sym)
                    subscribed.discard(sym)

                health["price_push_loop"]["last_run"] = datetime.now().isoformat()

            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in price_push_loop: {e}")
            await asyncio.sleep(30)


def verify_env_sync():
    """
    Verifies that IBKR_API_KEY in backend/.env matches VITE_IBKR_API_KEY in frontend/.env.
    Ref: Improvement #39.
    """
    backend_env_path = os.path.join(os.path.dirname(__file__), ".env")
    frontend_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", ".env")
    
    backend_key = os.getenv("IBKR_API_KEY", "")
    
    if not backend_key:
        return # Key not set in backend, nothing to sync
        
    if not os.path.exists(frontend_env_path):
        logger.warning("⚠️ frontend/.env missing. Approval requests will fail if IBKR_API_KEY is required.")
        return

    try:
        with open(frontend_env_path, "r") as f:
            content = f.read()
            match = re.search(r"VITE_IBKR_API_KEY\s*=\s*(.*)", content)
            if match:
                frontend_key = match.group(1).strip().strip("'").strip('"')
                if frontend_key != backend_key:
                    logger.error("🛑 ENVIRONMENT MISMATCH: backend/IBKR_API_KEY != frontend/VITE_IBKR_API_KEY")
                    logger.error("Approval requests will fail with 401. Sync your .env files!")
            else:
                logger.warning("⚠️ VITE_IBKR_API_KEY not found in frontend/.env")
    except Exception as e:
        logger.warning(f"Failed to read frontend/.env for sync check: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = []
    worker = None
    account_manager = None
    try:
        verify_env_sync()
        asyncio.set_event_loop(asyncio.get_running_loop())
        install_asyncio_excepthook()
        init_db()

        # Load accounts from DB; auto-seed from env vars if none exist yet
        from backend.core.database import SessionLocal
        from backend.core.models import Account as AccountModel
        _seed_db = SessionLocal()
        try:
            if not _seed_db.query(AccountModel).first():
                _host = os.getenv("IBKR_HOST", "127.0.0.1")
                _port = int(os.getenv("IBKR_PORT", "7497"))
                _is_paper = _port in (7497, 4002)
                _seed_acc = AccountModel(
                    label="Paper" if _is_paper else "Live",
                    host=_host,
                    port=_port,
                    client_id=1,
                    ibkr_account_id=os.getenv("IBKR_ACCOUNT_ID"),
                    is_paper=_is_paper,
                    is_active=True,
                )
                _seed_db.add(_seed_acc)
                _seed_db.commit()
                logger.info("Auto-seeded default account (host=%s port=%d)", _host, _port)
        finally:
            _seed_db.close()

        account_manager = get_account_manager()
        primary_account_id: int | None = None
        if account_manager.list_account_ids():
            # Multi-account: primary worker = first account
            first_id = account_manager.list_account_ids()[0]
            primary_account_id = first_id
            _db = SessionLocal()
            try:
                _acc = _db.query(AccountModel).filter(AccountModel.id == first_id).first()
                worker = account_manager.get_worker(_acc.id, _acc.host, _acc.port, _acc.client_id)
            finally:
                _db.close()
        else:
            worker = IBKRWorker()
            logger.info("No accounts in DB — using env-var defaults for primary worker")

        app.state.worker = worker
        app.state.account_manager = account_manager

        # main_loop owns all IBKR connections with retry logic.
        # Reconciliation and TWAP resume happen inside worker._reconnect() on connect.
        IBKR_CONNECTED.set(0)

        health = {
            "main_loop":               {"last_run": None, "status": "starting"},
            "compliance_audit_loop":   {"last_run": None, "status": "starting"},
            "cash_sweep_loop":         {"last_run": None, "status": "starting"},
            "halal_drip_loop":         {"last_run": None, "status": "starting"},
            "discovery_loop":          {"last_run": None, "status": "starting"},
            "position_rerating_loop":  {"last_run": None, "status": "starting"},
            "portfolio_snapshot_loop": {"last_run": None, "status": "starting"},
            "daily_report_loop":       {"last_run": None, "status": "starting"},
            "telegram_bot_loop":       {"last_run": None, "status": "starting"},
            "purification_reminder_loop": {"last_run": None, "status": "starting"},
            "zakat_monitoring_loop":   {"last_run": None, "status": "starting"},
            "audit_integrity_loop":    {"last_run": None, "status": "starting"},
            "price_push_loop":         {"last_run": None, "status": "starting"},
        }
        if HAS_AI_MODULE:
            health["ml_retraining_loop"]  = {"last_run": None, "status": "starting"}
            health["signal_outcome_loop"] = {"last_run": None, "status": "starting"}
            health["halal_universe_loop"] = {"last_run": None, "status": "starting"}
        app.state.loop_health = health

        async def _on_fill(symbol: str, side: str, qty: float, avg_price: float) -> None:
            pass

        worker._fill_callback = _on_fill
        tasks = [
            asyncio.create_task(main_loop(worker, manager, health, account_id=primary_account_id)),
            asyncio.create_task(compliance_audit_loop(worker, manager, health)),
            asyncio.create_task(cash_sweep_loop(worker, manager, health, account_id=primary_account_id)),
            asyncio.create_task(halal_drip_loop(worker, manager, health)),
            asyncio.create_task(discovery_loop(worker, manager, health, account_id=primary_account_id)),
            asyncio.create_task(position_rerating_loop(worker, manager, health, account_id=primary_account_id)),
            asyncio.create_task(portfolio_snapshot_loop(worker, health)),
            asyncio.create_task(daily_report_loop(worker, health)),
            asyncio.create_task(telegram_bot_loop(worker, health)),
            asyncio.create_task(purification_reminder_loop(health)),
            asyncio.create_task(zakat_monitoring_loop(worker, health)),
            asyncio.create_task(audit_integrity_loop(worker, health)),
            asyncio.create_task(price_push_loop(worker, health)),
        ]
        if HAS_AI_MODULE:
            tasks.extend([
                asyncio.create_task(ml_retraining_loop(health)),
                asyncio.create_task(signal_outcome_loop(health)),
                asyncio.create_task(halal_universe_refresh_loop(health)),
            ])
    except BaseException as _startup_exc:
        import traceback as _tb
        print(f"LIFESPAN STARTUP CRASH: {type(_startup_exc).__name__}: {_startup_exc}", flush=True)
        _tb.print_exc()
        raise
    yield
    for t in tasks:
        t.cancel()
    if account_manager is not None:
        account_manager.disconnect_all()
        if not account_manager.list_account_ids() and worker is not None:
            worker.disconnect()


app = FastAPI(title="IBKR Shariah Trader", lifespan=lifespan)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(compliance_router)
app.include_router(accounts_router)
app.include_router(trading_router)
app.include_router(zakat_router)
app.include_router(portfolio_router)
if HAS_AI_MODULE and ai_router is not None:
    app.include_router(ai_router)
app.include_router(settings_router)


@app.get("/")
def read_root():
    return {"status": "Ironclad System Active"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/system/health")
def system_health():
    return app.state.loop_health


@app.get("/api/system/markets")
def system_markets():
    """All configured exchanges with open/closed status + UTC session times + halal symbol count."""
    from backend.core.market_hours import (
        EXCHANGE_CONFIG, market_status, infer_exchange_from_symbol,
        get_exchange_config, SUNDAY_THURSDAY_EXCHANGES,
    )
    try:
        from backend.features.ai.halal_universe import SEED_UNIVERSE, REGIONAL_HALAL  # type: ignore
    except ImportError:
        # Public install: no halal universe shipped — return empty regions.
        # Plug in your own by adding `backend/features/ai/halal_universe.py`
        # exporting `SEED_UNIVERSE` (list[str]) and `REGIONAL_HALAL` (dict[str, list[str]]).
        SEED_UNIVERSE: list = []
        REGIONAL_HALAL: dict = {}
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Continent grouping for visual organization
    CONTINENT = {
        "US": "Americas", "CA": "Americas", "MX": "Americas", "BR": "Americas",
        "UK": "Europe", "DE": "Europe", "FR": "Europe", "NL": "Europe",
        "CH": "Europe", "SE": "Europe", "NO": "Europe", "IT": "Europe", "ES": "Europe",
        "SA": "MENA", "AE": "MENA", "EG": "MENA", "TR": "MENA", "PK": "MENA",
        "JP": "Asia", "CN": "Asia", "HK": "Asia", "KR": "Asia", "TW": "Asia",
        "SG": "Asia", "MY": "Asia", "ID": "Asia", "TH": "Asia", "PH": "Asia",
        "VN": "Asia", "IN": "Asia",
        "AU": "Oceania", "NZ": "Oceania",
        "ZA": "Africa",
    }

    # Compute today's UTC session windows from local time
    utc_now = datetime.utcnow()
    today_utc = utc_now.date()

    def _utc_sessions_for(ex_code: str) -> list[dict]:
        tz_name, sessions, _, _ = get_exchange_config(ex_code)
        tz = ZoneInfo(tz_name)
        out = []
        for open_t, close_t in sessions:
            # Today in market's local timezone
            now_local = datetime.now(tz)
            local_open = now_local.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)
            local_close = now_local.replace(hour=close_t.hour, minute=close_t.minute, second=0, microsecond=0)
            utc_open = local_open.astimezone(ZoneInfo("UTC"))
            utc_close = local_close.astimezone(ZoneInfo("UTC"))
            out.append({
                "open_utc_h": utc_open.hour + utc_open.minute / 60,
                "close_utc_h": utc_close.hour + utc_close.minute / 60,
                "local_open": open_t.strftime("%H:%M"),
                "local_close": close_t.strftime("%H:%M"),
            })
        return out

    # Region grouping
    region_meta: list = []
    for region, symbols in REGIONAL_HALAL.items():
        if not symbols:
            continue
        ex_code = infer_exchange_from_symbol(symbols[0])
        status = market_status(ex_code)
        region_meta.append({
            "region": region,
            "continent": CONTINENT.get(region, "Other"),
            "exchange": ex_code,
            "ibkr_exchange": status["ibkr_exchange"],
            "currency": status["currency"],
            "timezone": status["timezone"],
            "local_time": status["local_time"],
            "is_open": status["is_open"],
            "sessions": status["sessions"],
            "utc_sessions": _utc_sessions_for(ex_code),
            "symbol_count": len(symbols),
        })

    region_meta.sort(key=lambda r: (not r["is_open"], r["region"]))

    return {
        "regions": region_meta,
        "open_count": sum(1 for r in region_meta if r["is_open"]),
        "total_count": len(region_meta),
        "total_symbols": len(SEED_UNIVERSE),
        "utc_now_h": utc_now.hour + utc_now.minute / 60,
    }


@app.get("/api/system/readiness")
def system_readiness():
    """
    Automated paper→live readiness gate check.
    Returns structured pass/fail for each gate plus a top-level ready flag.
    """
    from backend.core.database import SessionLocal
    from backend.core.models import TradeHistory, SignalLog
    from datetime import datetime, timezone, timedelta
    import os

    health = getattr(app.state, "loop_health", {})
    worker = getattr(app.state, "worker", None)

    # ── Loop health ────────────────────────────────────────────────────────────
    critical_loops = ["main_loop", "compliance_audit_loop", "portfolio_snapshot_loop"]
    loops_ok = all(
        health.get(k, {}).get("status") not in ("starting", "error", "CRITICAL_ERROR")
        for k in critical_loops
    )

    # ── IBKR connectivity ──────────────────────────────────────────────────────
    ibkr_connected = worker is not None and worker.ib.isConnected()
    port = int(os.getenv("IBKR_PORT", "7497"))
    _LIVE_PORTS = {7496, 4001}
    port_type = "LIVE" if port in _LIVE_PORTS else "PAPER"

    # ── Drawdown CB ────────────────────────────────────────────────────────────
    drawdown_triggered = health.get("drawdown_triggered", False)

    # ── Trade error rate (rolling 7-day window — fixed bugs shouldn't poison forever)
    error_rate_pct: float | None = None
    trade_count = 0
    paper_trading_days = 0
    recent_errors: list = []
    try:
        with SessionLocal() as db:
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            cutoff_7d = now_utc - timedelta(days=7)
            trade_count = db.query(TradeHistory).filter(TradeHistory.created_at >= cutoff_7d).count()
            error_rows = db.query(TradeHistory).filter(
                TradeHistory.created_at >= cutoff_7d,
                TradeHistory.state == "IBKR_ERROR",
            ).order_by(TradeHistory.created_at.desc()).all()
            error_count = len(error_rows)
            if trade_count > 0:
                error_rate_pct = round(error_count / trade_count * 100, 1)
            # Last 10 errors for diagnostic display
            from backend.core.market_hours import infer_exchange_from_symbol
            for r in error_rows[:10]:
                recent_errors.append({
                    "symbol": r.symbol,
                    "side": r.side,
                    "exchange": infer_exchange_from_symbol(r.symbol),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })
            earliest = db.query(TradeHistory).order_by(TradeHistory.created_at.asc()).first()
            if earliest and earliest.created_at:
                now = datetime.now(timezone.utc)
                earliest_dt = earliest.created_at
                if earliest_dt.tzinfo is None:
                    earliest_dt = earliest_dt.replace(tzinfo=timezone.utc)
                paper_trading_days = max(0, (now - earliest_dt).days)
    except Exception:
        pass

    # Gate trips only when BOTH rate > 10% AND ≥5 absolute errors —
    # avoids false alarms during low-volume periods where 1-2 legit broker
    # rejections inflate the percentage.
    _MIN_ERRORS_FOR_GATE = 5
    error_count_7d = round((error_rate_pct or 0) * trade_count / 100) if error_rate_pct else 0
    error_rate_ok = (
        error_rate_pct is None
        or error_rate_pct <= 10.0
        or error_count_7d < _MIN_ERRORS_FOR_GATE
    )

    # ── Audit integrity ────────────────────────────────────────────────────────
    audit_ok = health.get("audit_integrity_loop", {}).get("status") != "CRITICAL_ERROR"

    # ── Signal quality performance gates ──────────────────────────────────────
    _MIN_RESOLVED = 10       # need at least 10 resolved BUY outcomes
    _MIN_WIN_RATE = 40.0     # % win rate threshold
    _MIN_AVG_RETURN = -5.0   # % avg 7d return floor
    _MIN_PAPER_DAYS = 7      # days of live paper trading

    n_resolved = 0
    win_rate_pct: float | None = None
    avg_7d_return: float | None = None
    try:
        with SessionLocal() as db:
            resolved_rows = db.query(SignalLog).filter(
                SignalLog.action == "BUY",
                SignalLog.outcome_7d_pct.isnot(None),
            ).all()
        n_resolved = len(resolved_rows)
        if n_resolved > 0:
            wins = sum(1 for r in resolved_rows if (r.outcome_7d_pct or 0) > 0)
            win_rate_pct = round(wins / n_resolved * 100, 1)
            avg_7d_return = round(sum(r.outcome_7d_pct or 0 for r in resolved_rows) / n_resolved, 2)
    except Exception:
        pass

    enough_signals = n_resolved >= _MIN_RESOLVED
    win_rate_ok = (not enough_signals) or (win_rate_pct is not None and win_rate_pct >= _MIN_WIN_RATE)
    avg_return_ok = avg_7d_return is None or avg_7d_return >= _MIN_AVG_RETURN
    paper_days_ok = paper_trading_days >= _MIN_PAPER_DAYS

    gates = {
        "ibkr_connected": ibkr_connected,
        "port_type": port_type,
        "loops_healthy": loops_ok,
        "drawdown_not_triggered": not drawdown_triggered,
        "trade_error_rate_ok": error_rate_ok,
        "audit_integrity_ok": audit_ok,
        "enough_signal_outcomes": enough_signals,
        "win_rate_ok": win_rate_ok,
        "avg_return_ok": avg_return_ok,
        "paper_days_ok": paper_days_ok,
    }

    blockers = []
    if not ibkr_connected:
        blockers.append("IBKR not connected")
    if not loops_ok:
        failed = [k for k in critical_loops if health.get(k, {}).get("status") in ("starting", "error", "CRITICAL_ERROR")]
        blockers.append(f"Loops unhealthy: {', '.join(failed)}")
    if drawdown_triggered:
        blockers.append("Drawdown circuit breaker is active — portfolio down >max_drawdown_pct")
    if not error_rate_ok:
        blockers.append(f"Trade error rate {error_rate_pct}% > 10% threshold ({error_count_7d} errors in {trade_count} trades)")
    if not audit_ok:
        blockers.append("Audit log integrity check failed — SAFE MODE")
    if not enough_signals:
        blockers.append(f"Need {_MIN_RESOLVED} resolved BUY signal outcomes (have {n_resolved}) — wait for 7-day outcomes to fill in")
    elif not win_rate_ok:
        blockers.append(f"Win rate {win_rate_pct}% below {_MIN_WIN_RATE}% threshold — strategy needs improvement")
    if not avg_return_ok:
        blockers.append(f"Avg 7d signal return {avg_7d_return}% below {_MIN_AVG_RETURN}% floor — signals losing too much")
    if not paper_days_ok:
        blockers.append(f"Only {paper_trading_days} days of paper trading (need {_MIN_PAPER_DAYS})")

    ready = len(blockers) == 0

    return {
        "ready": ready,
        "port_type": port_type,
        "trade_count": trade_count,
        "error_rate_pct": error_rate_pct,
        "gates": gates,
        "blockers": blockers,
        "performance": {
            "n_resolved_signals": n_resolved,
            "min_resolved_required": _MIN_RESOLVED,
            "win_rate_pct": win_rate_pct,
            "min_win_rate_pct": _MIN_WIN_RATE,
            "avg_7d_return_pct": avg_7d_return,
            "min_avg_return_pct": _MIN_AVG_RETURN,
            "paper_trading_days": paper_trading_days,
            "min_paper_days": _MIN_PAPER_DAYS,
        },
        "recent_errors": recent_errors,
        "note": "Switch port to LIVE (4001) and update DATABASE_URL before going live." if port_type == "PAPER" else None,
    }


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.websocket(WS_TICKERS)
async def websocket_tickers(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("WebSocket received invalid JSON — ignoring")
                continue
            if message.get("action") == "subscribe":
                symbol = message.get("symbol")
                if not symbol or not isinstance(symbol, str) or len(symbol) > 12:
                    logger.warning(f"WebSocket subscribe rejected: invalid symbol {symbol!r}")
                    continue
                symbol = symbol.upper()
                logger.info(f"Client subscribing to {symbol}")
                worker = websocket.app.state.worker

                def ticker_callback(update):
                    asyncio.create_task(websocket.send_json(TickerUpdate(data=update).model_dump()))

                await worker.subscribe_ticker(symbol, ticker_callback)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected from WebSocket")
