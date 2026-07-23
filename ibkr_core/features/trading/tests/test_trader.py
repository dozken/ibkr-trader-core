import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock
from ibkr_core.features.trading.trader import Trader, _calculate_position_size, _stop_take_prices, _MIN_FRACTIONAL_QTY, _exceeds_concentration_limit
from ibkr_core.core.state import TradeState
from ibkr_core.features.trading.schemas import TradeCreate
from ibkr_core.features.compliance.schemas import ComplianceStatus

_COMPLIANT = ComplianceStatus(
    symbol="AAPL", sector="Technology", is_compliant=True,
    debt_to_mkt_cap=0.1, cash_to_mkt_cap=0.1, impure_revenue_pct=0.01
)
_SETTINGS = {
    "min_trade_size": 10.0,
    "cash_reserve_pct": 5.0,
    "max_position_size_pct": 10.0,
    "risk_profile": "CONSERVATIVE",
    "stop_loss_pct": None,
    "take_profit_pct": None,
    "twap_threshold_pct": 100.0,  # disable TWAP in unit tests
    "use_kelly_sizing": False,     # isolate sizing math from Kelly in unit tests
}


class TestPositionSizing(unittest.TestCase):
    def setUp(self):
        # Isolate sizing math from the live VIX feed — _calculate_position_size
        # applies a VIX volatility factor (CALM=1.0, ELEVATED=0.75, CRISIS=0.5)
        # via get_current_vix(). Without this, the tests pass only when the real
        # VIX happens to be CALM and fail (×0.75) when it is ELEVATED.
        _p = patch("ibkr_core.features.trading.trader._get_vix_size_factor", return_value=1.0)
        _p.start()
        self.addCleanup(_p.stop)

    def test_normal_sizing(self):
        # 10k funds, 10k net_liq, 5% reserve=500, investable=9500, max_pos=10%*10k=1000, price=150
        # dollars = min(9500, 1000) = 1000, qty = 1000/150 ≈ 6.667 (fractional, not floored)
        qty = _calculate_position_size(10000.0, 10000.0, 150.0, _SETTINGS)
        self.assertAlmostEqual(qty, 1000.0 / 150.0, places=6)

    def test_caps_at_max_position_pct(self):
        # 100k funds, 100k net_liq, reserve=5k, investable=95k, max_pos=10k, price=100
        # qty = 10000/100 = 100.0
        qty = _calculate_position_size(100000.0, 100000.0, 100.0, _SETTINGS)
        self.assertAlmostEqual(qty, 100.0)

    def test_rejects_below_min_trade_size(self):
        # Very small net_liq → max_pos tiny → below min_trade_size → 0.0
        qty = _calculate_position_size(50.0, 50.0, 100.0, _SETTINGS)
        self.assertEqual(qty, 0.0)

    def test_zero_net_liquidation_returns_zero(self):
        qty = _calculate_position_size(5000.0, 0.0, 100.0, _SETTINGS)
        self.assertEqual(qty, 0.0)

    def test_fractional_quantity_returned_correctly(self):
        # $50 available / $500 price = 0.1 shares
        # net_liq=1000 → reserve=50, investable=0, max_pos=100
        # But available_funds=50, reserve=50, investable=0 → dollars=0 → below min_trade_size
        # Use larger net_liq so reserve doesn't eat the $50:
        # net_liq=500, reserve=25, investable=25, max_pos=50, min_trade_size=10 → dollars=25
        # price=500 → qty = 25/500 = 0.05
        qty = _calculate_position_size(50.0, 500.0, 500.0, _SETTINGS)
        self.assertAlmostEqual(qty, 25.0 / 500.0, places=6)  # 0.05

    def test_fractional_50_into_500_stock(self):
        # Scenario: $1000 available, net_liq=$1000, price=$500
        # reserve=5%*1000=50, investable=950, max_pos=10%*1000=100, dollars=100
        # qty = 100/500 = 0.2 shares
        qty = _calculate_position_size(1000.0, 1000.0, 500.0, _SETTINGS)
        self.assertAlmostEqual(qty, 0.2, places=6)
        self.assertGreater(qty, _MIN_FRACTIONAL_QTY)

    def test_returns_zero_when_qty_below_minimum(self):
        # Engineered so dollars/price < 0.001
        # net_liq=200, reserve=10, investable large, max_pos=20, price=100000
        # qty = 20/100000 = 0.0002 < 0.001 → 0.0
        qty = _calculate_position_size(1000.0, 200.0, 100000.0, _SETTINGS)
        self.assertEqual(qty, 0.0)


class TestStopTakePrices(unittest.TestCase):
    # Disable ATR so tests use deterministic pct-based fallback
    _NO_ATR = {**_SETTINGS, "use_atr_stops": False}

    def test_conservative_defaults(self):
        stop, tp, atr = _stop_take_prices("AAPL", 100.0, self._NO_ATR)
        self.assertAlmostEqual(stop, 97.0)
        self.assertAlmostEqual(tp, 106.0)
        self.assertIsNone(atr)

    def test_balanced_profile(self):
        settings = {**self._NO_ATR, "risk_profile": "BALANCED"}
        stop, tp, atr = _stop_take_prices("AAPL", 100.0, settings)
        self.assertAlmostEqual(stop, 95.0)
        self.assertAlmostEqual(tp, 110.0)

    def test_explicit_override(self):
        settings = {**self._NO_ATR, "stop_loss_pct": 7.0, "take_profit_pct": 14.0}
        stop, tp, atr = _stop_take_prices("AAPL", 100.0, settings)
        self.assertAlmostEqual(stop, 93.0)
        self.assertAlmostEqual(tp, 114.0)

    def test_atr_stops_used_when_enabled(self):
        """When use_atr_stops=True and ATR available, stop/tp derived from ATR."""
        settings = {**_SETTINGS, "use_atr_stops": True}
        with patch("ibkr_core.features.trading.trader._calculate_atr", return_value=5.0):
            stop, tp, trailing = _stop_take_prices("AAPL", 100.0, settings)
        # entry - 2*ATR = 90, entry + 3*ATR = 115, trailing = 2*ATR = 10
        self.assertAlmostEqual(stop, 90.0)
        self.assertAlmostEqual(tp, 115.0)
        self.assertAlmostEqual(trailing, 10.0)


