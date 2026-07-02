import asyncio
import logging
from datetime import date, datetime, time as dtime, timedelta
from typing import Optional, Tuple

import numpy as np
import yfinance as yf

# (symbol, action) → date last alerted; prevents duplicate Telegram noise per day
_signal_alerted: dict[Tuple[str, str], date] = {}

# ATR stop cache: (symbol, multiplier) → (stop_pct, fetched_at_timestamp)
_atr_cache: dict[tuple[str, float], tuple[float, float]] = {}
_ATR_CACHE_TTL = 86400.0  # 24 hours in seconds


def _compute_atr_stop(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                      multiplier: float = 2.5) -> float | None:
    if len(close) < 15:
        return None
    # True range needs the prior close, so drop the first bar and align all
    # three series on bars 1..N-1. (Previously `high`/`low` were full length N
    # while `prev_close[1:]` was N-1 — they never broadcast, so ATR stops were
    # always raising ValueError and silently never applied.)
    prev_close = close[:-1]
    high = high[1:]
    low = low[1:]
    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
    )
    atr = tr[-14:].mean()
    return float(atr * multiplier / close[-1])


def _atr_stop_pct(symbol: str, multiplier: float = 2.5) -> float | None:
    """Fallback: fetch 30d bars from yfinance and compute ATR stop."""
    try:
        hist = yf.Ticker(symbol).history(period="30d", interval="1d", auto_adjust=True)
        if hist.empty:
            return None
        return _compute_atr_stop(hist["High"].values, hist["Low"].values,
                                 hist["Close"].values, multiplier)
    except Exception:
        return None


# Wider ATR stops in volatile regimes avoid getting whipsawed out of good
# positions on noise; tighter stops in calm regimes cut losers faster.
_REGIME_ATR_SCALE = {"CALM": 1.0, "ELEVATED": 1.2, "CRISIS": 1.4}


def _regime_atr_multiplier(settings: dict) -> float:
    """ATR stop multiplier scaled by the current VIX regime.

    Base = settings['atr_stop_multiplier'] (default 2.5). When
    settings['atr_regime_scaling'] is on (default), the base is widened by the
    VIX tier so CRISIS regimes tolerate larger swings before stopping out.
    """
    base = float(settings.get("atr_stop_multiplier") or 2.5)
    if not (settings.get("atr_regime_scaling") if settings.get("atr_regime_scaling") is not None else True):
        return base
    try:
        from ibkr_core.features.compliance.vix import get_current_vix, vix_to_tier
        tier = vix_to_tier(get_current_vix())
    except Exception:
        tier = "CALM"
    return round(base * _REGIME_ATR_SCALE.get(tier, 1.0), 3)


async def _ibkr_daily_bars(worker, symbol: str, days: int = 30):
    """Fetch daily OHLC from IBKR. Returns (high, low, close) arrays or None."""
    try:
        from ib_insync import Stock
        from ibkr_core.core.market_hours import get_exchange_config, infer_exchange_from_symbol
        from ibkr_core.features.trading.worker import _ibkr_symbol
        exchange_code = infer_exchange_from_symbol(symbol)
        _, _, ibkr_exchange, currency = get_exchange_config(exchange_code)
        contract = Stock(_ibkr_symbol(symbol), ibkr_exchange, currency)
        await worker.ib.qualifyContractsAsync(contract)
        bars = await worker.ib.reqHistoricalDataAsync(
            contract, endDateTime='', durationStr=f'{days} D',
            barSizeSetting='1 day', whatToShow='TRADES', useRTH=True,
        )
        if not bars:
            return None
        return (
            np.array([b.high for b in bars]),
            np.array([b.low for b in bars]),
            np.array([b.close for b in bars]),
        )
    except Exception as e:
        logger.debug("IBKR bars failed for %s: %s", symbol, e)
        return None


async def _get_atr_stop(symbol: str, worker=None, multiplier: float = 2.5) -> float | None:
    """Return cached ATR stop pct, refreshing if stale (>24 h). Prefers IBKR over yfinance.

    The cache is keyed on (symbol, multiplier) so a regime change that widens
    the multiplier doesn't serve a stale stop computed for the old regime.
    """
    import time

    key = (symbol, round(multiplier, 3))
    cached = _atr_cache.get(key)
    if cached is not None:
        val, ts = cached
        if time.time() - ts < _ATR_CACHE_TTL:
            return val

    result = None
    if worker and worker.ib.isConnected():
        bars = await _ibkr_daily_bars(worker, symbol)
        if bars:
            result = _compute_atr_stop(*bars, multiplier=multiplier)
    if result is None:
        result = await asyncio.to_thread(_atr_stop_pct, symbol, multiplier)

    if result is not None:
        _atr_cache[key] = (result, time.time())
    return result


def _correlation_with_portfolio(symbol: str, positions: list) -> float:
    """Max absolute Pearson correlation of symbol vs any held position over 60 days."""
    try:
        held = [p["symbol"] for p in positions
                if p["symbol"] != symbol and float(p.get("quantity", 0)) > 0]
        if not held:
            return 0.0
        tickers = [symbol] + held[:9]  # cap to avoid rate limits
        hist = yf.download(tickers, period="60d", auto_adjust=True, progress=False)
        if isinstance(hist, dict) or hist.empty:
            return 0.0
        closes = hist["Close"] if "Close" in hist.columns else hist
        returns = closes.pct_change().dropna()
        if symbol not in returns.columns:
            return 0.0
        sym_ret = returns[symbol]
        return max(
            (abs(sym_ret.corr(returns[h])) for h in held if h in returns.columns
             and not returns[h].isnull().all()),
            default=0.0,
        )
    except Exception as e:
        logger.debug("Correlation check failed for %s: %s", symbol, e)
        return 0.0


def _compute_pullback(closes: np.ndarray) -> tuple[bool, str]:
    if len(closes) < 20:
        return True, ""
    price = float(closes[-1])
    high_20d = float(closes[-20:].max())
    sma20 = float(closes[-20:].mean())
    if price < sma20:
        return False, f"price ${price:.2f} below SMA20 ${sma20:.2f} — daily downtrend"
    pullback_pct = (high_20d - price) / high_20d if high_20d > 0 else 0.0
    if pullback_pct < 0.01:
        return False, f"price near 20d high (only {pullback_pct:.1%} dip) — wait for pullback"
    if pullback_pct > 0.05:
        return False, f"pullback {pullback_pct:.1%} too deep — potential breakdown"
    return True, f"healthy pullback {pullback_pct:.1%} from 20d high, above SMA20"


def _check_pullback_entry(symbol: str) -> tuple[bool, str]:
    """Fallback: yfinance-based pullback check."""
    try:
        hist = yf.Ticker(symbol).history(period="30d", interval="1d", auto_adjust=True)
        if hist.empty:
            return True, ""
        return _compute_pullback(hist["Close"].values)
    except Exception as e:
        logger.debug("Pullback check failed for %s: %s", symbol, e)
        return True, ""


async def _check_pullback_async(symbol: str, worker=None) -> tuple[bool, str]:
    """Pullback entry check. Prefers IBKR historical bars, falls back to yfinance."""
    if worker and worker.ib.isConnected():
        bars = await _ibkr_daily_bars(worker, symbol)
        if bars:
            return _compute_pullback(bars[2])
    return await asyncio.to_thread(_check_pullback_entry, symbol)

