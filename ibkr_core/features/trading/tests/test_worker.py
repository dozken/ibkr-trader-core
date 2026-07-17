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


class TestStockContractField(unittest.TestCase):
    """_stock_contract picks symbol-field (Asia numeric) vs localSymbol (EU).

    ib_insync is stubbed with MagicMock (root conftest), so we assert on the
    constructor call args rather than the built object's attributes.
    """

    def _build(self, symbol):
        w = _make_worker()
        with patch("ib_insync.Stock") as stock, patch("ib_insync.Contract") as contract:
            w._stock_contract(symbol)
        return stock, contract

    def test_asia_symbol_field_venue_uses_symbol_not_localsymbol(self):
        stock, contract = self._build("7203.T")   # Toyota, TSEJ
        contract.assert_not_called()               # NOT the failing localSymbol path
        args, kwargs = stock.call_args
        self.assertEqual(args[0], "7203")          # plain code in the symbol field
        self.assertEqual(kwargs.get("primaryExchange"), "TSEJ")
        self.assertEqual(args[2], "JPY")

    def test_hk_strips_leading_zero_in_symbol(self):
        stock, contract = self._build("0700.HK")   # Tencent, SEHK
        contract.assert_not_called()
        args, kwargs = stock.call_args
        self.assertEqual(args[0], "700")
        self.assertEqual(kwargs.get("primaryExchange"), "SEHK")

    def test_eu_class_share_stays_on_localsymbol(self):
        stock, contract = self._build("VOLV-B.ST")  # class share needs localSymbol
        stock.assert_not_called()
        _, kwargs = contract.call_args
        self.assertEqual(kwargs.get("localSymbol"), "VOLV B")
        self.assertEqual(kwargs.get("primaryExchange"), "SFB")

    def test_us_stays_smart_stock(self):
        stock, contract = self._build("AAPL")
        contract.assert_not_called()
        args, kwargs = stock.call_args
        self.assertEqual(args[0], "AAPL")
        self.assertEqual(args[1], "SMART")
        self.assertIsNone(kwargs.get("primaryExchange"))  # US: no venue disambiguator


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


# FX map for the fake _get_fx_rate: covers the currencies under test; any
# currency absent here returns None (simulating a missing rate → fail-closed).
_FAKE_FX = {"EUR": 1.10, "SEK": 0.10, "GBP": 1.25, "CHF": 1.20}


def _fake_get_fx_rate(frm, to="USD", *a, **k):
    return _FAKE_FX.get(frm)