class TestTrader(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_worker = MagicMock()
        self.mock_worker.get_market_data = AsyncMock(
            return_value={"bid": 149.9, "ask": 150.1, "last": 150.0, "volume": 1_000_000}
        )
        self.mock_worker.get_avg_volume_20d = AsyncMock(return_value=5_000_000)
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.place_bracket_order = AsyncMock(return_value=42)
        self.mock_worker.place_order = AsyncMock(return_value=42)
        self.trader = Trader(self.mock_worker)
        self.patcher_db = patch('ibkr_core.features.trading.trader.SessionLocal')
        self.mock_session_local = self.patcher_db.start()
        self.mock_db = MagicMock()
        self.mock_session_local.return_value = self.mock_db
        self.patcher_settings = patch('ibkr_core.features.trading.trader._load_settings',
                                      return_value=_SETTINGS)
        self.patcher_settings.start()
        # Isolate sizing from the live VIX feed (see TestPositionSizing.setUp).
        self.patcher_vix = patch('ibkr_core.features.trading.trader._get_vix_size_factor',
                                 return_value=1.0)
        self.patcher_vix.start()

    def tearDown(self):
        self.patcher_db.stop()
        self.patcher_settings.stop()
        self.patcher_vix.stop()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_execute_buy_dry_run_state(self, mock_check):
        """When dry_run=True, machine should transition to DRY_RUN and not place order."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        
        # Override settings for this test
        with patch('ibkr_core.features.trading.trader._load_settings', return_value={**_SETTINGS, "dry_run": True}):
            trade_req = TradeCreate(symbol="AAPL", quantity=5, side="BUY")
            trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.DRY_RUN)
        self.mock_worker.place_bracket_order.assert_not_called()

    @patch('ibkr_core.features.trading.trader.async_shariah_screen', new_callable=AsyncMock)
    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_unpre_screened_buy_uses_canonical_screen(self, mock_check, mock_async_screen):
        """A BUY with no pre_screened must run the canonical AAOIFI screen (fail-closed),
        NOT check_shariah_compliance with defaulted data (which would pass any symbol)."""
        mock_async_screen.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        with patch('ibkr_core.features.trading.trader._load_settings',
                   return_value={**_SETTINGS, "dry_run": True}):
            trade_req = TradeCreate(symbol="AAPL", quantity=5, side="BUY")
            trade = await self.trader.execute_trade(trade_req)  # no pre_screened

        mock_async_screen.assert_awaited_once_with("AAPL")
        mock_check.assert_not_called()  # defaulted-data helper must NOT gate the BUY
        self.assertEqual(trade.state, TradeState.DRY_RUN)  # passed compliance

    @patch('ibkr_core.features.trading.trader.async_shariah_screen', new_callable=AsyncMock)
    async def test_unpre_screened_buy_blocked_when_screen_non_compliant(self, mock_async_screen):
        """Canonical screen says NON_COMPLIANT → BUY rejected, no order placed."""
        mock_async_screen.return_value = ComplianceStatus(
            symbol="HARAM", sector="Conventional Finance", is_compliant=False,
            debt_to_mkt_cap=0.5, cash_to_mkt_cap=0.1, impure_revenue_pct=0.9,
            reason="Prohibited sector",
        )
        trade_req = TradeCreate(symbol="HARAM", quantity=5, side="BUY")
        trade = await self.trader.execute_trade(trade_req)  # no pre_screened

        self.assertEqual(trade.state, TradeState.REJECTED_COMPLIANCE)
        self.mock_worker.place_bracket_order.assert_not_called()
        self.mock_worker.place_order.assert_not_called()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_execute_sell_dry_run_state(self, mock_check):
        """When dry_run=True, SELL should also transition to DRY_RUN."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        
        # Hold the position so the no-short guard passes through to dry-run.
        self.mock_worker.get_positions.return_value = [{"symbol": "AAPL", "quantity": 10}]
        # Mock possession confirmed
        with patch.object(self.trader, "_is_possession_confirmed", return_value=True):
            with patch('ibkr_core.features.trading.trader._load_settings', return_value={**_SETTINGS, "dry_run": True}):
                trade_req = TradeCreate(symbol="AAPL", quantity=10, side="SELL")
                trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.DRY_RUN)
        self.mock_worker.place_order.assert_not_called()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_noncompliant_sell_is_not_rejected(self, mock_check):
        """Divestment is always permitted: a SELL of a HELD position that screens
        NON-compliant must NOT be blocked by the compliance gate (you must be able to
        exit a holding that became haram). Only BUYs are gated on compliance."""
        non_compliant = ComplianceStatus(
            symbol="AAPL", sector="Conventional Finance", is_compliant=False,
            debt_to_mkt_cap=0.9, cash_to_mkt_cap=0.1, impure_revenue_pct=0.5,
            reason="Prohibited sector",
        )
        mock_check.return_value = non_compliant
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.get_positions.return_value = [{"symbol": "AAPL", "quantity": 10}]
        with patch.object(self.trader, "_is_possession_confirmed", return_value=True):
            with patch('ibkr_core.features.trading.trader._load_settings',
                       return_value={**_SETTINGS, "dry_run": True}):
                trade_req = TradeCreate(symbol="AAPL", quantity=10, side="SELL")
                trade = await self.trader.execute_trade(trade_req, pre_screened=non_compliant)

        # NOT rejected on compliance — proceeds (dry-run here).
        self.assertNotEqual(trade.state, TradeState.REJECTED_COMPLIANCE)
        self.assertEqual(trade.state, TradeState.DRY_RUN)

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_no_short_guard_blocks_sell_when_not_held(self, mock_check):
        """SELL of an unheld symbol is blocked (would open a short — Rule #1)."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.get_positions.return_value = []  # nothing held
        with patch.object(self.trader, "_is_possession_confirmed", return_value=True):
            trade_req = TradeCreate(symbol="AAPL", quantity=10, side="SELL")
            trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.REJECTED_COMPLIANCE)
        self.assertIn("No-short guard", trade.error_message or "")
        self.mock_worker.place_order.assert_not_called()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_no_short_guard_clamps_oversell_to_held(self, mock_check):
        """SELL larger than held qty is clamped down to held — never crosses zero."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.get_positions.return_value = [{"symbol": "AAPL", "quantity": 7}]
        self.mock_worker.place_order = AsyncMock(return_value=99)
        with patch.object(self.trader, "_is_possession_confirmed", return_value=True):
            trade_req = TradeCreate(symbol="AAPL", quantity=100, side="SELL")
            trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        # Order placed for the held 7, not the requested 100.
        self.assertEqual(trade.quantity, 7)
        self.mock_worker.place_order.assert_awaited_once()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_execute_buy_explicit_quantity_uses_bracket(self, mock_check):
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 20000.0  # max_pos=2000 > 10*150=1500
        self.mock_worker.get_positions.return_value = []
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.place_bracket_order.return_value = 12345

        trade_req = TradeCreate(symbol="AAPL", quantity=10, side="BUY")
        trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                          debt=10, cash=10, revenue=100,
                                          prohibited_income=1, mkt_cap=1000)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.assertEqual(trade.ibkr_order_id, 12345)
        self.mock_worker.place_bracket_order.assert_called_once()
        self.mock_worker.place_order.assert_not_called()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_execute_buy_loads_per_account_settings(self, mock_check):
        """B1 regression: Trader(account_id=N) must load settings_N, not global.

        The per-account capital cap / stops live in settings_{account_id}.json;
        if execute_trade calls _load_settings() with no account_id it silently
        reads global settings and the cap (e.g. $436 paper) is voided. Do NOT
        mock this away — assert the account_id is threaded through.
        """
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        self.mock_worker.get_positions.return_value = []
        # account_id set → execute_trade runs the read_only guard (a DB lookup);
        # return a non-read-only account so the BUY proceeds to settings load.
        self.mock_db.query.return_value.filter.return_value.first.return_value = \
            MagicMock(read_only=False)
        trader = Trader(self.mock_worker, account_id=4)

        captured = {}
        def _fake_load(account_id=None):
            captured["account_id"] = account_id
            return _SETTINGS
        with patch('ibkr_core.features.trading.trader._load_settings', side_effect=_fake_load):
            trade_req = TradeCreate(symbol="AAPL", quantity=5, side="BUY")
            await trader.execute_trade(trade_req, sector="Technology",
                                       debt=10, cash=10, revenue=100,
                                       prohibited_income=1, mkt_cap=1000)
        self.assertEqual(captured.get("account_id"), 4)

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_bracket_exits_false_uses_plain_order(self, mock_check):
        """B2 regression: bracket_exits=False enters via place_order (no resting
        SELL children) so main_loop can drive the % trailing stop + floor."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 20000.0
        self.mock_worker.get_positions.return_value = []
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.place_order.return_value = 999

        with patch('ibkr_core.features.trading.trader._load_settings',
                   return_value={**_SETTINGS, "bracket_exits": False}):
            trade_req = TradeCreate(symbol="AAPL", quantity=10, side="BUY")
            trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                              debt=10, cash=10, revenue=100,
                                              prohibited_income=1, mkt_cap=1000)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.assertEqual(trade.ibkr_order_id, 999)
        self.mock_worker.place_order.assert_awaited()
        self.mock_worker.place_bracket_order.assert_not_called()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_execute_buy_auto_sizes_quantity(self, mock_check):
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        self.mock_worker.get_positions.return_value = []
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.place_bracket_order.return_value = 99

        trade_req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
        trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                          debt=10, cash=10, revenue=100,
                                          prohibited_income=1, mkt_cap=1000)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.assertAlmostEqual(trade.quantity, 1000.0 / 150.0, places=6)  # fractional, not floored

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_execute_buy_auto_size_too_small_rejected(self, mock_check):
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 50.0
        self.mock_worker.get_net_liquidation.return_value = 50.0
        self.mock_worker.get_last_price = AsyncMock(return_value=100.0)

        trade_req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
        trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                          debt=10, cash=10, revenue=100,
                                          prohibited_income=1, mkt_cap=1000)

        self.assertEqual(trade.state, TradeState.REJECTED_FUNDS)
        self.mock_worker.place_bracket_order.assert_not_called()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_capital_cap_budget_uses_position_value_not_funds_gap(self, mock_check):
        """trading_capital_cap budget = cap - market value of held positions.

        Regression: a flat paper account where NetLiq sits above cash by a
        baseline accrual gap (here 1090501 - 1088974 = 1526.81) must NOT count
        that gap as 'invested'. The old (net_liq - available_funds) proxy pegged
        the $436-cap budget at 0 and rejected every BUY despite zero positions.
        """
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_net_liquidation.return_value = 1_090_501.17
        self.mock_worker.get_available_funds.return_value = 1_088_974.36
        self.mock_worker.get_positions.return_value = []  # fully flat
        self.mock_worker.get_last_price = AsyncMock(return_value=100.0)
        self.mock_worker.place_bracket_order.return_value = 101

        capped = {**_SETTINGS, "trading_capital_cap": 436.0,
                  "max_position_size_pct": 100.0, "cash_reserve_pct": 0.0,
                  "max_sector_exposure_pct": 100.0, "min_sector_count": 1}
        with patch('ibkr_core.features.trading.trader._load_settings', return_value=capped):
            trade_req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
            trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                              debt=10, cash=10, revenue=100,
                                              prohibited_income=1, mkt_cap=1000)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        # Budget = full $436 cap (gap ignored). Deployed $ near the cap, allowing
        # the sizer's small fee/slippage reserve. Old proxy → budget 0 → REJECTED.
        deployed = trade.quantity * 100.0
        self.assertGreater(deployed, 0.97 * 436.0)
        self.assertLessEqual(deployed, 436.0)

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_capital_cap_budget_subtracts_held_market_value(self, mock_check):
        """Budget shrinks by the market value of positions already held."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_net_liquidation.return_value = 1_090_501.17
        self.mock_worker.get_available_funds.return_value = 1_088_974.36
        self.mock_worker.get_positions.return_value = [
            {"symbol": "MSFT", "quantity": 1, "market_value": 300.0},
        ]
        self.mock_worker.get_last_price = AsyncMock(return_value=100.0)
        self.mock_worker.place_bracket_order.return_value = 102

        capped = {**_SETTINGS, "trading_capital_cap": 436.0,
                  "max_position_size_pct": 100.0, "cash_reserve_pct": 0.0,
                  "max_sector_exposure_pct": 100.0, "min_sector_count": 1}
        with patch('ibkr_core.features.trading.trader._load_settings', return_value=capped):
            trade_req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
            trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                              debt=10, cash=10, revenue=100,
                                              prohibited_income=1, mkt_cap=1000)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        # Budget = cap - held market value = 436 - 300 = 136 (not 436, not 0).
        deployed = trade.quantity * 100.0
        self.assertGreater(deployed, 0.97 * 136.0)
        self.assertLessEqual(deployed, 136.0)

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_whole_share_fallback_floors_quantity(self, mock_check):
        """allow_fractional_shares=False → BUY floored to whole shares (IBKR 10243)."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_positions.return_value = []
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.place_bracket_order.return_value = 201

        nofrac = {**_SETTINGS, "max_position_size_pct": 10.0, "cash_reserve_pct": 0.0,
                  "allow_fractional_shares": False}
        with patch('ibkr_core.features.trading.trader._load_settings', return_value=nofrac):
            trade_req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
            trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                              debt=10, cash=10, revenue=100,
                                              prohibited_income=1, mkt_cap=1000)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        # 10% of 10000 = $1000 budget / $150 = 6.67 → floored to 6 whole shares.
        self.assertEqual(trade.quantity, 6.0)

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_whole_share_deploys_within_position_limit(self, mock_check):
        """Whole-share mode with a cap large enough to hold ≥1 share inside the
        per-position limit deploys floored whole shares."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_net_liquidation.return_value = 1_090_501.17
        self.mock_worker.get_available_funds.return_value = 1_088_974.36
        self.mock_worker.get_positions.return_value = []  # flat → cap budget = $4000
        self.mock_worker.get_last_price = AsyncMock(return_value=215.0)
        self.mock_worker.place_bracket_order.return_value = 202

        # cap $4000, position sized at max_position_size_pct 35% = $1400 / $215 =
        # 6.51 → floored to 6 whole shares ($1290), inside the 35% limit.
        nofrac = {**_SETTINGS, "trading_capital_cap": 4000.0, "max_position_size_pct": 35.0,
                  "cash_reserve_pct": 0.0, "max_sector_exposure_pct": 100.0,
                  "min_sector_count": 1, "allow_fractional_shares": False}
        with patch('ibkr_core.features.trading.trader._load_settings', return_value=nofrac):
            trade_req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
            trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                              debt=10, cash=10, revenue=100,
                                              prohibited_income=1, mkt_cap=1000)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.assertEqual(trade.quantity, 6.0)

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_whole_share_rejects_when_budget_under_one_share(self, mock_check):
        """Budget can't fund even one whole share → REJECTED_FUNDS (not a 10243 error)."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_net_liquidation.return_value = 1_090_501.17
        self.mock_worker.get_available_funds.return_value = 1_088_974.36
        self.mock_worker.get_positions.return_value = []  # cap budget = $436
        self.mock_worker.get_last_price = AsyncMock(return_value=900.0)  # 25% of 436 = $109 < $900
        self.mock_worker.place_bracket_order.return_value = 203

        nofrac = {**_SETTINGS, "trading_capital_cap": 436.0, "max_position_size_pct": 35.0,
                  "cash_reserve_pct": 0.0, "max_sector_exposure_pct": 100.0,
                  "min_sector_count": 1, "allow_fractional_shares": False}
        with patch('ibkr_core.features.trading.trader._load_settings', return_value=nofrac):
            trade_req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
            trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                              debt=10, cash=10, revenue=100,
                                              prohibited_income=1, mkt_cap=1000)

        self.assertEqual(trade.state, TradeState.REJECTED_FUNDS)
        self.mock_worker.place_bracket_order.assert_not_called()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_execute_buy_compliance_fail(self, mock_check):
        mock_check.return_value = ComplianceStatus(
            symbol="BANK", sector="Conventional Finance", is_compliant=False,
            debt_to_mkt_cap=0.5, cash_to_mkt_cap=0.1, impure_revenue_pct=0.01,
            reason="Prohibited sector"
        )

        trade_req = TradeCreate(symbol="BANK", quantity=10, side="BUY")
        trade = await self.trader.execute_trade(trade_req, sector="Conventional Finance",
                                          debt=50, cash=10, revenue=100,
                                          prohibited_income=1, mkt_cap=100)

        self.assertEqual(trade.state, TradeState.REJECTED_COMPLIANCE)
        self.assertFalse(trade.compliance_snapshot.is_compliant)
        self.mock_worker.place_bracket_order.assert_not_called()
        self.mock_worker.place_order.assert_not_called()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_execute_buy_insufficient_funds_shrinks_to_fit(self, mock_check):
        """Cash race condition: requested qty > available funds → shrink to affordable, not reject."""
        mock_check.return_value = _COMPLIANT
        # net_liq high enough that max_position_pct doesn't block, but cash drained low
        self.mock_worker.get_available_funds.return_value = 100.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        self.mock_worker.get_positions.return_value = []
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.place_bracket_order.return_value = 77

        trade_req = TradeCreate(symbol="AAPL", quantity=10, side="BUY")
        trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                          debt=10, cash=10, revenue=100,
                                          prohibited_income=1, mkt_cap=1000)

        # Should shrink to ~(100 * 0.98) / 150 = 0.6533 — not reject
        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.assertLess(trade.quantity, 10)
        self.assertLess(trade.quantity * 150, 100)  # within budget
        self.assertGreater(trade.quantity, 0.001)  # above min fractional

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_execute_buy_funds_below_fractional_min_rejected(self, mock_check):
        """When even fractional share unaffordable, must still reject."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 0.10  # absurdly low
        self.mock_worker.get_net_liquidation.return_value = 0.10
        self.mock_worker.get_last_price = AsyncMock(return_value=1500.0)  # ASML-like

        trade_req = TradeCreate(symbol="ASML", quantity=10, side="BUY")
        trade = await self.trader.execute_trade(trade_req, sector="Technology",
                                          debt=10, cash=10, revenue=100,
                                          prohibited_income=1, mkt_cap=1000)

        # 0.10 * 0.98 / 1500 = 0.000065 < _MIN_FRACTIONAL_QTY (0.001)
        self.assertEqual(trade.state, TradeState.REJECTED_FUNDS)
        self.mock_worker.place_bracket_order.assert_not_called()


    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_fractional_quantity_passes_guard(self, mock_check):
        """A valid fractional quantity like 0.5 should not be rejected by the funds guard."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0  # max_pos=1000 > 0.5*150=75
        self.mock_worker.get_positions.return_value = []
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.place_bracket_order.return_value = 55

        trade_req = TradeCreate(symbol="AAPL", quantity=0.5, side="BUY")
        trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.mock_worker.place_bracket_order.assert_called_once()

    @patch('ibkr_core.features.trading.trader.check_shariah_compliance')
    async def test_sub_minimum_quantity_rejected(self, mock_check):
        """A quantity of 0.0001 is below IBKR's minimum (0.001) and must be rejected."""
        mock_check.return_value = _COMPLIANT
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)

        trade_req = TradeCreate(symbol="AAPL", quantity=0.0001, side="BUY")
        trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.REJECTED_FUNDS)
        self.mock_worker.place_bracket_order.assert_not_called()

    # ── pre_screened path ──────────────────────────────────────────────────────

    async def test_pre_screened_skips_check_shariah_compliance(self):
        """pre_screened= bypasses check_shariah_compliance entirely."""
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 20000.0  # max_pos=2000 > 10*150=1500
        self.mock_worker.get_positions.return_value = []
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.place_bracket_order.return_value = 77

        trade_req = TradeCreate(symbol="AAPL", quantity=10, side="BUY")
        with patch("ibkr_core.features.trading.trader.check_shariah_compliance") as mock_check:
            trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)
            mock_check.assert_not_called()

        self.assertEqual(trade.state, TradeState.SUBMITTED)

    async def test_pre_screened_non_compliant_blocked(self):
        """pre_screened with is_compliant=False → REJECTED_COMPLIANCE (no re-check)."""
        non_compliant = ComplianceStatus(
            symbol="BANK", sector="Conventional Finance", is_compliant=False,
            debt_to_mkt_cap=0.5, cash_to_mkt_cap=0.1, impure_revenue_pct=0.01,
            reason="Prohibited sector",
        )
        trade_req = TradeCreate(symbol="BANK", quantity=10, side="BUY")
        with patch("ibkr_core.features.trading.trader.check_shariah_compliance") as mock_check:
            trade = await self.trader.execute_trade(trade_req, pre_screened=non_compliant)
            mock_check.assert_not_called()

        self.assertEqual(trade.state, TradeState.REJECTED_COMPLIANCE)

    # ── force_liquidation path ────────────────────────────────────────────────

    async def test_force_liquidation_sell_bypasses_compliance_block(self):
        """Kill-switch: SELL a non-compliant position regardless of compliance result."""
        non_compliant = ComplianceStatus(
            symbol="TOBK", sector="Tobacco", is_compliant=False,
            debt_to_mkt_cap=0.1, cash_to_mkt_cap=0.05, impure_revenue_pct=0.8,
            reason="Prohibited sector: Tobacco",
        )
        self.mock_worker.place_order = AsyncMock(return_value=999)
        # Hold the position being liquidated (no-short guard reads live positions).
        self.mock_worker.get_positions.return_value = [{"symbol": "TOBK", "quantity": 5}]
        # Simulate T+2 satisfied: patch possession check
        with patch.object(self.trader, "_is_possession_confirmed", return_value=True):
            trade_req = TradeCreate(symbol="TOBK", quantity=5, side="SELL")
            trade = await self.trader.execute_trade(
                trade_req, pre_screened=non_compliant, force_liquidation=True
            )

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.mock_worker.place_order.assert_awaited_once()

    async def test_force_liquidation_requires_pre_screened(self):
        """force_liquidation=True without pre_screened → IBKR_ERROR (not a silent pass)."""
        trade_req = TradeCreate(symbol="X", quantity=1, side="SELL")
        trade = await self.trader.execute_trade(trade_req, force_liquidation=True)
        self.assertEqual(trade.state, TradeState.IBKR_ERROR)

    # ── settlement guard ─────────────────────────────────────────────────────

    @patch("ibkr_core.features.trading.trader.check_shariah_compliance")
    async def test_sell_without_prior_buy_rejected(self, mock_check):
        """Sell with no prior BUY in DB → REJECTED_COMPLIANCE via settlement guard."""
        mock_check.return_value = _COMPLIANT
        # DB returns None for prior buy
        self.mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        trade_req = TradeCreate(symbol="AAPL", quantity=5, side="SELL")
        trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.REJECTED_COMPLIANCE)
        self.mock_worker.place_order.assert_not_called()


