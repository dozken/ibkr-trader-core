"""
Unit tests for IBKRWorker.
Mocks ib_insync.IB — no live IBKR connection required.
"""
import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from ibkr_core.features.trading.worker import IBKRWorker


def _make_worker():
    # Bypass __init__ entirely to avoid importing ib_insync (eventkit triggers
    # asyncio.get_event_loop() at module level which fails without a running loop).
    w = IBKRWorker.__new__(IBKRWorker)
    w.ib = MagicMock()
    w.host = "127.0.0.1"
    # LIVE port: keeps place_order on the MARKET path (no delayed-data marketable-LIMIT
    # upgrade / price fetch) so the order-shape assertions below stay deterministic.
    # Delayed-data routing is covered separately in test_order_policy.py.
    w.port = 7496
    w.client_id = 1
    w.ibkr_account_id = None
    w.account_id = None
    w._ticker_callbacks = {}
    w._reconnecting = False
    w._limiter = asyncio.Semaphore(5)
    w._last_request_time = 0.0
    w._fill_callback = None
    return w


class TestGetAvailableFunds(unittest.TestCase):
    def test_returns_available_funds_tag(self):
        w = _make_worker()
        v = MagicMock(); v.tag = "AvailableFunds"; v.value = "12345.67"
        w.ib.accountValues.return_value = [v]
        self.assertAlmostEqual(w.get_available_funds(), 12345.67)

    def test_ignores_cash_balance_tag(self):
        """CashBalance includes unsettled T+2 — must not be used."""
        w = _make_worker()
        cb = MagicMock(); cb.tag = "CashBalance"; cb.value = "99999.0"
        w.ib.accountValues.return_value = [cb]
        self.assertEqual(w.get_available_funds(), 0.0)

    def test_returns_zero_when_tag_missing(self):
        w = _make_worker()
        w.ib.accountValues.return_value = []
        self.assertEqual(w.get_available_funds(), 0.0)


class TestGetLastPrice(unittest.IsolatedAsyncioTestCase):
    async def test_returns_last_price_when_valid(self):
        w = _make_worker()
        ticker = MagicMock(); ticker.last = 150.5; ticker.close = 149.0
        w.ib.reqTickersAsync = AsyncMock(return_value=[ticker])
        w.ib.qualifyContractsAsync = AsyncMock()
        with patch("ib_insync.Stock"):
            price = await w.get_last_price("AAPL")
        self.assertAlmostEqual(price, 150.5)

    async def test_falls_back_to_close_on_nan(self):
        import math
        w = _make_worker()
        ticker = MagicMock(); ticker.last = float("nan"); ticker.close = 149.0
        w.ib.reqTickersAsync = AsyncMock(return_value=[ticker])
        w.ib.qualifyContractsAsync = AsyncMock()
        with patch("ib_insync.Stock"):
            price = await w.get_last_price("AAPL")
        self.assertAlmostEqual(price, 149.0)
        self.assertFalse(math.isnan(price))


class TestSubscribeTickerCallbackDeduplication(unittest.IsolatedAsyncioTestCase):
    async def test_second_subscription_removes_first_callback(self):
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()
        w.ib.reqMktData = MagicMock(return_value=MagicMock())

        cb1 = MagicMock()
        cb2 = MagicMock()

        with patch("ib_insync.Stock"):
            await w.subscribe_ticker("AAPL", cb1)
            first_fn = w._ticker_callbacks["AAPL"]
            # += rebinds pendingTickersEvent; capture the new binding before second call
            event_after_first_add = w.ib.pendingTickersEvent
            await w.subscribe_ticker("AAPL", cb2)

        # -= was called on the event object that existed after the first +=
        event_after_first_add.__isub__.assert_called_with(first_fn)
        # New callback stored
        self.assertIsNotNone(w._ticker_callbacks.get("AAPL"))
        self.assertIsNot(w._ticker_callbacks["AAPL"], first_fn)

    async def test_different_symbols_do_not_interfere(self):
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()
        w.ib.reqMktData = MagicMock(return_value=MagicMock())

        with patch("ib_insync.Stock"):
            await w.subscribe_ticker("AAPL", MagicMock())
            await w.subscribe_ticker("MSFT", MagicMock())

        self.assertIn("AAPL", w._ticker_callbacks)
        self.assertIn("MSFT", w._ticker_callbacks)


