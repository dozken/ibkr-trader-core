import asyncio
import math
import logging
from copy import copy
from datetime import datetime, timezone
from typing import Optional
from ibkr_core.core.state import TradeState, TradeStateMachine
from ibkr_core.features.trading.schemas import Trade, TradeCreate
from ibkr_core.features.compliance.schemas import ComplianceStatus
from ibkr_core.features.compliance.screening import check_shariah_compliance
from ibkr_core.core.database import SessionLocal
from ibkr_core.core.models import Account, TradeHistory, AuditLog, TwapExecution
from ibkr_core.features.settings.service import load_settings as _load_settings, RISK_STOP_TAKE
from ibkr_core.core.monitoring import TRADES_EXECUTED
from ibkr_core.features.compliance.vix import get_current_vix, vix_to_tier

logger = logging.getLogger(__name__)

# IBKR supports fractional shares down to 0.001; anything smaller is rejected.
_MIN_FRACTIONAL_QTY = 0.001

# IBKR US equity fee schedule: $0.005/share, min $1.00, max 0.5% of trade value.
_IBKR_FEE_PER_SHARE = 0.005
_IBKR_MIN_FEE = 1.00
_IBKR_MAX_FEE_PCT = 0.005  # 0.5%


def _estimate_fee(qty: float, trade_value: float) -> float:
    """Estimate one-way IBKR commission for a US equity trade."""
    fee = max(qty * _IBKR_FEE_PER_SHARE, _IBKR_MIN_FEE)
    return min(fee, trade_value * _IBKR_MAX_FEE_PCT)


def _get_vix_size_factor() -> float:
    """Scale position size by market volatility: CRISIS=0.5×, ELEVATED=0.75×, CALM=1.0×."""
    try:
        vix = get_current_vix()
        return {"CALM": 1.0, "ELEVATED": 0.75, "CRISIS": 0.5}.get(vix_to_tier(vix), 1.0)
    except Exception:
        return 1.0


def _slippage_scale(symbol: str) -> float:
    """Returns [0.5, 1.0] size factor. High historical slippage → smaller position."""
    try:
        with SessionLocal() as db:
            rows = (
                db.query(TradeHistory)
                .filter(
                    TradeHistory.symbol == symbol,
                    TradeHistory.fill_price.isnot(None),
                    TradeHistory.signal_price.isnot(None),
                    TradeHistory.signal_price > 0,
                )
                .order_by(TradeHistory.created_at.desc())
                .limit(10)
                .all()
            )
        if len(rows) < 3:
            return 1.0
        avg_slip = sum(abs(r.fill_price - r.signal_price) / r.signal_price for r in rows) / len(rows)
        if avg_slip > 0.01:
            return 0.5
        if avg_slip > 0.005:
            return 0.75
        return 1.0
    except Exception:
        return 1.0


def _kelly_scale(confidence: float, settings: dict) -> float:
    """
    Half-Kelly fraction normalised to 1.0 at baseline confidence (0.65).
    Returns a multiplier in [0.5, 1.5] to scale the base position size.
    """
    tp = (settings.get("take_profit_pct") or 15.0) / 100
    sl = (settings.get("stop_loss_pct") or 8.0) / 100
    b = tp / sl if sl > 0 else 1.875
    p = max(0.0, min(1.0, confidence))
    k_full = (p * b - (1.0 - p)) / b
    half_k = max(0.0, k_full * 0.5)
    # Normalise: at baseline p=0.65 the scale should be 1.0
    baseline = max(0.001, (0.65 * b - 0.35) / b * 0.5)
    return max(0.5, min(1.5, half_k / baseline))


