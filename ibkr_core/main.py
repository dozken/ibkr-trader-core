import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Literal, Optional

from ibkr_core.core.logging_config import setup_logging, install_asyncio_excepthook

setup_logging()

from fastapi import APIRouter, FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel

from ibkr_core.core.database import init_db
from ibkr_core.core.request_id import RequestIDMiddleware
from ibkr_core.features.alerts.telegram import send_telegram
from ibkr_core.core.monitoring import IBKR_CONNECTED
from ibkr_core.core.websocket import ConnectionManager, TickerUpdate, WS_TICKERS
from ibkr_core.features.alerts.loops import daily_report_loop, purification_reminder_loop
from ibkr_core.features.alerts.telegram_bot import telegram_bot_loop
from ibkr_core.features.compliance.loops import compliance_audit_loop
from ibkr_core.features.compliance.router import router as compliance_router
from ibkr_core.features.portfolio.loops import portfolio_snapshot_loop
from ibkr_core.features.portfolio.router import router as portfolio_router
from ibkr_core.features.settings.router import router as settings_router
from ibkr_core.features.trading.loops import cash_sweep_loop, main_loop, halal_drip_loop, discovery_loop, position_rerating_loop
from ibkr_core.features.trading.accounts_router import router as accounts_router
from ibkr_core.features.trading.gateway_router import router as gateway_router
# Canonical live-gateway API ports (7496 TWS / 4001 IBGW raw / 4003 gnzsnz live;
# paper = 7497 / 4002 / 4004). Single source of truth in order_policy.
from ibkr_core.features.trading.order_policy import LIVE_PORTS as _LIVE_PORTS
from ibkr_core.features.trading.order_policy import PAPER_PORTS as _PAPER_PORTS
from ibkr_core.features.trading.order_policy import cold_boot_arming
from ibkr_core.features.trading.router import router as trading_router
from ibkr_core.features.trading.worker import IBKRWorker
from ibkr_core.features.trading.account_manager import get_account_manager
from ibkr_core.features.zakat.router import router as zakat_router
from ibkr_core.features.zakat.loops import zakat_monitoring_loop
from ibkr_core.core.audit import verify_audit_chain
from ibkr_core.core.database import SessionLocal
from ibkr_core.core.clock import utc_now

# Optional AI/ML module — present only in the private fork. Public installs
# fall back to the bundled reference Strategy (SMA crossover).
try:
    from ibkr_core.features.ai.router import router as ai_router  # type: ignore
    from ibkr_core.features.ai.halal_universe import halal_universe_refresh_loop  # type: ignore
    from ibkr_core.features.ai.loops import ml_retraining_loop  # type: ignore
    from ibkr_core.features.ai.signal_outcome_checker import signal_outcome_loop  # type: ignore
    HAS_AI_MODULE = True
except ImportError:
    HAS_AI_MODULE = False
    ai_router = None
    halal_universe_refresh_loop = None
    ml_retraining_loop = None
    signal_outcome_loop = None

logger = logging.getLogger(__name__)

# Populated by create_app() so extension dists (e.g. the AI fork) can inject
# their own background loops + routers without re-declaring the application.
# Each extra loop is an async callable invoked as loop_fn(health).
_EXTRA_LOOPS: list = []
_EXTRA_ROUTERS: list = []

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

            health["audit_integrity_loop"]["last_run"] = utc_now().isoformat()
            await asyncio.sleep(3600) # Verify every hour
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in audit_integrity_loop: {e}")
            health["audit_integrity_loop"]["status"] = "error"
            await asyncio.sleep(300)

manager = ConnectionManager()