from ibkr_core.core.market_hours import (
    market_status,
    is_in_trading_window,
    is_market_open,
    infer_exchange_from_symbol,
    resolve_exchange,
)
from ibkr_core.core.health_utils import set_loop_error
from ibkr_core.core.websocket import ConnectionManager, WSBaseMessage
from ibkr_core.features.alerts.dispatcher import alert as send_alert
from ibkr_core.core.strategy import get_active_strategy, MarketContext

# AI analysis websocket message — private fork ships richer payloads.
try:
    from ibkr_core.features.ai.schemas import AIAnalysisMessage, AIAnalysisPayload  # type: ignore
except ImportError:
    from typing import Literal
    from pydantic import BaseModel

    class AIAnalysisPayload(BaseModel):
        symbol: str
        action: str
        sentiment_score: float
        reasoning: str

    class AIAnalysisMessage(WSBaseMessage):
        type: Literal["ai_analysis"] = "ai_analysis"
        payload: AIAnalysisPayload


# Strategy entry points — delegate to the active Strategy plugin.
async def generate_signals(watchlist=None, vix_buffer: float = 0.0):
    return await get_active_strategy().generate_signals(
        MarketContext(watchlist=watchlist or [], vix_buffer=vix_buffer)
    )


async def get_rebalance_sells(positions, signals):
    return await get_active_strategy().get_rebalance_sells(positions, signals)


async def discover_halal_buys(min_score: int = 70, chunk_size: int = 5, open_markets_only: bool = True):
    return await get_active_strategy().discover_halal_buys(
        min_score=min_score, chunk_size=chunk_size, open_markets_only=open_markets_only
    )
from ibkr_core.features.compliance.schemas import (
    ComplianceResultMessage,
    ComplianceResultPayload,
    ComplianceStatus,
)
from ibkr_core.features.compliance.screening import async_shariah_screen, screen_many
from ibkr_core.features.portfolio.allocator import PortfolioAllocator
from ibkr_core.features.settings.service import load_settings, set_active_account
from ibkr_core.features.trading.schemas import (
    PendingSignalMessage,
    PendingSignalPayload,
    TradeCreate,
    TradeSignal,
)
from ibkr_core.features.trading.trader import Trader, _estimate_fee
from ibkr_core.core.database import SessionLocal
from ibkr_core.core.models import PendingSignal, TradeHistory
from ibkr_core.core.state import TradeState

logger = logging.getLogger(__name__)


def _exceeds_daily_loss_limit(worker, settings: dict, account_id: Optional[int] = None) -> bool:
    """Returns True if today's realised + unrealised loss exceeds max_daily_loss_pct of open NLV."""
    max_loss_pct = float(settings.get("max_daily_loss_pct", 5.0))
    if max_loss_pct <= 0:
        return False
    try:
        from ibkr_core.core.database import SessionLocal
        from ibkr_core.core.models import PortfolioSnapshot
        today_start = datetime.combine(date.today(), dtime(0, 0))
        with SessionLocal() as db:
            q = db.query(PortfolioSnapshot).filter(
                PortfolioSnapshot.timestamp >= today_start,
            )
            if account_id is not None:
                q = q.filter(PortfolioSnapshot.account_id == account_id)
            else:
                q = q.filter(PortfolioSnapshot.account_id.is_(None))
            snap = q.order_by(PortfolioSnapshot.timestamp.asc()).first()
        if snap is None:
            return False
        current_nlv = worker.get_net_liquidation()
        if current_nlv <= 0:
            return False
        daily_pnl = current_nlv - snap.total_value
        max_loss = snap.total_value * (max_loss_pct / 100)
        if daily_pnl < -max_loss:
            logger.error(
                "Daily loss limit hit (account %s): P&L $%.2f < -$%.2f. Pausing trading.",
                account_id, daily_pnl, max_loss,
            )
            return True
    except Exception as e:
        logger.warning("Daily loss limit check failed: %s", e)
    return False