def _calculate_position_size(
    available_funds: float,
    net_liquidation: float,
    price: float,
    settings: dict,
    confidence: float = 0.5,
    symbol: str = "",
) -> float:
    """
    Fractional-share position size per SETTINGS_SCHEMA.md:
    - cash_reserve_pct: keep this % of net_liq as uninvested buffer
    - max_position_size_pct: cap single position as % of portfolio
    - min_trade_size: reject trade if deployable dollars < this
    - VIX-adjusted: scale by 0.5/0.75/1.0 for CRISIS/ELEVATED/CALM
    - Kelly-adjusted: scale by half-Kelly fraction when use_kelly_sizing=True
    Returns 0.0 if the computed quantity is below IBKR's minimum (0.001).
    """
    reserve = net_liquidation * (settings.get("cash_reserve_pct", 5.0) / 100)
    investable = max(available_funds - reserve, 0.0)
    max_position = net_liquidation * (settings.get("max_position_size_pct", 10.0) / 100)
    target_pct = settings.get("position_size_pct", settings.get("max_position_size_pct", 10.0))
    target_position = net_liquidation * (target_pct / 100)
    dollars = min(investable, min(target_position, max_position))
    if dollars < settings.get("min_trade_size", 10.0):
        return 0.0
    vix_factor = _get_vix_size_factor()
    if settings.get("use_kelly_sizing", True):
        kelly_factor = _kelly_scale(confidence, settings)
        dollars = dollars * kelly_factor
    slip_factor = _slippage_scale(symbol) if symbol else 1.0
    qty = (dollars / price) * vix_factor * slip_factor
    if math.isnan(qty) or qty < _MIN_FRACTIONAL_QTY:
        return 0.0
    # Reject if round-trip fee > max_commission_pct of trade value (default 0.5% each way = 1% RT)
    max_fee_pct = settings.get("max_commission_pct", 0.5) / 100
    one_way_fee = _estimate_fee(qty, dollars)
    if one_way_fee > dollars * max_fee_pct:
        logger.warning("Position size $%.0f too small — fee $%.2f exceeds %.1f%% threshold", dollars, one_way_fee, max_fee_pct * 100)
        return 0.0
    return qty  # NOT rounded — fractional shares supported


def _exceeds_concentration_limit(
    symbol: str,
    new_qty: float,
    price: float,
    net_liq: float,
    worker,
    settings: dict,
) -> bool:
    """Returns True if adding new_qty of symbol would breach position OR sector concentration limits."""
    max_pos = net_liq * (settings.get("max_position_size_pct", 10.0) / 100)
    max_sector = net_liq * (settings.get("max_sector_exposure_pct", 25.0) / 100)

    existing_value = 0.0
    positions = []
    try:
        positions = worker.get_positions()
        existing = next((p for p in positions if p["symbol"] == symbol), None)
        if existing:
            existing_value = float(existing.get("market_value", 0.0))
    except Exception:
        pass

    new_position_value = existing_value + new_qty * price
    if new_position_value > max_pos:
        logger.warning("%s: single-position limit exceeded (%.2f > %.2f)", symbol, new_position_value, max_pos)
        return True

    # Sector concentration check via PositionCompliance records
    try:
        from ibkr_core.core.models import PositionCompliance
        with SessionLocal() as db:
            target_rec = (
                db.query(PositionCompliance)
                .filter(PositionCompliance.symbol == symbol)
                .order_by(PositionCompliance.timestamp.desc())
                .first()
            )
            def _norm_sector(s: str | None) -> str:
                return (s or "Unknown").split("/")[0].strip()

            target_sector = _norm_sector(
                target_rec.metrics.get("sector") if target_rec and target_rec.metrics else None
            )

            if target_sector and target_sector not in ("Unknown", None, ""):
                sector_value = existing_value
                held_sectors: set[str] = set()
                for pos in positions:
                    if pos["symbol"] == symbol:
                        continue
                    pos_rec = (
                        db.query(PositionCompliance)
                        .filter(PositionCompliance.symbol == pos["symbol"])
                        .order_by(PositionCompliance.timestamp.desc())
                        .first()
                    )
                    if pos_rec and pos_rec.metrics:
                        ps = _norm_sector(pos_rec.metrics.get("sector"))
                        held_sectors.add(ps)
                        if ps == target_sector:
                            sector_value += float(pos.get("market_value", 0.0))

                if (sector_value + new_qty * price) > max_sector:
                    logger.warning(
                        "%s: sector '%s' limit exceeded (%.2f > %.2f)",
                        symbol, target_sector, sector_value + new_qty * price, max_sector,
                    )
                    return True

                # Enforce minimum sector diversification: if portfolio has fewer than
                # min_sector_count distinct sectors, block adding more to an existing one.
                min_sectors = settings.get("min_sector_count", 4)
                all_sectors = held_sectors | {target_sector}
                if len(all_sectors) < min_sectors and target_sector in held_sectors:
                    logger.warning(
                        "%s: only %d sector(s) held, need %d before adding more '%s'",
                        symbol, len(held_sectors), min_sectors, target_sector,
                    )
                    return True
    except Exception as e:
        logger.warning("Sector concentration check failed for %s: %s", symbol, e)

    return False


