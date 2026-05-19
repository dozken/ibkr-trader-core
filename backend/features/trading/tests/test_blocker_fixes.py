"""Tests for the 3 production blockers:
  1. Peak NLV persistence across restarts
  2. Open order management (get/cancel)
  3. Possession confirmation fallback when fill event was missed
"""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

from backend.core.state import TradeState
from backend.features.trading.schemas import TradeCreate
from backend.features.compliance.schemas import ComplianceStatus

_COMPLIANT = ComplianceStatus(
    symbol="AAPL", sector="Technology", is_compliant=True,
    debt_to_mkt_cap=0.1, cash_to_mkt_cap=0.1, impure_revenue_pct=0.01,
)
_SETTINGS = {
    "min_trade_size": 10.0,
    "cash_reserve_pct": 5.0,
    "max_position_size_pct": 10.0,
    "risk_profile": "CONSERVATIVE",
    "stop_loss_pct": None,
    "take_profit_pct": None,
    "twap_threshold_pct": 100.0,
}


# ── Blocker 1: Peak NLV seeded from DB ────────────────────────────────────────

class TestPeakNLVSeed(unittest.TestCase):

    def test_seeds_from_db_on_startup(self):
        from backend.features.portfolio.loops import _load_peak_nlv_from_db
        snap = MagicMock()
        snap.total_value = 42000.0
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.scalar.return_value = 42000.0

        with patch("backend.features.portfolio.loops.SessionLocal", return_value=mock_db):
            result = _load_peak_nlv_from_db()
        self.assertAlmostEqual(result, 42000.0)

    def test_returns_zero_when_no_snapshots(self):
        from backend.features.portfolio.loops import _load_peak_nlv_from_db
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.scalar.return_value = None

        with patch("backend.features.portfolio.loops.SessionLocal", return_value=mock_db):
            result = _load_peak_nlv_from_db()
        self.assertEqual(result, 0.0)

    def test_returns_zero_on_db_error(self):
        from backend.features.portfolio.loops import _load_peak_nlv_from_db
        with patch("backend.features.portfolio.loops.SessionLocal", side_effect=Exception("db down")):
            result = _load_peak_nlv_from_db()
        self.assertEqual(result, 0.0)


# ── Blocker 2: Open order management ──────────────────────────────────────────

class TestOpenOrderManagement(unittest.TestCase):

    def _make_worker(self):
        from backend.features.trading.worker import IBKRWorker
        w = MagicMock(spec=IBKRWorker)
        w.ib = MagicMock()
        w.get_open_orders = IBKRWorker.get_open_orders.__get__(w, IBKRWorker)
        w.cancel_all_orders = IBKRWorker.cancel_all_orders.__get__(w, IBKRWorker)
        w.cancel_order = IBKRWorker.cancel_order.__get__(w, IBKRWorker)
        return w

    def test_get_open_orders_returns_dicts(self):
        w = self._make_worker()
        t = MagicMock()
        t.order.orderId = 101
        t.contract.symbol = "AAPL"
        t.order.action = "BUY"
        t.order.totalQuantity = 10.0
        t.order.orderType = "MKT"
        t.orderStatus.status = "Submitted"
        t.order.lmtPrice = None
        t.order.auxPrice = None
        w.ib.openTrades.return_value = [t]

        result = w.get_open_orders()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["order_id"], 101)
        self.assertEqual(result[0]["symbol"], "AAPL")

    def test_cancel_all_orders_calls_global_cancel(self):
        w = self._make_worker()
        w.cancel_all_orders()
        w.ib.reqGlobalCancel.assert_called_once()

    def test_cancel_order_success(self):
        w = self._make_worker()
        t = MagicMock()
        t.order.orderId = 55
        w.ib.openTrades.return_value = [t]

        result = w.cancel_order(55)
        self.assertTrue(result)
        w.ib.cancelOrder.assert_called_once_with(t.order)

    def test_cancel_order_not_found(self):
        w = self._make_worker()
        w.ib.openTrades.return_value = []
        result = w.cancel_order(999)
        self.assertFalse(result)
        w.ib.cancelOrder.assert_not_called()

    def test_get_open_orders_returns_empty_on_error(self):
        w = self._make_worker()
        w.ib.openTrades.side_effect = Exception("connection lost")
        result = w.get_open_orders()
        self.assertEqual(result, [])


