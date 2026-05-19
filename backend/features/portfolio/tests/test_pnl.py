"""
Tests for GET /api/portfolio/pnl (FR11 – P&L Tracking).

Covers:
- No positions, no trades → all zeros
- Unrealized P&L aggregation from live IBKR positions
- Realized P&L computation from TradeHistory buy/sell fills
- Disconnected IBKR → DB-only realized P&L with 0 unrealized
"""
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from backend.features.portfolio.router import router, get_pnl
from backend.core.models import TradeHistory
from backend.core.state import TradeState


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_request(worker=None):
    """Build a mock FastAPI Request with an optional worker on app.state."""
    request = MagicMock()
    state = MagicMock()
    state.worker = worker
    request.app.state = state
    return request


def _make_worker(connected: bool, positions=None):
    """Build a mock IBKRWorker."""
    worker = MagicMock()
    ib = MagicMock()
    ib.isConnected.return_value = connected
    worker.ib = ib
    worker.get_positions.return_value = positions or []
    return worker


def _make_trade(symbol: str, side: str, quantity: int, fill_price: float) -> TradeHistory:
    """Build a filled TradeHistory row (not persisted)."""
    trade = TradeHistory(
        symbol=symbol,
        side=side,
        quantity=quantity,
        fill_price=fill_price,
        state=TradeState.FILLED,
    )
    return trade


def _make_compliance_row(symbol: str, impure_pct: float):
    """Build a mock PositionCompliance row."""
    row = MagicMock()
    row.symbol = symbol
    row.metrics = {"impure_revenue_pct": impure_pct}
    return row


def _make_db(trades=None, compliance_rows=None):
    """Build a mock SQLAlchemy Session for both TradeHistory and PositionCompliance queries."""
    from backend.core.models import TradeHistory, PositionCompliance
    db = MagicMock()

    trade_q = MagicMock()
    trade_filter = MagicMock()
    trade_filter.all.return_value = trades or []
    trade_q.filter.return_value = trade_filter

    comp_q = MagicMock()
    comp_filter = MagicMock()
    comp_order = MagicMock()
    comp_order.all.return_value = compliance_rows or []
    comp_filter.order_by.return_value = comp_order
    comp_q.filter.return_value = comp_filter

    def _query(model):
        if model is TradeHistory:
            return trade_q
        if model is PositionCompliance:
            return comp_q
        return MagicMock()

    db.query.side_effect = _query
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPnLNoData(unittest.TestCase):
    """No positions, no trades → everything is zero."""

    def test_empty_result(self):
        worker = _make_worker(connected=True, positions=[])
        request = _make_request(worker=worker)
        db = _make_db(trades=[])

        result = get_pnl(request=request, db=db)

        self.assertEqual(result.total_unrealized_pnl, 0.0)
        self.assertEqual(result.total_realized_pnl, 0.0)
        self.assertEqual(result.positions, [])


class TestUnrealizedPnL(unittest.TestCase):
    """Live IBKR positions contribute unrealized P&L."""

    def test_single_position(self):
        positions = [
            {"symbol": "AAPL", "quantity": 10, "avg_cost": 150.0,
             "market_value": 1600.0, "unrealized_pnl": 100.0},
        ]
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db(trades=[])

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_unrealized_pnl, 100.0)
        self.assertEqual(len(result.positions), 1)
        self.assertAlmostEqual(result.positions[0].unrealized_pnl, 100.0)
        self.assertAlmostEqual(result.positions[0].realized_pnl, 0.0)

    def test_multiple_positions_aggregated(self):
        positions = [
            {"symbol": "AAPL", "quantity": 10, "avg_cost": 150.0,
             "market_value": 1600.0, "unrealized_pnl": 100.0},
            {"symbol": "MSFT", "quantity": 5, "avg_cost": 300.0,
             "market_value": 1400.0, "unrealized_pnl": -100.0},
        ]
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db(trades=[])

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_unrealized_pnl, 0.0)
        self.assertEqual(len(result.positions), 2)