async def price_push_loop(worker, health: dict) -> None:
    """Subscribe to IBKR ticks for positions + watchlist; broadcast to WS clients."""
    health["price_push_loop"] = {"status": "running", "last_run": None}
    subscribed: set = set()

    while True:
        try:
            if worker.ib.isConnected():
                current = {p["symbol"] for p in await asyncio.to_thread(worker.get_positions)}
                try:
                    from ibkr_core.features.settings.service import load_settings
                    watchlist = set(load_settings().get("watchlist", []))
                except Exception:
                    watchlist = set()
                target = current | watchlist

                for sym in target - subscribed:
                    def make_cb(s: str):
                        def cb(update):
                            asyncio.create_task(manager.broadcast(TickerUpdate(data=update)))
                        return cb
                    await worker.subscribe_ticker(sym, make_cb(sym))
                    subscribed.add(sym)

                for sym in subscribed - target:
                    worker.unsubscribe_ticker(sym)
                    subscribed.discard(sym)

                health["price_push_loop"]["last_run"] = utc_now().isoformat()

            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in price_push_loop: {e}")
            await asyncio.sleep(30)


def verify_env_sync():
    """
    Verifies that IBKR_API_KEY in ibkr_core/.env matches VITE_IBKR_API_KEY in frontend/.env.
    Ref: Improvement #39.
    """
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


