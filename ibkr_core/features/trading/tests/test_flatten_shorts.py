"""Tests for the /api/trades/flatten-shorts buy-to-cover endpoint."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ibkr_core.features.trading.router import flatten_shorts, FlattenShortsRequest


def _request_with_worker(worker):
    req = MagicMock()
    req.app.state.account_manager = None
    req.app.state.worker = worker
    return req


class TestFlattenShorts(unittest.IsolatedAsyncioTestCase):
    def _worker(self, positions):
        w = MagicMock()
        w.ib.isConnected.return_value = True
        w.get_positions = MagicMock(return_value=positions)
        w.place_order = AsyncMock(return_value=123)
        return w

    async def test_covers_only_shorts_with_abs_qty(self):
        w = self._worker([
            {"symbol": "NVDA", "quantity": -320},
            {"symbol": "AMD", "quantity": -158},
            {"symbol": "AAPL", "quantity": 100},  # long — must be left alone
        ])
        with patch("ibkr_core.features.trading.router._resolve_worker", return_value=w), \
             patch.dict("os.environ", {"EMERGENCY_PIN": "1234"}):
            out = await flatten_shorts(FlattenShortsRequest(emergency_pin="1234"), _request_with_worker(w))

        self.assertEqual(out["total"], 2)
        covered = {c["symbol"]: c["quantity"] for c in out["covered"]}
        self.assertEqual(covered, {"NVDA": 320.0, "AMD": 158.0})  # abs qty, longs excluded
        # Every placed order was a BUY of the abs short size.
        sides = [c.args[0].side for c in w.place_order.call_args_list]
        qtys = [c.args[0].quantity for c in w.place_order.call_args_list]
        self.assertEqual(set(sides), {"BUY"})
        self.assertCountEqual(qtys, [320.0, 158.0])

    async def test_no_shorts_is_noop(self):
        w = self._worker([{"symbol": "AAPL", "quantity": 100}])
        with patch("ibkr_core.features.trading.router._resolve_worker", return_value=w), \
             patch.dict("os.environ", {"EMERGENCY_PIN": "1234"}):
            out = await flatten_shorts(FlattenShortsRequest(emergency_pin="1234"), _request_with_worker(w))
        self.assertEqual(out["total"], 0)
        w.place_order.assert_not_called()

    async def test_bad_pin_rejected(self):
        from fastapi import HTTPException
        w = self._worker([{"symbol": "NVDA", "quantity": -10}])
        with patch("ibkr_core.features.trading.router._resolve_worker", return_value=w), \
             patch.dict("os.environ", {"EMERGENCY_PIN": "1234"}):
            with self.assertRaises(HTTPException) as ctx:
                await flatten_shorts(FlattenShortsRequest(emergency_pin="wrong"), _request_with_worker(w))
        self.assertEqual(ctx.exception.status_code, 403)
        w.place_order.assert_not_called()

    async def test_no_pin_configured_503(self):
        from fastapi import HTTPException
        w = self._worker([{"symbol": "NVDA", "quantity": -10}])
        with patch("ibkr_core.features.trading.router._resolve_worker", return_value=w), \
             patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("EMERGENCY_PIN", None)
            with self.assertRaises(HTTPException) as ctx:
                await flatten_shorts(FlattenShortsRequest(emergency_pin="x"), _request_with_worker(w))
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
