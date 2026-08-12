"""
Tests for new exit logic added to main_loop:
- Trailing stop (HWM-based)
- Time-based exit (stale thesis)
- Partial profit
- Re-entry cooldown
- Pullback entry filter
"""
import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
from ibkr_core.core.clock import db_now


# ── Helpers ───────────────────────────────────────────────────────────────

def _loops_module():
    from ibkr_core.features.trading import loops
    return loops


class TestRegimeAtrMultiplier(unittest.TestCase):
    """ATR stop multiplier widens with the VIX regime (CALM<ELEVATED<CRISIS)."""

    def _mult(self, tier, settings=None):
        loops = _loops_module()
        with patch("ibkr_core.features.compliance.vix.get_current_vix", return_value=20.0), \
             patch("ibkr_core.features.compliance.vix.vix_to_tier", return_value=tier):
            return loops._regime_atr_multiplier(settings or {})

    def test_calm_is_base(self):
        self.assertAlmostEqual(self._mult("CALM", {"atr_stop_multiplier": 2.5}), 2.5, places=3)

    def test_crisis_wider_than_calm(self):
        calm = self._mult("CALM", {"atr_stop_multiplier": 2.5})
        elevated = self._mult("ELEVATED", {"atr_stop_multiplier": 2.5})
        crisis = self._mult("CRISIS", {"atr_stop_multiplier": 2.5})
        self.assertLess(calm, elevated)
        self.assertLess(elevated, crisis)

    def test_scaling_disabled_returns_base(self):
        m = self._mult("CRISIS", {"atr_stop_multiplier": 3.0, "atr_regime_scaling": False})
        self.assertAlmostEqual(m, 3.0, places=3)

    def test_vix_failure_falls_back_to_base(self):
        loops = _loops_module()
        with patch("ibkr_core.features.compliance.vix.get_current_vix", side_effect=Exception("net")):
            self.assertAlmostEqual(loops._regime_atr_multiplier({"atr_stop_multiplier": 2.5}), 2.5, places=3)


