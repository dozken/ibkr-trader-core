"""
Tests for new exit logic added to main_loop:
- Trailing stop (HWM-based)
- Time-based exit (stale thesis)
- Partial profit
- Re-entry cooldown
- Pullback entry filter
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np


# ── Helpers ───────────────────────────────────────────────────────────────

def _loops_module():
    from ibkr_core.features.trading import loops
    return loops


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
        old_date = (datetime.now() - timedelta(days=15)).isoformat()
        with open(self.cd_path, "w") as f:
            json.dump({"AAPL": old_date}, f)
        self.assertFalse(loops._is_in_cooldown("AAPL", days=14))

    def test_cooldown_active_within_window(self):
        loops = _loops_module()
        self._patch_cd(loops)
        recent = (datetime.now() - timedelta(days=3)).isoformat()
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


if __name__ == "__main__":
    unittest.main()