# ── Blocker 2b: reconcile uses openTrades not trades() ────────────────────────

class TestReconciliation(unittest.IsolatedAsyncioTestCase):

    async def test_reconcile_marks_filled_when_position_exists(self):
        """BUY order not in active orders but position exists → marked FILLED."""
        from backend.features.trading.reconciliation import reconcile_with_ibkr
        from backend.core.models import TradeHistory

        worker = MagicMock()
        worker.ib.isConnected.return_value = True
        worker.get_positions.return_value = [{"symbol": "AAPL", "quantity": 10}]
        worker.ib.openTrades.return_value = []  # order no longer in IBKR open list

        trade = MagicMock(spec=TradeHistory)
        trade.ibkr_order_id = 42
        trade.side = "BUY"
        trade.symbol = "AAPL"
        trade.state = TradeState.SUBMITTED

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.all.return_value = [trade]

        with patch("backend.features.trading.reconciliation.SessionLocal", return_value=mock_db):
            await reconcile_with_ibkr(worker)

        self.assertEqual(trade.state, TradeState.FILLED)

    async def test_reconnect_triggers_reconciliation(self):
        """After successful reconnect, reconcile_with_ibkr is called."""
        from backend.features.trading.worker import IBKRWorker
        w = MagicMock(spec=IBKRWorker)
        w._reconnecting = False
        w._reconnect = IBKRWorker._reconnect.__get__(w, IBKRWorker)
        w.connect = AsyncMock(return_value=True)

        with patch("backend.features.trading.reconciliation.reconcile_with_ibkr", new_callable=AsyncMock) as mock_recon, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await w._reconnect()

        mock_recon.assert_called_once_with(w)


# ── Blocker 3: Possession confirmation fallback ────────────────────────────────

class TestPossessionFallback(unittest.IsolatedAsyncioTestCase):

    def _make_trader_with_db(self, positions, oldest_buy_days_ago):
        from backend.features.trading.trader import Trader
        worker = MagicMock()
        worker.get_positions.return_value = positions
        worker.get_last_price = AsyncMock(return_value=150.0)
        worker.get_available_funds.return_value = 10000.0
        worker.get_net_liquidation.return_value = 10000.0
        worker.get_avg_volume_20d = AsyncMock(return_value=1_000_000)
        worker.get_market_data = AsyncMock(
            return_value={"bid": 149.9, "ask": 150.1, "last": 150.0}
        )
        trader = Trader(worker)

        db = MagicMock()
        # No FILLED record
        db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
            None,  # first call: settled states query → no record
        ]
        if positions:
            # second call: oldest SUBMITTED query
            submitted = MagicMock()
            submitted.state = TradeState.SUBMITTED
            submitted.updated_at = datetime.now(timezone.utc) - timedelta(days=oldest_buy_days_ago)
            db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
                None, submitted,
            ]
        return trader, db

    def test_fallback_confirms_when_position_exists_and_old_enough(self):
        from backend.features.trading.trader import Trader
        worker = MagicMock()
        worker.get_positions.return_value = [{"symbol": "AAPL", "quantity": 10}]
        trader = Trader(worker)

        settled = MagicMock()
        settled.state = TradeState.SUBMITTED
        settled.updated_at = datetime.now(timezone.utc) - timedelta(days=3)

        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
            None,      # no FILLED record
            settled,   # oldest SUBMITTED record
        ]

        result = trader._is_possession_confirmed(db, "AAPL")
        self.assertTrue(result)
        # Should heal the record
        self.assertEqual(settled.state, TradeState.FILLED)

    def test_fallback_blocks_when_position_too_new(self):
        from backend.features.trading.trader import Trader
        worker = MagicMock()
        worker.get_positions.return_value = [{"symbol": "AAPL", "quantity": 10}]
        trader = Trader(worker)

        settled = MagicMock()
        settled.state = TradeState.SUBMITTED
        settled.updated_at = datetime.now(timezone.utc) - timedelta(days=1)

        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
            None, settled,
        ]

        result = trader._is_possession_confirmed(db, "AAPL")
        self.assertFalse(result)

    def test_fallback_blocks_when_position_not_held(self):
        from backend.features.trading.trader import Trader
        worker = MagicMock()
        worker.get_positions.return_value = []  # not in IBKR
        trader = Trader(worker)

        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        result = trader._is_possession_confirmed(db, "AAPL")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
