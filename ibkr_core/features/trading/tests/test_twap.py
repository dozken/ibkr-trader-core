"""Tests for TWAP execution and IBKR trailing stop wiring."""
import asyncio
import unittest
from copy import copy
from unittest.mock import AsyncMock, MagicMock, call, patch

from ibkr_core.features.trading.schemas import TradeCreate
from ibkr_core.features.compliance.schemas import ComplianceStatus
from ibkr_core.core.state import TradeState
from ibkr_core.features.trading.trader import Trader

_COMPLIANT = ComplianceStatus(
    symbol="AAPL", sector="Technology", is_compliant=True,
    debt_to_mkt_cap=0.1, cash_to_mkt_cap=0.1, impure_revenue_pct=0.01,
)
_SETTINGS_TWAP = {
    "min_trade_size": 10.0,
    "cash_reserve_pct": 5.0,
    "max_position_size_pct": 10.0,
    "max_slippage_pct": 0.5,
    "max_liquidity_pct": 50.0,   # don't downsize — we want TWAP path
    "twap_threshold_pct": 0.5,   # 0.5% of avg daily volume triggers TWAP
    "twap_slices": 3,
    "twap_interval_secs": 1,
    "risk_profile": "CONSERVATIVE",
    "stop_loss_pct": None,
    "take_profit_pct": None,
    "use_atr_stops": False,
}