class TestUnsubscribeTicker(unittest.TestCase):
    def test_unsubscribe_removes_callback_and_detaches_event(self):
        w = _make_worker()
        cb = MagicMock()
        w._ticker_callbacks["AAPL"] = cb
        event = w.ib.pendingTickersEvent  # capture before rebind
        w.unsubscribe_ticker("AAPL")
        event.__isub__.assert_called_once_with(cb)
        self.assertNotIn("AAPL", w._ticker_callbacks)

    def test_unsubscribe_unknown_symbol_is_noop(self):
        w = _make_worker()
        event = w.ib.pendingTickersEvent
        w.unsubscribe_ticker("NVDA")  # must not raise
        event.__isub__.assert_not_called()

    def test_unsubscribe_only_removes_target_symbol(self):
        w = _make_worker()
        cb_aapl = MagicMock()
        cb_msft = MagicMock()
        w._ticker_callbacks["AAPL"] = cb_aapl
        w._ticker_callbacks["MSFT"] = cb_msft
        w.unsubscribe_ticker("AAPL")
        self.assertNotIn("AAPL", w._ticker_callbacks)
        self.assertIn("MSFT", w._ticker_callbacks)


class TestPlaceOrder(unittest.IsolatedAsyncioTestCase):
    async def test_place_order_preserves_fractional_quantity(self):
        """place_order preserves fractional quantity (fractional trading enabled),
        rounded to 4dp for IBKR precision."""
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()

        placed_trade = MagicMock()
        placed_trade.order.orderId = 77
        w.ib.placeOrder.return_value = placed_trade

        trade = MagicMock()
        trade.side = "BUY"
        trade.quantity = 0.06757751931246998
        trade.symbol = "LLY"

        with patch("ib_insync.Stock"), \
             patch("ib_insync.MarketOrder") as MockMkt, \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "SMART", "USD")):
            order_id = await w.place_order(trade)

        args, _ = MockMkt.call_args
        qty_passed = args[1]
        self.assertIsInstance(qty_passed, float)
        self.assertAlmostEqual(qty_passed, 0.0676)
        self.assertEqual(order_id, 77)

    async def test_place_order_whole_number_stays_float(self):
        """Even when quantity is a whole number (e.g. 10), it must arrive as float."""
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()

        placed_trade = MagicMock()
        placed_trade.order.orderId = 88
        w.ib.placeOrder.return_value = placed_trade

        trade = MagicMock()
        trade.side = "BUY"
        trade.quantity = 10
        trade.symbol = "MSFT"

        with patch("ib_insync.Stock"), \
             patch("ib_insync.MarketOrder") as MockMkt, \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "SMART", "USD")):
            await w.place_order(trade)

        args, _ = MockMkt.call_args
        qty_passed = args[1]
        self.assertIsInstance(qty_passed, float)
        self.assertAlmostEqual(qty_passed, 10.0)

    async def test_place_order_sets_tif_day(self):
        """Plain order must set TIF=DAY explicitly — paper IB Gateway otherwise
        applies an order preset and cancels at submit (Error 10349)."""
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()

        placed_trade = MagicMock()
        placed_trade.order.orderId = 99
        w.ib.placeOrder.return_value = placed_trade

        trade = MagicMock()
        trade.side = "BUY"
        trade.quantity = 5
        trade.symbol = "MSFT"

        with patch("ib_insync.Stock"), \
             patch("ib_insync.MarketOrder") as MockMkt, \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "SMART", "USD")):
            await w.place_order(trade)

        order_passed = w.ib.placeOrder.call_args[0][1]
        self.assertEqual(order_passed.tif, "DAY")
        self.assertIs(order_passed, MockMkt.return_value)


