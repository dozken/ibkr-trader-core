import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_worker(nlv: float = 10000.0, connected: bool = True):
    w = MagicMock()
    w.ib.isConnected.return_value = connected
    w.get_net_liquidation.return_value = nlv
    w.get_available_funds.return_value = nlv * 0.1
    w.get_positions.return_value = []
    return w


async def _run_one_tick(worker, health: dict, settings: dict):
    """Run one iteration of portfolio_snapshot_loop logic, extracted for testing."""
    from backend.features.portfolio.loops import portfolio_snapshot_loop
    import asyncio as _asyncio

    async def _fake_sleep(_):
        raise _asyncio.CancelledError

    async def _fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("backend.features.portfolio.loops._load_peak_nlv_from_db", return_value=health.get("peak_nlv", 0.0)), \
         patch("backend.features.portfolio.loops.asyncio.sleep", side_effect=_fake_sleep), \
         patch("backend.features.portfolio.loops.load_settings", return_value=settings), \
         patch("backend.features.portfolio.loops.send_alert", new_callable=AsyncMock) as mock_alert, \
         patch("backend.features.portfolio.loops.asyncio.to_thread", side_effect=_fake_to_thread), \
         patch("backend.features.portfolio.loops.SessionLocal"):
        try:
            await portfolio_snapshot_loop(worker, health)
        except asyncio.CancelledError:
            pass
        return mock_alert


class TestDrawdownCircuitBreaker(unittest.IsolatedAsyncioTestCase):

    async def test_peak_nlv_tracked(self):
        health = {"portfolio_snapshot_loop": {"status": "starting"}}
        worker = _make_worker(nlv=12000.0)
        await _run_one_tick(worker, health, {"max_drawdown_pct": 15.0, "alert_channels": []})
        self.assertAlmostEqual(health["peak_nlv"], 12000.0)

    async def test_no_trigger_within_limit(self):
        health = {"portfolio_snapshot_loop": {"status": "starting"}, "peak_nlv": 10000.0}
        worker = _make_worker(nlv=9000.0)  # 10% drawdown < 15% limit
        mock_alert = await _run_one_tick(worker, health, {"max_drawdown_pct": 15.0, "alert_channels": []})
        self.assertFalse(health["drawdown_triggered"])
        mock_alert.assert_not_called()

    async def test_trigger_fires_when_exceeded(self):
        health = {"portfolio_snapshot_loop": {"status": "starting"}, "peak_nlv": 10000.0}
        worker = _make_worker(nlv=8000.0)  # 20% drawdown > 15% limit
        mock_alert = await _run_one_tick(worker, health, {"max_drawdown_pct": 15.0, "alert_channels": ["telegram"]})
        self.assertTrue(health["drawdown_triggered"])
        mock_alert.assert_called_once()
        args = mock_alert.call_args[0]
        self.assertIn("20.0%", args[1])

    async def test_no_double_trigger(self):
        health = {"portfolio_snapshot_loop": {"status": "starting"}, "peak_nlv": 10000.0, "drawdown_triggered": True}
        worker = _make_worker(nlv=8000.0)
        mock_alert = await _run_one_tick(worker, health, {"max_drawdown_pct": 15.0, "alert_channels": []})
        mock_alert.assert_not_called()

    async def test_auto_recovery_when_drawdown_halves(self):
        # Triggered at 20% drawdown; NLV recovers so drawdown < 7.5% → auto-reset
        health = {
            "portfolio_snapshot_loop": {"status": "starting"},
            "peak_nlv": 10000.0,
            "drawdown_triggered": True,
        }
        worker = _make_worker(nlv=9800.0)  # 2% drawdown < 7.5% (15%/2)
        await _run_one_tick(worker, health, {"max_drawdown_pct": 15.0, "alert_channels": []})
        self.assertFalse(health["drawdown_triggered"])


class TestDailyLossLimit(unittest.TestCase):

    def _check(self, open_nlv: float, current_nlv: float, max_loss_pct: float = 5.0) -> bool:
        from backend.features.trading.loops import _exceeds_daily_loss_limit
        from backend.core.models import PortfolioSnapshot

        snap = MagicMock(spec=PortfolioSnapshot)
        snap.total_value = open_nlv

        worker = MagicMock()
        worker.get_net_liquidation.return_value = current_nlv

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = snap

        settings = {"max_daily_loss_pct": max_loss_pct}
        with patch("backend.core.database.SessionLocal", return_value=mock_db):
            return _exceeds_daily_loss_limit(worker, settings)

    def test_no_loss_passes(self):
        self.assertFalse(self._check(10000.0, 10500.0))

    def test_loss_below_limit_passes(self):
        self.assertFalse(self._check(10000.0, 9600.0))  # -4% < -5%

    def test_loss_exceeds_limit_blocks(self):
        self.assertTrue(self._check(10000.0, 9400.0))  # -6% > -5%

    def test_disabled_when_pct_zero(self):
        from backend.features.trading.loops import _exceeds_daily_loss_limit
        worker = MagicMock()
        # Returns early before any DB access when pct=0
        self.assertFalse(_exceeds_daily_loss_limit(worker, {"max_daily_loss_pct": 0.0}))

    def test_no_snapshot_passes(self):
        from backend.features.trading.loops import _exceeds_daily_loss_limit
        worker = MagicMock()
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        with patch("backend.core.database.SessionLocal", return_value=mock_db):
            result = _exceeds_daily_loss_limit(worker, {"max_daily_loss_pct": 5.0})
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