class TestRealizedPnL(unittest.TestCase):
    """Realized P&L is computed from TradeHistory buy/sell cash flows."""

    def test_buy_then_sell_profitable(self):
        # BUY 10 @ $100 = -$1000, SELL 10 @ $120 = +$1200 → realized = +$200
        trades = [
            _make_trade("AAPL", "BUY",  10, 100.0),
            _make_trade("AAPL", "SELL", 10, 120.0),
        ]
        worker = _make_worker(connected=True, positions=[])
        request = _make_request(worker=worker)
        db = _make_db(trades=trades)

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_realized_pnl, 200.0)
        self.assertEqual(len(result.positions), 1)
        self.assertAlmostEqual(result.positions[0].realized_pnl, 200.0)
        self.assertEqual(result.positions[0].symbol, "AAPL")

    def test_buy_then_sell_loss(self):
        # BUY 5 @ $200 = -$1000, SELL 5 @ $160 = +$800 → realized = -$200
        trades = [
            _make_trade("TSLA", "BUY",  5, 200.0),
            _make_trade("TSLA", "SELL", 5, 160.0),
        ]
        worker = _make_worker(connected=True, positions=[])
        request = _make_request(worker=worker)
        db = _make_db(trades=trades)

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_realized_pnl, -200.0)

    def test_multiple_symbols(self):
        # AAPL: BUY 10@100 (-1000), SELL 10@120 (+1200) → +200
        # MSFT: BUY 5@300 (-1500), SELL 5@280 (+1400) → -100
        trades = [
            _make_trade("AAPL", "BUY",  10, 100.0),
            _make_trade("AAPL", "SELL", 10, 120.0),
            _make_trade("MSFT", "BUY",  5,  300.0),
            _make_trade("MSFT", "SELL", 5,  280.0),
        ]
        worker = _make_worker(connected=True, positions=[])
        request = _make_request(worker=worker)
        db = _make_db(trades=trades)

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_realized_pnl, 100.0)  # 200 - 100
        pnl_map = {p.symbol: p.realized_pnl for p in result.positions}
        self.assertAlmostEqual(pnl_map["AAPL"], 200.0)
        self.assertAlmostEqual(pnl_map["MSFT"], -100.0)

    def test_partial_sell_still_open(self):
        # BUY 10@100 (-1000), SELL 5@130 (+650) → realized = -350 (still holding 5)
        trades = [
            _make_trade("AAPL", "BUY",  10, 100.0),
            _make_trade("AAPL", "SELL", 5,  130.0),
        ]
        worker = _make_worker(connected=True, positions=[])
        request = _make_request(worker=worker)
        db = _make_db(trades=trades)

        result = get_pnl(request=request, db=db)

        # Cash flow: +650 - 1000 = -350
        self.assertAlmostEqual(result.total_realized_pnl, -350.0)


class TestDisconnectedIBKR(unittest.TestCase):
    """When IBKR is disconnected, unrealized = 0 but realized still comes from DB."""

    def test_disconnected_returns_db_realized_only(self):
        trades = [
            _make_trade("AAPL", "BUY",  10, 100.0),
            _make_trade("AAPL", "SELL", 10, 150.0),
        ]
        # Worker not connected
        worker = _make_worker(connected=False, positions=[])
        request = _make_request(worker=worker)
        db = _make_db(trades=trades)

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_unrealized_pnl, 0.0)
        self.assertAlmostEqual(result.total_realized_pnl, 500.0)  # (150-100)*10
        self.assertEqual(len(result.positions), 1)
        self.assertAlmostEqual(result.positions[0].unrealized_pnl, 0.0)

    def test_no_worker_returns_db_realized_only(self):
        trades = [
            _make_trade("MSFT", "BUY",  3, 300.0),
            _make_trade("MSFT", "SELL", 3, 360.0),
        ]
        request = _make_request(worker=None)
        db = _make_db(trades=trades)

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_unrealized_pnl, 0.0)
        self.assertAlmostEqual(result.total_realized_pnl, 180.0)  # (360-300)*3

    def test_worker_exception_falls_back_to_db(self):
        worker = _make_worker(connected=True)
        worker.get_positions.side_effect = RuntimeError("IBKR exploded")
        trades = [_make_trade("NVDA", "BUY", 2, 500.0)]
        request = _make_request(worker=worker)
        db = _make_db(trades=trades)

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_unrealized_pnl, 0.0)
        self.assertAlmostEqual(result.total_realized_pnl, -1000.0)  # only buy, no sell