class TestPlaceBracketOrder(unittest.IsolatedAsyncioTestCase):
    def _make_bracket_mocks(self, parent_order_id=42):
        from ib_insync import StopOrder
        parent = MagicMock(); parent.orderId = parent_order_id; parent.transmit = False
        tp = MagicMock(); tp.transmit = False
        sl = StopOrder("SELL", 10.0, 95.0); sl.transmit = True
        return parent, tp, sl

    async def test_places_three_orders_via_bracket(self):
        """bracketOrder places parent + take-profit + stop-loss (3 placeOrder calls)."""
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()
        w.ib.reqAllOpenOrdersAsync = AsyncMock(return_value=[])
        parent, tp, sl = self._make_bracket_mocks(42)
        w.ib.bracketOrder.return_value = [parent, tp, sl]

        trade = MagicMock(); trade.side = "BUY"; trade.quantity = 10; trade.symbol = "AAPL"
        trade.signal_price = 100.0

        with patch("ib_insync.Stock"), \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "SMART", "USD")), \
             patch("asyncio.sleep"):
            await w.place_bracket_order(trade, stop_price=95.0, take_profit_price=110.0)

        self.assertEqual(w.ib.placeOrder.call_count, 3)

    async def test_returns_parent_order_id(self):
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()
        w.ib.reqAllOpenOrdersAsync = AsyncMock(return_value=[])
        parent, tp, sl = self._make_bracket_mocks(99)
        w.ib.bracketOrder.return_value = [parent, tp, sl]

        trade = MagicMock(); trade.side = "BUY"; trade.quantity = 5; trade.symbol = "AAPL"
        trade.signal_price = 100.0

        with patch("ib_insync.Stock"), \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "SMART", "USD")), \
             patch("asyncio.sleep"):
            order_id = await w.place_bracket_order(trade, 95.0, 110.0)

        self.assertEqual(order_id, 99)

    async def test_bracket_order_preserves_fractional_quantity(self):
        """Fractional quantity is preserved (fractional trading enabled), rounded to
        4dp before passing to bracketOrder."""
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()
        w.ib.reqAllOpenOrdersAsync = AsyncMock(return_value=[])
        parent, tp, sl = self._make_bracket_mocks(42)
        w.ib.bracketOrder.return_value = [parent, tp, sl]

        trade = MagicMock(); trade.side = "BUY"; trade.quantity = 1.95047243; trade.symbol = "UMMA"
        trade.signal_price = 100.0

        with patch("ib_insync.Stock"), \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "SMART", "USD")), \
             patch("asyncio.sleep"):
            await w.place_bracket_order(trade, stop_price=95.0, take_profit_price=110.0)

        call_args = w.ib.bracketOrder.call_args[0]
        qty_arg = call_args[1]  # second positional arg is quantity
        self.assertIsInstance(qty_arg, float)
        self.assertAlmostEqual(qty_arg, 1.9505)


def _inc(low, increment):
    m = MagicMock(); m.lowEdge = low; m.increment = increment
    return m