class TestPossessionConfirmed(unittest.TestCase):
    """Unit tests for _is_possession_confirmed (Qabd/T+2 settlement guard)."""

    def setUp(self):
        self.worker = MagicMock()
        self.trader = Trader(self.worker)

    def _buy_row(self, days_old, state="REJECTED_FUNDS"):
        from datetime import timedelta
        row = MagicMock()
        row.created_at = datetime.utcnow() - timedelta(days=days_old)
        row.updated_at = row.created_at
        row.state = state
        return row

    def _db(self, first_results):
        """Mock db whose query().filter().order_by().first() yields results in order."""
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = list(first_results)
        return db

    def test_held_with_stale_rejected_buy_confirms_possession(self):
        """Held in IBKR + only old REJECTED buy records (>=2d) → possession TRUE.

        Regression: previously trapped — no SUBMITTED/FILLED record returned False,
        so a genuinely-held position could never be sold, stop-lossed, or divested
        (even via emergency liquidation). first() order: settled=None,
        submitted=None, oldest-any=old rejected.
        """
        self.worker.get_positions.return_value = [{"symbol": "NXPI", "quantity": 250}]
        db = self._db([None, None, self._buy_row(40)])
        self.assertTrue(self.trader._is_possession_confirmed(db, "NXPI"))

    def test_held_with_fresh_buy_attempt_not_yet_settled(self):
        """Held but oldest BUY attempt not yet settled (0 trading days elapsed) →
        Qabd not satisfied → FALSE. Patch the trading-day counter so the assertion
        is deterministic regardless of wall-clock/tz/holidays."""
        from unittest.mock import patch
        self.worker.get_positions.return_value = [{"symbol": "NXPI", "quantity": 250}]
        db = self._db([None, None, self._buy_row(0)])
        with patch("ibkr_core.features.trading.trader._settled_trading_days", return_value=0):
            self.assertFalse(self.trader._is_possession_confirmed(db, "NXPI"))

    def test_held_with_no_buy_record_is_external_acquisition(self):
        """Held in IBKR + zero bot BUY records → external acquisition → TRUE (unchanged)."""
        self.worker.get_positions.return_value = [{"symbol": "NXPI", "quantity": 250}]
        db = self._db([None, None, None])
        self.assertTrue(self.trader._is_possession_confirmed(db, "NXPI"))

    def test_not_held_in_ibkr_blocks(self):
        """Not held in IBKR → cannot possess → FALSE (no-short / phantom-sell guard)."""
        self.worker.get_positions.return_value = []
        db = self._db([None])
        self.assertFalse(self.trader._is_possession_confirmed(db, "NXPI"))

    def test_settled_filled_buy_confirms_via_primary_path(self):
        """Primary path: a FILLED buy >=2d old confirms without touching the fallback."""
        self.worker.get_positions.return_value = [{"symbol": "NXPI", "quantity": 250}]
        db = self._db([self._buy_row(5, state=TradeState.FILLED)])
        self.assertTrue(self.trader._is_possession_confirmed(db, "NXPI"))