async def _dispatch_signal(
    signal: TradeSignal,
    compliance: ComplianceStatus,
    exchange: str,
    trader: Trader,
    manager: ConnectionManager,
    settings: dict,
    trade: Optional[TradeCreate] = None,
    source: Optional[str] = None,
    account_id: Optional[int] = None,
) -> None:
    min_confidence = int(settings.get("signal_min_confidence") or 30)
    if signal.confidence < min_confidence:
        logger.info(f"Skip {signal.symbol}: confidence {signal.confidence}% < min {min_confidence}%")
        return

    # Guard against zero-quantity SELL (IBKR returns Error 321 "size value cannot be zero")
    # BUY uses quantity=0 to trigger auto-sizing in trader.py, so only check SELL.
    if signal.action == "SELL" and trade is not None and (trade.quantity is None or trade.quantity <= 0):
        logger.warning(f"Skip {signal.symbol} SELL: zero/None quantity ({trade.quantity})")
        return

    auto_threshold = int(settings.get("auto_execute_threshold") or 0)
    channels = settings.get("alert_channels", [])
    should_auto = auto_threshold > 0 and signal.confidence >= auto_threshold

    if should_auto:
        # Cooldown gate: skip recent failures to prevent retry storms.
        #   REJECTED_FUNDS BUY: 24h (cash situation unlikely to change fast)
        #   REJECTED_FUNDS SELL: 1h (rare; allow retry)
        #   REJECTED_COMPLIANCE BUY: 24h (non-halal name won't turn compliant fast)
        #   REJECTED_COMPLIANCE SELL: 1h (Qabd/T+2 settlement or no-short guard —
        #     condition can't change within the hour; without this, an exit-signalled
        #     but unsettled position re-fires + re-logs every 60s until T+2)
        #   IBKR_ERROR: 15min (broker rejected — back off briefly)
        try:
            with SessionLocal() as _db:
                now = datetime.utcnow()
                # IBKR_ERROR cooldown (same symbol + side, 15min)
                err_cutoff = now - timedelta(minutes=15)
                recent_err = _db.query(TradeHistory).filter(
                    TradeHistory.symbol == signal.symbol,
                    TradeHistory.side == signal.action,
                    TradeHistory.state == TradeState.IBKR_ERROR,
                    TradeHistory.created_at >= err_cutoff,
                ).first()
                if recent_err:
                    logger.info("Auto-execute skip %s %s — IBKR_ERROR within 15min cooldown",
                                signal.symbol, signal.action)
                    return

                # REJECTED_FUNDS cooldown (side-aware)
                rej_window = timedelta(hours=24) if signal.action == "BUY" else timedelta(hours=1)
                rej_cutoff = now - rej_window
                recent_reject = _db.query(TradeHistory).filter(
                    TradeHistory.symbol == signal.symbol,
                    TradeHistory.side == signal.action,
                    TradeHistory.state == TradeState.REJECTED_FUNDS,
                    TradeHistory.created_at >= rej_cutoff,
                ).first()
                if recent_reject:
                    logger.info("Auto-execute skip %s %s — REJECTED_FUNDS within %s",
                                signal.symbol, signal.action, rej_window)
                    return

                # REJECTED_COMPLIANCE cooldown (side-aware). SELL blocks are the
                # Qabd/T+2 settlement guard or the no-short guard — neither clears
                # within an hour, so re-firing every loop only spams the trade log.
                comp_window = timedelta(hours=24) if signal.action == "BUY" else timedelta(hours=1)
                comp_cutoff = now - comp_window
                recent_comp = _db.query(TradeHistory).filter(
                    TradeHistory.symbol == signal.symbol,
                    TradeHistory.side == signal.action,
                    TradeHistory.state == TradeState.REJECTED_COMPLIANCE,
                    TradeHistory.created_at >= comp_cutoff,
                ).first()
                if recent_comp:
                    logger.info("Auto-execute skip %s %s — REJECTED_COMPLIANCE within %s",
                                signal.symbol, signal.action, comp_window)
                    return
        except Exception:
            pass
        logger.info(f"Auto-{signal.action} {signal.symbol} (confidence={signal.confidence}%, threshold={auto_threshold}%)")
        t = trade or TradeCreate(symbol=signal.symbol, quantity=0, side=signal.action,
                                confidence=signal.confidence,
                                win_probability=getattr(signal, "win_probability", None))
        result = await trader.execute_trade(t, exchange=exchange, pre_screened=compliance)
        logger.info(f"Trade {signal.symbol}: {result.state}")
    else:
        # Persist before broadcast — skip if identical signal already pending for same account
        db = SessionLocal()
        try:
            q = db.query(PendingSignal).filter(
                PendingSignal.symbol == signal.symbol,
                PendingSignal.action == signal.action,
            )
            if account_id is not None:
                q = q.filter(PendingSignal.account_id == account_id)
            existing = q.first()
            if existing:
                logger.debug(f"{signal.symbol} {signal.action} already pending (id={existing.id}), skipping duplicate")
                return
            logger.info(f"{signal.symbol} queued for approval (confidence={signal.confidence}%, account={account_id})")
            pending_row = PendingSignal(
                symbol=signal.symbol,
                action=signal.action,
                confidence=signal.confidence,
                sentiment_score=signal.sentiment_score,
                reasoning=signal.reasoning,
                exchange=exchange,
                source=source,
                account_id=account_id,
            )
            db.add(pending_row)
            db.commit()
        except Exception:
            logger.exception("Failed to persist PendingSignal for %s", signal.symbol)
        finally:
            db.close()
        await manager.broadcast(PendingSignalMessage(payload=PendingSignalPayload(
            symbol=signal.symbol,
            action=signal.action,
            confidence=signal.confidence,
            sentiment_score=signal.sentiment_score,
            reasoning=signal.reasoning,
            exchange=exchange,
            source=source,
            account_id=account_id,
        )))
        # Resolve account label for alert
        acct_label = ""
        if account_id is not None:
            try:
                from ibkr_core.core.database import SessionLocal as _SL
                from ibkr_core.core.models import Account as _Acc
                with _SL() as _db:
                    _row = _db.query(_Acc).filter(_Acc.id == account_id).first()
                    acct_label = _row.label if _row else f"Account {account_id}"
            except Exception:
                acct_label = f"Account {account_id}"

        emoji = "🟢" if signal.action == "BUY" else "🔴"
        acct_line = f"\n🏦 <b>{acct_label}</b>" if acct_label else ""
        body = (
            f"{emoji} <b>{signal.action} {signal.symbol}</b>\n"
            f"Confidence: {signal.confidence}%\n"
            f"<i>{signal.reasoning}</i>"
            f"{acct_line}"
        )
        markup = None
        if signal.action == "BUY":
            cb = f"approve:{signal.symbol}:{account_id}" if account_id else f"approve:{signal.symbol}"
            markup = {"inline_keyboard": [[
                {"text": f"✅ Approve BUY {signal.symbol}", "callback_data": cb}
            ]]}
        today = date.today()
        dedup_key = (signal.symbol, signal.action, account_id)
        if _signal_alerted.get(dedup_key) == today:
            logger.debug("Signal alert suppressed (already sent today): %s %s acct=%s", signal.action, signal.symbol, account_id)
            return
        _signal_alerted[dedup_key] = today
        if not settings.get("notify_signals", True):
            logger.debug("Signal alert muted via notify_signals: %s %s acct=%s",
                         signal.action, signal.symbol, account_id)
            return
        await send_alert(f"{signal.action} Signal: {signal.symbol}", body, channels,
                         reply_markup=markup)