class TestMergedLiveAndDB(unittest.TestCase):
    """Symbols from both live positions and DB are merged correctly."""

    def test_live_position_with_realized_history(self):
        # Still holding AAPL (5 shares @ avg 100), sold 5 earlier @ 130.
        # Realized P&L = proceeds - cost_of_sold = 5*130 - 5*100 = +150
        # Formula: raw_net(-350) + remaining_cost_basis(5*100=500) = +150
        live_positions = [
            {"symbol": "AAPL", "quantity": 5, "avg_cost": 100.0,
             "market_value": 600.0, "unrealized_pnl": 100.0},
        ]
        trades = [
            _make_trade("AAPL", "BUY",  10, 100.0),
            _make_trade("AAPL", "SELL", 5,  130.0),
        ]
        worker = _make_worker(connected=True, positions=live_positions)
        request = _make_request(worker=worker)
        db = _make_db(trades=trades)

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_unrealized_pnl, 100.0)
        self.assertAlmostEqual(result.total_realized_pnl, 150.0)
        self.assertEqual(len(result.positions), 1)
        pos = result.positions[0]
        self.assertAlmostEqual(pos.unrealized_pnl, 100.0)
        self.assertAlmostEqual(pos.realized_pnl, 150.0)
        self.assertAlmostEqual(pos.quantity, 5.0)


class TestPurificationAdjustedPnL(unittest.TestCase):
    """
    Purification cost = market_value × impure_revenue_pct from latest PositionCompliance.
    halal_pnl = unrealized_pnl − purification_cost.
    """

    def test_purification_cost_computed_from_compliance(self):
        """AAPL: market_value=1000, impure_pct=0.05 → purification_cost=50."""
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 90.0,
                      "market_value": 1000.0, "unrealized_pnl": 100.0}]
        compliance = [_make_compliance_row("AAPL", 0.05)]
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db(trades=[], compliance_rows=compliance)

        result = get_pnl(request=request, db=db)

        pos = result.positions[0]
        self.assertAlmostEqual(pos.purification_cost, 50.0)

    def test_halal_pnl_subtracts_purification_from_unrealized(self):
        """unrealized=100, purification=50 → halal_pnl=50."""
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 90.0,
                      "market_value": 1000.0, "unrealized_pnl": 100.0}]
        compliance = [_make_compliance_row("AAPL", 0.05)]
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db(trades=[], compliance_rows=compliance)

        result = get_pnl(request=request, db=db)

        pos = result.positions[0]
        self.assertAlmostEqual(pos.halal_pnl, 50.0)  # 100 - 50

    def test_no_compliance_data_purification_cost_zero(self):
        """No PositionCompliance row → purification_cost=0, halal_pnl=unrealized_pnl."""
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 90.0,
                      "market_value": 1000.0, "unrealized_pnl": 150.0}]
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db(trades=[], compliance_rows=[])

        result = get_pnl(request=request, db=db)

        pos = result.positions[0]
        self.assertAlmostEqual(pos.purification_cost, 0.0)
        self.assertAlmostEqual(pos.halal_pnl, 150.0)

    def test_total_purification_cost_in_summary(self):
        """PnLSummary.total_purification_cost = sum of all position purification costs."""
        positions = [
            {"symbol": "AAPL", "quantity": 10, "avg_cost": 90.0,
             "market_value": 1000.0, "unrealized_pnl": 100.0},
            {"symbol": "MSFT", "quantity": 5, "avg_cost": 280.0,
             "market_value": 1500.0, "unrealized_pnl": 50.0},
        ]
        compliance = [
            _make_compliance_row("AAPL", 0.05),   # 1000 * 0.05 = 50
            _make_compliance_row("MSFT", 0.02),   # 1500 * 0.02 = 30
        ]
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db(trades=[], compliance_rows=compliance)

        result = get_pnl(request=request, db=db)

        self.assertAlmostEqual(result.total_purification_cost, 80.0)  # 50 + 30

    def test_zero_impure_pct_no_purification(self):
        """impure_revenue_pct=0 → purification_cost=0, halal_pnl=unrealized_pnl."""
        positions = [{"symbol": "SPUS", "quantity": 5, "avg_cost": 50.0,
                      "market_value": 275.0, "unrealized_pnl": 25.0}]
        compliance = [_make_compliance_row("SPUS", 0.0)]
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db(trades=[], compliance_rows=compliance)

        result = get_pnl(request=request, db=db)

        pos = result.positions[0]
        self.assertAlmostEqual(pos.purification_cost, 0.0)
        self.assertAlmostEqual(pos.halal_pnl, 25.0)


    def test_pnl_account_id_filters_trades(self):
        """With account_id, a second filter scoped to account_id is applied on TradeHistory."""
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0,
                      "market_value": 1200.0, "unrealized_pnl": 200.0}]
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db()

        get_pnl(request=request, db=db, account_id=42)

        from backend.core.models import TradeHistory
        trade_q = db.query(TradeHistory)
        # trades_q.filter(state==FILLED) returns trade_filter mock
        # trades_q.filter(account_id==42) is called on that return value
        trade_filter = trade_q.filter.return_value
        trade_filter.filter.assert_called_once()

    def test_pnl_no_account_id_skips_second_filter(self):
        """Without account_id, only the state filter is applied on TradeHistory."""
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0,
                      "market_value": 1200.0, "unrealized_pnl": 200.0}]
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db()

        get_pnl(request=request, db=db)

        from backend.core.models import TradeHistory
        trade_q = db.query(TradeHistory)
        trade_filter = trade_q.filter.return_value
        trade_filter.filter.assert_not_called()