class TestQuantizeToTick(unittest.IsolatedAsyncioTestCase):
    # MiFID II bands: 0.01 below 50, 0.05 in [50,100), 0.1 at/above 100.
    BANDS = [_inc(0, 0.01), _inc(50, 0.05), _inc(100, 0.1)]

    def _worker_with_rule(self, market_rule_ids="26,26", valid_exchanges="IBIS,SMART"):
        w = _make_worker()
        cd = MagicMock()
        cd.marketRuleIds = market_rule_ids
        cd.validExchanges = valid_exchanges
        w.ib.reqContractDetailsAsync = AsyncMock(return_value=[cd])
        w.ib.reqMarketRuleAsync = AsyncMock(return_value=self.BANDS)
        return w

    async def test_buy_rounds_up_sell_rounds_down_to_band(self):
        w = self._worker_with_rule()
        contract = MagicMock(); contract.primaryExchange = "IBIS"; contract.exchange = "SMART"
        # price 100.12 -> band starting at 100 has 0.1 tick.
        self.assertAlmostEqual(await w._quantize_to_tick(contract, 100.12, "BUY"), 100.2)
        self.assertAlmostEqual(await w._quantize_to_tick(contract, 100.12, "SELL"), 100.1)
        # Rule id resolved to the primaryExchange's parallel entry (IBIS -> "26").
        w.ib.reqMarketRuleAsync.assert_awaited_with(26)

    async def test_mid_band_five_cent_tick(self):
        w = self._worker_with_rule()
        contract = MagicMock(); contract.primaryExchange = "IBIS"; contract.exchange = "SMART"
        # 73.33 falls in [50,100) -> 0.05 tick.
        self.assertAlmostEqual(await w._quantize_to_tick(contract, 73.33, "BUY"), 73.35)
        self.assertAlmostEqual(await w._quantize_to_tick(contract, 73.33, "SELL"), 73.30)

    async def test_us_fallback_uses_two_decimals_when_rule_missing(self):
        w = _make_worker()
        w.ib.reqContractDetailsAsync = AsyncMock(return_value=[])  # no details
        contract = MagicMock(); contract.currency = "USD"
        # Both sides fall back to legacy 2dp (US equities tick at 0.01).
        self.assertAlmostEqual(await w._quantize_to_tick(contract, 100.126, "BUY"), 100.13)
        self.assertAlmostEqual(await w._quantize_to_tick(contract, 100.124, "SELL"), 100.12)

    async def test_nonus_fallback_uses_coarse_tick_when_rule_missing(self):
        w = _make_worker()
        # reqContractDetailsAsync raising is swallowed -> [] -> coarse fallback.
        w.ib.reqContractDetailsAsync = AsyncMock(side_effect=RuntimeError("no perms"))
        contract = MagicMock(); contract.currency = "EUR"
        contract.localSymbol = "ASML"
        # Coarse 0.05 tick, marketable direction (BUY up, SELL down).
        self.assertAlmostEqual(await w._quantize_to_tick(contract, 100.12, "BUY"), 100.15)
        self.assertAlmostEqual(await w._quantize_to_tick(contract, 100.12, "SELL"), 100.10)

    async def test_zero_price_returns_unchanged_without_rule_lookup(self):
        w = _make_worker()
        w.ib.reqContractDetailsAsync = AsyncMock()
        contract = MagicMock()
        self.assertEqual(await w._quantize_to_tick(contract, 0.0, "BUY"), 0.0)
        w.ib.reqContractDetailsAsync.assert_not_awaited()

    def test_pick_market_rule_id_prefers_primary_exchange(self):
        contract = MagicMock(); contract.primaryExchange = "IBIS"; contract.exchange = "SMART"
        self.assertEqual(
            IBKRWorker._pick_market_rule_id("11,22", "IBIS,SMART", contract), 11
        )

    def test_pick_market_rule_id_falls_back_to_first(self):
        contract = MagicMock(); contract.primaryExchange = "XXX"; contract.exchange = "SMART"
        self.assertEqual(
            IBKRWorker._pick_market_rule_id("33,44", "IBIS,SMART", contract), 33
        )

    def test_pick_market_rule_id_empty_returns_none(self):
        contract = MagicMock(); contract.primaryExchange = ""; contract.exchange = ""
        self.assertIsNone(IBKRWorker._pick_market_rule_id("", "", contract))


class TestPlaceBracketOrderTickQuantization(unittest.IsolatedAsyncioTestCase):
    async def test_bracket_prices_snapped_to_market_rule(self):
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock(
            return_value=[MagicMock(conId=123)]
        )
        cd = MagicMock(); cd.marketRuleIds = "26,26"; cd.validExchanges = "IBIS,SMART"
        w.ib.reqContractDetailsAsync = AsyncMock(return_value=[cd])
        w.ib.reqMarketRuleAsync = AsyncMock(
            return_value=[_inc(0, 0.01), _inc(50, 0.05), _inc(100, 0.1)]
        )
        w.ib.reqAllOpenOrdersAsync = AsyncMock(return_value=[])
        from ib_insync import StopOrder
        parent = MagicMock(); parent.orderId = 7; parent.transmit = False
        tp = MagicMock(); tp.transmit = False
        sl = StopOrder("SELL", 10.0, 95.0); sl.transmit = True
        w.ib.bracketOrder.return_value = [parent, tp, sl]

        trade = MagicMock(); trade.side = "BUY"; trade.quantity = 10; trade.symbol = "ASML.AS"
        trade.signal_price = 100.0

        with patch("ib_insync.Contract"), patch("ib_insync.Stock"), \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "IBIS", "EUR")), \
             patch("asyncio.sleep"):
            await w.place_bracket_order(trade, stop_price=95.03, take_profit_price=110.07)

        entry, tp_arg, sl_arg = w.ib.bracketOrder.call_args[0][2:5]
        # entry = marketable_limit(100, BUY, 0.5%) = 100.5 -> on 0.1 tick.
        self.assertAlmostEqual(entry, 100.5)
        # TP/stop are SELL exits -> round DOWN to their band tick.
        self.assertAlmostEqual(tp_arg, 110.0)   # 110.07 -> 0.1 tick -> 110.0
        self.assertAlmostEqual(sl_arg, 95.0)    # 95.03 -> 0.05 tick -> 95.0