async def main_loop(worker, manager: ConnectionManager, health: dict,
                    account_id: Optional[int] = None, manage_connection: bool = True) -> None:
    loop_key = f"main_loop_{account_id}" if account_id else "main_loop"
    health.setdefault(loop_key, {"last_run": None, "status": "starting"})
    logger.info("Starting Main Loop for account %s...", account_id or "primary")
    health[loop_key]["status"] = "running"
    # Bind this task's settings context so account-agnostic call sites in signal
    # generation (e.g. the AI strategy's buy_threshold gate) read settings_{id},
    # not bare global settings.json. Task-local — no cross-account leakage.
    set_active_account(account_id)
    trader = Trader(worker, account_id=account_id)
    if manage_connection:
        connected = False
        while not connected:
            worker.disconnect()
            connected = await worker.connect()
            if not connected:
                logger.warning("IBKR not reachable, retrying in 30s...")
                await asyncio.sleep(30)
    else:
        while not worker.ib.isConnected():
            logger.info("main_loop(%s): waiting for connection...", account_id)
            await asyncio.sleep(10)
    tick = 0
    last_symbol: Optional[str] = None
    while True:
        try:
            tick += 1
            if tick % 5 == 0:
                logger.info(
                    "main_loop heartbeat: tick=%d last_symbol=%s",
                    tick, last_symbol,
                    extra={"heartbeat": "main_loop", "tick": tick},
                )
            health[loop_key]["last_run"] = datetime.now().isoformat()
            health[loop_key]["status"] = "running"

            # Reconnect if IBKR dropped
            if not worker.ib.isConnected():
                if manage_connection:
                    logger.warning("main_loop(%s): IBKR disconnected — reconnecting...", account_id)
                    worker.disconnect()
                    if not await worker.connect():
                        logger.warning("main_loop(%s): reconnect failed, retrying in 30s...", account_id)
                        await asyncio.sleep(30)
                        continue
                else:
                    logger.warning("main_loop(%s): IBKR disconnected — waiting...", account_id)
                    await asyncio.sleep(10)
                    continue

            settings = load_settings(account_id)

            # --- Risk guards (fail-closed) ---
            if health.get("drawdown_triggered"):
                logger.warning("main_loop: drawdown circuit breaker active — skipping cycle.")
                await asyncio.sleep(300)
                continue

            if _exceeds_daily_loss_limit(worker, settings, account_id):
                await asyncio.sleep(3600)
                continue

            start_off = int(settings.get("trading_start_offset_min", 30))
            end_off = int(settings.get("trading_end_offset_min", 30))

            # ── Follow-the-sun gate ──────────────────────────────────────────
            # Gate per-exchange, not globally on NMS (which froze exits for any
            # foreign position ~24/6). A cycle runs when ANY exchange relevant
            # to this account — watchlist names' or held positions' home
            # exchanges — has an OPEN session; symbol-level work below then
            # re-checks its own exchange. Exits gate on the raw session
            # (protective sells deserve the full session); BUY dispatch keeps
            # the offset liquidity buffer per exchange.
            loop = asyncio.get_running_loop()
            positions = await loop.run_in_executor(None, worker.get_positions)
            relevant_exchanges = {"NMS"}
            relevant_exchanges |= {
                infer_exchange_from_symbol(s) for s in settings.get("watchlist", [])
            }
            relevant_exchanges |= {
                infer_exchange_from_symbol(p.get("symbol", "")) for p in positions
            }
            open_exchanges = {c for c in relevant_exchanges if is_market_open(c)}
            if not open_exchanges:
                logger.info("main_loop: no relevant exchange in session — skipping cycle.")
                await asyncio.sleep(60)
                continue

            # Skip buying a symbol if it already has a pending BUY order (avoid duplicate entries).
            # Protective SELL orders (take-profit, stop-loss) don't block new BUYs for other symbols.
            open_orders = await loop.run_in_executor(None, worker.get_open_orders)
            pending_buy_symbols = {
                o.get("symbol") for o in open_orders
                if o.get("action") == "BUY"
                and o.get("status") in ("PendingSubmit", "Submitted", "PreSubmitted")
            }
            max_positions = int(settings.get("max_positions", 15))
            available_cash = await asyncio.to_thread(worker.get_available_funds)
            min_trade = float(settings.get("min_trade_size", 50))

            # ── Stop-loss / take-profit exits ────────────────────────────────────────
            pending_sell_symbols = {
                o.get("symbol") for o in open_orders
                if o.get("action") == "SELL"
                and o.get("status") in ("PendingSubmit", "Submitted", "PreSubmitted")
            }
            # Per-account settings store unset keys as None (key present, value
            # None) so `.get(key, default)` returns None, not the default —
            # `or default` guards it, matching the `or 0` idiom below.
            fixed_stop_loss_pct = float(settings.get("stop_loss_pct") or 8.0) / 100
            take_profit_pct = float(settings.get("take_profit_pct") or 15.0) / 100
            use_atr_stops = bool(settings.get("use_atr_stops") or False)

            from ibkr_core.features.compliance.screening import live_shariah_screen
            _trail = settings.get("use_trailing_stop")
            use_trailing = True if _trail is None else bool(_trail)
            # Trailing distance from HWM, independent of the hard floor stop.
            # Falls back to stop_loss_pct (old single-knob behavior) when unset.
            trailing_stop_pct = float(
                settings.get("trailing_stop_pct") or settings.get("stop_loss_pct") or 8.0
            ) / 100
            time_exit_days = int(settings.get("time_exit_days") or 45)
            time_exit_min_gain = float(settings.get("time_exit_min_gain_pct") or 5.0) / 100
            partial_pct = float(settings.get("partial_profit_pct") or 10.0) / 100
            partial_frac = float(settings.get("partial_profit_fraction") or 0.5)

            for pos in positions:
                symbol    = pos.get("symbol", "")
                # `or 0` guards against None values (vs default-only with .get(key, 0))
                avg_cost  = float(pos.get("avg_cost") or 0)
                qty       = float(pos.get("quantity") or 0)
                mkt_val   = float(pos.get("market_value") or 0)
                if avg_cost <= 0 or qty <= 0 or symbol in pending_sell_symbols:
                    continue
                # Follow-the-sun: only work positions whose home exchange has an
                # open session — its exits can't fill elsewhere anyway.
                if not is_market_open(infer_exchange_from_symbol(symbol)):
                    continue
                cost_basis = avg_cost * qty
                upnl_pct   = (mkt_val - cost_basis) / cost_basis
                current_price = mkt_val / qty

                # Determine effective stop distance (ATR-based or fixed)
                if use_atr_stops:
                    atr_mult = _regime_atr_multiplier(settings)
                    atr_stop = await _get_atr_stop(symbol, worker=worker, multiplier=atr_mult)
                    stop_loss_pct = atr_stop if atr_stop is not None else fixed_stop_loss_pct
                    if atr_stop is None:
                        logger.debug("ATR fetch failed for %s — falling back to fixed stop %.1f%%", symbol, fixed_stop_loss_pct * 100)
                else:
                    stop_loss_pct = fixed_stop_loss_pct

                # Estimate round-trip fee as % of cost basis
                rt_fee_pct = (_estimate_fee(qty, mkt_val) * 2) / cost_basis if cost_basis > 0 else 0.0

                # Trailing stop: update HWM and check if price fell stop_pct from peak
                hwm_price = await asyncio.to_thread(_update_hwm, symbol, current_price)
                trail_drop = (hwm_price - current_price) / hwm_price if hwm_price > 0 else 0.0

                # ── Aging alert (non-exit, once per week) ─────────────────────
                try:
                    entry_dt = await asyncio.to_thread(_position_entry_date, symbol)
                    if entry_dt:
                        days_held = (datetime.now() - entry_dt.replace(tzinfo=None)).days
                        if days_held > 60 and upnl_pct < 0.05:
                            last_alert = _aging_alerted.get(symbol)
                            if last_alert is None or (date.today() - last_alert).days >= 7:
                                _aging_alerted[symbol] = date.today()
                                channels = settings.get("alert_channels", [])
                                await send_alert(
                                    f"Position Review: {symbol}",
                                    f"⏳ <b>{symbol}</b> held {days_held}d with only {upnl_pct:.1%} gain. Thesis stale?",
                                    channels,
                                )
                except Exception:
                    pass

                # ── Partial profit: sell half at first target ──────────────────
                if (upnl_pct >= partial_pct
                        and upnl_pct < take_profit_pct
                        and not _has_partial_sell(symbol)):
                    net_partial = upnl_pct - rt_fee_pct
                    if net_partial > 0:
                        partial_reason = (
                            f"Partial profit {upnl_pct:.1%} ≥ +{partial_pct:.0%}"
                            f" — selling {partial_frac:.0%} of position"
                        )
                        logger.info("Partial profit trigger %s: %s", symbol, partial_reason)
                        try:
                            cr = live_shariah_screen(symbol)
                            exchange = resolve_exchange(symbol, cr.exchange)
                            if market_status(exchange)["is_open"]:
                                partial_signal = TradeSignal(
                                    symbol=symbol, action="SELL", confidence=80,
                                    sentiment_score=0.0, reasoning=partial_reason,
                                    timestamp=datetime.now(),
                                )
                                partial_trade = TradeCreate(
                                    symbol=symbol, quantity=qty * partial_frac, side="SELL"
                                )
                                await _dispatch_signal(partial_signal, cr, exchange, trader,
                                                       manager, settings, trade=partial_trade,
                                                       account_id=account_id)
                                _mark_partial_sell(symbol)
                        except Exception as ex:
                            logger.warning("Partial profit dispatch failed for %s: %s", symbol, ex)
                        continue  # don't check full exits this cycle

                # ── Full exit checks ───────────────────────────────────────────
                exit_reason: str | None = None

                # Trailing stop (measured from HWM) — protects locked-in gains.
                # Uses trailing_stop_pct (wide, lets winners run) — distinct from
                # the tight hard floor below.
                if use_trailing and trail_drop >= trailing_stop_pct:
                    stop_label = "ATR-trail" if use_atr_stops else "trail"
                    exit_reason = f"Trailing stop ({stop_label}): -{trail_drop:.1%} from HWM ${hwm_price:.2f}"
                # Fixed floor stop (always active, from avg cost) — catches straight-down losses
                # Runs regardless of trailing stop mode — the two are complementary.
                elif upnl_pct <= -stop_loss_pct:
                    stop_label = "ATR" if use_atr_stops else "fixed"
                    exit_reason = f"Stop-loss ({stop_label}) {upnl_pct:.1%} ≤ -{stop_loss_pct:.1%}"
                # Full take-profit
                elif upnl_pct >= take_profit_pct:
                    net_gain_pct = upnl_pct - rt_fee_pct
                    if net_gain_pct > 0:
                        exit_reason = f"Take-profit {upnl_pct:.1%} ≥ +{take_profit_pct:.0%} (net after fees: {net_gain_pct:.1%})"
                    else:
                        logger.info("%s: take-profit triggered but fees (%.2f%%) eat gain — holding", symbol, rt_fee_pct * 100)
                # Time-based exit: stale thesis
                else:
                    try:
                        if entry_dt is None:
                            entry_dt = await asyncio.to_thread(_position_entry_date, symbol)
                        if entry_dt:
                            days_held = (datetime.now() - entry_dt.replace(tzinfo=None)).days
                            if days_held > time_exit_days and upnl_pct < time_exit_min_gain:
                                exit_reason = (
                                    f"Stale thesis: {days_held}d held,"
                                    f" gain {upnl_pct:.1%} < +{time_exit_min_gain:.0%} target"
                                )
                    except Exception:
                        pass

                if exit_reason:
                    logger.info("Exit trigger %s: %s", symbol, exit_reason)
                    try:
                        cr = live_shariah_screen(symbol)
                        exchange = resolve_exchange(symbol, cr.exchange)
                        if market_status(exchange)["is_open"]:
                            exit_signal = TradeSignal(
                                symbol=symbol, action="SELL", confidence=95,
                                sentiment_score=0.0, reasoning=exit_reason,
                                timestamp=datetime.now(),
                            )
                            exit_trade = TradeCreate(symbol=symbol, quantity=qty, side="SELL")
                            await _dispatch_signal(exit_signal, cr, exchange, trader, manager,
                                                   settings, trade=exit_trade,
                                                   account_id=account_id)
                            _clear_partial_sell(symbol)
                            _clear_hwm(symbol)
                            # Block re-entry for cooldown period after take-profit
                            if "Take-profit" in exit_reason:
                                _mark_cooldown_sell(symbol)
                                logger.info("Re-entry cooldown started for %s", symbol)
                    except Exception as ex:
                        logger.warning("Exit dispatch failed for %s: %s", symbol, ex)

            # ── Max-positions trim: sell weakest if over limit ───────────────────────
            over = len(positions) - max_positions
            if over > 0:
                logger.info("max_positions exceeded (%d/%d) — trimming %d weakest", len(positions), max_positions, over)
                from ibkr_core.core.models import SignalLog
                scored = []
                for pos in positions:
                    sym = pos.get("symbol", "")
                    if sym in pending_sell_symbols:
                        continue
                    try:
                        with SessionLocal() as _db:
                            row = (_db.query(SignalLog)
                                   .filter(SignalLog.symbol == sym)
                                   .order_by(SignalLog.created_at.desc())
                                   .first())
                        score = float(row.t_score) if row and row.t_score is not None else 50.0
                    except Exception:
                        score = 50.0
                    scored.append((score, pos))
                scored.sort(key=lambda x: x[0])
                for _, pos in scored[:over]:
                    sym = pos.get("symbol", "")
                    qty = float(pos.get("quantity") or 0)
                    if qty <= 0:
                        continue
                    try:
                        from ibkr_core.features.compliance.screening import live_shariah_screen
                        cr = live_shariah_screen(sym)
                        exchange = resolve_exchange(sym, cr.exchange)
                        if market_status(exchange)["is_open"]:
                            trim_signal = TradeSignal(
                                symbol=sym, action="SELL", confidence=75,
                                sentiment_score=0.0,
                                reasoning=f"Max positions trim: {len(positions)}/{max_positions}",
                                timestamp=datetime.now(),
                            )
                            trim_trade = TradeCreate(symbol=sym, quantity=qty, side="SELL")
                            await _dispatch_signal(trim_signal, cr, exchange, trader, manager,
                                                   settings, trade=trim_trade, account_id=account_id)
                    except Exception as ex:
                        logger.warning("Trim dispatch failed for %s: %s", sym, ex)

            # Kill switch: skip all new BUY/SELL signals when paused
            if settings.get("trading_paused", False):
                logger.info("main_loop: trading PAUSED — skipping signal generation")
                await asyncio.sleep(60)
                continue

            # ── BUY signals ───────────────────────────────────────────────────────────
            can_buy = len(positions) < max_positions and available_cash >= min_trade
            if not can_buy:
                logger.info(
                    f"BUY skipped: positions={len(positions)}/{max_positions} "
                    f"cash=${available_cash:.0f} min=${min_trade:.0f}"
                )
            else:
                logger.info("AI Strategy Agent: Scanning for opportunities...")
                watchlist = settings.get("watchlist", [])
                signals = await generate_signals(watchlist=watchlist or None)
                buy_signals = [s for s in signals if s.action == "BUY"]

                if buy_signals:
                    for signal in buy_signals:
                        await manager.broadcast(AIAnalysisMessage(payload=AIAnalysisPayload(
                            symbol=signal.symbol,
                            action="BUY",
                            sentiment_score=signal.sentiment_score,
                            reasoning=signal.reasoning,
                        )))

                    logger.info(f"Compliance Guard: Screening {len(buy_signals)} symbols in parallel...")
                    compliance_results = await screen_many([s.symbol for s in buy_signals])
                    signal_map = {s.symbol: s for s in buy_signals}

                    # Sort compliant signals: underrepresented sectors first, then by confidence.
                    from ibkr_core.core.strategy import get_active_strategy
                    sector_wts = get_active_strategy().get_portfolio_sector_weights()
                    if sector_wts:
                        def _sector_key(cr):
                            sec = (cr.sector or "Unknown").split("/")[0].strip()
                            return (sector_wts.get(sec, 0.0), -signal_map[cr.symbol].confidence)
                        compliance_results = sorted(compliance_results, key=_sector_key)
                    else:
                        compliance_results = sorted(
                            compliance_results,
                            key=lambda cr: -signal_map[cr.symbol].confidence,
                        )

                    require_pullback = bool(settings.get("require_pullback_entry", True))
                    cooldown_days = int(settings.get("re_entry_cooldown_days", 14))
                    max_corr = float(settings.get("max_correlation", 0.85))

                    # Cross-sectional top-N: signals are sorted best-first (momentum
                    # confidence), so dispatch at most (max_positions - current) BUYs this
                    # cycle. Without this the loop could open more than max_positions when
                    # many candidates pass the per-name filters (budget alone isn't a count cap).
                    open_slots = max(0, max_positions - len(positions))
                    dispatched_buys = 0

                    for cr in compliance_results:
                        if dispatched_buys >= open_slots:
                            logger.info("Top-N cap reached (%d open slots filled) — stopping BUY dispatch.", open_slots)
                            break
                        exchange = resolve_exchange(cr.symbol, cr.exchange)
                        await manager.broadcast(ComplianceResultMessage(payload=ComplianceResultPayload(
                            symbol=cr.symbol,
                            is_compliant=cr.is_compliant,
                            reason=cr.reason or "",
                            debt_to_mkt_cap=cr.debt_to_mkt_cap,
                            cash_to_mkt_cap=cr.cash_to_mkt_cap,
                            impure_revenue_pct=cr.impure_revenue_pct,
                            sector=cr.sector,
                            country=cr.country,
                            exchange=exchange,
                        )))
                        if not cr.is_compliant:
                            logger.warning(f"Blocked {cr.symbol}: {cr.reason}")
                            continue
                        if not is_in_trading_window(exchange, start_off, end_off):
                            logger.info(f"{cr.symbol} ({exchange}) outside its trading window. Skipping BUY.")
                            continue
                        if cr.symbol in pending_buy_symbols:
                            logger.info(f"{cr.symbol} already has pending BUY order — skipping.")
                            continue
                        if _is_in_cooldown(cr.symbol, cooldown_days):
                            logger.info("Re-entry cooldown active for %s — skipping BUY.", cr.symbol)
                            continue
                        if require_pullback:
                            ok, reason = await _check_pullback_async(cr.symbol, worker=worker)
                            if not ok:
                                logger.info("Pullback filter: skip %s — %s", cr.symbol, reason)
                                continue
                        if max_corr < 1.0:
                            corr = await asyncio.to_thread(
                                _correlation_with_portfolio, cr.symbol, positions
                            )
                            if corr >= max_corr:
                                logger.info(
                                    "Correlation filter: skip %s — corr %.2f >= %.2f",
                                    cr.symbol, corr, max_corr,
                                )
                                continue
                        last_symbol = cr.symbol
                        await _dispatch_signal(signal_map[cr.symbol], cr, exchange, trader, manager, settings, account_id=account_id)
                        dispatched_buys += 1

                    # Rebalance SELLs (AI score-based)
                    sell_signals = await get_rebalance_sells(positions, signals)
                    if sell_signals:
                        sell_compliance = await screen_many([s.symbol for s in sell_signals])
                        sell_map = {r.symbol: r for r in sell_compliance}
                        for signal in sell_signals:
                            cr = sell_map.get(signal.symbol)
                            if cr is None:
                                continue
                            exchange = resolve_exchange(signal.symbol, cr.exchange)
                            if not market_status(exchange)["is_open"]:
                                logger.info(f"SELL {signal.symbol} ({exchange}) skipped — market closed.")
                                continue
                            await _dispatch_signal(signal, cr, exchange, trader, manager, settings, account_id=account_id)

            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("Main loop cancelled — shutting down.")
            worker.disconnect()
            break
        except Exception as e:
            logger.error(f"main_loop cycle error: {e}", exc_info=True)
            set_loop_error(health[loop_key], 60, e)
            channels = load_settings(account_id).get("alert_channels", [])
            await send_alert("Main Loop Error", f"Cycle error: {e}\nWill auto-retry in 60s.", channels)
            await asyncio.sleep(60)


