"""
TDD tests for Phase 5.1A — Dynamic VIX-driven ratio buffers.
Implementing per AGENT.md: failing tests first.
"""
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd


class TestVixToRatioBuffer(unittest.TestCase):
    def setUp(self):
        from ibkr_core.features.compliance.vix import vix_to_ratio_buffer
        self.vix_to_ratio_buffer = vix_to_ratio_buffer

    def test_calm_market_zero_buffer(self):
        self.assertEqual(self.vix_to_ratio_buffer(12.0), 0.0)

    def test_boundary_below_20_is_zero(self):
        self.assertEqual(self.vix_to_ratio_buffer(19.9), 0.0)

    def test_boundary_exactly_20_is_medium(self):
        self.assertEqual(self.vix_to_ratio_buffer(20.0), 2.0)

    def test_elevated_vol_2pct_buffer(self):
        self.assertEqual(self.vix_to_ratio_buffer(25.0), 2.0)

    def test_boundary_below_30_is_medium(self):
        self.assertEqual(self.vix_to_ratio_buffer(29.9), 2.0)

    def test_boundary_exactly_30_is_high(self):
        self.assertEqual(self.vix_to_ratio_buffer(30.0), 5.0)

    def test_crisis_vol_5pct_buffer(self):
        self.assertEqual(self.vix_to_ratio_buffer(45.0), 5.0)

    def test_extreme_vix_still_5pct(self):
        self.assertEqual(self.vix_to_ratio_buffer(80.0), 5.0)


class TestGetCurrentVix(unittest.IsolatedAsyncioTestCase):
    def test_returns_close_price_from_yfinance(self):
        from ibkr_core.features.compliance.vix import get_current_vix
        mock_hist = pd.DataFrame({"Close": [23.5]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist
        with patch("ibkr_core.features.compliance.vix.yf.Ticker", return_value=mock_ticker):
            result = get_current_vix()
        self.assertAlmostEqual(result, 23.5)

    def test_returns_fallback_on_empty_history(self):
        from ibkr_core.features.compliance.vix import get_current_vix, _FALLBACK_VIX
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        with patch("ibkr_core.features.compliance.vix.yf.Ticker", return_value=mock_ticker):
            result = get_current_vix()
        self.assertEqual(result, _FALLBACK_VIX)

    def test_returns_fallback_on_exception(self):
        from ibkr_core.features.compliance.vix import get_current_vix, _FALLBACK_VIX
        with patch("ibkr_core.features.compliance.vix.yf.Ticker", side_effect=Exception("network error")):
            result = get_current_vix()
        self.assertEqual(result, _FALLBACK_VIX)


class TestDynamicBufferComplianceEffect(unittest.TestCase):
    """
    Verifies that a stock passing at normal VIX can FAIL under high-VIX buffer.
    AAOIFI base debt threshold = 30% (COMPLIANCE.md §1). Boundary stock: debt = 27%
    (passes at 0 buffer, fails at the 25% threshold when VIX>30 applies a 5pp buffer).
    """

    def _screen(self, ratio_buffer_override=None):
        # Use check_shariah_compliance directly to avoid network calls
        from ibkr_core.features.compliance.screening import check_shariah_compliance
        return check_shariah_compliance(
            symbol="BOUNDARY_CO",
            debt=27, cash=5, revenue=100,
            prohibited_income=1, mkt_cap=100,
            sector="Technology",
            ratio_buffer=ratio_buffer_override if ratio_buffer_override is not None else 0.0,
        )

    def test_27pct_debt_passes_at_zero_buffer(self):
        # 30% threshold; 27% < 30% → passes
        result = self._screen(ratio_buffer_override=0.0)
        self.assertTrue(result.is_compliant)

    def test_27pct_debt_fails_at_5pct_buffer(self):
        # 30% - 5% = 25% threshold; 27% debt >= 25% → fails
        result = self._screen(ratio_buffer_override=5.0)
        self.assertFalse(result.is_compliant)
        self.assertIn("Debt ratio", result.reason)

    def test_27pct_debt_passes_at_2pct_buffer(self):
        # 30% - 2% = 28% threshold; 27% < 28% → still passes
        result = self._screen(ratio_buffer_override=2.0)
        self.assertTrue(result.is_compliant)


class TestLiveScreenWithBufferOverride(unittest.TestCase):
    """live_shariah_screen must accept ratio_buffer_override and bypass cache."""

    def test_override_bypasses_cache(self):
        from ibkr_core.features.compliance.screening import live_shariah_screen, _screen_cache
        import time

        # Plant a stale compliant result in the cache
        from ibkr_core.features.compliance.schemas import ComplianceStatus
        stale = ComplianceStatus(
            symbol="TEST_CACHE", sector="Technology", is_compliant=True,
            debt_to_mkt_cap=0.30, cash_to_mkt_cap=0.05, impure_revenue_pct=0.01,
        )
        _screen_cache["TEST_CACHE"] = (stale, time.time())

        # With override, should NOT return cached result — should call uncached
        with patch(
            "ibkr_core.features.compliance.screening._live_shariah_screen_uncached"
        ) as mock_uncached:
            mock_uncached.return_value = stale
            live_shariah_screen("TEST_CACHE", ratio_buffer_override=5.0)
            mock_uncached.assert_called_once_with("TEST_CACHE", 5.0)

    def test_no_override_uses_cache(self):
        from ibkr_core.features.compliance.screening import live_shariah_screen, _screen_cache
        import time

        from ibkr_core.features.compliance.schemas import ComplianceStatus
        cached = ComplianceStatus(
            symbol="CACHED_SYM", sector="Technology", is_compliant=True,
            debt_to_mkt_cap=0.10, cash_to_mkt_cap=0.05, impure_revenue_pct=0.01,
        )
        _screen_cache["CACHED_SYM"] = (cached, time.time())

        with patch(
            "ibkr_core.features.compliance.screening._live_shariah_screen_uncached"
        ) as mock_uncached:
            result = live_shariah_screen("CACHED_SYM")
            mock_uncached.assert_not_called()
        self.assertEqual(result.symbol, "CACHED_SYM")

    def test_settings_buffer_is_floor(self):
        """When VIX buffer < settings buffer, settings buffer wins."""
        from ibkr_core.features.compliance.screening import check_shariah_compliance
        # AAOIFI 30% base: debt = 29% — passes at 0% buffer (30% thr),
        # fails at 2% buffer (28% thr; 29% >= 28%).
        result_zero = check_shariah_compliance(
            "FLOOR_TEST", debt=29, cash=5, revenue=100,
            prohibited_income=1, mkt_cap=100, sector="Technology",
            ratio_buffer=0.0,
        )
        result_two = check_shariah_compliance(
            "FLOOR_TEST", debt=29, cash=5, revenue=100,
            prohibited_income=1, mkt_cap=100, sector="Technology",
            ratio_buffer=2.0,
        )
        self.assertTrue(result_zero.is_compliant)
        self.assertFalse(result_two.is_compliant)


if __name__ == "__main__":
    unittest.main()