class TestSettlementTradingDays(unittest.TestCase):
    """H2: Qabd guard must count TRADING days STRICTLY AFTER the trade date T on the
    position's HOME exchange (T+2), never raw calendar days — else a Friday EU fill
    reads 'settled' on Monday (3 calendar days) while real settlement is Tuesday, and
    a stop-loss SELL would dispatch on unsettled shares (Rule #2 / COMPLIANCE.md Sec 4).
    """

    @staticmethod
    def _freeze(y, m, d, hour=16):
        """Patch trader.datetime so datetime.now(tz) is a fixed instant (UTC hour)."""
        import ibkr_core.features.trading.trader as trader_mod
        from datetime import datetime as _dt, timezone as _tz
        fixed = _dt(y, m, d, hour, 0, tzinfo=_tz.utc)

        class _Frozen(_dt):
            @classmethod
            def now(cls, tz=None):
                return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)

        return patch.object(trader_mod, "datetime", _Frozen)

    @staticmethod
    def _fill(y, m, d):
        """A fill instant mid-session (15:00 UTC ≈ 11:00 ET / 16:00 London)."""
        from datetime import datetime as _dt, timezone as _tz
        return _dt(y, m, d, 15, 0, tzinfo=_tz.utc)

    def _count(self, fill, symbol):
        from ibkr_core.features.trading.trader import _settled_trading_days
        return _settled_trading_days(fill, symbol)

    def test_fill_day_itself_never_counted(self):
        """Off-by-one guard: same-day and weekend-only ranges yield 0 trading days."""
        fri = self._fill(2026, 7, 10)  # Friday
        with self._freeze(2026, 7, 10):  # same Friday
            self.assertEqual(self._count(fri, "AZN.L"), 0)
        with self._freeze(2026, 7, 11):  # Saturday
            self.assertEqual(self._count(fri, "AZN.L"), 0)

    def test_eu_friday_fill_not_settled_monday_settled_tuesday(self):
        """EU (LSE) Friday fill: Monday = 1 trading day (NOT possessed), Tuesday = 2 (possessed)."""
        fri = self._fill(2026, 7, 10)  # Friday
        with self._freeze(2026, 7, 13):  # Monday
            self.assertEqual(self._count(fri, "AZN.L"), 1)
        with self._freeze(2026, 7, 14):  # Tuesday
            self.assertEqual(self._count(fri, "AZN.L"), 2)

    def test_us_midweek_fill_unaffected(self):
        """US (NMS) mid-week fill with no holidays: calendar==trading days, so a Monday
        fill is possessed on Wednesday (2 trading days) exactly as before — unaffected."""
        mon = self._fill(2026, 7, 13)  # Monday
        with self._freeze(2026, 7, 14):  # Tuesday
            self.assertEqual(self._count(mon, "AAPL"), 1)
        with self._freeze(2026, 7, 15):  # Wednesday
            self.assertEqual(self._count(mon, "AAPL"), 2)

    def test_holiday_between_fill_and_now_extends_wait(self):
        """A holiday between T and now extends the wait. Thu Jul 2 fill, now Mon Jul 6:
        NMS closes Fri Jul 3 (Independence Day observed) → only 1 trading day → NOT
        settled; LSE has no such holiday → 2 trading days → settled. Same dates, the US
        holiday alone delays possession."""
        thu = self._fill(2026, 7, 2)  # Thursday
        with self._freeze(2026, 7, 6):  # Monday
            self.assertEqual(self._count(thu, "AAPL"), 1)   # Jul 3 holiday skipped
            self.assertEqual(self._count(thu, "AZN.L"), 2)  # LSE open Jul 3

    def test_possession_guard_uses_trading_days_end_to_end(self):
        """_is_possession_confirmed (primary FILLED path) honors the T+2 trading-day rule
        for an EU name: a Friday fill is NOT possessed on Monday, possessed on Tuesday."""
        worker = MagicMock()
        worker.get_positions.return_value = [{"symbol": "AZN.L", "quantity": 100}]
        trader = Trader(worker)

        buy = MagicMock()
        buy.updated_at = self._fill(2026, 7, 10)  # Friday, tz-aware
        buy.state = TradeState.FILLED
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = buy

        with self._freeze(2026, 7, 13):  # Monday → 1 trading day
            self.assertFalse(trader._is_possession_confirmed(db, "AZN.L"))
        with self._freeze(2026, 7, 14):  # Tuesday → 2 trading days
            self.assertTrue(trader._is_possession_confirmed(db, "AZN.L"))