def _assert_paper_test_safety() -> None:
    """Refuse to boot when a paper test could run alongside real money.

    Defense-in-depth companion to the compose ``live`` profile gating: even if an
    operator hand-rolls ``docker compose --profile live up`` (or flips the live
    gateway back on) during a paper test, this aborts startup. Raises
    ``RuntimeError`` — surfaced by the lifespan startup-crash handler — when EITHER:

      (a) COEXISTENCE: an active LIVE account and an active PAPER account both
          exist in the DB (the genuinely dangerous state); OR
      (b) FLAG: env ``PAPER_TEST`` is truthy AND any active LIVE account exists.

    Returns silently otherwise, so normal single-mode operation is untouched.
    """
    def _is_live(acc) -> bool:
        # Real money if flagged live OR pointed at a live gateway API port
        # (a paper flag on a live port is still treated as live — fail-safe).
        return (not acc.is_paper) or (acc.port in _LIVE_PORTS)

    from ibkr_core.core.models import Account
    db = SessionLocal()
    try:
        active = db.query(Account).filter(Account.is_active.is_(True)).all()
    finally:
        db.close()

    live = [a for a in active if _is_live(a)]
    paper = [a for a in active if not _is_live(a)]

    def _fmt(accts) -> str:
        return str([(a.id, a.label, a.port) for a in accts])

    paper_test = os.getenv("PAPER_TEST", "").strip().lower() in ("1", "true", "yes")

    if live and paper:
        raise RuntimeError(
            "Refusing to boot: active LIVE and PAPER accounts coexist — a paper "
            f"test must not run alongside real money. LIVE={_fmt(live)} "
            f"PAPER={_fmt(paper)}. Deactivate one side (is_active=false) or stop "
            "the live gateway."
        )
    if paper_test and live:
        raise RuntimeError(
            "Refusing to boot: PAPER_TEST is set but active LIVE account(s) "
            f"present: {_fmt(live)}. Deactivate them (is_active=false) or stop "
            "the live gateway before a paper test."
        )


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
        from ibkr_core.core.database import SessionLocal
        from ibkr_core.core.models import Account as AccountModel
        _seed_db = SessionLocal()
        try:
            if not _seed_db.query(AccountModel).first():
                _host = os.getenv("IBKR_HOST", "127.0.0.1")
                _port = int(os.getenv("IBKR_PORT", "7497"))
                # is_paper mirrors how the rest of the code classifies a port
                # (line 192 / 578 / 869), but ARMING requires proof: an
                # unrecognised port is real money until shown otherwise.
                _is_paper = _port not in _LIVE_PORTS
                _active, _read_only = cold_boot_arming(_port)
                _provably_paper = _active
                _seed_acc = AccountModel(
                    label="Paper" if _is_paper else "Live",
                    host=_host,
                    port=_port,
                    client_id=1,
                    ibkr_account_id=os.getenv("IBKR_ACCOUNT_ID"),
                    is_paper=_is_paper,
                    # Fail closed. A cold boot on an empty DB must never produce
                    # an account that can place real orders: compose defaults
                    # IBKR_PORT to 4003 (the REAL-MONEY gateway), so the old
                    # unconditional is_active=True — with read_only defaulting
                    # to False — armed live trading with no human in the loop.
                    # Paper seeds ready to run; anything else is inert until
                    # someone deliberately activates it.
                    is_active=_active,
                    read_only=_read_only,
                )
                _seed_db.add(_seed_acc)
                _seed_db.commit()
                if _provably_paper:
                    logger.info("Auto-seeded default PAPER account (host=%s port=%d), active",
                                _host, _port)
                else:
                    logger.warning(
                        "Auto-seeded account on host=%s port=%d INACTIVE and READ-ONLY: "
                        "port %d is not a known paper port %s, so it is treated as real "
                        "money. Trading stays disarmed until you activate it deliberately.",
                        _host, _port, _port, sorted(_PAPER_PORTS),
                    )
        finally:
            _seed_db.close()

        account_manager = get_account_manager()
        # Defense-in-depth: refuse to boot if a paper test could run alongside
        # real money. Raised here — before any worker connects — so a
        # misconfiguration aborts startup rather than trading live.
        _assert_paper_test_safety()
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
        for _fn in _EXTRA_LOOPS:
            health.setdefault(getattr(_fn, "__name__", "extra_loop"), {"last_run": None, "status": "starting"})
        app.state.loop_health = health

        async def _on_fill(symbol: str, side: str, qty: float, avg_price: float) -> None:
            pass

        async def _connect_secondary_workers():
            """Connect workers for non-primary accounts (multi-account). Shares
            a connection when accounts point at the same gateway."""
            connected_ibs = set()
            if worker:
                connected_ibs.add(id(worker.ib))
            for aid in account_manager.list_account_ids():
                if aid == primary_account_id:
                    continue
                w = account_manager.get_worker_by_id(aid)
                if not w:
                    continue
                if id(w.ib) in connected_ibs:
                    logger.info(f"Secondary worker for account {aid} shares existing connection")
                    continue
                while True:
                    try:
                        if await w.connect():
                            logger.info(f"Secondary worker connected: account {aid}")
                            connected_ibs.add(id(w.ib))
                            break
                    except Exception:
                        # Unlogged, this retries every 30s forever in total silence.
                        logger.warning("Secondary worker for account %s failed to "
                                       "connect — retrying in 30s", aid, exc_info=True)
                    await asyncio.sleep(30)

        worker._fill_callback = _on_fill
        tasks = [
            asyncio.create_task(main_loop(worker, manager, health, account_id=primary_account_id)),
            asyncio.create_task(compliance_audit_loop(worker, manager, health, account_manager=account_manager)),
            asyncio.create_task(cash_sweep_loop(worker, manager, health, account_id=primary_account_id)),
            asyncio.create_task(halal_drip_loop(worker, manager, health, account_id=primary_account_id)),
            asyncio.create_task(discovery_loop(worker, manager, health, account_id=primary_account_id)),
            asyncio.create_task(position_rerating_loop(worker, manager, health, account_id=primary_account_id)),
            asyncio.create_task(portfolio_snapshot_loop(worker, health, account_id=primary_account_id)),
            asyncio.create_task(daily_report_loop(worker, health, account_manager=account_manager)),
            asyncio.create_task(telegram_bot_loop(worker, health, account_manager=account_manager)),
            asyncio.create_task(purification_reminder_loop(health)),
            asyncio.create_task(zakat_monitoring_loop(worker, health)),
            asyncio.create_task(audit_integrity_loop(worker, health)),
            asyncio.create_task(price_push_loop(worker, health)),
            asyncio.create_task(_connect_secondary_workers()),
        ]
        # Multi-account: spawn per-account trading loops for each secondary
        # account (connection managed by _connect_secondary_workers above).
        for aid in account_manager.list_account_ids():
            if aid == primary_account_id:
                continue
            sec_worker = account_manager.get_worker_by_id(aid)
            if sec_worker:
                health[f"main_loop_{aid}"] = {"last_run": None, "status": "starting"}
                tasks.append(asyncio.create_task(
                    main_loop(sec_worker, manager, health, account_id=aid, manage_connection=False)
                ))
                tasks.append(asyncio.create_task(
                    cash_sweep_loop(sec_worker, manager, health, account_id=aid)
                ))
                tasks.append(asyncio.create_task(
                    position_rerating_loop(sec_worker, manager, health, account_id=aid)
                ))
                # Per-account portfolio snapshots — without this, secondary accounts
                # show "No history yet" forever (only the primary was snapshotted).
                # Secondaries don't drive the global drawdown breaker.
                tasks.append(asyncio.create_task(
                    portfolio_snapshot_loop(sec_worker, health, account_id=aid, manage_drawdown=False)
                ))
        if HAS_AI_MODULE:
            tasks.extend([
                asyncio.create_task(ml_retraining_loop(health)),
                asyncio.create_task(signal_outcome_loop(health)),
                asyncio.create_task(halal_universe_refresh_loop(health)),
            ])
        for _fn in _EXTRA_LOOPS:
            tasks.append(asyncio.create_task(_fn(health)))
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


