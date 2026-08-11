import os
import math
import logging
import asyncio
from typing import Any, List, Dict, Optional
from datetime import datetime, UTC
from dotenv import load_dotenv
from ibkr_core.core.market_hours import get_exchange_config
from ibkr_core.features.trading.order_policy import (
    BRACKET_ENTRY_PREMIUM_PCT,
    COARSE_NONUS_TICK,
    DataState,
    OrderPolicy,
    marketable_limit,
    quantize_to_increment,
    select_tick_increment,
    subscription_for_port,
)

load_dotenv()

logger = logging.getLogger(__name__)

# ib_insync market-data coroutines can hang FOREVER on a half-open socket: IBKR
# raises nothing, the awaitable simply never completes. Because these awaits are
# taken while holding self._limiter, one stuck call also starves every other
# market-data request. On 2026-08-10 that pinned execute_trade for 14h38m — the
# loop dispatched exactly one BUY all day and every later candidate was skipped
# as "outside its trading window". Every IBKR market-data await is now bounded.
_IBKR_CALL_TIMEOUT = float(os.getenv("IBKR_CALL_TIMEOUT_SEC", "20"))

# Canonical (yfinance-suffixed) → IBKR bare symbol. Full suffix table +
# hyphen class-share handling live in core.symbols (the old local set covered
# only 12 suffixes, so most foreign contracts failed qualification).
from ibkr_core.core.market_hours import resolve_exchange as _resolve_exchange
from ibkr_core.core.symbols import from_ibkr, to_ibkr as _ibkr_symbol, to_usd, uses_symbol_field


def _ibkr_amount_to_usd(amount, currency: str):
    """Convert an IBKR portfolio amount to USD via the FX leg ONLY.

    IBKR's portfolio/position fields — averageCost, marketPrice, marketValue,
    unrealizedPNL — are ALL reported in the contract's LOCAL currency, in MAJOR
    units, consistently per position (verified live 2026-07-17 on the paper
    gateway: BHP.L averageCost=29.61 GBP — pounds, NOT pence; ALFA.ST
    marketValue=32973.92 SEK = 59 * 558.88). This is unlike yfinance, which
    quotes LSE in pence — so `symbols.to_usd` (which applies a minor-unit
    divisor keyed on exchange) is CORRECT for the yfinance feed but WRONG for
    IBKR data. This helper takes the contract currency directly and applies no
    divisor. Returns None when a required non-USD FX rate is missing — callers
    MUST fail closed (never size or value a position on a blind rate).
    """
    if amount is None:
        return None
    if not currency or currency == "USD":
        return amount
    from ibkr_core.features.compliance.data_fetcher import _get_fx_rate
    fx = _get_fx_rate(currency, "USD")
    if not fx:
        return None
    return amount * fx