class TestHWMTracking(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.hwm_path = os.path.join(self.tmpdir, "hwm.json")

    def _patch_hwm(self, loops):
        loops._HWM_FILE = self.hwm_path

    def test_update_hwm_creates_new_entry(self):
        loops = _loops_module()
        self._patch_hwm(loops)
        peak = loops._update_hwm("AAPL", 150.0)
        self.assertEqual(peak, 150.0)

    def test_update_hwm_preserves_peak(self):
        loops = _loops_module()
        self._patch_hwm(loops)
        loops._update_hwm("AAPL", 150.0)
        loops._update_hwm("AAPL", 140.0)  # price dipped
        peak = loops._update_hwm("AAPL", 145.0)
        self.assertEqual(peak, 150.0)

    def test_update_hwm_rises_to_new_peak(self):
        loops = _loops_module()
        self._patch_hwm(loops)
        loops._update_hwm("AAPL", 150.0)
        peak = loops._update_hwm("AAPL", 170.0)
        self.assertEqual(peak, 170.0)

    def test_clear_hwm_removes_symbol(self):
        loops = _loops_module()
        self._patch_hwm(loops)
        loops._update_hwm("AAPL", 150.0)
        loops._clear_hwm("AAPL")
        hwm = loops._load_hwm()
        self.assertNotIn("AAPL", hwm)


class TestPartialSells(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ps_path = os.path.join(self.tmpdir, "partial_sells.json")

    def _patch_ps(self, loops):
        loops._PARTIAL_SELLS_FILE = self.ps_path

    def test_no_partial_sell_by_default(self):
        loops = _loops_module()
        self._patch_ps(loops)
        self.assertFalse(loops._has_partial_sell("AAPL"))

    def test_mark_and_check_partial_sell(self):
        loops = _loops_module()
        self._patch_ps(loops)
        loops._mark_partial_sell("AAPL")
        self.assertTrue(loops._has_partial_sell("AAPL"))

    def test_clear_partial_sell(self):
        loops = _loops_module()
        self._patch_ps(loops)
        loops._mark_partial_sell("AAPL")
        loops._clear_partial_sell("AAPL")
        self.assertFalse(loops._has_partial_sell("AAPL"))


class TestCooldown(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cd_path = os.path.join(self.tmpdir, "cooldowns.json")

    def _patch_cd(self, loops):
        loops._COOLDOWN_FILE = self.cd_path

    def test_no_cooldown_by_default(self):
        loops = _loops_module()
        self._patch_cd(loops)
        self.assertFalse(loops._is_in_cooldown("AAPL"))

    def test_in_cooldown_after_mark(self):
        loops = _loops_module()
        self._patch_cd(loops)
        loops._mark_cooldown_sell("AAPL")
        self.assertTrue(loops._is_in_cooldown("AAPL", days=14))

    def test_cooldown_expired(self):
        loops = _loops_module()
        self._patch_cd(loops)
        old_date = (db_now() - timedelta(days=15)).isoformat()
        with open(self.cd_path, "w") as f:
            json.dump({"AAPL": old_date}, f)
        self.assertFalse(loops._is_in_cooldown("AAPL", days=14))

    def test_cooldown_active_within_window(self):
        loops = _loops_module()
        self._patch_cd(loops)
        recent = (db_now() - timedelta(days=3)).isoformat()
        with open(self.cd_path, "w") as f:
            json.dump({"AAPL": recent}, f)
        self.assertTrue(loops._is_in_cooldown("AAPL", days=14))


class TestPullbackFilter(unittest.TestCase):
    def _make_hist(self, closes):
        import pandas as pd
        return pd.DataFrame({
            "Close": closes,
            "High": closes * 1.01,
            "Low": closes * 0.99,
        })

    def test_allows_healthy_pullback(self):
        """Price 3% below 20d high, above SMA20 → allow."""
        loops = _loops_module()
        closes = np.concatenate([np.linspace(100, 120, 19), [116.4]])  # 3% below 120
        hist = self._make_hist(closes)
        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = hist
            ok, reason = loops._check_pullback_entry("AAPL")
        self.assertTrue(ok, reason)

    def test_blocks_price_at_peak(self):
        """Price only 0.5% below high → 'wait for pullback'."""
        loops = _loops_module()
        closes = np.concatenate([np.linspace(100, 120, 19), [119.4]])  # 0.5% below
        hist = self._make_hist(closes)
        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = hist
            ok, _ = loops._check_pullback_entry("AAPL")
        self.assertFalse(ok)

    def test_blocks_downtrend(self):
        """Price below SMA20 → block."""
        loops = _loops_module()
        # Falling prices: SMA20 is above current price
        closes = np.concatenate([np.linspace(120, 100, 19), [95.0]])
        hist = self._make_hist(closes)
        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = hist
            ok, _ = loops._check_pullback_entry("AAPL")
        self.assertFalse(ok)

    def test_allows_on_insufficient_data(self):
        """< 20 bars → allow through (no data to filter on)."""
        loops = _loops_module()
        import pandas as pd
        hist = pd.DataFrame({"Close": [100, 101, 102], "High": [101, 102, 103], "Low": [99, 100, 101]})
        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = hist
            ok, _ = loops._check_pullback_entry("AAPL")
        self.assertTrue(ok)


class TestPositionEntryDate(unittest.TestCase):
    def test_returns_none_when_no_history(self):
        loops = _loops_module()
        with patch("ibkr_core.features.trading.loops.SessionLocal") as mock_db:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
            mock_db.return_value = mock_session
            result = loops._position_entry_date("AAPL")
        self.assertIsNone(result)

    def test_returns_created_at_when_found(self):
        loops = _loops_module()
        expected = datetime(2026, 1, 15, 10, 0, 0)
        mock_row = MagicMock()
        mock_row.created_at = expected
        with patch("ibkr_core.features.trading.loops.SessionLocal") as mock_db:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_row
            mock_db.return_value = mock_session
            result = loops._position_entry_date("AAPL")
        self.assertEqual(result, expected)


class TestComputeAtrStop(unittest.TestCase):
    """Regression: ATR true-range previously mixed full-length high/low with the
    N-1 prev_close slice and always raised ValueError (broadcast mismatch), so
    ATR stops never applied."""

    def test_returns_finite_pct_for_30_bars(self):
        loops = _loops_module()
        rng = np.random.default_rng(0)
        close = 100 + np.cumsum(rng.normal(0, 1, 30))
        high = close + np.abs(rng.normal(0, 0.5, 30))
        low = close - np.abs(rng.normal(0, 0.5, 30))
        result = loops._compute_atr_stop(high, low, close, multiplier=2.5)
        self.assertIsNotNone(result)
        self.assertTrue(np.isfinite(result))
        self.assertGreater(result, 0)

    def test_no_broadcast_error_uneven_volatility(self):
        loops = _loops_module()
        high = np.linspace(100, 130, 30)
        low = np.linspace(99, 128, 30)
        close = np.linspace(99.5, 129, 30)
        # Must not raise ValueError on broadcasting.
        self.assertIsNotNone(loops._compute_atr_stop(high, low, close))

    def test_returns_none_below_min_bars(self):
        loops = _loops_module()
        arr = np.linspace(100, 110, 14)
        self.assertIsNone(loops._compute_atr_stop(arr, arr, arr))


class TestLocalHwmKey(unittest.TestCase):
    """M1: local-currency HWM is namespaced apart from the USD HWM."""

    def test_key_is_distinct_from_symbol(self):
        loops = _loops_module()
        self.assertNotEqual(loops._local_hwm_key("AZN.L"), "AZN.L")
        self.assertTrue(loops._local_hwm_key("AZN.L").startswith("AZN.L"))

    def test_usd_and_local_hwm_do_not_mix(self):
        loops = _loops_module()
        tmp = os.path.join(tempfile.mkdtemp(), "hwm.json")
        loops._HWM_FILE = tmp
        loops._update_hwm("AZN.L", 200.0)                       # USD trail
        loops._update_hwm(loops._local_hwm_key("AZN.L"), 100.0)  # local trail
        hwm = loops._load_hwm()
        self.assertEqual(hwm["AZN.L"], 200.0)
        self.assertEqual(hwm[loops._local_hwm_key("AZN.L")], 100.0)


class TestCashSleeveResolveExchange(unittest.IsolatedAsyncioTestCase):
    """M2: cash-sleeve routes the ETF through resolve_exchange, not `or 'NMS'`,
    so a suffixed foreign ETF (compliance.exchange=None) is gated by its own
    session (LSE) rather than defaulted to US hours."""

    async def test_foreign_etf_gated_by_home_session_not_us(self):
        loops = _loops_module()
        compliance = MagicMock(is_compliant=True, exchange=None)
        seen = {}

        def _mkt_status(exch):
            seen["exchange"] = exch
            return {"is_open": False}  # closed → early return after resolution

        worker = MagicMock()
        with patch.object(loops, "async_shariah_screen",
                          new=_AsyncReturn(compliance)), \
             patch.object(loops, "market_status", side_effect=_mkt_status), \
             patch("asyncio.to_thread", new=_async_passthrough):
            settings = {"cash_sweep_fallback_etf": "ISDU.L",
                        "cash_sweep_fallback_max_pct": 20.0}
            worker.get_net_liquidation = MagicMock(return_value=10000.0)
            worker.get_positions = MagicMock(return_value=[])
            result = await loops._cash_sleeve_buy(
                worker, MagicMock(), MagicMock(), settings, 500.0, None)
        self.assertFalse(result)                 # market closed → no dispatch
        self.assertEqual(seen["exchange"], "LSE")  # resolved from .L suffix, not NMS


# ── Helpers for the main_loop exit-path drive tests ────────────────────────

def _AsyncReturn(value):
    async def _coro(*a, **k):
        return value
    return _coro


async def _async_passthrough(fn, *a, **k):
    return fn(*a, **k)


class _StopCycle(Exception):
    pass


class TestExitFxGate(unittest.IsolatedAsyncioTestCase):
    """H3 + M1: main_loop exit path honors avg_cost_fx_ok and trails in local ccy."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    async def _drive(self, loops, positions, settings, hwm_seed=None):
        """Run exactly one main_loop cycle over `positions` and return the
        patched _dispatch_signal mock + captured WARNING log lines."""
        from unittest.mock import AsyncMock
        import contextlib

        hwm_path = os.path.join(self.tmpdir, "hwm.json")
        if hwm_seed:
            with open(hwm_path, "w") as f:
                json.dump(hwm_seed, f)
        loops._HWM_FILE = hwm_path
        loops._PARTIAL_SELLS_FILE = os.path.join(self.tmpdir, "partial.json")

        base_settings = {
            "watchlist": [], "max_positions": 15, "trading_paused": True,
            "use_atr_stops": False, "min_trade_size": 50,
        }
        base_settings.update(settings)

        worker = MagicMock()
        worker.ib.isConnected.return_value = True
        worker.get_positions.return_value = positions
        worker.get_open_orders.return_value = []
        worker.get_available_funds.return_value = 0.0
        manager = MagicMock()
        manager.broadcast = AsyncMock()

        dispatch = AsyncMock()
        sleep_mock = AsyncMock(side_effect=asyncio.CancelledError())

        cr = MagicMock(exchange="LSE", is_compliant=True)

        with contextlib.ExitStack() as es:
            es.enter_context(patch.object(loops, "load_settings", return_value=base_settings))
            es.enter_context(patch.object(loops, "set_active_account"))
            es.enter_context(patch.object(loops, "Trader", MagicMock()))
            es.enter_context(patch.object(loops, "_exceeds_daily_loss_limit", return_value=False))
            es.enter_context(patch.object(loops, "is_market_open", return_value=True))
            es.enter_context(patch.object(loops, "market_status", return_value={"is_open": True}))
            es.enter_context(patch.object(loops, "_position_entry_date", return_value=None))
            es.enter_context(patch.object(loops, "_dispatch_signal", dispatch))
            es.enter_context(patch(
                "ibkr_core.features.compliance.screening.live_shariah_screen",
                return_value=cr))
            es.enter_context(patch("asyncio.sleep", sleep_mock))
            health = {}
            with self.assertLogs("ibkr_core.features.trading.loops", level="WARNING") as cm:
                # assertLogs requires >=1 record; emit a sentinel so the no-warning
                # cases don't raise, then filter it out.
                loops.logger.warning("test-sentinel")
                await loops.main_loop(worker, manager, health,
                                      account_id=None, manage_connection=False)
        warnings = [ln for ln in cm.output if "test-sentinel" not in ln]
        return dispatch, warnings

    async def test_fx_inconsistent_suppresses_upnl_stop(self):
        """avg_cost_fx_ok=False + fictitious -99% upnl → NO exit, WARNING logged."""
        loops = _loops_module()
        pos = {"symbol": "AZN.L", "quantity": 10.0, "avg_cost": 14456.0,
               "market_value": 1500.0, "avg_cost_fx_ok": False, "local_price": 150.0}
        dispatch, warnings = await self._drive(
            loops, [pos], {}, hwm_seed={loops._local_hwm_key("AZN.L"): 150.0})
        self.assertEqual(dispatch.await_count, 0)
        self.assertTrue(any("suppressing upnl-based exits" in w for w in warnings),
                        warnings)

    async def test_fx_ok_real_loss_still_stops_out(self):
        """avg_cost_fx_ok=True + genuine -10% USD loss → fixed stop fires."""
        loops = _loops_module()
        pos = {"symbol": "AAPL", "quantity": 10.0, "avg_cost": 100.0,
               "market_value": 900.0, "avg_cost_fx_ok": True}
        dispatch, _ = await self._drive(loops, [pos], {})
        self.assertEqual(dispatch.await_count, 1)
        # dispatched a SELL
        self.assertEqual(dispatch.await_args.args[0].action, "SELL")

    async def test_trailing_uses_local_price_no_false_exit(self):
        """FX swing: USD trail would show -25% but local is -2% → NO liquidation."""
        loops = _loops_module()
        pos = {"symbol": "AZN.L", "quantity": 10.0, "avg_cost": 150.0,
               "market_value": 1500.0, "avg_cost_fx_ok": True, "local_price": 98.0}
        dispatch, _ = await self._drive(
            loops, [pos], {},
            hwm_seed={"AZN.L": 200.0, loops._local_hwm_key("AZN.L"): 100.0})
        self.assertEqual(dispatch.await_count, 0)

    async def test_trailing_local_drop_does_fire(self):
        """Local price -10% from local HWM → trailing stop still fires (in local)."""
        loops = _loops_module()
        pos = {"symbol": "AZN.L", "quantity": 10.0, "avg_cost": 150.0,
               "market_value": 1500.0, "avg_cost_fx_ok": True, "local_price": 90.0}
        dispatch, _ = await self._drive(
            loops, [pos], {},
            hwm_seed={"AZN.L": 150.0, loops._local_hwm_key("AZN.L"): 100.0})
        self.assertEqual(dispatch.await_count, 1)
        self.assertEqual(dispatch.await_args.args[0].action, "SELL")


if __name__ == "__main__":
    unittest.main()