async def _cash_sleeve_buy(worker, trader, manager, settings: dict,
                           available_cash: float, account_id: Optional[int]) -> bool:
    """Park idle cash in a compliance-allowlisted broad Shariah ETF when momentum
    selection is quiet (no BUY signals). Returns True iff a sleeve BUY was dispatched.

    Off unless settings.cash_sweep_fallback_etf is set. Guards:
      - sleeve value capped at cash_sweep_fallback_max_pct of the (capital-capped)
        net-liq, so it accumulates one slice per quiet cycle and never dominates;
      - the ETF must pass the AAOIFI compliance screen (allowlist → COMPLIANT);
      - the market must be open.
    The BUY is auto-sized (quantity=0) so it inherits the Trader's position-% and
    trading_capital_cap sizing — no separate pricing path, no starving momentum
    (this only runs when momentum produced nothing).
    """
    etf = (settings.get("cash_sweep_fallback_etf") or "").strip().upper()
    if not etf:
        return False
    max_pct = float(settings.get("cash_sweep_fallback_max_pct", 20.0) or 0.0)
    if max_pct <= 0:
        return False

    # Sleeve-cap guard: current ETF market value vs max_pct of effective net-liq.
    net_liq = await asyncio.to_thread(worker.get_net_liquidation)
    _cap = settings.get("trading_capital_cap")
    if _cap and float(_cap) > 0:
        net_liq = min(net_liq, float(_cap))
    positions = await asyncio.to_thread(worker.get_positions)
    etf_val = sum(max(0.0, float(p.get("market_value") or 0.0))
                  for p in positions if (p.get("symbol") or "").upper() == etf)
    if net_liq <= 0 or etf_val >= (max_pct / 100.0) * net_liq:
        logger.info("Cash sleeve: %s at/over %.0f%% cap (val=%.2f, nlv=%.2f). Skipping.",
                    etf, max_pct, etf_val, net_liq)
        return False

    compliance = await async_shariah_screen(etf)
    if not compliance.is_compliant:
        logger.warning("Cash sleeve: %s NOT compliant (%s). Skipping.", etf, compliance.reason)
        return False

    exchange = compliance.exchange or "NMS"
    if not market_status(exchange)["is_open"]:
        logger.info("Cash sleeve: %s (%s) market closed. Skipping.", etf, exchange)
        return False

    signal = TradeSignal(symbol=etf, sentiment_score=0.0, confidence=60,
                         action="BUY", reasoning="Halal cash sleeve (momentum quiet)")
    trade = TradeCreate(symbol=etf, quantity=0, side="BUY", order_type="MKT", confidence=60)
    await _dispatch_signal(signal, compliance, exchange, trader, manager, settings,
                           trade=trade, source="cash_sleeve", account_id=account_id)
    logger.info("Cash sleeve: dispatched %s BUY to park idle $%.2f.", etf, available_cash)
    await send_alert("Cash Sleeve",
                     f"Parked idle cash in {etf} (momentum quiet).",
                     settings.get("alert_channels", []))
    return True