class TestSettledSellableQty(unittest.TestCase):
    """Lot-level Qabd: _settled_sellable_qty exposes only the SETTLED share count so
    a fresh unsettled add can't trap the already-settled portion behind the exit."""

    def setUp(self):
        self.trader = Trader(MagicMock())

    def _buy(self, qty, settled):
        """A FILLED BUY row tagged settled/unsettled via updated_at year (the
        patched _settled_trading_days keys off it)."""
        from datetime import timezone as _tz
        row = MagicMock()
        row.quantity = qty
        row.state = TradeState.FILLED
        row.updated_at = datetime(2020 if settled else 2026, 1, 1, tzinfo=_tz.utc)
        return row

    def _db(self, rows):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = rows
        return db

    def _patch_days(self):
        # AAPL req = 1 (US). Settled rows (year 2020) → 5 >= 1; unsettled (2026) → 0.
        return patch(
            "ibkr_core.features.trading.trader._settled_trading_days",
            side_effect=lambda t, s: 5 if t.year == 2020 else 0,
        )

    def test_all_lots_settled_returns_full_held(self):
        db = self._db([self._buy(100, settled=True), self._buy(50, settled=True)])
        with self._patch_days():
            self.assertEqual(self.trader._settled_sellable_qty(db, "AAPL", 150), 150)

    def test_mixed_holds_back_unsettled_lot(self):
        """100 settled + 10 fresh add → held 110, sellable 100 (the stuck-stop fix)."""
        db = self._db([self._buy(100, settled=True), self._buy(10, settled=False)])
        with self._patch_days():
            self.assertEqual(self.trader._settled_sellable_qty(db, "AAPL", 110), 100)

    def test_all_lots_unsettled_returns_zero(self):
        db = self._db([self._buy(30, settled=False)])
        with self._patch_days():
            self.assertEqual(self.trader._settled_sellable_qty(db, "AAPL", 30), 0)

    def test_no_filled_rows_defers_to_held(self):
        """No FILLED ledger → return held_qty, let the coarse possession fallback decide."""
        db = self._db([])
        with self._patch_days():
            self.assertEqual(self.trader._settled_sellable_qty(db, "AAPL", 42), 42)

    def test_unsettled_exceeding_held_clamps_to_zero(self):
        """Defensive: DB-vs-IBKR desync (ledger qty > live held) never yields negative."""
        db = self._db([self._buy(500, settled=False)])
        with self._patch_days():
            self.assertEqual(self.trader._settled_sellable_qty(db, "AAPL", 100), 0)


