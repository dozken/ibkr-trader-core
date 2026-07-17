"""
HTTP-level tests for GET /api/portfolio/purification/pending.

Covers:
- Disconnected IBKR → empty list
- No worker on app.state → empty list
- No positions held → empty list
- Returns correct PurificationPending fields
- Dividend fetch exception falls back to empty dividends_map
- Already-purified amount deducted correctly in HTTP response
"""
import unittest
from unittest.mock import MagicMock, AsyncMock

from ibkr_core.features.portfolio.router import get_pending_purification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(worker=None):
    req = MagicMock()
    state = MagicMock()
    state.worker = worker
    req.app.state = state
    return req


def _make_worker(connected: bool, positions=None, dividends=None):
    worker = MagicMock()
    worker.ib.isConnected.return_value = connected
    worker.get_positions.return_value = positions or []
    worker.get_dividends_batch = AsyncMock(return_value=dividends or [])
    return worker


def _make_compliance_row(symbol: str, impure_pct: float):
    row = MagicMock()
    row.symbol = symbol
    row.metrics = {"impure_revenue_pct": impure_pct}
    return row


def _make_purification_row(symbol: str, total: float):
    row = MagicMock()
    row.symbol = symbol
    row.total = total
    return row


def _make_db(compliance_rows=None, purification_rows=None):
    from ibkr_core.core.models import PositionCompliance, PurificationHistory
    db = MagicMock()

    comp_q = MagicMock()
    comp_q.filter.return_value.order_by.return_value.all.return_value = compliance_rows or []

    purify_q = MagicMock()
    purify_q.filter.return_value.group_by.return_value.all.return_value = purification_rows or []

    def _query(*args):
        # Single model argument → route by model type
        first = args[0] if args else None
        if first is PositionCompliance:
            return comp_q
        # Two-column query: (PurificationHistory.symbol, func.sum(...))
        # first arg is an instrumented attribute whose parent class is PurificationHistory
        try:
            if first.class_ is PurificationHistory:
                return purify_q
        except AttributeError:
            pass
        return purify_q

    db.query.side_effect = _query
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPurificationEndpointNoConnection(unittest.IsolatedAsyncioTestCase):

    async def test_returns_empty_when_worker_missing(self):
        req = _make_request(worker=None)
        result = await get_pending_purification(request=req, db=MagicMock())
        self.assertEqual(result, [])

    async def test_returns_empty_when_ibkr_disconnected(self):
        worker = _make_worker(connected=False)
        req = _make_request(worker=worker)
        result = await get_pending_purification(request=req, db=MagicMock())
        self.assertEqual(result, [])

    async def test_returns_empty_when_no_positions(self):
        worker = _make_worker(connected=True, positions=[])
        req = _make_request(worker=worker)
        result = await get_pending_purification(request=req, db=MagicMock())
        self.assertEqual(result, [])


class TestPurificationEndpointFields(unittest.IsolatedAsyncioTestCase):

    async def _run(self, positions, dividends, compliance_rows, purification_rows=None):
        worker = _make_worker(connected=True, positions=positions, dividends=dividends)
        req = _make_request(worker=worker)
        db = _make_db(
            compliance_rows=compliance_rows,
            purification_rows=purification_rows or [],
        )
        return await get_pending_purification(request=req, db=db)

    async def test_basic_pending_calculation(self):
        # AAPL: div=100, impure=5% → pending=5.0
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0,
                      "market_value": 1000.0, "unrealized_pnl": 0.0}]
        dividends = [{"symbol": "AAPL", "total_received": 100.0,
                      "past12_per_share": 1.0, "quantity": 10}]
        compliance = [_make_compliance_row("AAPL", 0.05)]

        result = await self._run(positions, dividends, compliance)

        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual(row.symbol, "AAPL")
        self.assertAlmostEqual(row.purification_needed, 5.0)
        self.assertAlmostEqual(row.pending, 5.0)
        self.assertAlmostEqual(row.already_purified, 0.0)
        self.assertAlmostEqual(row.impure_pct, 0.05)
        self.assertAlmostEqual(row.dividend_total, 100.0)

    async def test_already_purified_deducted(self):
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0,
                      "market_value": 1000.0, "unrealized_pnl": 0.0}]
        dividends = [{"symbol": "AAPL", "total_received": 100.0,
                      "past12_per_share": 1.0, "quantity": 10}]
        compliance = [_make_compliance_row("AAPL", 0.05)]
        purified = [_make_purification_row("AAPL", 3.0)]

        result = await self._run(positions, dividends, compliance, purified)

        row = result[0]
        self.assertAlmostEqual(row.already_purified, 3.0)
        self.assertAlmostEqual(row.pending, 2.0)

    async def test_zero_impure_pct_no_pending(self):
        positions = [{"symbol": "MSFT", "quantity": 5, "avg_cost": 300.0,
                      "market_value": 1500.0, "unrealized_pnl": 0.0}]
        dividends = [{"symbol": "MSFT", "total_received": 200.0,
                      "past12_per_share": 4.0, "quantity": 5}]
        compliance = [_make_compliance_row("MSFT", 0.0)]

        result = await self._run(positions, dividends, compliance)

        row = result[0]
        self.assertAlmostEqual(row.pending, 0.0)
        self.assertAlmostEqual(row.purification_needed, 0.0)

    async def test_dividend_fetch_exception_returns_zero_pending(self):
        positions = [{"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0,
                      "market_value": 1000.0, "unrealized_pnl": 0.0}]
        worker = _make_worker(connected=True, positions=positions)
        worker.get_dividends_batch = AsyncMock(side_effect=Exception("IBKR timeout"))
        req = _make_request(worker=worker)
        compliance = [_make_compliance_row("AAPL", 0.05)]
        db = _make_db(compliance_rows=compliance)

        result = await get_pending_purification(request=req, db=db)

        # dividends_map is {} after exception → pending = 0
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].pending, 0.0)

    async def test_multiple_positions_returned(self):
        positions = [
            {"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0,
             "market_value": 1000.0, "unrealized_pnl": 0.0},
            {"symbol": "MSFT", "quantity": 5, "avg_cost": 300.0,
             "market_value": 1500.0, "unrealized_pnl": 0.0},
        ]
        dividends = [
            {"symbol": "AAPL", "total_received": 100.0, "past12_per_share": 1.0, "quantity": 10},
            {"symbol": "MSFT", "total_received": 50.0, "past12_per_share": 2.0, "quantity": 5},
        ]
        compliance = [
            _make_compliance_row("AAPL", 0.04),   # 100 * 0.04 = 4
            _make_compliance_row("MSFT", 0.02),   # 50 * 0.02 = 1
        ]

        result = await self._run(positions, dividends, compliance)

        self.assertEqual(len(result), 2)
        sym_map = {r.symbol: r for r in result}
        self.assertAlmostEqual(sym_map["AAPL"].pending, 4.0)
        self.assertAlmostEqual(sym_map["MSFT"].pending, 1.0)


if __name__ == "__main__":
    unittest.main()
