import os
import math
import logging
import asyncio
from typing import Any, List, Dict
from datetime import datetime, UTC
from dotenv import load_dotenv
from ibkr_core.core.market_hours import get_exchange_config

load_dotenv()

logger = logging.getLogger(__name__)

# yfinance appends exchange suffixes (6367.T, 0700.HK) that IBKR doesn't accept.
# Strip them so IBKR gets the bare ticker (6367, 0700).
_YFINANCE_SUFFIXES = {".T", ".HK", ".KS", ".KQ", ".NS", ".BO", ".AS", ".PA", ".DE", ".L", ".SI", ".KL"}

def _ibkr_symbol(symbol: str) -> str:
    for suffix in _YFINANCE_SUFFIXES:
        if symbol.upper().endswith(suffix.upper()):
            return symbol[: -len(suffix)]
    return symbol


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
            self.ib.orderStatusEvent -= self._on_order_status
            self.ib.execDetailsEvent -= self._on_exec_details
            self.ib.disconnectedEvent -= self._on_disconnect
            self.ib.errorEvent -= self._on_error
            self.ib.orderStatusEvent += self._on_order_status
            self.ib.execDetailsEvent += self._on_exec_details
            self.ib.disconnectedEvent += self._on_disconnect
            self.ib.errorEvent += self._on_error
            _LIVE_PORTS = {7496, 4001, 4003}
            if self.port not in _LIVE_PORTS:
                self.ib.reqMarketDataType(3)

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

    @staticmethod
    def _on_error(reqId, errorCode: int, errorString: str, contract) -> None:
        """
        IBKR error filter. Suppresses transient reconnect noise (322, 1100, 1102, 10197).
        Real errors propagate via order/exec event handlers.
        """
        # 322: Max account summary requests — caused by stale subscription on reconnect.
        # 1100/1102: Connection lost/restored — reconnect logic handles.
        # 10197: Competing live session (another client holding market data).
        # 10141: Paper trading disclaimer — requires manual click in Gateway.
        # 10349: Order TIF default override — informational.
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
                    s = load_settings()
                    await alert(
                        "IBKR Reconnected",
                        f"Connection restored after {attempt} attempt(s).",
                        channels=s.get("alert_channels", []),
                    )
                    return
            logger.error("All reconnect attempts failed — manual intervention required")
            from ibkr_core.features.settings.service import load_settings
            from ibkr_core.features.alerts.dispatcher import alert
            s = load_settings()
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
        Retrieves the available cash balance from the account.
        Ref: COMPLIANCE.md - Zero Leverage/Margin.
        """
        for v in self.ib.accountValues():
            if v.tag == 'AvailableFunds' and self._match_account(v.account):
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

    async def get_last_price(self, symbol: str, exchange: str = "NMS") -> float:
        from ib_insync import Stock
        async with self._limiter:
            await self._wait_for_pacing()
            _, _, ibkr_exchange, currency = get_exchange_config(exchange)
            contract = Stock(_ibkr_symbol(symbol), ibkr_exchange, currency)
            await self.ib.qualifyContractsAsync(contract)
            for attempt in range(3):
                tickers = await self.ib.reqTickersAsync(contract)
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
            # Fallback: yfinance when IBKR market data unavailable
            try:
                import yfinance as yf
                tick = yf.Ticker(symbol)
                hist = tick.history(period="1d")
                if not hist.empty:
                    val = float(hist["Close"].iloc[-1])
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
        from ib_insync import Stock
        async with self._limiter:
            await self._wait_for_pacing()
            _, _, ibkr_exchange, currency = get_exchange_config(exchange)
            contract = Stock(_ibkr_symbol(symbol), ibkr_exchange, currency)
            await self.ib.qualifyContractsAsync(contract)
            tickers = await self.ib.reqTickersAsync(contract)
            if not tickers:
                return {"bid": 0.0, "ask": 0.0, "last": 0.0, "volume": 0.0}
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
        from ib_insync import Stock
        async with self._limiter:
            await self._wait_for_pacing()
            _, _, ibkr_exchange, currency = get_exchange_config(exchange)
            contract = Stock(_ibkr_symbol(symbol), ibkr_exchange, currency)
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
        from ib_insync import Stock
        async with self._limiter:
            await self._wait_for_pacing()
            contract = Stock(_ibkr_symbol(symbol), 'SMART', 'USD')
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
                    if t.contract.symbol == symbol:
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

        portfolio_map: dict = {}
        for item in self.ib.portfolio():
            if self._match_account(item.account):
                portfolio_map[item.contract.symbol] = item

        raw = []
        for p in self.ib.positions():
            if not self._match_account(p.account):
                continue
            raw.append(p)

        need_prices = not portfolio_map and raw
        price_map: dict = {}
        if need_prices:
            try:
                import yfinance as yf
                symbols = [p.contract.symbol for p in raw]
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

        positions = []
        for p in raw:
            sym = p.contract.symbol
            item = portfolio_map.get(sym)
            if item:
                mkt_val = item.marketValue
                pnl = item.unrealizedPNL
            elif sym in price_map:
                mkt_val = p.position * price_map[sym]
                pnl = mkt_val - p.position * p.avgCost
            else:
                mkt_val = p.position * p.avgCost
                pnl = 0.0
            positions.append({
                "symbol": sym,
                "quantity": p.position,
                "avg_cost": p.avgCost,
                "market_value": mkt_val,
                "unrealized_pnl": pnl,
                "exchange": p.contract.primaryExchange or p.contract.exchange or "",
            })

        IBKRWorker._positions_cache[cache_key] = (positions, _time.time())
        return positions

    def get_dividends_batch(self, positions: List[Dict]) -> List[Dict]:
        """Batch fetch past-12-month dividends for all positions (tick 456). Single sleep."""
        from ib_insync import Stock
        pending = []
        for pos in positions:
            _, _, ibkr_exchange, currency = get_exchange_config("NMS")
            contract = Stock(_ibkr_symbol(pos["symbol"]), ibkr_exchange, currency)
            self.ib.qualifyContracts(contract)
            ticker = self.ib.reqMktData(contract, '456', True, False)
            pending.append((pos["symbol"], pos["quantity"], contract, ticker))

        self.ib.sleep(2)  # single wait for all ticks

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
        from ib_insync import Stock, MarketOrder, LimitOrder
        from ibkr_core.features.settings.service import load_settings as _ls
        _, _, ibkr_exchange, currency = get_exchange_config(exchange)
        contract = Stock(_ibkr_symbol(trade.symbol), ibkr_exchange, currency)
        await self.ib.qualifyContractsAsync(contract)
        # Fractional shares supported (account has fractional trading enabled).
        # Round to 4dp to satisfy IBKR's fractional precision limit; if the gateway
        # rejects fractional orders, the cancel handler alerts via Telegram.
        quantity = round(float(trade.quantity), 4)
        settings = _ls()
        if settings.get("use_limit_orders", False):
            price = await self.get_last_price(trade.symbol, exchange)
            slip = settings.get("limit_order_slippage_pct", 0.1) / 100
            lmt = round(price * (1 + slip if trade.side == "BUY" else 1 - slip), 2)
            order = LimitOrder(trade.side, quantity, lmt)
        else:
            order = MarketOrder(trade.side, quantity)
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
        from ib_insync import Stock
        _, _, ibkr_exchange, currency = get_exchange_config(exchange)
        contract = Stock(_ibkr_symbol(trade.symbol), ibkr_exchange, currency)
        await self.ib.qualifyContractsAsync(contract)

        # Fractional shares supported (account has fractional trading enabled).
        # Round to 4dp for IBKR's fractional precision limit. If the gateway rejects
        # fractional orders, the cancel handler alerts via Telegram.
        quantity = round(float(trade.quantity), 4)
        if quantity < 0.001:  # IBKR fractional minimum
            raise ValueError(f"Quantity {quantity} below IBKR fractional minimum for {trade.symbol}")

        # Entry limit slightly above current price so it fills immediately like a market order.
        # bracketOrder() signature: (action, qty, limitPrice, takeProfitPrice, stopLossPrice)
        signal_price = getattr(trade, "signal_price", None) or stop_price / 0.95
        entry_limit = round(signal_price * 1.005, 2)  # 0.5% premium ensures fill

        # Use ib_insync bracketOrder helper — handles OCA group + transmit flags correctly
        bracket = self.ib.bracketOrder(
            trade.side,
            quantity,
            entry_limit,
            round(take_profit_price, 2),
            round(stop_price, 2),
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