class TestExceedsConcentrationLimit(unittest.TestCase):
    """Unit tests for the _exceeds_concentration_limit helper."""

    def _make_worker(self, positions):
        w = MagicMock()
        w.get_positions.return_value = positions
        return w

    def test_exceeds_when_existing_plus_new_over_limit(self):
        # net_liq=10000, max_pos=10%=1000, existing=900, new=2*150=300 → 1200 > 1000
        worker = self._make_worker([{"symbol": "AAPL", "market_value": 900.0}])
        self.assertTrue(_exceeds_concentration_limit("AAPL", 2.0, 150.0, 10000.0, worker, _SETTINGS))

    def test_does_not_exceed_when_within_limit(self):
        # net_liq=10000, max_pos=1000, existing=700, new=1*150=150 → 850 < 1000
        worker = self._make_worker([{"symbol": "AAPL", "market_value": 700.0}])
        self.assertFalse(_exceeds_concentration_limit("AAPL", 1.0, 150.0, 10000.0, worker, _SETTINGS))

    def test_no_existing_position_counts_only_new_trade(self):
        # no existing AAPL, new=5*150=750 < max_pos=1000
        worker = self._make_worker([])
        self.assertFalse(_exceeds_concentration_limit("AAPL", 5.0, 150.0, 10000.0, worker, _SETTINGS))

    def test_exactly_at_limit_not_exceeded(self):
        # existing=500, new=5*100=500, total=1000 = max_pos → NOT > → allowed
        worker = self._make_worker([{"symbol": "AAPL", "market_value": 500.0}])
        self.assertFalse(_exceeds_concentration_limit("AAPL", 5.0, 100.0, 10000.0, worker, _SETTINGS))