# ---------------------------------------------------------------------------
# System + WebSocket routes — mounted by create_app()
# ---------------------------------------------------------------------------
system_router = APIRouter()



def _loop_ok(entry: dict) -> bool:
    """A background-loop health entry is OK unless it is still starting, in
    CRITICAL_ERROR, or carries an ``error: <ExcType>`` status. set_loop_error
    writes the prefixed form, so match the prefix — an exact "error" check
    silently passed every errored loop. Shared by /api/system/readiness and
    /api/system/trading.
    """
    status = (entry or {}).get("status") or ""
    return not (status in ("starting", "CRITICAL_ERROR") or status.startswith("error"))


@system_router.get("/")
def read_root():
    return {"status": "Ironclad System Active"}


@system_router.get("/health")
def health():
    return {"status": "ok"}


@system_router.get("/api/system/health")
def system_health(request: Request):
    return request.app.state.loop_health


@system_router.get("/api/system/markets")
def system_markets():
    """All configured exchanges with open/closed status + UTC session times + halal symbol count."""
    from ibkr_core.core.market_hours import (
        market_status, infer_exchange_from_symbol,
        get_exchange_config,
    )
    # Universe source resolution order:
    #   1. HALAL_UNIVERSE_MODULE env var (extension dists point here, e.g. the
    #      AI fork sets it to `backend.features.ai.halal_universe`)
    #   2. ibkr_core.features.ai.halal_universe (namespace-package extension)
    #   3. bundled reference seed list (public standalone)
    SEED_UNIVERSE = REGIONAL_HALAL = None
    _um = os.getenv("HALAL_UNIVERSE_MODULE")
    if _um:
        try:
            import importlib
            _mod = importlib.import_module(_um)
            SEED_UNIVERSE, REGIONAL_HALAL = _mod.SEED_UNIVERSE, _mod.REGIONAL_HALAL
        except Exception as e:
            logger.warning("HALAL_UNIVERSE_MODULE=%s failed to load: %s", _um, e)
    if SEED_UNIVERSE is None:
        try:
            from ibkr_core.features.ai.halal_universe import SEED_UNIVERSE, REGIONAL_HALAL  # type: ignore
        except ImportError:
            from ibkr_core.strategies.halal_universe_seed import SEED_UNIVERSE, REGIONAL_HALAL
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

    # Compute today's UTC session windows from local time. Named now_utc, not
    # utc_now: the latter is the imported clock function and shadowing it here
    # would silently break any later call in this scope.
    now_utc = utc_now()

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
        "utc_now_h": now_utc.hour + now_utc.minute / 60,
    }