class TestPositionLevels(unittest.TestCase):
    """days_held, stop_price, target_price, partial_price fields."""

    _SETTINGS = {
        "stop_loss_pct": 5.0,
        "take_profit_pct": 15.0,
        "partial_profit_pct": 10.0,
    }

    def _get_pnl(self, positions, trades):
        worker = _make_worker(connected=True, positions=positions)
        request = _make_request(worker=worker)
        db = _make_db(trades=trades)
        with patch("backend.features.portfolio.router.load_settings", return_value=self._SETTINGS):
            return get_pnl(request=request, db=db)

    def test_price_levels_computed_from_avg_cost(self):
        # avg_cost=100, stop=5%, target=15%, partial=10%
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0,
                      "market_value": 1050.0, "unrealized_pnl": 50.0}]
        result = self._get_pnl(positions, [])
        pos = result.positions[0]
        self.assertAlmostEqual(pos.stop_price, 95.0)
        self.assertAlmostEqual(pos.target_price, 115.0)
        self.assertAlmostEqual(pos.partial_price, 110.0)

    def test_levels_none_for_closed_position(self):
        # Symbol only in DB (fully sold), not in live_map
        trades = [
            _make_trade("AAPL", "BUY",  10, 100.0),
            _make_trade("AAPL", "SELL", 10, 120.0),
        ]
        result = self._get_pnl([], trades)
        pos = result.positions[0]
        self.assertIsNone(pos.stop_price)
        self.assertIsNone(pos.target_price)
        self.assertIsNone(pos.partial_price)

    def test_days_held_from_first_buy(self):
        from datetime import datetime, timedelta
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0,
                      "market_value": 1100.0, "unrealized_pnl": 100.0}]
        buy = _make_trade("AAPL", "BUY", 10, 100.0)
        buy.created_at = datetime.now() - timedelta(days=30)
        result = self._get_pnl(positions, [buy])
        pos = result.positions[0]
        self.assertIn(pos.days_held, (29, 30))

    def test_days_held_uses_earliest_buy(self):
        from datetime import datetime, timedelta
        positions = [{"symbol": "AAPL", "quantity": 15, "avg_cost": 105.0,
                      "market_value": 1600.0, "unrealized_pnl": 75.0}]
        buy1 = _make_trade("AAPL", "BUY", 10, 100.0)
        buy1.created_at = datetime.now() - timedelta(days=60)
        buy2 = _make_trade("AAPL", "BUY", 5, 115.0)
        buy2.created_at = datetime.now() - timedelta(days=10)
        result = self._get_pnl(positions, [buy1, buy2])
        pos = result.positions[0]
        self.assertIn(pos.days_held, (59, 60))

    def test_days_held_none_when_no_buy_in_db(self):
        # Position held but no BUY in DB (manually bought in TWS)
        positions = [{"symbol": "ASML", "quantity": 5, "avg_cost": 800.0,
                      "market_value": 4100.0, "unrealized_pnl": 100.0}]
        result = self._get_pnl(positions, [])
        pos = result.positions[0]
        self.assertIsNone(pos.days_held)

    def test_levels_zero_avg_cost_returns_none(self):
        # avg_cost=0 (fractional / crypto edge case) → no meaningful levels
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 0.0,
                      "market_value": 500.0, "unrealized_pnl": 500.0}]
        result = self._get_pnl(positions, [])
        pos = result.positions[0]
        self.assertIsNone(pos.stop_price)
        self.assertIsNone(pos.target_price)
        self.assertIsNone(pos.partial_price)


if __name__ == "__main__":
    unittest.main()