async def cash_sweep_loop(worker, manager: ConnectionManager, health: dict, account_id: Optional[int] = None) -> None:
    logger.info("Starting Cash Sweep Loop...")
    set_active_account(account_id)
    health["cash_sweep_loop"]["status"] = "running"

    _POLL_S = 30
    while not worker.ib.isConnected():
        health["cash_sweep_loop"]["status"] = "waiting"
        await asyncio.sleep(_POLL_S)

    health["cash_sweep_loop"]["status"] = "running"
    trader = Trader(worker, account_id=account_id)

    while True:
        sleep_s = 1800  # default 30 min; overridden by settings below
        try:
            if not worker.ib.isConnected():
                health["cash_sweep_loop"]["status"] = "waiting"
                await asyncio.sleep(_POLL_S)
                continue
            health["cash_sweep_loop"]["status"] = "running"
            health["cash_sweep_loop"]["last_run"] = datetime.now().isoformat()
            settings = load_settings(account_id)
            sleep_s = int(settings.get("cash_sweep_interval_min", 30)) * 60

            if not settings.get("cash_sweep_enabled", True):
                logger.info("Cash sweep skipped: cash_sweep_enabled=False.")
                await asyncio.sleep(60)
                continue

            if health.get("drawdown_triggered"):
                logger.warning("cash_sweep_loop: drawdown circuit breaker active — skipping.")
                await asyncio.sleep(sleep_s)
                continue

            if _exceeds_daily_loss_limit(worker, settings, account_id):
                await asyncio.sleep(sleep_s)
                continue

            available_cash = await asyncio.to_thread(worker.get_available_funds)
            min_trade = float(settings.get("min_trade_size", 100))
            if available_cash < min_trade:
                logger.info(f"Cash sweep: ${available_cash:.2f} < min ${min_trade:.2f}. Sleeping.")
                await asyncio.sleep(sleep_s)
                continue

            watchlist = settings.get("watchlist") or None
            signals = await generate_signals(watchlist=watchlist)
            buy_signals = [s for s in signals if s.action == "BUY"]

            if not buy_signals:
                # Momentum quiet — optionally park idle cash in a halal ETF sleeve.
                try:
                    await _cash_sleeve_buy(worker, trader, manager, settings,
                                           available_cash, account_id)
                except Exception as sleeve_err:
                    logger.exception("Cash sleeve error: %s", sleeve_err)
                logger.info("Cash sweep: no BUY signals. Sleeping.")
                await asyncio.sleep(sleep_s)
                continue

            allocator = PortfolioAllocator(min_trade_size=min_trade)
            trades = allocator.allocate(available_cash, buy_signals, {})

            if not trades:
                logger.info("Cash sweep: allocator produced no trades. Sleeping.")
                await asyncio.sleep(sleep_s)
                continue

            signal_map = {s.symbol: s for s in buy_signals}
            channels = settings.get("alert_channels", [])
            deployed_n = 0

            for trade in trades:
                try:
                    compliance = await async_shariah_screen(trade.symbol)
                    if not compliance.is_compliant:
                        logger.info(f"Cash sweep: {trade.symbol} non-compliant ({compliance.reason}). Skipping.")
                        continue

                    exchange = compliance.exchange or "NMS"
                    if not market_status(exchange)["is_open"]:
                        logger.info(f"Cash sweep: {trade.symbol} ({exchange}) market closed. Skipping.")
                        continue

                    signal = signal_map.get(trade.symbol) or TradeSignal(
                        symbol=trade.symbol, sentiment_score=0.0, confidence=0,
                        action="BUY", reasoning="Cash sweep opportunity",
                    )
                    await _dispatch_signal(signal, compliance, exchange, trader, manager, settings,
                                           trade=trade, source="cash_sweep", account_id=account_id)
                    deployed_n += 1
                except Exception as trade_err:
                    logger.exception(f"Cash sweep: error processing {trade.symbol}: {trade_err}")

            if deployed_n > 0:
                await send_alert(
                    "Cash Sweep Complete",
                    f"Found {deployed_n} opportunity(ies) for ${available_cash:.2f} idle cash.",
                    channels,
                )

        except Exception as e:
            logger.exception(f"Error in cash_sweep_loop: {e}")

        await asyncio.sleep(sleep_s)