@system_router.get("/api/system/readiness")
def system_readiness(request: Request):
    """
    Automated paper→live readiness gate check.
    Returns structured pass/fail for each gate plus a top-level ready flag.
    """
    from ibkr_core.core.database import SessionLocal
    from ibkr_core.core.models import TradeHistory, SignalLog
    from datetime import timezone, timedelta
    import os

    health = getattr(request.app.state, "loop_health", {})
    worker = getattr(request.app.state, "worker", None)

    # ── Loop health ────────────────────────────────────────────────────────────
    # The primary trading loop runs under "main_loop" in single-account mode but
    # under "main_loop_<account_id>" in multi-account mode (the plain "main_loop"
    # entry is then a vestigial seed that stays "starting" forever). Require at
    # least one trading loop to be live rather than the fixed "main_loop" key.
    main_loop_keys = [k for k in health if k == "main_loop" or k.startswith("main_loop_")]
    trading_ok = any(_loop_ok(health[k]) for k in main_loop_keys)
    other_critical = ["compliance_audit_loop", "portfolio_snapshot_loop"]
    loops_ok = trading_ok and all(_loop_ok(health.get(k, {})) for k in other_critical)

    # ── IBKR connectivity ──────────────────────────────────────────────────────
    ibkr_connected = worker is not None and worker.ib.isConnected()
    # Prefer the connected worker's actual port — the IBKR_PORT env is a static
    # default and can disagree with the per-account gateway the bot really uses
    # (e.g. env=4003 live while the active account trades paper on 4004), which
    # would mislabel a paper run as LIVE.
    port = int(getattr(worker, "port", None) or os.getenv("IBKR_PORT", "7497"))
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
            from ibkr_core.core.market_hours import infer_exchange_from_symbol
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
        logger.warning("Readiness: trade-history stats unavailable — the gate will "
                       "judge on partial data", exc_info=True)

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
        import math
        with SessionLocal() as db:
            resolved_rows = db.query(SignalLog).filter(
                SignalLog.action == "BUY",
                SignalLog.outcome_7d_pct.isnot(None),
            ).all()
        # Drop NaN/Inf outcomes — some backfilled rows stored NaN, which both
        # corrupts the averages and makes the JSON response non-serializable
        # (ValueError: Out of range float values are not JSON compliant).
        outcomes = [
            r.outcome_7d_pct for r in resolved_rows
            if r.outcome_7d_pct is not None and math.isfinite(r.outcome_7d_pct)
        ]
        n_resolved = len(outcomes)
        if n_resolved > 0:
            wins = sum(1 for v in outcomes if v > 0)
            win_rate_pct = round(wins / n_resolved * 100, 1)
            avg_7d_return = round(sum(outcomes) / n_resolved, 2)
    except Exception:
        # n_resolved stays 0, which reads as "not enough signals yet" rather
        # than "the query broke" — two very different things to a reader.
        logger.warning("Readiness: resolved-signal stats unavailable — reporting "
                       "zero resolved signals", exc_info=True)

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
        if not trading_ok:
            failed = [k for k in main_loop_keys if not _loop_ok(health[k])] or ["main_loop"]
        else:
            failed = [k for k in other_critical if not _loop_ok(health.get(k, {}))]
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


class ActiveAccount(BaseModel):
    id: int
    label: str
    is_paper: bool
    read_only: bool
    port: int
    connected: bool


class TradingInvariants(BaseModel):
    """Typed live-trading safety posture — verify with one ``assert resp["ok"]``
    instead of stitching /readiness + /gateway + /accounts together by hand."""
    ok: bool
    live_gateway: Literal["stopped", "connected"]
    expected_paper: bool
    any_live_account_active: bool
    active_account: Optional[ActiveAccount]
    # Capital-cap budget for the primary active account; same math the trader
    # uses to size (invested = net_liq − available_funds).
    cap: Optional[float]
    invested: float
    cap_budget: Optional[float]
    # Exit posture for the primary active account.
    exits_armed: bool
    use_trailing_stop: bool
    trailing_stop_pct: Optional[float]
    stop_loss_pct: Optional[float]
    bracket_exits: bool
    main_loop_healthy: bool
    # Market-data mode (paper ports run delayed). Inferred from the port unless
    # the worker stores its actual reqMarketDataType.
    data_mode: Literal["delayed", "realtime"]
    data_mode_inferred: bool
    violations: List[str]