class TestConcentrationRiskGuard(unittest.IsolatedAsyncioTestCase):
    """Integration tests: concentration guard in execute_trade BUY path."""

    def setUp(self):
        self.mock_worker = MagicMock()
        self.mock_worker.get_market_data = AsyncMock(
            return_value={"bid": 149.9, "ask": 150.1, "last": 150.0, "volume": 1_000_000}
        )
        self.mock_worker.get_avg_volume_20d = AsyncMock(return_value=5_000_000)
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.place_bracket_order = AsyncMock(return_value=42)
        self.mock_worker.place_order = AsyncMock(return_value=42)
        self.trader = Trader(self.mock_worker)
        self.patcher_db = patch('ibkr_core.features.trading.trader.SessionLocal')
        self.mock_session_local = self.patcher_db.start()
        self.mock_db = MagicMock()
        self.mock_session_local.return_value = self.mock_db
        self.patcher_settings = patch('ibkr_core.features.trading.trader._load_settings',
                                      return_value=_SETTINGS)
        self.patcher_settings.start()
        # Isolate sizing from the live VIX feed (see TestPositionSizing.setUp).
        self.patcher_vix = patch('ibkr_core.features.trading.trader._get_vix_size_factor',
                                 return_value=1.0)
        self.patcher_vix.start()

    def tearDown(self):
        self.patcher_db.stop()
        self.patcher_settings.stop()
        self.patcher_vix.stop()

    async def test_rejects_buy_when_existing_plus_new_exceeds_limit(self):
        """Existing AAPL position + new buy > max_position_size_pct → REJECTED_FUNDS."""
        # net_liq=10000, max_pos=10%=1000
        # existing AAPL = 900, new = 2*150=300 → total 1200 > 1000 → rejected
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.get_positions.return_value = [
            {"symbol": "AAPL", "market_value": 900.0, "quantity": 6, "avg_cost": 150.0, "unrealized_pnl": 0.0}
        ]

        trade_req = TradeCreate(symbol="AAPL", quantity=2, side="BUY")
        trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.REJECTED_FUNDS)
        self.mock_worker.place_bracket_order.assert_not_called()

    async def test_allows_buy_when_existing_plus_new_within_limit(self):
        """Existing AAPL position + new buy < max_position_size_pct → submitted."""
        # net_liq=10000, max_pos=10%=1000
        # existing AAPL = 700, new = 1*150=150 → total 850 < 1000 → allowed
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.get_positions.return_value = [
            {"symbol": "AAPL", "market_value": 700.0, "quantity": 4, "avg_cost": 150.0, "unrealized_pnl": 0.0}
        ]
        self.mock_worker.place_bracket_order.return_value = 42

        trade_req = TradeCreate(symbol="AAPL", quantity=1, side="BUY")
        trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.mock_worker.place_bracket_order.assert_called_once()

    async def test_allows_buy_with_no_existing_position(self):
        """No existing position + new buy within limit → submitted."""
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.get_positions.return_value = []  # no existing AAPL
        self.mock_worker.place_bracket_order.return_value = 99

        trade_req = TradeCreate(symbol="AAPL", quantity=5, side="BUY")  # 5*150=750 < 1000
        trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.SUBMITTED)


class TestVIXAdjustedSizing(unittest.TestCase):
    """VIX factor scales position size: CALM=1.0, ELEVATED=0.75, CRISIS=0.5."""

    _BASE = {
        "min_trade_size": 10.0,
        "cash_reserve_pct": 0.0,
        "max_position_size_pct": 100.0,
        "use_kelly_sizing": False,
    }

    def _size(self, vix_tier: str) -> float:
        from ibkr_core.features.trading.trader import _calculate_position_size
        tier_map = {"CALM": 15.0, "ELEVATED": 27.0, "CRISIS": 42.0}
        vix_val = tier_map[vix_tier]
        with patch("ibkr_core.features.trading.trader.get_current_vix", return_value=vix_val):
            return _calculate_position_size(1000.0, 1000.0, 100.0, self._BASE)

    def test_calm_market_full_size(self):
        qty = self._size("CALM")
        self.assertAlmostEqual(qty, 10.0, places=5)

    def test_elevated_market_reduced_size(self):
        qty = self._size("ELEVATED")
        self.assertAlmostEqual(qty, 7.5, places=5)

    def test_crisis_market_half_size(self):
        qty = self._size("CRISIS")
        self.assertAlmostEqual(qty, 5.0, places=5)

    def test_vix_fetch_failure_falls_back_to_full_size(self):
        with patch("ibkr_core.features.trading.trader.get_current_vix", side_effect=Exception("network error")):
            qty = _calculate_position_size(1000.0, 1000.0, 100.0, self._BASE)
        self.assertAlmostEqual(qty, 10.0, places=5)