class TestGetPositionsFxFlag(unittest.TestCase):
    def _pos(self, local, avg_cost, qty=10.0, primary="", exchange="SMART",
             account="U1", currency="USD"):
        p = MagicMock()
        p.account = account
        p.position = qty
        p.avgCost = avg_cost
        p.contract.localSymbol = local
        p.contract.symbol = local
        p.contract.primaryExchange = primary
        p.contract.exchange = exchange
        p.contract.currency = currency
        return p

    def _item(self, local, mv, pnl, primary="", exchange="SMART", account="U1",
              market_price=0.0, currency="USD"):
        it = MagicMock()
        it.account = account
        it.marketValue = mv
        it.unrealizedPNL = pnl
        it.marketPrice = market_price  # per-share, LOCAL quote ccy
        it.contract.localSymbol = local
        it.contract.symbol = local
        it.contract.primaryExchange = primary
        it.contract.exchange = exchange
        it.contract.currency = currency
        return it

    def setUp(self):
        # _positions_cache is class-level; clear before AND after each test so a
        # cached fake result can't leak into other files' get_positions calls.
        IBKRWorker._positions_cache.clear()
        self.addCleanup(IBKRWorker._positions_cache.clear)

    def _run(self, w):
        # Patch the FX source that _ibkr_amount_to_usd imports (data_fetcher)
        # plus from_ibkr (identity) so canonical == localSymbol in tests.
        with patch("ibkr_core.features.trading.worker.from_ibkr", side_effect=lambda s, e="": s), \
             patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate",
                   side_effect=_fake_get_fx_rate):
            return {p["symbol"]: p for p in w.get_positions()}

    def test_us_passthrough_eur_converted(self):
        """USD is a no-op; EUR avg_cost AND market_value both FX-converted."""
        w = _make_worker()
        w.ib.positions.return_value = [
            self._pos("AAPL", avg_cost=150.0, primary="NASDAQ", currency="USD"),
            self._pos("ASML", avg_cost=600.0, primary="AEB", exchange="AEB", currency="EUR"),
        ]
        w.ib.portfolio.return_value = [
            self._item("AAPL", mv=1600.0, pnl=100.0, primary="NASDAQ", currency="USD"),
            self._item("ASML", mv=6500.0, pnl=500.0, primary="AEB", exchange="AEB", currency="EUR"),
        ]
        by_sym = self._run(w)
        self.assertTrue(by_sym["AAPL"]["avg_cost_fx_ok"])
        self.assertAlmostEqual(by_sym["AAPL"]["avg_cost"], 150.0)
        self.assertAlmostEqual(by_sym["AAPL"]["market_value"], 1600.0)
        # EUR: avg_cost 600*1.1, market_value 6500*1.1 — both in USD, one unit.
        self.assertTrue(by_sym["ASML"]["avg_cost_fx_ok"])
        self.assertAlmostEqual(by_sym["ASML"]["avg_cost"], 660.0)
        self.assertAlmostEqual(by_sym["ASML"]["market_value"], 7150.0)

    def test_sek_market_value_not_trusted_as_base_usd(self):
        """Regression: a Stockholm (SEK) marketValue must be FX-converted, not
        passed through as if it were already account-base USD (the bug that read
        a $3.7k position as ~$37k and poisoned cap accounting)."""
        w = _make_worker()
        w.ib.positions.return_value = [
            self._pos("SAND", avg_cost=342.0, qty=114.0, primary="SFB", exchange="SFB", currency="SEK"),
        ]
        w.ib.portfolio.return_value = [
            self._item("SAND", mv=39000.0, pnl=-200.0, primary="SFB", exchange="SFB",
                       market_price=342.0, currency="SEK"),
        ]
        p = self._run(w)["SAND"]
        self.assertTrue(p["avg_cost_fx_ok"])
        self.assertAlmostEqual(p["avg_cost"], 34.2)          # 342 * 0.10
        self.assertAlmostEqual(p["market_value"], 3900.0)    # 39000 * 0.10, NOT 39000
        self.assertAlmostEqual(p["unrealized_pnl"], -20.0)   # -200 * 0.10
        self.assertAlmostEqual(p["local_price"], 342.0)      # local, for trailing

    def test_gbp_no_pence_divisor_on_portfolio(self):
        """Regression: IBKR portfolio quotes LSE in GBP MAJOR (not pence), so no
        /100 divisor — avg_cost must be ~price*fx, not price/100*fx (the bug that
        read BHP.L cost basis 74x too small)."""
        w = _make_worker()
        w.ib.positions.return_value = [
            self._pos("BHP", avg_cost=29.60, qty=100.0, primary="LSE", exchange="LSE", currency="GBP"),
        ]
        w.ib.portfolio.return_value = [
            self._item("BHP", mv=2949.0, pnl=-12.0, primary="LSE", exchange="LSE",
                       market_price=29.49, currency="GBP"),
        ]
        p = self._run(w)["BHP"]
        self.assertAlmostEqual(p["avg_cost"], 37.0)          # 29.60 * 1.25, NOT 0.37
        self.assertAlmostEqual(p["market_value"], 3686.25)   # 2949 * 1.25

    def test_missing_fx_flags_false_and_keeps_local(self):
        """No rate for the currency → avg_cost_fx_ok False, position kept, and
        market_value falls back to raw local (avg_cost also raw → consistent
        unit; loops.py suppresses upnl exits on the False flag)."""
        w = _make_worker()
        # JPY absent from _FAKE_FX → _get_fx_rate returns None.
        w.ib.positions.return_value = [
            self._pos("7203", avg_cost=2500.0, qty=100.0, primary="TSEJ", exchange="TSEJ", currency="JPY"),
        ]
        w.ib.portfolio.return_value = [
            self._item("7203", mv=260000.0, pnl=0.0, primary="TSEJ", exchange="TSEJ", currency="JPY"),
        ]
        p = self._run(w)["7203"]
        self.assertFalse(p["avg_cost_fx_ok"])
        self.assertAlmostEqual(p["avg_cost"], 2500.0)        # raw local
        self.assertAlmostEqual(p["market_value"], 260000.0)  # raw local fallback
        self.assertIn("7203", self._run(w))                  # kept for guards

    def test_default_key_is_true_when_present(self):
        """Every emitted position carries the boolean explicitly (no missing key)."""
        w = _make_worker()
        w.ib.positions.return_value = [self._pos("MSFT", avg_cost=400.0, primary="NASDAQ")]
        w.ib.portfolio.return_value = [self._item("MSFT", mv=4200.0, pnl=200.0, primary="NASDAQ")]
        positions_by = self._run(w)
        self.assertIn("avg_cost_fx_ok", positions_by["MSFT"])
        self.assertTrue(positions_by["MSFT"]["avg_cost_fx_ok"])

    def test_local_price_emitted_from_market_price_and_nan_guarded(self):
        """M1: get_positions surfaces the LOCAL per-share price for FX-neutral
        trailing; a valid marketPrice passes through, a 0/NaN one becomes None."""
        w = _make_worker()
        w.ib.positions.return_value = [
            self._pos("ASML", avg_cost=600.0, primary="AEB", exchange="AEB", currency="EUR"),
            self._pos("SAP", avg_cost=100.0, primary="IBIS", exchange="IBIS", currency="EUR"),
        ]
        w.ib.portfolio.return_value = [
            self._item("ASML", mv=6500.0, pnl=500.0, primary="AEB", exchange="AEB", market_price=650.0, currency="EUR"),
            self._item("SAP", mv=1000.0, pnl=0.0, primary="IBIS", exchange="IBIS", market_price=float("nan"), currency="EUR"),
        ]
        by_sym = self._run(w)
        self.assertAlmostEqual(by_sym["ASML"]["local_price"], 650.0)   # local, not USD
        self.assertIsNone(by_sym["SAP"]["local_price"])                # NaN guarded → None


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