import os
import json

# CWD-relative data dir (matches DATA_DIR convention in screening.py). Resolving
# relative to __file__ breaks when ibkr_core is installed as a wheel — the path
# lands in read-only site-packages and writes raise PermissionError.
_DATA_DIR = os.getenv("DATA_DIR", "data")


def _atomic_write_json(path: str, data, indent=None) -> None:
    """Atomically write JSON. Uses a unique temp file in the same dir so that
    concurrent writers (per-account loops update HWM/cooldown via
    run_in_executor threads) don't collide on a shared "<path>.tmp" and race
    each other's os.replace into FileNotFoundError."""
    import tempfile
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=indent)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


DRIP_STATE_FILE = os.path.join(_DATA_DIR, "drip_state.json")

def load_drip_state() -> dict:
    if os.path.exists(DRIP_STATE_FILE):
        try:
            with open(DRIP_STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("drip_state.json corrupt or unreadable — resetting to empty")
            return {}
    return {}

def save_drip_state(state: dict):
    _atomic_write_json(DRIP_STATE_FILE, state, indent=2)


# ── Trailing stop — high-water mark ───────────────────────────────────────
_HWM_FILE = os.path.join(_DATA_DIR, "hwm.json")


def _load_hwm() -> dict:
    try:
        if os.path.exists(_HWM_FILE):
            with open(_HWM_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _update_hwm(symbol: str, current_price: float) -> float:
    """Update HWM if current_price is a new peak. Returns the HWM price."""
    hwm = _load_hwm()
    hwm[symbol] = max(hwm.get(symbol, current_price), current_price)
    _atomic_write_json(_HWM_FILE, hwm)
    return hwm[symbol]


def _clear_hwm(symbol: str) -> None:
    hwm = _load_hwm()
    hwm.pop(symbol, None)
    _atomic_write_json(_HWM_FILE, hwm)


# ── Partial profit tracking ────────────────────────────────────────────────
_PARTIAL_SELLS_FILE = os.path.join(_DATA_DIR, "partial_sells.json")


def _load_partial_sells() -> dict:
    try:
        if os.path.exists(_PARTIAL_SELLS_FILE):
            with open(_PARTIAL_SELLS_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _has_partial_sell(symbol: str) -> bool:
    return symbol in _load_partial_sells()


def _mark_partial_sell(symbol: str) -> None:
    ps = _load_partial_sells()
    ps[symbol] = datetime.now().isoformat()
    _atomic_write_json(_PARTIAL_SELLS_FILE, ps)


def _clear_partial_sell(symbol: str) -> None:
    ps = _load_partial_sells()
    ps.pop(symbol, None)
    _atomic_write_json(_PARTIAL_SELLS_FILE, ps)


# ── Position entry date ────────────────────────────────────────────────────
def _position_entry_date(symbol: str) -> Optional[datetime]:
    """Earliest filled/submitted BUY in TradeHistory for this symbol."""
    try:
        from ibkr_core.core.models import TradeHistory
        with SessionLocal() as db:
            row = (
                db.query(TradeHistory)
                .filter(
                    TradeHistory.symbol == symbol,
                    TradeHistory.side == "BUY",
                )
                .order_by(TradeHistory.created_at.asc())
                .first()
            )
        return row.created_at if row else None
    except Exception:
        return None


# ── Aging alert deduplication (once per week per symbol) ──────────────────
_aging_alerted: dict[str, date] = {}

# ── Re-entry cooldown ──────────────────────────────────────────────────────
_COOLDOWN_FILE = os.path.join(_DATA_DIR, "cooldown_sells.json")


def _load_cooldowns() -> dict:
    try:
        if os.path.exists(_COOLDOWN_FILE):
            with open(_COOLDOWN_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _mark_cooldown_sell(symbol: str) -> None:
    """Record that symbol was just sold at take-profit; blocks re-entry for cooldown period."""
    cooldowns = _load_cooldowns()
    cooldowns[symbol] = datetime.now().isoformat()
    _atomic_write_json(_COOLDOWN_FILE, cooldowns, indent=2)


def _is_in_cooldown(symbol: str, days: int = 14) -> bool:
    """Returns True if symbol was recently sold at take-profit and cooldown has not expired."""
    ts = _load_cooldowns().get(symbol)
    if not ts:
        return False
    try:
        return (datetime.now() - datetime.fromisoformat(ts)).days < days
    except Exception:
        return False

async def halal_drip_loop(worker, manager: ConnectionManager, health: dict, account_id: Optional[int] = None) -> None:
    logger.info("Starting Halal DRIP Loop...")
    set_active_account(account_id)
    health["halal_drip_loop"] = {"status": "running", "last_run": None}

    _MAX_WAIT_S = 300
    _POLL_S = 30
    elapsed = 0
    while not worker.ib.isConnected():
        if elapsed >= _MAX_WAIT_S:
            logger.warning("Halal DRIP loop: IBKR not connected after 5 min — will retry next cycle")
            health["halal_drip_loop"]["status"] = "waiting"
            elapsed = 0  # reset so next cycle tries again
            await asyncio.sleep(_MAX_WAIT_S)
        await asyncio.sleep(_POLL_S)
        elapsed += _POLL_S

    trader = Trader(worker, account_id=account_id)

    while True:
        sleep_s = 21600  # Check every 6 hours
        try:
            settings = load_settings(account_id)
            if not settings.get("enable_halal_drip", False):
                await asyncio.sleep(3600)
                continue

            health["halal_drip_loop"]["last_run"] = datetime.now().isoformat()
            
            positions = await asyncio.to_thread(worker.get_positions)
            if not positions:
                await asyncio.sleep(sleep_s)
                continue

            dividends = await asyncio.to_thread(worker.get_dividends_batch, positions)
            min_trade = float(settings.get("min_trade_size", 100))
            channels = settings.get("alert_channels", [])
            drip_state = load_drip_state()
            
            for div in dividends:
                sym = div["symbol"]
                total_received = div.get("total_received")
                if not total_received or total_received <= 0:
                    continue
                
                already_reinvested = drip_state.get(sym, 0.0)
                unreinvested = total_received - already_reinvested
                
                if unreinvested <= 0:
                    continue

                compliance = await async_shariah_screen(sym)
                impure_pct = compliance.impure_revenue_pct or 0.0
                
                pure_amount = unreinvested - (unreinvested * impure_pct)
                
                if pure_amount > min_trade:
                    exchange = compliance.exchange or "NMS"
                    if not market_status(exchange)["is_open"]:
                        logger.info(f"Halal DRIP: {sym} market closed.")
                        continue
                    
                    price = await worker.get_last_price(sym, exchange)
                    qty = pure_amount / price if price > 0 else 0.0
                    if qty < 0.001:
                        continue
                        
                    logger.info(f"Halal DRIP: reinvesting ${pure_amount:.2f} of {sym}")
                    trade = TradeCreate(symbol=sym, quantity=qty, side="BUY")
                    result = await trader.execute_trade(trade, exchange=exchange, pre_screened=compliance)
                    
                    if result.state.name in ("FILLED", "SUBMITTED", "PRE_ORDER", "HALAL_CERTIFIED"):
                        drip_state[sym] = already_reinvested + unreinvested
                        save_drip_state(drip_state)
                        await send_alert(
                            "Halal DRIP Executed",
                            f"Reinvested ${pure_amount:.2f} of purified dividends into {sym}.",
                            channels,
                        )

        except Exception as e:
            logger.exception(f"Error in halal_drip_loop: {e}")

        await asyncio.sleep(sleep_s)


async def discovery_loop(worker, manager: ConnectionManager, health: dict, account_id: Optional[int] = None) -> None:
    """
    Periodically runs the Discovery scan and auto-executes halal BUY signals
    that meet the auto_execute_threshold. Runs only when enable_discovery_auto=True.
    Cadence: discovery_interval_hours (default 6h).
    """
    logger.info("Starting Discovery Auto-Execute Loop...")
    set_active_account(account_id)
    health["discovery_loop"] = {"status": "running", "last_run": None}
    trader = Trader(worker, account_id=account_id)

    while True:
        try:
            settings = load_settings(account_id)
            if not settings.get("enable_discovery_auto", False):
                await asyncio.sleep(3600)
                continue

            if health.get("drawdown_triggered"):
                logger.warning("discovery_loop: drawdown circuit breaker active — skipping.")
                await asyncio.sleep(3600)
                continue

            if _exceeds_daily_loss_limit(worker, settings, account_id):
                await asyncio.sleep(3600)
                continue

            from ibkr_core.core.market_hours import any_market_open
            if not any_market_open():
                logger.info("discovery_loop: all markets closed — sleeping 30m.")
                await asyncio.sleep(1800)
                continue

            from ibkr_core.features.compliance.vix import get_current_vix
            vix = await asyncio.to_thread(get_current_vix)
            max_vix = float(settings.get("max_vix_for_buys", 30.0))
            if vix > max_vix:
                logger.warning("Discovery Loop: VIX %.1f > %.1f — skipping new BUYs.", vix, max_vix)
                await asyncio.sleep(3600)
                continue

            logger.info("Discovery Loop: scanning market for halal BUYs (VIX=%.1f)...", vix)
            signals = await discover_halal_buys()

            if signals:
                compliance_map = {c.symbol: c for c in await screen_many([s.symbol for s in signals])}
                for signal in signals:
                    compliance = compliance_map.get(signal.symbol)
                    if not compliance or not compliance.is_compliant:
                        continue
                    exchange = compliance.exchange or "NMS"
                    if not market_status(exchange)["is_open"]:
                        continue
                    await _dispatch_signal(
                        signal, compliance, exchange, trader, manager, settings,
                        source="discovery", account_id=account_id,
                    )

            health["discovery_loop"]["last_run"] = datetime.now().isoformat()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception(f"Error in discovery_loop: {e}")
            set_loop_error(health["discovery_loop"], 3600, e)

        _MIN_INTERVAL_S = 4 * 3600  # 4h floor — prevent yfinance API abuse
        interval_s = max(int(settings.get("discovery_interval_hours", 6)) * 3600, _MIN_INTERVAL_S)
        await asyncio.sleep(interval_s)


async def position_rerating_loop(worker, manager: ConnectionManager, health: dict, account_id: Optional[int] = None) -> None:
    """
    Every 4h: re-score all held positions via multi-factor scoring.
    If score drops below rerate_sell_threshold, dispatch SELL signal.
    Prevents holding deteriorating positions until stop-loss triggers.
    """
    logger.info("Starting Position Re-Rating Loop...")
    set_active_account(account_id)
    health["position_rerating_loop"] = {"status": "running", "last_run": None}

    while True:
        try:
            settings = load_settings(account_id)
            if not worker.ib.isConnected():
                await asyncio.sleep(3600)
                continue

            positions = await asyncio.to_thread(worker.get_positions)
            if not positions:
                await asyncio.sleep(4 * 3600)
                continue

            threshold = int(settings.get("rerate_sell_threshold") or 35)
            trader = Trader(worker, account_id=account_id)

            from ibkr_core.core.strategy import get_active_strategy
            strategy = get_active_strategy()
            from ibkr_core.features.compliance.vix import get_current_vix, vix_to_ratio_buffer

            vix = await asyncio.to_thread(get_current_vix)
            buf = vix_to_ratio_buffer(vix)

            for pos in positions:
                symbol = pos.get("symbol", "")
                qty = float(pos.get("quantity", 0))
                if not symbol or qty <= 0:
                    continue
                try:
                    res = await strategy.get_multi_factor_score(symbol, vix_buffer=buf)
                    if res is None:
                        continue
                    score = res["total_score"]
                    if score <= threshold:
                        logger.info("Re-rating SELL: %s score=%d <= threshold=%d", symbol, score, threshold)
                        from ibkr_core.features.compliance.screening import async_shariah_screen
                        cr = await async_shariah_screen(symbol)
                        exchange = resolve_exchange(symbol, cr.exchange)
                        if market_status(exchange)["is_open"]:
                            signal = TradeSignal(
                                symbol=symbol, action="SELL", confidence=80,
                                sentiment_score=0.0,
                                reasoning=f"Re-rating: score {score} ≤ threshold {threshold}. Fundamentals/technicals degraded.",
                                timestamp=datetime.now(),
                            )
                            await _dispatch_signal(signal, cr, exchange, trader, manager, settings, account_id=account_id)
                except Exception as e:
                    logger.warning("Re-rating failed for %s: %s", symbol, e)

            health["position_rerating_loop"]["last_run"] = datetime.now().isoformat()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("position_rerating_loop error: %s", e)
            set_loop_error(health["position_rerating_loop"], 4 * 3600, e)

        await asyncio.sleep(4 * 3600)