@system_router.get("/api/system/trading", response_model=TradingInvariants)
@system_router.get("/health/trading", response_model=TradingInvariants, include_in_schema=False)
def system_trading(request: Request) -> TradingInvariants:
    """Structured live-trading invariants for the active account(s).

    Read-only, mirrors /api/system/readiness wiring (app.state.worker /
    account_manager / loop_health + SessionLocal). Returns a top-level ``ok``
    plus a ``violations`` list so verifying the safety posture (e.g. real-money
    paused during a paper test, exits armed, cap budget, delayed data) is one
    assert rather than eyeballing positions across several endpoints.
    """
    from ibkr_core.core.models import Account
    from ibkr_core.features.settings.service import load_settings

    am = getattr(request.app.state, "account_manager", None)
    primary_worker = getattr(request.app.state, "worker", None)
    health = getattr(request.app.state, "loop_health", {}) or {}

    def _connected(w) -> bool:
        try:
            return bool(w is not None and w.ib.isConnected())
        except Exception:
            return False

    # ── Active accounts (DB is the source of truth for is_active) ───────────────
    active: list = []
    db_ok = True
    try:
        with SessionLocal() as db:
            active = [
                {"id": a.id, "label": a.label, "is_paper": a.is_paper,
                 "read_only": a.read_only, "port": a.port}
                for a in db.query(Account)
                           .filter(Account.is_active.is_(True))
                           .order_by(Account.id).all()
            ]
    except Exception:
        db_ok = False  # can't read posture ⇒ fail-safe to a violation below
    any_live_active = any(not a["is_paper"] for a in active)

    # ── Live gateway: "connected" iff a worker on a live port is connected ──────
    workers: list = []
    if am is not None:
        try:
            for aid in am.list_account_ids():
                w = am.get_worker_by_id(aid)
                if w is not None:
                    workers.append(w)
        except Exception:
            workers = []
    if primary_worker is not None and not any(primary_worker is w for w in workers):
        workers.append(primary_worker)
    live_gateway = "stopped"
    for w in workers:
        if int(getattr(w, "port", 0) or 0) in _LIVE_PORTS and _connected(w):
            live_gateway = "connected"
            break

    # ── Primary active account: cap budget + exit posture + data mode ───────────
    active_account: Optional[ActiveAccount] = None
    cap: Optional[float] = None
    invested = 0.0
    cap_budget: Optional[float] = None
    exits_armed = False
    use_trailing = False
    trailing_pct: Optional[float] = None
    stop_pct: Optional[float] = None
    bracket = False
    main_loop_healthy = False
    data_mode = "delayed"
    data_mode_inferred = True

    if active:
        acc = active[0]
        worker = None
        if am is not None:
            try:
                worker = am.get_worker_by_id(acc["id"])
            except Exception:
                worker = None
        if worker is None:
            worker = primary_worker
        connected = _connected(worker)
        port = acc["port"]
        _wp = getattr(worker, "port", None)
        if isinstance(_wp, int):
            port = _wp
        active_account = ActiveAccount(
            id=acc["id"], label=acc["label"], is_paper=acc["is_paper"],
            read_only=acc["read_only"], port=port, connected=connected,
        )

        # data_mode: prefer a worker-stored reqMarketDataType, else infer from port.
        # (3 = delayed, 4 = delayed-frozen; 1/2 = live/frozen real-time.)
        _mdt = getattr(worker, "_market_data_type", None)
        if isinstance(_mdt, int):
            data_mode = "delayed" if _mdt in (3, 4) else "realtime"
            data_mode_inferred = False
        else:
            data_mode = "realtime" if port in _LIVE_PORTS else "delayed"
            data_mode_inferred = True

        try:
            s = load_settings(account_id=acc["id"])
        except Exception:
            s = {}
        cap = s.get("trading_capital_cap")
        if connected:
            try:
                # Deployed capital = market value of held positions. Must match
                # trader.py sizing: (net_liq - available_funds) over-counts by a
                # paper account's baseline NLV-over-cash accrual gap when flat.
                held = worker.get_positions()
                invested = sum(max(0.0, float(p.get("market_value") or 0.0)) for p in held)
            except Exception:
                invested = 0.0
        if cap is not None and float(cap) > 0:
            cap = float(cap)
            cap_budget = max(0.0, cap - invested)  # mirrors trader.py sizing
        else:
            cap = None  # 0 / unset ⇒ uncapped
            cap_budget = None

        use_trailing = bool(s.get("use_trailing_stop"))
        trailing_pct = s.get("trailing_stop_pct")
        stop_pct = s.get("stop_loss_pct")
        bracket = bool(s.get("bracket_exits"))
        main_loop_healthy = _loop_ok(
            health.get(f"main_loop_{acc['id']}", health.get("main_loop", {}))
        )
        # Native brackets arm exits broker-side; otherwise the main loop drives
        # the trailing/hard stop, so it must be live with a stop distance set.
        if bracket:
            exits_armed = True
        else:
            exits_armed = use_trailing and bool(trailing_pct or stop_pct) and main_loop_healthy

    # ── Intended mode + invariant violations ────────────────────────────────────
    paper_test = os.getenv("PAPER_TEST", "").strip().lower() in ("1", "true", "yes")
    # Expected paper iff an explicit PAPER_TEST flag is set, or every active
    # account is paper (normal paper operation). A live account under normal
    # live operation (no flag) leaves expected_paper False — no false violation.
    expected_paper = paper_test or (bool(active) and all(a["is_paper"] for a in active))

    violations: List[str] = []
    if not db_ok:
        violations.append("could not read accounts from DB — trading posture unverified")
    if expected_paper and any_live_active:
        live_ids = [a["id"] for a in active if not a["is_paper"]]
        violations.append(
            f"real-money NOT paused — active LIVE account(s) {live_ids} present "
            "while paper mode expected"
        )
    if expected_paper and live_gateway == "connected":
        violations.append("live gateway connected while paper mode expected")
    if active_account is not None and not exits_armed:
        violations.append(f"account {active_account.id} exits not armed")
    # Coexistence is dangerous regardless of intended/flagged mode: an active LIVE
    # and an active PAPER account at once means real-money trading is not isolated.
    # Mirrors _assert_paper_test_safety's boot-time refusal (#1) so this endpoint
    # cannot report ok=true for the exact state the startup guard refuses to boot on.
    if any_live_active and any(a["is_paper"] for a in active):
        violations.append(
            "active LIVE and PAPER accounts coexist — real-money trading not isolated"
        )

    return TradingInvariants(
        ok=not violations,
        live_gateway=live_gateway,
        expected_paper=expected_paper,
        any_live_account_active=any_live_active,
        active_account=active_account,
        cap=cap,
        invested=invested,
        cap_budget=cap_budget,
        exits_armed=exits_armed,
        use_trailing_stop=use_trailing,
        trailing_stop_pct=trailing_pct,
        stop_loss_pct=stop_pct,
        bracket_exits=bracket,
        main_loop_healthy=main_loop_healthy,
        data_mode=data_mode,
        data_mode_inferred=data_mode_inferred,
        violations=violations,
    )


@system_router.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@system_router.websocket(WS_TICKERS)
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


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def create_app(extra_routers=(), extra_loops=(), title: str = "IBKR Shariah Trader") -> FastAPI:
    """Build the FastAPI app.

    Extension dists (e.g. the AI fork) call this with their own routers and
    background loops instead of re-declaring the whole application:

        from ibkr_core.main import create_app
        from backend.features.ai.router import router as ai_router
        from backend.features.ai.loops import ml_retraining_loop
        app = create_app(extra_routers=[ai_router], extra_loops=[ml_retraining_loop])

    `extra_loops` are async callables invoked as loop_fn(health) at startup.
    """
    global _EXTRA_LOOPS, _EXTRA_ROUTERS
    _EXTRA_LOOPS = list(extra_loops)
    _EXTRA_ROUTERS = list(extra_routers)

    app = FastAPI(title=title, lifespan=lifespan)
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
    app.include_router(gateway_router)
    if HAS_AI_MODULE and ai_router is not None:
        app.include_router(ai_router)
    app.include_router(settings_router)
    for r in _EXTRA_ROUTERS:
        app.include_router(r)
    app.include_router(system_router)
    return app


# Default app for standalone core deployment: `uvicorn ibkr_core.main:app`.
app = create_app()