class TestGetPositionsFxFlag(unittest.TestCase):
    def _pos(self, local, avg_cost, qty=10.0, primary="", exchange="SMART", account="U1"):
        p = MagicMock()
        p.account = account
        p.position = qty
        p.avgCost = avg_cost
        p.contract.localSymbol = local
        p.contract.symbol = local
        p.contract.primaryExchange = primary
        p.contract.exchange = exchange
        return p

    def _item(self, local, mv, pnl, primary="", exchange="SMART", account="U1"):
        it = MagicMock()
        it.account = account
        it.marketValue = mv
        it.unrealizedPNL = pnl
        it.contract.localSymbol = local
        it.contract.symbol = local
        it.contract.primaryExchange = primary
        it.contract.exchange = exchange
        return it

    def setUp(self):
        # _positions_cache is class-level; clear before AND after each test so a
        # cached fake result can't leak into other files' get_positions calls.
        IBKRWorker._positions_cache.clear()
        self.addCleanup(IBKRWorker._positions_cache.clear)

    def test_us_position_fx_ok_true_eur_missing_fx_false(self):
        w = _make_worker()
        w.ib.positions.return_value = [
            self._pos("AAPL", avg_cost=150.0, primary="NASDAQ"),
            self._pos("ASML", avg_cost=600.0, primary="AEB", exchange="AEB"),
        ]
        w.ib.portfolio.return_value = [
            self._item("AAPL", mv=1600.0, pnl=100.0, primary="NASDAQ"),
            self._item("ASML", mv=6500.0, pnl=500.0, primary="AEB", exchange="AEB"),
        ]

        # to_usd: USD names pass through (never None); EUR ASML has no FX -> None.
        def fake_to_usd(price, sym, *a, **k):
            return None if sym == "ASML" else price

        with patch("ibkr_core.features.trading.worker.from_ibkr", side_effect=lambda s, e="": s), \
             patch("ibkr_core.features.trading.worker.to_usd", side_effect=fake_to_usd):
            positions = w.get_positions()

        by_sym = {p["symbol"]: p for p in positions}
        # US position: FX always OK, avg_cost normalized.
        self.assertTrue(by_sym["AAPL"]["avg_cost_fx_ok"])
        self.assertAlmostEqual(by_sym["AAPL"]["avg_cost"], 150.0)
        # EUR position with missing FX: flagged False, position NOT dropped,
        # avg_cost left in local ccy (raw), so downstream can skip the stop.
        self.assertFalse(by_sym["ASML"]["avg_cost_fx_ok"])
        self.assertAlmostEqual(by_sym["ASML"]["avg_cost"], 600.0)
        self.assertIn("ASML", by_sym)  # kept for no-short / Qabd guards

    def test_default_key_is_true_when_present(self):
        """Every emitted position carries the boolean explicitly (no missing key)."""
        w = _make_worker()
        w.ib.positions.return_value = [self._pos("MSFT", avg_cost=400.0, primary="NASDAQ")]
        w.ib.portfolio.return_value = [self._item("MSFT", mv=4200.0, pnl=200.0, primary="NASDAQ")]
        with patch("ibkr_core.features.trading.worker.from_ibkr", side_effect=lambda s, e="": s), \
             patch("ibkr_core.features.trading.worker.to_usd", side_effect=lambda price, sym, *a, **k: price):
            positions = w.get_positions()
        self.assertIn("avg_cost_fx_ok", positions[0])
        self.assertTrue(positions[0]["avg_cost_fx_ok"])


class TestOnOrderStatus(unittest.TestCase):
    @patch("ibkr_core.core.database.SessionLocal")
    def test_filled_status_updates_trade_history(self, MockSession):
        w = _make_worker()
        mock_db = MagicMock()
        MockSession.return_value = mock_db
        row = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = row

        trade = MagicMock()
        trade.orderStatus.status = "Filled"
        trade.order.orderId = 123

        w._on_order_status(trade)

        from ibkr_core.core.state import TradeState
        self.assertEqual(row.state, TradeState.FILLED)
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("ibkr_core.core.database.SessionLocal")
    def test_cancelled_status_sets_error_state(self, MockSession):
        w = _make_worker()
        mock_db = MagicMock()
        MockSession.return_value = mock_db
        row = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = row

        trade = MagicMock()
        trade.orderStatus.status = "Cancelled"
        trade.order.orderId = 456

        w._on_order_status(trade)

        from ibkr_core.core.state import TradeState
        self.assertEqual(row.state, TradeState.IBKR_ERROR)

    @patch("ibkr_core.core.database.SessionLocal")
    def test_intermediate_status_no_db_write(self, MockSession):
        w = _make_worker()
        mock_db = MagicMock()
        MockSession.return_value = mock_db

        trade = MagicMock()
        trade.orderStatus.status = "Submitted"
        trade.order.orderId = 789

        w._on_order_status(trade)

        mock_db.commit.assert_not_called()


