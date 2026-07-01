"""
Integration tests for the screening chain in _live_shariah_screen_uncached.

Source-of-truth = our canonical AAOIFI ratio screen; certifiers (Zoya/Musaffa) are advisory
and may only TIGHTEN, never loosen (COMPLIANCE.md §3). Covers:
1. Certifier agrees with our screen → corroboration recorded
2. Certifier flags non-compliant/doubtful while ratios pass → blocked fail-closed
3. Certifier says compliant but ratios fail → still blocked (our screen necessary)
4. No certifier → ratio-only path via yfinance (COMPLIANT or NON_COMPLIANT)
5. All data sources fail → UNKNOWN block
"""
import unittest
from unittest.mock import patch

from ibkr_core.features.compliance.screening import _live_shariah_screen_uncached


# ---------------------------------------------------------------------------
# Shared fixture factories
# ---------------------------------------------------------------------------

def _financial_data(
    debt=1_000_000, cash=500_000, revenue=10_000_000,
    mkt_cap=20_000_000, prohibited_income=0.0,
    sector="Technology", exchange="NMS", symbol="AAPL",
):
    return {
        "symbol": symbol, "sector": sector, "exchange": exchange,
        "mkt_cap": mkt_cap, "debt": debt, "cash": cash,
        "revenue": revenue, "prohibited_income": prohibited_income,
        "sources": ["YahooFinance"], "quote_type": "EQUITY",
        "company_name": "Test Corp",
    }


def _zoya_verdict(compliant=True):
    return {"compliant": compliant, "doubtful": False,
            "status": "COMPLIANT" if compliant else "NON_COMPLIANT",
            "sources": ["Zoya"]}


def _musaffa_verdict(compliant=True):
    return {"compliant": compliant, "doubtful": False,
            "status": "COMPLIANT" if compliant else "NON_COMPLIANT",
            "sources": ["Musaffa"]}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScreeningCertifierAgrees(unittest.TestCase):
    """Certifier agrees with our canonical AAOIFI screen → recorded as corroboration."""

    def test_zoya_compliant_corroborates(self):
        # Clean ratios → our screen COMPLIANT; Zoya agrees. Zoya appears as corroboration.
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=_zoya_verdict(compliant=True)), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=_financial_data()), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("AAPL")

        self.assertTrue(result.is_compliant)
        self.assertEqual(result.verdict, "COMPLIANT")
        self.assertTrue(any("Zoya" in s.source for s in result.sources_detail))
        self.assertFalse(any(s.source == "DISAGREEMENT" for s in result.sources_detail))

    def test_musaffa_compliant_corroborates(self):
        musaffa_only = {**_musaffa_verdict(compliant=True), "sources": ["Musaffa"]}
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=musaffa_only), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=_financial_data()), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("MSFT")

        self.assertTrue(result.is_compliant)
        self.assertTrue(any("Musaffa" in s.source for s in result.sources_detail))


class TestScreeningCertifierTightens(unittest.TestCase):
    """Our AAOIFI screen is canonical; a certifier may only TIGHTEN (fail-closed), never loosen."""

    def test_certifier_noncompliant_blocks_even_when_ratios_pass(self):
        # Clean ratios → our screen COMPLIANT, but Zoya says NON_COMPLIANT → blocked fail-closed.
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=_zoya_verdict(compliant=False)), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=_financial_data()), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("AAPL")

        self.assertFalse(result.is_compliant)
        self.assertTrue(any(s.source == "DISAGREEMENT" for s in result.sources_detail))

    def test_certifier_compliant_cannot_rescue_failing_ratios(self):
        # High debt (80%) → our screen NON_COMPLIANT; Zoya says COMPLIANT → still blocked.
        data = _financial_data(debt=16_000_000, cash=500_000,
                               revenue=10_000_000, mkt_cap=20_000_000,
                               prohibited_income=0.0)
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=_zoya_verdict(compliant=True)), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("AAPL")

        self.assertFalse(result.is_compliant)
        self.assertTrue(any(s.source == "DISAGREEMENT" for s in result.sources_detail))

    def test_musaffa_non_compliant_blocks(self):
        musaffa_only = {**_musaffa_verdict(compliant=False), "sources": ["Musaffa"]}
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=musaffa_only), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=_financial_data()), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("MSFT")

        self.assertFalse(result.is_compliant)


class TestScreeningCertifierDoubtful(unittest.TestCase):
    """Certifier DOUBTFUL while our ratios pass → blocked fail-closed."""

    def test_doubtful_blocks(self):
        doubtful = {
            "compliant": False, "doubtful": True,
            "status": "DOUBTFUL (sources disagree)",
            "sources": ["Zoya", "Musaffa"],
        }
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=doubtful), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=_financial_data()), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("XYZ")

        self.assertFalse(result.is_compliant)
        self.assertEqual(result.verdict, "NON_COMPLIANT")
        sources = [s.source for s in result.sources_detail]
        self.assertTrue(any("Zoya" in s or "Musaffa" in s for s in sources))
        self.assertIn("DISAGREEMENT", sources)


class TestScreeningFallbackRatioOnly(unittest.TestCase):
    """Both Zoya and Musaffa fail (return None) → pure AAOIFI ratio screening."""

    def test_compliant_ratios_pass(self):
        # debt=5%, cash=5%, impure=0% — all well under AAOIFI limits
        data = _financial_data(debt=1_000_000, cash=1_000_000,
                               revenue=10_000_000, mkt_cap=20_000_000,
                               prohibited_income=0.0)
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("NVDA")

        self.assertTrue(result.is_compliant)
        self.assertEqual(result.verdict, "COMPLIANT")

    def test_high_debt_ratio_blocked(self):
        # debt = 80% of mkt_cap → fails AAOIFI 30% limit
        data = _financial_data(debt=16_000_000, cash=500_000,
                               revenue=10_000_000, mkt_cap=20_000_000,
                               prohibited_income=0.0)
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("NVDA")

        self.assertFalse(result.is_compliant)
        self.assertEqual(result.verdict, "NON_COMPLIANT")

    def test_high_impure_revenue_blocked(self):
        # impure = 10% > 5% AAOIFI limit
        data = _financial_data(debt=1_000_000, cash=500_000,
                               revenue=10_000_000, mkt_cap=20_000_000,
                               prohibited_income=1_000_000)  # 10% impure
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("NVDA")

        self.assertFalse(result.is_compliant)
        self.assertGreater(result.impure_revenue_pct, 0.05)

    def test_prohibited_sector_blocked_even_with_good_ratios(self):
        data = _financial_data(debt=1_000_000, cash=500_000,
                               revenue=10_000_000, mkt_cap=20_000_000,
                               sector="Alcohol")
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("BEER")

        self.assertFalse(result.is_compliant)


class TestScreeningFallbackAllFail(unittest.TestCase):
    """Both APIs and financial data all fail → UNKNOWN block."""

    def test_no_data_at_all_returns_unknown_blocked(self):
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("UNKN")

        self.assertFalse(result.is_compliant)
        self.assertEqual(result.verdict, "UNKNOWN")
        self.assertIsNone(result.data_source)

    def test_no_financial_data_but_zoya_compliant_passes(self):
        """Zoya verdict alone is sufficient when financial data is unavailable."""
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=_zoya_verdict(compliant=True)), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("GULF")

        self.assertTrue(result.is_compliant)
        self.assertIn("Zoya", result.data_source)


if __name__ == "__main__":
    unittest.main()