class TestCalibratedKellySizing(unittest.TestCase):
    """When a calibrated win_prob is supplied, Kelly uses a 0.50 baseline so a
    real probabilistic edge sizes up, independent of the heuristic confidence."""

    _SET = {"take_profit_pct": 15.0, "stop_loss_pct": 8.0}

    def test_calibrated_baseline_is_neutral_at_half(self):
        from ibkr_core.features.trading.trader import _kelly_scale
        # 0.50 calibrated is the neutral baseline → 1.0x; below it scales down.
        self.assertAlmostEqual(_kelly_scale(0.0, self._SET, win_prob=0.50), 1.0, places=3)
        self.assertLess(_kelly_scale(0.0, self._SET, win_prob=0.45), 1.0)

    def test_calibrated_high_prob_scales_up(self):
        from ibkr_core.features.trading.trader import _kelly_scale
        big = _kelly_scale(0.0, self._SET, win_prob=0.70)
        mid = _kelly_scale(0.0, self._SET, win_prob=0.55)
        self.assertGreater(big, mid)
        self.assertGreater(mid, 1.0)  # 0.55 calibrated is already an edge → >baseline

    def test_win_prob_overrides_confidence(self):
        from ibkr_core.features.trading.trader import _kelly_scale
        # low heuristic confidence but strong calibrated prob → sizes up
        self.assertGreater(_kelly_scale(0.30, self._SET, win_prob=0.70), 1.0)

    def test_none_win_prob_uses_confidence_path(self):
        from ibkr_core.features.trading.trader import _kelly_scale
        # baseline confidence 0.65 → ~1.0x
        self.assertAlmostEqual(_kelly_scale(0.65, self._SET), 1.0, places=2)

    def test_position_size_threads_win_probability(self):
        from ibkr_core.features.trading.trader import _calculate_position_size
        base = {"min_trade_size": 1.0, "cash_reserve_pct": 0.0,
                "max_position_size_pct": 100.0, "use_kelly_sizing": True,
                "take_profit_pct": 15.0, "stop_loss_pct": 8.0}
        with patch("ibkr_core.features.trading.trader.get_current_vix", return_value=15.0):
            hi = _calculate_position_size(1000.0, 1000.0, 100.0, base,
                                          confidence=0.5, win_probability=0.75)
            lo = _calculate_position_size(1000.0, 1000.0, 100.0, base,
                                          confidence=0.5, win_probability=0.50)
        self.assertGreater(hi, lo)


class TestSectorConcentrationLimit(unittest.TestCase):
    """_exceeds_concentration_limit blocks trades that push a sector over max_sector_exposure_pct."""

    _SETTINGS = {
        "max_position_size_pct": 50.0,
        "max_sector_exposure_pct": 25.0,
    }

    def _make_worker(self, existing_positions=None):
        w = MagicMock()
        w.get_positions.return_value = existing_positions or []
        return w

    def test_no_sector_data_passes(self):
        """No PositionCompliance records → sector check skipped → passes."""
        worker = self._make_worker([])
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=mock_db):
            result = _exceeds_concentration_limit("AAPL", 1.0, 100.0, 10000.0, worker, self._SETTINGS)
        self.assertFalse(result)

    def test_sector_limit_triggered(self):
        """Existing $2000 in Tech + new $500 > 25% of $10000 = $2500 → blocked."""
        worker = self._make_worker([{"symbol": "MSFT", "market_value": 2000.0}])
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)

        def fake_first(symbol="AAPL"):
            rec = MagicMock()
            rec.metrics = {"sector": "Technology"}
            return rec

        mock_db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
            fake_first("AAPL"),  # target symbol lookup
            fake_first("MSFT"),  # MSFT sector lookup
        ]
        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=mock_db):
            # new_qty=5, price=100 → $500 new. sector_value = 0 (no existing AAPL) + 2000 (MSFT) + 500 new = 2500 = exactly limit
            # 2500 > 2500 is False, so use 2001 existing to push it over
            worker2 = self._make_worker([{"symbol": "MSFT", "market_value": 2001.0}])
            mock_db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
                fake_first("AAPL"),
                fake_first("MSFT"),
            ]
            result = _exceeds_concentration_limit("AAPL", 5.0, 100.0, 10000.0, worker2, self._SETTINGS)
        self.assertTrue(result)

    def test_position_size_limit_still_blocks(self):
        """Single-position check still fires even without sector data."""
        worker = self._make_worker([])
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=mock_db):
            # 100 * 200 = $20000 > 50% of $10000 = $5000 → blocked
            result = _exceeds_concentration_limit("AAPL", 100.0, 200.0, 10000.0, worker, self._SETTINGS)
        self.assertTrue(result)


class TestIsInTradingWindow(unittest.TestCase):
    """is_in_trading_window respects open/close offsets."""

    def _check(self, hour: int, minute: int, start_off: int = 30, end_off: int = 30) -> bool:
        from ibkr_core.core.market_hours import is_in_trading_window
        tz = __import__("zoneinfo").ZoneInfo("America/New_York")
        fake_now = datetime(2024, 1, 22, hour, minute, 0, tzinfo=tz)  # Monday (non-holiday)
        with patch("ibkr_core.core.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            return is_in_trading_window("NMS", start_off, end_off)

    def test_inside_window(self):
        self.assertTrue(self._check(10, 30))  # 10:30 — 30 min after open, 90 min before close

    def test_too_early(self):
        self.assertFalse(self._check(9, 45))  # 9:45 — only 15 min past open (< 30 min offset)

    def test_too_late(self):
        self.assertFalse(self._check(15, 45))  # 15:45 — only 15 min before close (< 30 min offset)

    def test_after_close(self):
        self.assertFalse(self._check(16, 30))  # after close


if __name__ == "__main__":
    unittest.main()