def _calculate_atr(symbol: str, window: int = 14) -> float:
    import yfinance as yf
    import pandas as pd
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1mo")
        if df.empty or len(df) < window:
            return 0.0
        # TR calculation
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift(1)).abs()
        low_close = (df['Low'] - df['Close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window).mean().iloc[-1]
        return float(atr)
    except Exception as e:
        logger.warning(f"Failed to calculate ATR for {symbol}: {e}")
        return 0.0


def _stop_take_prices(symbol: str, entry_price: float, settings: dict) -> tuple:
    """Derives stop-loss and take-profit prices from risk_profile or explicit overrides. Optionally uses ATR."""
    if settings.get("use_atr_stops", True):
        atr = _calculate_atr(symbol)
        if atr > 0:
            return round(entry_price - 2 * atr, 4), round(entry_price + 3 * atr, 4), round(2 * atr, 4)

    profile = settings.get("risk_profile", "CONSERVATIVE")
    stop_pct, tp_pct = RISK_STOP_TAKE.get(profile, (3.0, 6.0))
    stop_pct = settings.get("stop_loss_pct") or stop_pct
    tp_pct = settings.get("take_profit_pct") or tp_pct
    return round(entry_price * (1 - stop_pct / 100), 4), round(entry_price * (1 + tp_pct / 100), 4), None

class Trader:
    """
    Manages the execution lifecycle of a trade with strict Shariah guardrails.
    Ref: AGENT.md - Ironclad Engineering & Fail-Closed logic.
    Ref: COMPLIANCE.md - Transactional Prohibitions (No Margin, No Shorting).
    Track C: Trading & Infrastructure - Ref: PARALLEL_WORKFLOW.md.
    """
    def __init__(self, worker, account_id: Optional[int] = None):
        self.worker = worker
        self.account_id = account_id

    async def _check_slippage_liquidity(
        self, 
        symbol: str, 
        quantity: float, 
        exchange: str, 
        settings: dict
    ) -> tuple:
        """
        Returns (is_ok, reason, suggested_quantity).
        Formula: Estimated Slippage = (Ask - Bid) / 2.
        If Slippage > max_slippage_pct (0.5%), abort.
        If Trade Size > max_liquidity_pct (1%) of 20d avg volume, downsize.
        """
        try:
            mkt = await self.worker.get_market_data(symbol, exchange)
            avg_vol = await self.worker.get_avg_volume_20d(symbol, exchange)
            
            bid = mkt.get("bid", 0.0)
            ask = mkt.get("ask", 0.0)
            last = mkt.get("last", 0.0)

            # Delayed paper data often lacks live bid/ask — skip slippage check, proceed with order
            if last <= 0 or bid <= 0 or ask <= 0:
                logger.info(f"No live bid/ask for {symbol} (delayed data) — skipping slippage check")
            else:
                slippage_dollars = (ask - bid) / 2
                slippage_pct = (slippage_dollars / last) * 100
                if slippage_pct > settings.get("max_slippage_pct", 0.5):
                    return False, f"Slippage too high: {slippage_pct:.2f}% > {settings.get('max_slippage_pct')}%", quantity

            suggested_qty = quantity
            if avg_vol > 0:
                limit_pct = settings.get("max_liquidity_pct", 1.0)
                vol_pct = (quantity / avg_vol) * 100
                if vol_pct > limit_pct:
                    max_safe_qty = (limit_pct / 100) * avg_vol
                    # Round down to prevent fractional edge cases if needed, 
                    # but our system supports fractional. 
                    suggested_qty = max_safe_qty
                    logger.warning(
                        f"Liquidity risk for {symbol}: {vol_pct:.2f}% of daily volume. "
                        f"Downsizing {quantity:.4f} -> {suggested_qty:.4f}"
                    )
            
            return True, "", suggested_qty
        except Exception as e:
            logger.error(f"Slippage/Liquidity check failed for {symbol}: {e}")
            # Fail-closed: if check fails, we assume high risk.
            return False, f"Verification failed: {e}", quantity

    async def execute_trade(
        self,
        trade_req: TradeCreate,
        exchange: str = "NMS",
        pre_screened: Optional[ComplianceStatus] = None,
        force_liquidation: bool = False,
        **compliance_data,
    ) -> Trade:
        """
        Executes a trade request following the state machine and compliance rules.
        Includes persistence to the immutable AuditLog and TradeHistory.

        pre_screened: pass an already-computed ComplianceStatus to skip re-screening.
        force_liquidation: True only for kill-switch SELLs on non-compliant positions.
        """
        if self.account_id is not None:
            _db = SessionLocal()
            try:
                acct = _db.query(Account).filter(Account.id == self.account_id).first()
                if acct and acct.read_only:
                    logger.info(f"Account {self.account_id} is read-only — blocking {trade_req.side} {trade_req.symbol}")
                    return Trade(**trade_req.model_dump(), state=TradeState.REJECTED_COMPLIANCE)
            finally:
                _db.close()

        machine = TradeStateMachine()
        db = SessionLocal()

        trade = Trade(
            **trade_req.model_dump(),
            state=machine.state
        )

        try:
            # 1. AI Analysis
            machine.transition_to(TradeState.AI_ANALYSIS)
            trade.state = machine.state

            # 2. Screening
            machine.transition_to(TradeState.SCREENING)
            trade.state = machine.state

            if force_liquidation and trade.side == "SELL":
                # Kill-switch path: selling because the stock is non-compliant.
                # Use pre_screened result for the audit record; skip re-check.
                if pre_screened is None:
                    raise ValueError("force_liquidation requires pre_screened ComplianceStatus")
                compliance_status = pre_screened
            elif pre_screened is not None:
                compliance_status = pre_screened
            else:
                compliance_status = check_shariah_compliance(
                    symbol=trade.symbol,
                    debt=compliance_data.get("debt", 0),
                    cash=compliance_data.get("cash", 0),
                    revenue=compliance_data.get("revenue", 0),
                    prohibited_income=compliance_data.get("prohibited_income", 0),
                    mkt_cap=compliance_data.get("mkt_cap", 1),
                    sector=compliance_data.get("sector", "Unknown"),
                )
            trade.compliance_snapshot = compliance_status
            
            # Persist to Immutable Audit Log
            # Ref: AUDIT_LOG.md Section 1
            from ibkr_core.core.audit import secure_log_entry
            audit_entry = AuditLog(
                symbol=trade.symbol,
                action=trade.side,
                shariah_status="COMPLIANT" if compliance_status.is_compliant else "NON_COMPLIANT",
                data_source=compliance_status.data_source,
                metrics={
                    "debt_to_market_cap": compliance_status.debt_to_mkt_cap,
                    "cash_to_market_cap": compliance_status.cash_to_mkt_cap,
                    "impure_revenue_ratio": compliance_status.impure_revenue_pct
                },
                business_activity=compliance_status.sector,
                ibkr_order_id=None # Will update later if submitted
            )
            secure_log_entry(db, audit_entry)
            
            if not compliance_status.is_compliant and not force_liquidation:
                machine.transition_to(TradeState.REJECTED_COMPLIANCE)
                trade.state = machine.state
                self._persist_trade_history(db, trade)
                return trade
            
            # 3. Halal Certified
            machine.transition_to(TradeState.HALAL_CERTIFIED)
            trade.state = machine.state
            
            # 4. Pre-Order (Cash-Only Guard & Settlement Guard)
            # Ref: COMPLIANCE.md Section 3 (Zero Leverage) & 4 (Possession)
            machine.transition_to(TradeState.PRE_ORDER)
            trade.state = machine.state
            
            settings = _load_settings()
            price = await self.worker.get_last_price(trade.symbol, exchange)

            # Fail-closed: if price is missing or zero, abort to prevent NaN/division errors
            if price <= 0:
                logger.error(f"Trade aborted for {trade.symbol}: Invalid or missing price ({price})")
                machine.transition_to(TradeState.IBKR_ERROR)
                trade.state = machine.state
                self._persist_trade_history(db, trade)
                return trade

            trade.signal_price = price

            if trade.side == 'BUY':
                available_funds, net_liq = await asyncio.gather(
                    asyncio.to_thread(self.worker.get_available_funds),
                    asyncio.to_thread(self.worker.get_net_liquidation),
                )

                if trade.quantity == 0:
                    trade.quantity = _calculate_position_size(
                        available_funds, net_liq, price, settings,
                        confidence=trade_req.confidence / 100,
                        symbol=trade.symbol,
                    )

                if trade.quantity < _MIN_FRACTIONAL_QTY:
                    machine.transition_to(TradeState.REJECTED_FUNDS)
                    trade.state = machine.state
                    self._persist_trade_history(db, trade)
                    return trade

                # Shrink-to-fit: if requested qty exceeds available funds (race condition
                # from earlier in-flight orders draining cash), shrink to what we can afford
                # instead of rejecting. Leave 2% headroom for fees + slippage.
                if trade.quantity * price > available_funds:
                    affordable_qty = (available_funds * 0.98) / price
                    if affordable_qty < _MIN_FRACTIONAL_QTY:
                        logger.info(
                            "REJECT_FUNDS %s: cannot afford even fractional (%.4f@$%.2f vs $%.2f)",
                            trade.symbol, affordable_qty, price, available_funds,
                        )
                        machine.transition_to(TradeState.REJECTED_FUNDS)
                        trade.state = machine.state
                        self._persist_trade_history(db, trade)
                        return trade
                    logger.info(
                        "Shrink %s: %.4f → %.4f (cash cap $%.2f @ $%.2f)",
                        trade.symbol, trade.quantity, affordable_qty, available_funds, price,
                    )
                    trade.quantity = affordable_qty

                if _exceeds_concentration_limit(trade.symbol, trade.quantity, price, net_liq, self.worker, settings):
                    machine.transition_to(TradeState.REJECTED_FUNDS)
                    trade.state = machine.state
                    self._persist_trade_history(db, trade)
                    return trade

                is_ok, slip_reason, suggested_qty = await self._check_slippage_liquidity(
                    trade.symbol, trade.quantity, exchange, settings
                )
                if not is_ok:
                    logger.warning(f"Trade aborted for {trade.symbol}: {slip_reason}")
                    machine.transition_to(TradeState.IBKR_ERROR)
                    trade.state = machine.state
                    self._persist_trade_history(db, trade)
                    return trade

                if suggested_qty < _MIN_FRACTIONAL_QTY:
                    logger.warning(
                        f"Trade aborted for {trade.symbol}: Liquidity-adjusted quantity "
                        f"{suggested_qty:.4f} below minimum {_MIN_FRACTIONAL_QTY}"
                    )
                    machine.transition_to(TradeState.REJECTED_FUNDS)
                    trade.state = machine.state
                    self._persist_trade_history(db, trade)
                    return trade

                trade.quantity = suggested_qty
                est_fee = _estimate_fee(trade.quantity, trade.quantity * price)
                logger.info("BUY %s qty=%.4f est_fee=$%.2f (one-way)", trade.symbol, trade.quantity, est_fee)

                if settings.get("dry_run", False):
                    logger.info(f"[DRY RUN] BUY {trade.quantity:.4f} {trade.symbol} @ ~{price:.2f}")
                    machine.transition_to(TradeState.DRY_RUN)
                    trade.state = machine.state
                    self._persist_trade_history(db, trade)
                    return trade

                stop_price, tp_price, trailing_amount = _stop_take_prices(trade.symbol, price, settings)

                # Pre-commit PRE_ORDER to DB before IBKR call — crash recovery guard
                self._persist_trade_history(db, trade)

                # TWAP: split large orders to reduce market impact
                avg_vol = await self.worker.get_avg_volume_20d(trade.symbol, exchange)
                twap_thresh = float(settings.get("twap_threshold_pct", 0.5)) / 100
                use_twap = avg_vol > 0 and (trade.quantity / avg_vol) > twap_thresh
                if use_twap:
                    n_slices = int(settings.get("twap_slices", 5))
                    interval_secs = int(settings.get("twap_interval_secs", 60))
                    slice_qty = trade.quantity / n_slices
                    logger.info("TWAP execution for %s: %.4f shares in %d slices", trade.symbol, trade.quantity, n_slices)
                    # Persist TWAP plan before any IBKR call — enables crash recovery
                    twap_row = TwapExecution(
                        symbol=trade.symbol,
                        slice_qty=slice_qty,
                        n_slices=n_slices,
                        slices_submitted=0,
                        interval_secs=interval_secs,
                        stop_price=stop_price,
                        tp_price=tp_price,
                        trailing_amount=trailing_amount,
                        exchange=exchange,
                        status="RUNNING",
                    )
                    db.add(twap_row)
                    db.commit()
                    db.refresh(twap_row)
                    order_id = await self.worker.place_twap_bracket_order(
                        trade, stop_price, tp_price, exchange, trailing_amount, n_slices, interval_secs
                    )
                    twap_row.slices_submitted = 1
                    db.commit()
                    asyncio.create_task(_run_twap_slices(self.worker, twap_row.id))
                else:
                    order_id = await self.worker.place_bracket_order(trade, stop_price, tp_price, exchange, trailing_amount)
            else:
                # SELL: Settlement Guard check (T+2)
                if not self._is_possession_confirmed(db, trade.symbol):
                    machine.transition_to(TradeState.IBKR_ERROR)
                    trade.state = machine.state
                    self._persist_trade_history(db, trade)
                    return trade

                if settings.get("dry_run", False):
                    logger.info(f"[DRY RUN] SELL {trade.quantity} {trade.symbol} @ ~{price:.2f}")
                    machine.transition_to(TradeState.DRY_RUN)
                    trade.state = machine.state
                    self._persist_trade_history(db, trade)
                    return trade

                # Pre-commit PRE_ORDER to DB before IBKR call — crash recovery guard
                self._persist_trade_history(db, trade)

                order_id = await self.worker.place_order(trade, exchange)

            # 5. Submitted
            machine.transition_to(TradeState.SUBMITTED)
            trade.state = machine.state
            TRADES_EXECUTED.labels(side=trade_req.side.upper()).inc()

            trade.ibkr_order_id = order_id
            trade.updated_at = datetime.now(timezone.utc)
            audit_entry.ibkr_order_id = order_id
            db.commit()

            self._persist_trade_history(db, trade)

            # Telegram push: order submitted to broker
            try:
                from ibkr_core.features.alerts.dispatcher import alert
                emoji = "🟢" if trade.side == "BUY" else "🔴"
                body = f"{emoji} {trade.symbol} {trade.side} {trade.quantity:.4f} @ ~${price:.2f} · Order #{order_id}"
                channels = settings.get("alert_channels", [])
                asyncio.create_task(alert("Order Submitted", body, channels))
            except Exception:
                logger.exception("Submit alert dispatch failed")

            return trade

        except Exception as e:
            logger.exception(f"execute_trade failed for {trade_req.symbol}: {e}")
            if machine.state not in {TradeState.IDLE, TradeState.SETTLED}:
                machine.transition_to(TradeState.IBKR_ERROR)
            trade.state = machine.state
            self._persist_trade_history(db, trade)
            return trade
        finally:
            db.close()

    def _persist_trade_history(self, db, trade_schema):
        """Upsert trade state to DB. If trade_schema.id is set, updates existing row."""
        if trade_schema.id:
            row = db.query(TradeHistory).filter(TradeHistory.id == trade_schema.id).first()
            if row:
                row.state = trade_schema.state
                row.quantity = trade_schema.quantity
                row.ibkr_order_id = trade_schema.ibkr_order_id
                row.fill_price = getattr(trade_schema, "fill_price", None)
                row.signal_price = getattr(trade_schema, "signal_price", None)
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
                return
        trade_db = TradeHistory(
            symbol=trade_schema.symbol,
            quantity=trade_schema.quantity,
            side=trade_schema.side,
            order_type=trade_schema.order_type,
            state=trade_schema.state,
            ibkr_order_id=trade_schema.ibkr_order_id,
            signal_price=getattr(trade_schema, "signal_price", None),
            account_id=self.account_id,
        )
        db.add(trade_db)
        db.commit()
        db.refresh(trade_db)
        trade_schema.id = trade_db.id

    def _is_possession_confirmed(self, db, symbol: str) -> bool:
        """
        Verifies legal possession (Qabd) before allowing a sale.
        Primary: FILLED BUY record in DB at least 2 days old.
        Fallback: if no FILLED record exists (fill event missed due to reconnect),
          check that the position actually exists in IBKR AND the oldest SUBMITTED
          BUY is at least 2 days old — meaning we genuinely hold the asset.
        Ref: COMPLIANCE.md Section 4.
        """
        settled_states = (
            TradeState.FILLED,
            TradeState.PENDING_SETTLEMENT,
            TradeState.SETTLED,
        )
        last_buy = (
            db.query(TradeHistory)
            .filter(
                TradeHistory.symbol == symbol,
                TradeHistory.state.in_(settled_states),
                TradeHistory.side == "BUY",
            )
            .order_by(TradeHistory.updated_at.desc())
            .first()
        )

        if last_buy:
            last_buy_time = last_buy.updated_at
            if last_buy_time.tzinfo is None:
                last_buy_time = last_buy_time.replace(tzinfo=timezone.utc)
            days_held = (datetime.now(timezone.utc) - last_buy_time).days
            return days_held >= 2

        # Fallback: fill event may have been missed after reconnect.
        # Confirm via live IBKR position + age of the SUBMITTED record.
        try:
            positions = self.worker.get_positions()
            held = any(p["symbol"] == symbol and float(p.get("quantity", 0)) > 0 for p in positions)
            if not held:
                return False

            oldest_submitted = (
                db.query(TradeHistory)
                .filter(
                    TradeHistory.symbol == symbol,
                    TradeHistory.side == "BUY",
                    TradeHistory.state == TradeState.SUBMITTED,
                )
                .order_by(TradeHistory.updated_at.asc())
                .first()
            )
            if not oldest_submitted:
                return False

            buy_time = oldest_submitted.updated_at
            if buy_time.tzinfo is None:
                buy_time = buy_time.replace(tzinfo=timezone.utc)
            days_held = (datetime.now(timezone.utc) - buy_time).days
            if days_held >= 2:
                # Heal the DB record so future checks use the primary path
                oldest_submitted.state = TradeState.FILLED
                oldest_submitted.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(
                    "_is_possession_confirmed: healed %s SUBMITTED → FILLED (position confirmed in IBKR)",
                    symbol,
                )
                return True
        except Exception as e:
            logger.warning("Possession fallback check failed for %s: %s", symbol, e)

        return False


async def _run_twap_slices(worker, twap_id: int, start_idx: int = 1) -> None:
    """
    Execute remaining TWAP slices with DB persistence after each.
    start_idx: first slice index to submit (0-based). Default 1 = slice 0 already placed.
    Called from Trader.execute_trade and resume_pending_twap on startup.
    """
    db = SessionLocal()
    try:
        twap = db.query(TwapExecution).filter(TwapExecution.id == twap_id).first()
        if not twap:
            logger.error("TWAP recovery: row %d not found", twap_id)
            return
        symbol = twap.symbol
        n_slices = twap.n_slices
        interval_secs = twap.interval_secs
        slice_qty = twap.slice_qty
        stop_price = twap.stop_price
        tp_price = twap.tp_price
        trailing_amount = twap.trailing_amount
        exchange = twap.exchange
    finally:
        db.close()

    for i in range(start_idx, n_slices):
        await asyncio.sleep(interval_secs)
        db = SessionLocal()
        try:
            twap = db.query(TwapExecution).filter(TwapExecution.id == twap_id).first()
            if not twap or twap.status != "RUNNING":
                logger.info("TWAP %s aborted at slice %d (status=%s)", symbol, i + 1, getattr(twap, "status", "gone"))
                return
            t = TradeCreate(symbol=symbol, quantity=slice_qty, side="BUY")
            oid = await worker.place_bracket_order(t, stop_price, tp_price, exchange, trailing_amount)
            logger.info("TWAP %s slice %d/%d qty=%.4f order=%d", symbol, i + 1, n_slices, slice_qty, oid)
            twap.slices_submitted += 1
            if twap.slices_submitted >= n_slices:
                twap.status = "COMPLETED"
            db.commit()
        except Exception as e:
            logger.error("TWAP slice %d/%d failed for %s: %s", i + 1, n_slices, symbol, e)
            try:
                twap = db.query(TwapExecution).filter(TwapExecution.id == twap_id).first()
                if twap:
                    twap.status = "FAILED"
                    db.commit()
            except Exception:
                pass
            return
        finally:
            db.close()


async def resume_pending_twap(worker) -> None:
    """Call on startup after IBKR connects. Resumes any TWAP executions interrupted by a crash."""
    db = SessionLocal()
    try:
        pending = db.query(TwapExecution).filter(TwapExecution.status == "RUNNING").all()
        for twap in pending:
            remaining = twap.n_slices - twap.slices_submitted
            if remaining <= 0:
                twap.status = "COMPLETED"
                db.commit()
                continue
            logger.info("Resuming TWAP %s: %d/%d slices remaining", twap.symbol, remaining, twap.n_slices)
            asyncio.create_task(_run_twap_slices(worker, twap.id, start_idx=twap.slices_submitted))
    finally:
        db.close()