class TestFillCallback(unittest.IsolatedAsyncioTestCase):

    def test_fill_callback_none_by_default(self):
        w = _make_worker()
        self.assertIsNone(w._fill_callback)

    @patch("ibkr_core.core.database.SessionLocal")
    async def test_fill_callback_fired_on_filled(self, MockSession):
        w = _make_worker()
        MockSession.return_value = MagicMock()

        callback = AsyncMock()
        w._fill_callback = callback

        trade = MagicMock()
        trade.orderStatus.status = "Filled"
        trade.order.orderId = 42
        trade.contract.symbol = "AAPL"
        trade.order.action = "BUY"
        trade.orderStatus.filled = 10.0
        trade.orderStatus.avgFillPrice = 175.50

        w._on_order_status(trade)
        await asyncio.sleep(0)  # let create_task run

        callback.assert_awaited_once_with("AAPL", "BUY", 10.0, 175.50)

    def test_fill_callback_not_fired_on_submitted(self):
        w = _make_worker()
        callback = AsyncMock()
        w._fill_callback = callback

        trade = MagicMock()
        trade.orderStatus.status = "Submitted"

        w._on_order_status(trade)

        callback.assert_not_called()

    @patch("ibkr_core.core.database.SessionLocal")
    def test_fill_callback_none_does_not_raise(self, MockSession):
        """_fill_callback=None (default) must not cause AttributeError on fill."""
        w = _make_worker()
        MockSession.return_value = MagicMock()

        trade = MagicMock()
        trade.orderStatus.status = "Filled"
        trade.order.orderId = 99
        trade.contract.symbol = "MSFT"
        trade.order.action = "SELL"
        trade.orderStatus.filled = 5.0
        trade.orderStatus.avgFillPrice = 400.0

        w._on_order_status(trade)  # must not raise


class TestNoShortGuard(unittest.IsolatedAsyncioTestCase):
    def _sell_trade(self, symbol="AAPL", qty=10.0):
        t = MagicMock(); t.symbol = symbol; t.side = "SELL"; t.quantity = qty
        return t

    async def test_place_order_sell_blocked_when_not_held(self):
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()
        w.get_positions = MagicMock(return_value=[])  # nothing held
        with patch("ib_insync.Stock"), \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "SMART", "USD")), \
             patch("ibkr_core.features.settings.service.load_settings", return_value={}):
            with self.assertRaises(ValueError):
                await w.place_order(self._sell_trade(qty=10))
        w.ib.placeOrder.assert_not_called()

    async def test_place_order_sell_clamped_to_held(self):
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()
        w.get_positions = MagicMock(return_value=[{"symbol": "AAPL", "quantity": 3}])
        w.ib.placeOrder = MagicMock(return_value=MagicMock(order=MagicMock(orderId=5)))
        with patch("ib_insync.Stock"), \
             patch("ib_insync.MarketOrder") as MockMO, \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "SMART", "USD")), \
             patch("ibkr_core.features.settings.service.load_settings", return_value={}):
            await w.place_order(self._sell_trade(qty=100))
        # MarketOrder(side, quantity) — second positional arg is the clamped qty.
        MockMO.assert_called_once()
        self.assertEqual(MockMO.call_args[0][1], 3)

    async def test_bracket_rejects_sell_side(self):
        w = _make_worker()
        w.ib.qualifyContractsAsync = AsyncMock()
        t = MagicMock(); t.symbol = "AAPL"; t.side = "SELL"; t.quantity = 5
        with patch("ib_insync.Stock"), \
             patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=(None, None, "SMART", "USD")):
            with self.assertRaises(ValueError):
                await w.place_bracket_order(t, 95.0, 110.0)


if __name__ == "__main__":
    unittest.main()