class TestTWAPExecution(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.worker.get_last_price = AsyncMock(return_value=100.0)
        self.worker.get_available_funds.return_value = 50000.0
        self.worker.get_net_liquidation.return_value = 50000.0
        self.worker.get_positions.return_value = []
        self.worker.get_market_data = AsyncMock(
            return_value={"bid": 99.9, "ask": 100.1, "last": 100.0}
        )
        # avg_vol small enough that any reasonable qty triggers TWAP (0.5% threshold)
        self.worker.get_avg_volume_20d = AsyncMock(return_value=100)
        self.worker.place_twap_bracket_order = AsyncMock(return_value=42)
        self.worker.place_bracket_order = AsyncMock(return_value=99)

        self.trader = Trader(self.worker)
        self.patcher_db = patch("ibkr_core.features.trading.trader.SessionLocal")
        mock_sl = self.patcher_db.start()
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        self.patcher_settings = patch(
            "ibkr_core.features.trading.trader._load_settings", return_value=_SETTINGS_TWAP
        )
        self.patcher_settings.start()

    def tearDown(self):
        self.patcher_db.stop()
        self.patcher_settings.stop()

    async def test_twap_triggered_when_qty_exceeds_threshold(self):
        """qty/avg_vol > 0.5% → place_twap_bracket_order called, not place_bracket_order."""
        # qty auto-sized: 50k * 10% = $5000 / $100 = 50 shares. 50/100 = 50% >> 0.5%
        req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
        trade = await self.trader.execute_trade(req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.worker.place_twap_bracket_order.assert_called_once()
        self.worker.place_bracket_order.assert_not_called()

    async def test_twap_not_triggered_when_below_threshold(self):
        """qty/avg_vol < threshold → regular bracket order used."""
        self.worker.get_avg_volume_20d = AsyncMock(return_value=100_000_000)  # huge volume
        req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
        trade = await self.trader.execute_trade(req, pre_screened=_COMPLIANT)

        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.worker.place_bracket_order.assert_called_once()
        self.worker.place_twap_bracket_order.assert_not_called()

    async def test_twap_passes_correct_slice_count_and_interval(self):
        req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
        await self.trader.execute_trade(req, pre_screened=_COMPLIANT)

        _, kwargs = self.worker.place_twap_bracket_order.call_args
        self.assertEqual(kwargs.get("n_slices") or self.worker.place_twap_bracket_order.call_args[0][5], 3)


class TestTWAPWorkerMethod(unittest.IsolatedAsyncioTestCase):
    async def test_first_slice_placed_immediately(self):
        from ibkr_core.features.trading.worker import IBKRWorker
        w = MagicMock(spec=IBKRWorker)
        w.place_bracket_order = AsyncMock(side_effect=[10, 11, 12])
        w.place_twap_bracket_order = IBKRWorker.place_twap_bracket_order.__get__(w, IBKRWorker)

        trade = TradeCreate(symbol="AAPL", quantity=3.0, side="BUY")
        with patch("asyncio.create_task"):
            oid = await w.place_twap_bracket_order(
                trade, stop_price=90.0, take_profit_price=110.0,
                exchange="NMS", n_slices=3, interval_secs=1,
            )
        self.assertEqual(oid, 10)
        self.assertEqual(w.place_bracket_order.call_count, 1)

    async def test_only_first_slice_submitted_by_worker(self):
        # Remaining slices are managed by Trader._run_twap_slices (DB-persisted runner),
        # not by the worker directly. Worker submits exactly 1 slice.
        from ibkr_core.features.trading.worker import IBKRWorker
        w = MagicMock(spec=IBKRWorker)
        order_ids = iter([10, 11, 12])
        w.place_bracket_order = AsyncMock(side_effect=order_ids)
        w.place_twap_bracket_order = IBKRWorker.place_twap_bracket_order.__get__(w, IBKRWorker)

        trade = TradeCreate(symbol="AAPL", quantity=3.0, side="BUY")
        oid = await w.place_twap_bracket_order(
            trade, stop_price=90.0, take_profit_price=110.0,
            exchange="NMS", n_slices=3, interval_secs=0,
        )
        self.assertEqual(oid, 10)
        self.assertEqual(w.place_bracket_order.call_count, 1)

    async def test_slice_qty_equals_total_divided_by_n(self):
        from ibkr_core.features.trading.worker import IBKRWorker
        w = MagicMock(spec=IBKRWorker)
        w.place_bracket_order = AsyncMock(return_value=1)
        w.place_twap_bracket_order = IBKRWorker.place_twap_bracket_order.__get__(w, IBKRWorker)

        trade = TradeCreate(symbol="AAPL", quantity=9.0, side="BUY")
        await w.place_twap_bracket_order(trade, 90.0, 110.0, "NMS", n_slices=3, interval_secs=0)
        called_trade = w.place_bracket_order.call_args[0][0]
        self.assertAlmostEqual(called_trade.quantity, 3.0)


class TestTrailingStopOrder(unittest.IsolatedAsyncioTestCase):
    """place_bracket_order uses IBKR TRAIL order when trailing_amount is set."""

    async def _place(self, trailing_amount):
        from ib_insync import StopOrder
        from ibkr_core.features.trading.worker import IBKRWorker
        w = MagicMock(spec=IBKRWorker)
        w.ib = MagicMock()
        w.ib.qualifyContractsAsync = AsyncMock()
        w.ib.reqAllOpenOrdersAsync = AsyncMock(return_value=[])
        w.place_bracket_order = IBKRWorker.place_bracket_order.__get__(w, IBKRWorker)

        parent = MagicMock(); parent.orderId = 1
        tp = MagicMock()
        sl = StopOrder("SELL", 10.0, 90.0)
        w.ib.bracketOrder.return_value = [parent, tp, sl]

        trade = TradeCreate(symbol="AAPL", quantity=10.0, side="BUY")
        with patch("ibkr_core.features.trading.worker.get_exchange_config",
                   return_value=("America/New_York", [], "SMART", "USD")), \
             patch("asyncio.sleep"):
            await w.place_bracket_order(trade, stop_price=90.0, take_profit_price=110.0,
                                        exchange="NMS", trailing_amount=trailing_amount)
        return w.ib.placeOrder.call_args_list

    async def test_trailing_stop_order_type_when_trailing_amount_set(self):
        calls = await self._place(trailing_amount=5.0)
        # 3 calls: parent, take_profit, stop_loss
        stop_order = calls[2][0][1]  # second arg of third call
        self.assertEqual(stop_order.orderType, "TRAIL")
        self.assertAlmostEqual(stop_order.auxPrice, 5.0)

    async def test_fixed_stop_order_when_no_trailing_amount(self):
        from ib_insync import StopOrder
        calls = await self._place(trailing_amount=None)
        stop_order = calls[2][0][1]
        self.assertIsInstance(stop_order, StopOrder)

    async def test_fixed_stop_order_when_trailing_amount_zero(self):
        from ib_insync import StopOrder
        calls = await self._place(trailing_amount=0.0)
        stop_order = calls[2][0][1]
        self.assertIsInstance(stop_order, StopOrder)


if __name__ == "__main__":
    unittest.main()