class IBKRWorker:
    def __init__(self, host=None, port=None, client_id=1, ibkr_account_id=None, readonly=False,
                 account_id=None):
        # TWS paper=7497, live=7496 | IB Gateway paper=4002, live=4001
        host = host or os.getenv("IBKR_HOST", "127.0.0.1")
        port = port or int(os.getenv("IBKR_PORT", "7497"))
        from ib_insync import IB
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ibkr_account_id = ibkr_account_id
        self.account_id = account_id  # DB Account.id — used to load per-account settings
        self.readonly = readonly
        # Fix #11: track per-symbol pending-tickers callbacks to prevent leaks
        self._ticker_callbacks: Dict[str, Any] = {}
        # Fix #25: guard against concurrent reconnection attempts
        self._reconnecting: bool = False
        # Fix: Rate limiting to prevent IBKR pacing violations
        self._limiter = asyncio.Semaphore(5)  # Max 5 concurrent market data requests
        self._last_request_time = 0.0
        self._fill_callback = None  # optional async (symbol, action, qty, price) hook
        self._competing_session = False  # set when IBKR error 10197 (competing live session) seen
        # Actual IBKR market-data type after connect (1=realtime, 3=delayed); None
        # until connected. Lets /api/system/trading report data_mode authoritatively
        # instead of inferring from the port.
        self._market_data_type: Optional[int] = None

    async def _wait_for_pacing(self):
        """Simple delay to ensure we don't spam requests too fast."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < 0.1:  # 100ms between requests
            await asyncio.sleep(0.1 - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def connect(self, timeout=30):
        """
        Establishes a connection to IBKR TWS or Gateway.
        Ref: ARCHITECTURE.md Track C
        """
        try:
            if self.ib.isConnected():
                try:
                    self.ib.disconnect()
                except Exception:
                    pass

            if self.readonly:
                await self._connect_readonly(timeout)
            else:
                await asyncio.wait_for(
                    self.ib.connectAsync(self.host, self.port, clientId=self.client_id),
                    timeout=timeout
                )

            logger.info(f"Connected to IBKR at {self.host}:{self.port}"
                        f"{' (readonly)' if self.readonly else ''}")
            self._competing_session = False  # clean connect — clear competing-session latch
            self.ib.orderStatusEvent -= self._on_order_status
            self.ib.execDetailsEvent -= self._on_exec_details
            self.ib.disconnectedEvent -= self._on_disconnect
            self.ib.errorEvent -= self._on_error
            self.ib.orderStatusEvent += self._on_order_status
            self.ib.execDetailsEvent += self._on_exec_details
            self.ib.disconnectedEvent += self._on_disconnect
            self.ib.errorEvent += self._on_error
            if subscription_for_port(self.port) is DataState.DELAYED:
                self.ib.reqMarketDataType(3)
                self._market_data_type = 3  # delayed
            else:
                self._market_data_type = 1  # realtime (IBKR default)

            return True
        except asyncio.CancelledError:
            logger.error("Failed to connect to IBKR: connection cancelled by Gateway")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            return False

    async def _connect_readonly(self, timeout=30):
        """
        Connect for read-only accounts. The standard connectAsync fails because
        reqExecutionsAsync times out on gateways with Read-Only API. We replicate
        the connect sequence but skip that final step.
        """
        self.ib.wrapper.clientId = self.client_id
        await self.ib.client.connectAsync(self.host, self.port, self.client_id, timeout)

        accounts = self.ib.client.getAccounts()
        account = accounts[0] if len(accounts) == 1 else ""

        reqs = {}
        reqs['positions'] = self.ib.reqPositionsAsync()
        if account:
            reqs['account updates'] = self.ib.reqAccountUpdatesAsync(account)
        if len(accounts) <= self.ib.MaxSyncedSubAccounts:
            for acc in accounts:
                reqs[f'account updates for {acc}'] = \
                    self.ib.reqAccountUpdatesMultiAsync(acc)

        tasks = [asyncio.wait_for(req, timeout) for req in reqs.values()]
        resps = await asyncio.gather(*tasks, return_exceptions=True)
        for name, resp in zip(reqs, resps):
            if isinstance(resp, (asyncio.TimeoutError, Exception)):
                logger.debug(f"Readonly connect: {name} timed out (expected)")

        if not self.ib.client.isReady():
            raise ConnectionError("Socket broken during readonly connect")

        self.ib._logger.info("Synchronization complete (readonly)")
        self.ib.connectedEvent.emit()

    def _on_error(self, reqId, errorCode: int, errorString: str, contract) -> None:
        """
        IBKR error filter. Suppresses transient reconnect noise (322, 1100, 1102, 10197).
        Real errors propagate via order/exec event handlers.
        """
        # 322: Max account summary requests — caused by stale subscription on reconnect.
        # 1100/1102: Connection lost/restored — reconnect logic handles.
        # 10197: Competing live session (another client holding market data).
        # 10141: Paper trading disclaimer — requires manual click in Gateway.
        # 10349: Order TIF default override — informational.
        # 10197 latches a flag so /api/gateway/auth can surface the real cause;
        # cleared on a clean (re)connect.
        if errorCode == 10197:
            self._competing_session = True
        SUPPRESSED = {322, 1100, 1102, 10141, 10197, 10349}
        if errorCode in SUPPRESSED:
            logger.debug("IBKR %d (suppressed): %s", errorCode, errorString)
            return
        logger.warning("IBKR %d (reqId=%s): %s", errorCode, reqId, errorString)

    def disconnect(self):
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Fix #9: fill event callbacks
    # ------------------------------------------------------------------

    def _on_order_status(self, trade) -> None:
        """
        Called by ib_insync whenever an order status changes.
        DB write offloaded to thread pool so the event loop is not blocked.
        """
        from ibkr_core.core.state import TradeState

        ibkr_status = trade.orderStatus.status
        if ibkr_status == "Filled":
            new_state = TradeState.FILLED
        elif ibkr_status in ("Cancelled", "Inactive"):
            new_state = TradeState.IBKR_ERROR
        else:
            return

        order_id = trade.order.orderId
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(self._db_update_order_status, order_id, new_state))
            if new_state == TradeState.FILLED and self._fill_callback is not None:
                symbol = trade.contract.symbol
                action = trade.order.action
                qty = trade.orderStatus.filled
                price = trade.orderStatus.avgFillPrice
                loop.create_task(self._fill_callback(symbol, action, qty, price))
            elif new_state == TradeState.IBKR_ERROR:
                loop.create_task(self._send_cancel_alert(trade, ibkr_status))
        except RuntimeError:
            self._db_update_order_status(order_id, new_state)

    async def _send_cancel_alert(self, trade, status: str) -> None:
        """Push notification when broker cancels/rejects an order."""
        from ibkr_core.features.alerts.dispatcher import alert
        from ibkr_core.features.settings.service import load_settings

        try:
            symbol = trade.contract.symbol
            side = trade.order.action
            qty = trade.order.totalQuantity
            order_id = trade.order.orderId
            # Prefer the broker's actual error text (last log entry) so reasons like
            # fractional-not-permitted surface, instead of a bare "Cancelled".
            reason = getattr(trade.orderStatus, "whyHeld", "") or status
            try:
                err_logs = [e for e in getattr(trade, "log", []) if getattr(e, "message", "")]
                if err_logs:
                    last = err_logs[-1]
                    code = getattr(last, "errorCode", 0)
                    reason = f"{last.message}" + (f" (code {code})" if code else "")
            except Exception:
                pass
            body = f"❌ {symbol} {side} {qty} cancelled — {reason} · Order #{order_id}"
            settings = load_settings(self.account_id)
            if not settings.get("notify_trade_fills", True):
                return
            channels = settings.get("alert_channels", [])
            await alert("Trade Cancelled", body, channels)
        except Exception:
            logger.exception("_send_cancel_alert failed")

    @staticmethod
    def _db_update_order_status(order_id: int, new_state) -> None:
        from ibkr_core.core.database import SessionLocal
        from ibkr_core.core.models import TradeHistory

        db = SessionLocal()
        try:
            row = db.query(TradeHistory).filter(
                TradeHistory.ibkr_order_id == order_id
            ).first()
            if row:
                row.state = new_state
                row.updated_at = datetime.now(UTC)
                db.commit()
                logger.info(f"Order {order_id} → state={new_state.value}")
        finally:
            db.close()

    def _on_exec_details(self, trade, fill) -> None:
        """
        Called by ib_insync whenever an execution detail arrives.
        DB write offloaded to thread pool so the event loop is not blocked.
        Telegram alert is sent immediately via create_task so the event loop
        is not blocked.
        """
        order_id = trade.order.orderId
        fill_price = fill.execution.price
        commission = fill.commissionReport.commission if fill.commissionReport else None
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(self._db_update_fill_details, order_id, fill_price, commission))
            loop.create_task(self._send_fill_alert(trade, fill))
        except RuntimeError:
            self._db_update_fill_details(order_id, fill_price, commission)

    async def _send_fill_alert(self, trade, fill) -> None:
        """Fire a Telegram push notification when a fill is confirmed."""
        from ibkr_core.features.alerts.dispatcher import alert
        from ibkr_core.features.settings.service import load_settings

        try:
            symbol = trade.contract.symbol
            side = trade.order.action          # "BUY" or "SELL"
            qty = fill.execution.cumQty        # cumulative filled quantity
            price = fill.execution.price
            order_id = trade.order.orderId

            body = f"{symbol} {side} {qty} @ ${price:.2f} · Order #{order_id}"
            settings = load_settings(self.account_id)
            if not settings.get("notify_trade_fills", True):
                return
            channels = settings.get("alert_channels", [])
            await alert("Trade Filled", body, channels)
        except Exception:
            logger.exception("_send_fill_alert failed — fill notification not sent")

    @staticmethod
    def _db_update_fill_details(order_id: int, fill_price: float, commission) -> None:
        from ibkr_core.core.database import SessionLocal
        from ibkr_core.core.models import TradeHistory

        db = SessionLocal()
        try:
            row = db.query(TradeHistory).filter(
                TradeHistory.ibkr_order_id == order_id
            ).first()
            if row:
                row.fill_price = fill_price
                row.commission = commission
                row.updated_at = datetime.now(UTC)
                db.commit()
                logger.info(f"Order {order_id} fill_price={fill_price} commission={commission}")
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Fix #25: reconnection logic with exponential backoff
    # ------------------------------------------------------------------

    def _on_disconnect(self) -> None:
        """Sync handler wired to ib.disconnectedEvent; schedules async reconnect."""
        from ibkr_core.core.monitoring import IBKR_CONNECTED
        IBKR_CONNECTED.set(0)
        logger.warning("IBKR connection lost — scheduling reconnect")
        asyncio.ensure_future(self._reconnect())

    async def _reconnect(self) -> None:
        """
        Reconnects with escalating backoff to survive IB Gateway daily restarts.

        IB Gateway resets daily (~23:45 ET) and takes up to 2 minutes to come back.
        Strategy: short retries first (transient drop), then 60s intervals for up to
        10 minutes total to cover the daily restart window.
        Sends an alert if all attempts fail.
        """
        if self._reconnecting:
            return
        self._reconnecting = True
        # 5s, 15s, 30s, then 60s x7 = ~8 min total window
        delays = [5, 15, 30, 60, 60, 60, 60, 60, 60, 60]
        try:
            for attempt, delay in enumerate(delays, start=1):
                logger.info("Reconnect attempt %d/%d in %ds …", attempt, len(delays), delay)
                await asyncio.sleep(delay)
                success = await self.connect()
                if success:
                    from ibkr_core.core.monitoring import IBKR_CONNECTED
                    IBKR_CONNECTED.set(1)
                    logger.info("Reconnected to IBKR after %d attempt(s) — reconciling", attempt)
                    from ibkr_core.features.trading.reconciliation import reconcile_with_ibkr
                    await reconcile_with_ibkr(self)
                    from ibkr_core.features.settings.service import load_settings
                    from ibkr_core.features.alerts.dispatcher import alert
                    s = load_settings(self.account_id)
                    await alert(
                        "IBKR Reconnected",
                        f"Connection restored after {attempt} attempt(s).",
                        channels=s.get("alert_channels", []),
                    )
                    return
            logger.error("All reconnect attempts failed — manual intervention required")
            from ibkr_core.features.settings.service import load_settings
            from ibkr_core.features.alerts.dispatcher import alert
            s = load_settings(self.account_id)
            await alert(
                "CRITICAL: IBKR Connection Lost",
                "Failed to reconnect after 10 attempts (~8 minutes). Manual restart required.",
                channels=s.get("alert_channels", []),
            )
        finally:
            self._reconnecting = False

    # ------------------------------------------------------------------

    def _match_account(self, account: str) -> bool:
        if not self.ibkr_account_id:
            return True
        return account == self.ibkr_account_id

    def get_available_funds(self) -> float:
        """
        IBKR AvailableFunds — NetLiquidation minus the initial margin requirement.

        This is BUYING POWER, not cash: on a margin-enabled account it exceeds
        the settled cash balance (measured on paper DUN514226 2026-08-08:
        AvailableFunds 1,068,625 vs TotalCashValue 998,592). Anything that must
        not borrow has to bound this by `get_total_cash()`.
        Ref: COMPLIANCE.md - Zero Leverage/Margin.
        """
        for v in self.ib.accountValues():
            if v.tag == 'AvailableFunds' and self._match_account(v.account):
                val = float(v.value)
                return 0.0 if math.isnan(val) else val
        return 0.0

    def get_total_cash(self) -> float:
        """
        IBKR TotalCashValue — settled cash actually held, in account-base currency.

        Unlike AvailableFunds this carries no margin component, so it is the
        honest number for both portfolio valuation and any no-leverage budget.
        Returns 0.0 when the tag is absent (readonly accounts report no values),
        which callers must treat as "unknown", never as "no cash".
        """
        for v in self.ib.accountValues():
            if v.tag == 'TotalCashValue' and self._match_account(v.account):
                val = float(v.value)
                return 0.0 if math.isnan(val) else val
        return 0.0

    def get_net_liquidation(self) -> float:
        for v in self.ib.accountValues():
            if v.tag == 'NetLiquidation' and self._match_account(v.account):
                val = float(v.value)
                return 0.0 if math.isnan(val) else val
        # Readonly accounts: accountValues empty, approximate from positions
        if self.readonly:
            positions = self.get_positions()
            return sum(float(p.get("market_value", 0)) for p in positions)
        return 0.0

    def get_open_orders(self) -> list:
        """Returns all open (working) orders from IBKR as plain dicts."""
        try:
            return [
                {
                    "order_id": t.order.orderId,
                    "symbol": t.contract.symbol,
                    "action": t.order.action,
                    "quantity": float(t.order.totalQuantity),
                    "order_type": t.order.orderType,
                    "status": t.orderStatus.status,
                    "limit_price": getattr(t.order, "lmtPrice", None),
                    "stop_price": getattr(t.order, "auxPrice", None),
                }
                for t in self.ib.openTrades()
            ]
        except Exception as e:
            logger.error("get_open_orders failed: %s", e)
            return []

    def cancel_all_orders(self) -> None:
        """Broadcasts global cancel to IBKR — cancels every open order in this account."""
        logger.warning("Sending reqGlobalCancel to IBKR")
        self.ib.reqGlobalCancel()

    def cancel_order(self, order_id: int) -> bool:
        """Cancel a single order by IBKR order ID. Returns True if cancel was sent."""
        try:
            trades = {t.order.orderId: t for t in self.ib.openTrades()}
            if order_id not in trades:
                logger.warning("cancel_order: order %d not found in open trades", order_id)
                return False
            self.ib.cancelOrder(trades[order_id].order)
            logger.info("Cancel sent for order %d", order_id)
            return True
        except Exception as e:
            logger.error("cancel_order %d failed: %s", order_id, e)
            return False

    def get_account_summary(self) -> dict:
        """Returns account metadata for the /ibkr/health endpoint."""
        values = {v.tag: v.value for v in self.ib.accountValues()}
        account_id = values.get("AccountCode", "") or values.get("AccountID", "")
        available_funds = float(values.get("AvailableFunds", 0) or 0)
        buying_power = float(values.get("BuyingPower", 0) or 0)
        # Cash account: BuyingPower ≈ AvailableFunds
        # Margin account: BuyingPower is 2-4× AvailableFunds
        account_type = "CASH"
        warnings = []
        if available_funds > 0 and buying_power > available_funds * 1.1:
            account_type = "MARGIN"
            warnings.append("MARGIN account detected — Riba risk, verify cash-only settings")
        return {"account_id": account_id, "account_type": account_type, "warnings": warnings}

    def _stock_contract(self, symbol: str, exchange: str = "NMS"):
        """Build a qualifiable IBKR contract for a canonical (yfinance) symbol.

        US listings use Stock(local, SMART, ccy) — the proven path, where the
        local ticker equals IBKR's `symbol`. Foreign listings instead put the
        exchange-local ticker in the `localSymbol` field and route SMART with a
        `primaryExchange` disambiguator: IBKR's `symbol` field diverges from the
        local ticker for class shares (VOLV B) and cross-listed names, so using
        `symbol` silently fails to qualify. This localSymbol builder qualifies EU
        class shares, resolves ambiguous cross-listings to the intended company
        (SAN→Sanofi not Banco Santander, AMP→Amplifon not Amper), and handles
        trailing-dot LSE EPICs (RR.). Verified 77/82 EU names / 0 regressions on
        the live paper gateway (2026-07-13). An unqualifiable contract still fails
        closed at the qualify check in place_order/place_bracket_order.
        """
        from ib_insync import Stock, Contract
        _, _, ibkr_exchange, currency = get_exchange_config(_resolve_exchange(symbol, exchange))
        local = _ibkr_symbol(symbol)
        if ibkr_exchange == "SMART":
            return Stock(local, "SMART", currency)
        if uses_symbol_field(ibkr_exchange):
            # Numeric-ticker Asia venues (Japan/HK/…): the plain code goes in the
            # `symbol` field; a bare localSymbol fails Error 200 (IBKR's localSymbol
            # is suffixed "7203.T"). to_ibkr already stripped HK leading zeros.
            return Stock(local, "SMART", currency, primaryExchange=ibkr_exchange)
        return Contract(secType="STK", localSymbol=local, exchange="SMART",
                        primaryExchange=ibkr_exchange, currency=currency)

    @staticmethod
    def _pick_market_rule_id(rule_ids: str, valid_exchanges: str, contract) -> Optional[int]:
        """Pick the market-rule id for the exchange this contract routes to.

        ContractDetails.marketRuleIds is a comma-separated list parallel to
        validExchanges. Prefer the contract's primaryExchange (foreign SMART
        contracts carry it), else its exchange, else the first listed rule.
        """
        ids = [r.strip() for r in (rule_ids or "").split(",") if r.strip()]
        if not ids:
            return None
        exchanges = [e.strip() for e in (valid_exchanges or "").split(",")]
        target = getattr(contract, "primaryExchange", "") or getattr(contract, "exchange", "")
        candidates = []
        if target and target in exchanges:
            idx = exchanges.index(target)
            if idx < len(ids):
                candidates.append(ids[idx])
        candidates.append(ids[0])
        for cand in candidates:
            try:
                return int(cand)
            except (TypeError, ValueError):
                continue
        return None

    async def _market_rule_increments(self, contract) -> list:
        """Resolve a contract's (low_edge, increment) tick bands via IBKR.

        Returns [] when contract details or the market rule are unavailable so
        the caller can fail SAFE to a coarse tick rather than an invalid price.
        """
        sym = getattr(contract, "localSymbol", "") or getattr(contract, "symbol", "")
        try:
            details = await self.ib.reqContractDetailsAsync(contract)
            if not details:
                return []
            cd = details[0]
            rule_id = self._pick_market_rule_id(
                getattr(cd, "marketRuleIds", "") or "",
                getattr(cd, "validExchanges", "") or "",
                contract,
            )
            if rule_id is None:
                return []
            rule = await self.ib.reqMarketRuleAsync(rule_id)
            if not rule:
                return []
            return [(float(pi.lowEdge), float(pi.increment)) for pi in rule]
        except Exception as e:
            logger.warning("market-rule lookup failed for %s: %s", sym, e)
            return []

    async def _quantize_to_tick(self, contract, price: float, side: str) -> float:
        """Snap a limit price to a VALID exchange tick, marketable direction.

        IBKR rejects (error 110) any limit whose price is not a multiple of the
        minimum price variation for its price BAND. MiFID II ticks are per
        price-band AND per venue, so a fixed 2dp/minTick is wrong for
        SIX/Euronext/XETRA large-tick names: the whole bracket (entry limit +
        protective stop/TP) is cancelled, leaving an EU position unentered OR a
        stop-loss SELL repeatedly rejected (position left unprotected).

        Resolve the contract's market rule -> price-increment bands, pick the
        band containing ``price``, and quantize: BUY rounds UP, SELL rounds DOWN
        (keeps the order marketable while landing on a valid tick). Falls back to
        a coarse, definitely-valid increment (never a finer one) when the rule is
        unavailable — US SMART keeps the existing 2dp; other venues snap to
        COARSE_NONUS_TICK rather than submit a possibly-invalid price.
        """
        if not price or price <= 0:
            return price
        increments = await self._market_rule_increments(contract)
        if increments:
            tick = select_tick_increment(price, increments)
            if tick and tick > 0:
                return quantize_to_increment(price, side, tick)
        # Market rule unavailable — fail SAFE to a coarse tick, never a finer one.
        currency = getattr(contract, "currency", "") or ""
        if currency == "USD":
            return round(price, 2)  # US equities tick at 0.01 above $1 — unchanged
        sym = getattr(contract, "localSymbol", "") or getattr(contract, "symbol", "")
        logger.warning(
            "quantize: no market rule for %s — coarse %.2f tick fallback", sym, COARSE_NONUS_TICK
        )
        return quantize_to_increment(price, side, COARSE_NONUS_TICK)

    async def _bounded(self, coro, what: str, symbol: str):
        """Await an IBKR coroutine with a hard timeout. Returns None if it timed out.

        None is unambiguous here: these calls return lists on success, so a None
        means "the socket is not answering", which callers treat as a dead path
        rather than as an empty result worth retrying.
        """
        try:
            return await asyncio.wait_for(coro, timeout=_IBKR_CALL_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(
                "%s(%s): no response after %.0fs — abandoning call",
                what, symbol, _IBKR_CALL_TIMEOUT,
            )
            return None

    async def get_last_price(self, symbol: str, exchange: str = "NMS") -> float:
        async with self._limiter:
            await self._wait_for_pacing()
            contract = self._stock_contract(symbol, exchange)
            qualified = await self._bounded(
                self.ib.qualifyContractsAsync(contract), "qualifyContractsAsync", symbol
            )
            if qualified is not None:
                for attempt in range(3):
                    tickers = await self._bounded(
                        self.ib.reqTickersAsync(contract), "reqTickersAsync", symbol
                    )
                    if tickers is None:
                        break  # socket unhealthy — retrying just burns more timeouts
                    if not tickers:
                        await asyncio.sleep(1)
                        continue
                    ticker = tickers[0]
                    # Prefer last, then close, then marketPrice() (bid/ask mid for delayed data)
                    candidates = [ticker.last, ticker.close, ticker.marketPrice()]
                    for val in candidates:
                        if val is not None and not math.isnan(val) and val > 0:
                            return val
                    await asyncio.sleep(1)
            # Fallback: yfinance when IBKR market data unavailable. Runs in a thread
            # because yf.history() is blocking — awaiting it inline would stall the
            # whole event loop, not just this call.
            try:
                import yfinance as yf

                def _yf_close() -> float:
                    hist = yf.Ticker(symbol).history(period="1d")
                    return float(hist["Close"].iloc[-1]) if not hist.empty else 0.0

                val = await asyncio.wait_for(
                    asyncio.to_thread(_yf_close), timeout=_IBKR_CALL_TIMEOUT
                )
                if val > 0:
                    logger.info("get_last_price(%s): yfinance fallback → %.2f", symbol, val)
                    return val
            except Exception:
                pass
            return 0.0

    async def get_market_data(self, symbol: str, exchange: str = "NMS") -> Dict[str, float]:
        """
        Retrieves bid, ask, and last price for a symbol.
        Used for slippage calculation.
        """
        async with self._limiter:
            await self._wait_for_pacing()
            contract = self._stock_contract(symbol, exchange)
            _empty = {"bid": 0.0, "ask": 0.0, "last": 0.0, "volume": 0.0}
            if await self._bounded(
                self.ib.qualifyContractsAsync(contract), "qualifyContractsAsync", symbol
            ) is None:
                return _empty
            tickers = await self._bounded(
                self.ib.reqTickersAsync(contract), "reqTickersAsync", symbol
            )
            if not tickers:
                return _empty
            t = tickers[0]
            last = t.close if math.isnan(t.last) else t.last
            return {
                "bid": t.bid if not math.isnan(t.bid) else last,
                "ask": t.ask if not math.isnan(t.ask) else last,
                "last": last,
                "volume": t.volume if not math.isnan(t.volume) else 0.0
            }

    async def get_avg_volume_20d(self, symbol: str, exchange: str = "NMS") -> float:
        """
        Retrieves the 20-day average trading volume.
        Used for liquidity awareness.
        """
        async with self._limiter:
            await self._wait_for_pacing()
            contract = self._stock_contract(symbol, exchange)
            await self.ib.qualifyContractsAsync(contract)
            # Fetch 30 days of daily bars to be safe for 20-day avg
            bars = await self.ib.reqHistoricalDataAsync(
                contract, endDateTime='', durationStr='30 D',
                barSizeSetting='1 day', whatToShow='TRADES', useRTH=True
            )
            if not bars:
                return 0.0
            volumes = [b.volume for b in bars][-20:]
            return sum(volumes) / len(volumes) if volumes else 0.0

    async def subscribe_ticker(self, symbol: str, callback):
        """
        Subscribes to real-time ticker updates for a symbol.
        Calls the callback function whenever a new price update arrives.
        Ref: ARCHITECTURE.md - Communication: WebSockets for real-time data streaming.
        """
        async with self._limiter:
            await self._wait_for_pacing()
            contract = self._stock_contract(symbol)
            qualified = await self.ib.qualifyContractsAsync(contract)
            if not qualified:
                logger.debug("subscribe_ticker: no contract found for %s — skipping", symbol)
                return None
            ticker = self.ib.reqMktData(contract, '', False, False)

            # Fix #11: remove stale callback for this symbol before registering a new one
            if symbol in self._ticker_callbacks:
                self.ib.pendingTickersEvent -= self._ticker_callbacks[symbol]

            def on_pending_tickers(tickers):
                for t in tickers:
                    if t.contract.symbol == _ibkr_symbol(symbol):
                        # Fix #13: replace informal NaN idiom with math.isnan
                        last = t.close if math.isnan(t.last) else t.last
                        callback({
                            "symbol": symbol,
                            "last": last,
                            "bid": t.bid,
                            "ask": t.ask,
                            "timestamp": datetime.now().isoformat()
                        })

            self._ticker_callbacks[symbol] = on_pending_tickers
            self.ib.pendingTickersEvent += on_pending_tickers
            return ticker

    def unsubscribe_ticker(self, symbol: str) -> None:
        if symbol in self._ticker_callbacks:
            self.ib.pendingTickersEvent -= self._ticker_callbacks.pop(symbol)

    _positions_cache: Dict[str, tuple] = {}
    _POSITIONS_CACHE_TTL = 30

    def get_positions(self) -> List[Dict]:
        """
        Retrieves current account positions with live market value and unrealized P&L.
        Falls back to yfinance prices when IBKR portfolio data is unavailable (readonly).
        Results cached 30s to avoid repeated yfinance calls from concurrent endpoints.
        """
        import time as _time
        cache_key = self.ibkr_account_id or "_default"
        cached = IBKRWorker._positions_cache.get(cache_key)
        if cached:
            result, ts = cached
            if _time.time() - ts < self._POSITIONS_CACHE_TTL:
                return result

        # Keyed by CANONICAL (yfinance-suffixed) symbol so every downstream
        # guard (no-short, Qabd possession, exit scan) matches TradeHistory /
        # SignalLog records for foreign listings — IBKR returns bare local
        # symbols ("ASML" @AEB), which previously made foreign fills invisible.
        # Round-trip via localSymbol (the exchange-local ticker), NOT the
        # internal `symbol` field: IBKR's `symbol` diverges from the local ticker
        # for class shares ("VOLV.B") and cross-listed names ("SAN1"/"AMP2"), which
        # would not map back to the canonical suffixed ticker — silently orphaning
        # the position from the suffix-keyed guards. localSymbol inverts cleanly.
        portfolio_map: dict = {}
        for item in self.ib.portfolio():
            if self._match_account(item.account):
                canon = from_ibkr(getattr(item.contract, "localSymbol", "") or item.contract.symbol,
                                  item.contract.primaryExchange or item.contract.exchange)
                portfolio_map[canon] = item

        raw = []
        for p in self.ib.positions():
            if not self._match_account(p.account):
                continue
            raw.append((from_ibkr(getattr(p.contract, "localSymbol", "") or p.contract.symbol,
                                  p.contract.primaryExchange or p.contract.exchange), p))

        need_prices = not portfolio_map and raw
        price_map: dict = {}
        if need_prices:
            try:
                import yfinance as yf
                symbols = [canon for canon, _ in raw]
                df = yf.download(symbols, period="1d", progress=False, threads=True)
                if not df.empty:
                    close = df["Close"]
                    if hasattr(close, "columns"):
                        for sym in symbols:
                            if sym in close.columns:
                                val = close[sym].dropna()
                                if not val.empty:
                                    price_map[sym] = float(val.iloc[-1])
                    else:
                        if len(symbols) == 1 and not close.dropna().empty:
                            price_map[symbols[0]] = float(close.dropna().iloc[-1])
            except Exception:
                pass

        # IBKR reports averageCost / marketPrice / marketValue / unrealizedPNL
        # ALL in the contract's LOCAL currency, in MAJOR units, consistently per
        # position — NOT account-base USD, and NOT LSE pence (verified live
        # 2026-07-17 on the paper gateway: BHP.L avgCost=29.61 GBP, ALFA.ST
        # marketValue=32973.92 SEK = 59*558.88). Convert every field via the
        # currency FX leg (_ibkr_amount_to_usd, no minor-unit divisor) so cost
        # basis, market value and PnL share one unit (USD). Trusting marketValue
        # as base-USD (its old behaviour) left SEK/CHF/EUR/GBP holdings in local
        # ccy — a Stockholm position read ~10x inflated, poisoning cap accounting
        # and every upnl-based exit. The yfinance fallback price stays on
        # symbols.to_usd, which DOES apply the pence divisor (correct for that
        # feed, which quotes LSE in pence).
        positions = []
        for sym, p in raw:
            qty = p.position
            ccy = getattr(p.contract, "currency", "") or "USD"
            avg_cost_usd = _ibkr_amount_to_usd(p.avgCost, ccy)
            # avg_cost_fx_ok flags whether avg_cost is a trustworthy USD figure.
            # _ibkr_amount_to_usd returns None ONLY when a required non-USD FX
            # rate is missing (USD names never hit an FX lookup, so they are
            # always True). When False both avg_cost AND market_value below stay
            # in LOCAL ccy (consistent unit, but on an unverified rate), and the
            # loops.py consumer reads pos.get("avg_cost_fx_ok", True) to skip the
            # upnl-based exits rather than act on a blind rate. We keep the
            # position (do NOT drop it) so no-short/Qabd guards still see it.
            avg_cost_fx_ok = avg_cost_usd is not None
            if not avg_cost_fx_ok:  # missing FX — keep raw, flag (exit math off)
                logger.warning("get_positions: no FX (%s) for %s — avg_cost stays local", ccy, sym)
                avg_cost_usd = p.avgCost
            # local_price = per-share price in the CONTRACT's own quote currency
            # (IBKR marketPrice is local major). loops.py samples the trailing
            # stop in this unit so a pure FX move can't fake a trail drop (M1).
            item = portfolio_map.get(sym)
            if item:
                iccy = getattr(item.contract, "currency", "") or ccy
                mv_usd = _ibkr_amount_to_usd(item.marketValue, iccy)
                pnl_usd = _ibkr_amount_to_usd(item.unrealizedPNL, iccy)
                if mv_usd is not None:
                    mkt_val = mv_usd
                    pnl = pnl_usd if pnl_usd is not None else (mkt_val - qty * avg_cost_usd)
                else:
                    # FX gap — fall back to raw local (avg_cost_fx_ok already
                    # False, so upnl exits are suppressed upstream); keep the
                    # position visible for guards.
                    mkt_val = item.marketValue
                    pnl = item.unrealizedPNL
                local_price = item.marketPrice
            elif sym in price_map:              # yfinance close = LOCAL quote unit
                px_usd = to_usd(price_map[sym], sym)
                mkt_val = qty * (px_usd if px_usd is not None else price_map[sym])
                pnl = mkt_val - qty * avg_cost_usd
                local_price = price_map[sym]
            else:
                mkt_val = qty * avg_cost_usd
                pnl = 0.0
                local_price = None
            if local_price is not None and (
                not isinstance(local_price, (int, float))
                or local_price <= 0
                or math.isnan(local_price)
            ):
                local_price = None  # 0/NaN/garbage → let loops use USD fallback
            positions.append({
                "symbol": sym,
                "quantity": qty,
                "avg_cost": avg_cost_usd,
                "avg_cost_fx_ok": avg_cost_fx_ok,
                "market_value": mkt_val,
                "unrealized_pnl": pnl,
                "local_price": local_price,
                "exchange": p.contract.primaryExchange or p.contract.exchange or "",
            })

        IBKRWorker._positions_cache[cache_key] = (positions, _time.time())
        return positions

    async def get_dividends_batch(self, positions: List[Dict]) -> List[Dict]:
        """Batch fetch past-12-month dividends for all positions (tick 456). Single sleep.

        Async because it issues live ib_insync requests (qualify) that must run on
        the connection's event loop. reqMktData/cancelMktData are non-blocking sends
        (they queue a wire message and return immediately — no ib._run), so they stay
        synchronous; only the blocking qualify + the settle-wait need awaiting. Must be
        awaited directly on the event loop — never via asyncio.to_thread (a worker
        thread has no event loop → ib._run raises "no current event loop in thread").
        """
        pending = []
        for pos in positions:
            contract = self._stock_contract(pos["symbol"])
            await self.ib.qualifyContractsAsync(contract)
            ticker = self.ib.reqMktData(contract, '456', True, False)
            pending.append((pos["symbol"], pos["quantity"], contract, ticker))

        await asyncio.sleep(2)  # single wait for all ticks

        results = []
        for symbol, quantity, contract, ticker in pending:
            self.ib.cancelMktData(contract)
            past12 = ticker.dividends.past12Months if ticker.dividends else None
            results.append({
                "symbol": symbol,
                "past12_per_share": past12,
                "quantity": quantity,
                "total_received": (past12 * quantity) if past12 is not None else None,
            })
        return results

    async def place_order(self, trade, exchange: str = "NMS") -> int:
        from ib_insync import MarketOrder, LimitOrder
        from ibkr_core.features.settings.service import load_settings as _ls
        _, _, ibkr_exchange, currency = get_exchange_config(_resolve_exchange(trade.symbol, exchange))
        contract = self._stock_contract(trade.symbol, exchange)
        qualified = await self.ib.qualifyContractsAsync(contract)
        # Fail-closed: an unqualified contract (bad suffix strip, wrong venue,
        # unknown symbol) used to be submitted anyway and die broker-side with
        # an opaque error. Refuse it here with an actionable message instead.
        if not qualified or not getattr(qualified[0], "conId", 0):
            raise ValueError(
                f"Contract qualification failed for {trade.symbol} "
                f"({ibkr_exchange}/{currency}) — refusing to submit order"
            )
        # Fractional shares supported (account has fractional trading enabled).
        # Round to 4dp to satisfy IBKR's fractional precision limit; if the gateway
        # rejects fractional orders, the cancel handler alerts via Telegram.
        quantity = round(float(trade.quantity), 4)

        # No-short guard (Rule #1), defense-in-depth at the broker layer: a SELL
        # may never exceed the live held quantity (would cross zero into a short).
        # Trader.execute_trade clamps too, but this protects any other caller.
        if trade.side == "SELL":
            held = 0.0
            try:
                for _p in self.get_positions():
                    if _p.get("symbol") == trade.symbol:
                        held = float(_p.get("quantity", 0) or 0)
                        break
            except Exception as _pe:
                logger.warning("place_order no-short guard: positions read failed for %s: %s", trade.symbol, _pe)
                held = 0.0
            if held <= 0:
                raise ValueError(
                    f"No-short guard: refusing SELL {trade.symbol} — not held (qty={held:g})"
                )
            if quantity > held:
                logger.info("place_order no-short guard: clamping SELL %s %.4f → held %.4f",
                            trade.symbol, quantity, held)
                quantity = round(held, 4)
        settings = _ls(self.account_id)
        # Order-type decision is centralised in OrderPolicy (pure, broker-free).
        # Base intent comes from use_limit_orders; the policy upgrades a MARKET
        # order to a marketable LIMIT on delayed data (a bare MARKET would be
        # cancelled by IBKR 10349) and fail-closes on a 0/None price.
        base_type = "LMT" if settings.get("use_limit_orders", False) else "MKT"
        data_state = subscription_for_port(self.port)
        # Source a price only when a limit may be needed (operator opt-in or
        # delayed data) — avoids an unnecessary market-data round-trip otherwise.
        price = (
            await self.get_last_price(trade.symbol, exchange)
            if base_type == "LMT" or data_state is DataState.DELAYED
            else 0.0
        )
        decision = OrderPolicy.decide(
            data_state, base_type, trade.side, price,
            settings.get("limit_order_slippage_pct", 0.1),
            symbol=trade.symbol,
        )
        if decision.order_type == "LMT":
            # OrderPolicy returns a 2dp marketable limit; snap it to the
            # contract's real per-band exchange tick (MiFID II) so an EU
            # entry/protective-exit limit isn't rejected with IBKR error 110.
            limit_price = await self._quantize_to_tick(contract, decision.limit_price, trade.side)
            order = LimitOrder(trade.side, quantity, limit_price)
        else:
            order = MarketOrder(trade.side, quantity)
        # Paper IB Gateway forces TIF=DAY from an order preset and silently cancels
        # an order that leaves TIF unset (Error 10349: "Order TIF was set to DAY
        # based on order preset."). The bracket path already sets this explicitly;
        # the plain path must too, or every plain LIMIT/MARKET is cancelled at submit.
        order.tif = 'DAY'
        trade_obj = self.ib.placeOrder(contract, order)
        return trade_obj.order.orderId

    async def place_bracket_order(
        self,
        trade,
        stop_price: float,
        take_profit_price: float,
        exchange: str = "NMS",
        trailing_amount: float = None,
    ) -> int:
        """
        Places a market-entry BUY with attached stop-loss and take-profit (OCA group).
        When trailing_amount is set, uses IBKR native TRAIL order (dollar trail) instead
        of a fixed stop — the stop ratchets up automatically as price rises.
        Stop-loss on owned asset is Shariah-permissible: conditional liquidation, no riba.
        Ref: COMPLIANCE.md Section 3 (no leverage), BEST_PRACTICES.md Section 1 (kill-switch).
        """
        _, _, ibkr_exchange, currency = get_exchange_config(_resolve_exchange(trade.symbol, exchange))
        contract = self._stock_contract(trade.symbol, exchange)
        qualified = await self.ib.qualifyContractsAsync(contract)
        if not qualified or not getattr(qualified[0], "conId", 0):
            raise ValueError(
                f"Contract qualification failed for {trade.symbol} "
                f"({ibkr_exchange}/{currency}) — refusing to submit bracket"
            )

        # Bracket entry is BUY-only: parent buys, children (stop/TP) are SELL exits
        # of the position the BUY opens. A SELL-side bracket would short on the
        # children — refuse it (Rule #1, defense-in-depth).
        if trade.side != "BUY":
            raise ValueError(
                f"place_bracket_order is BUY-entry only; got side={trade.side} for {trade.symbol}"
            )

        # Fractional shares supported (account has fractional trading enabled).
        # Round to 4dp for IBKR's fractional precision limit. If the gateway rejects
        # fractional orders, the cancel handler alerts via Telegram.
        quantity = round(float(trade.quantity), 4)
        if quantity < 0.001:  # IBKR fractional minimum
            raise ValueError(f"Quantity {quantity} below IBKR fractional minimum for {trade.symbol}")

        # Entry limit slightly above current price so it fills immediately like a market order.
        # bracketOrder() signature: (action, qty, limitPrice, takeProfitPrice, stopLossPrice)
        signal_price = getattr(trade, "signal_price", None) or stop_price / 0.95
        # Marketable-limit entry: BRACKET_ENTRY_PREMIUM_PCT (0.5%) above signal so
        # it fills immediately like a market order. Reuses the same helper as the
        # single-order path, but with its own distinct premium (not slippage_pct).
        entry_limit = marketable_limit(signal_price, "BUY", BRACKET_ENTRY_PREMIUM_PCT)

        # Snap entry/TP/stop to the contract's real per-band exchange tick (MiFID
        # II) so an EU bracket is not cancelled with IBKR error 110 (which would
        # leave no entry AND an unplaced protective stop). BUY entry rounds up,
        # SELL exits (TP/stop) round down — marketable AND tick-valid. The TRAIL
        # child auxPrice (4dp, set below) is already tick-safe and left as-is.
        entry_limit = await self._quantize_to_tick(contract, entry_limit, "BUY")
        tp_price = await self._quantize_to_tick(contract, take_profit_price, "SELL")
        sl_price = await self._quantize_to_tick(contract, stop_price, "SELL")

        # Use ib_insync bracketOrder helper — handles OCA group + transmit flags correctly
        bracket = self.ib.bracketOrder(
            trade.side,
            quantity,
            entry_limit,
            tp_price,
            sl_price,
        )
        parent, take_profit, stop_loss = bracket

        # Paper trading IB Gateway forces TIF=DAY — set explicitly to avoid silent rejection
        parent.tif = 'DAY'
        take_profit.tif = 'DAY'
        stop_loss.tif = 'DAY'

        if trailing_amount is not None and trailing_amount > 0:
            stop_loss.orderType = 'TRAIL'
            stop_loss.auxPrice = round(trailing_amount, 4)
            stop_loss.lmtPrice = 0.0

        for o in bracket:
            self.ib.placeOrder(contract, o)

        # Force ib_insync to flush socket and get order acknowledgment from TWS
        await asyncio.sleep(1)
        await self.ib.reqAllOpenOrdersAsync()
        await asyncio.sleep(0.5)
        return parent.orderId

    async def place_twap_bracket_order(
        self,
        trade,
        stop_price: float,
        take_profit_price: float,
        exchange: str = "NMS",
        trailing_amount: float = None,
        n_slices: int = 5,
        interval_secs: int = 60,
    ) -> int:
        """
        Places ONLY the first TWAP slice. Caller must schedule remaining slices
        with persistence (see Trader._run_twap_slices) so they survive restarts.
        Returns the first slice's order ID.
        """
        from copy import copy
        slice_qty = float(trade.quantity) / n_slices
        t = copy(trade)
        t.quantity = slice_qty
        oid = await self.place_bracket_order(t, stop_price, take_profit_price, exchange, trailing_amount)
        logger.info("TWAP %s slice 1/%d qty=%.4f order=%d", trade.symbol, n_slices, slice_qty, oid)
        return oid
