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
    """Both Zoya and Musaffa fail (return None) → pure AAOIFI ratio screening.

    Uses a synthetic ticker (RATIOTEST) and patches _check_manual_verification →
    None so the ratio path is what's exercised. A real symbol like NVDA carries a
    persisted 'Manual (Zoya App)' verification that short-circuits before ratios,
    which silently voided the assertions."""

    def _no_manual(self):
        return patch(
            "ibkr_core.features.compliance.screening._check_manual_verification",
            return_value=None,
        )

    def test_compliant_ratios_pass(self):
        # debt=5%, cash=5%, impure=0% — all well under AAOIFI limits
        data = _financial_data(symbol="RATIOTEST", debt=1_000_000, cash=1_000_000,
                               revenue=10_000_000, mkt_cap=20_000_000,
                               prohibited_income=0.0)
        with self._no_manual(), \
             patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("RATIOTEST")

        self.assertTrue(result.is_compliant)
        self.assertEqual(result.verdict, "COMPLIANT")

    def test_high_debt_ratio_blocked(self):
        # debt = 80% of mkt_cap → fails AAOIFI 30% limit
        data = _financial_data(symbol="RATIOTEST", debt=16_000_000, cash=500_000,
                               revenue=10_000_000, mkt_cap=20_000_000,
                               prohibited_income=0.0)
        with self._no_manual(), \
             patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("RATIOTEST")

        self.assertFalse(result.is_compliant)
        self.assertEqual(result.verdict, "NON_COMPLIANT")

    def test_high_impure_revenue_blocked(self):
        # impure = 10% > 5% AAOIFI limit
        data = _financial_data(symbol="RATIOTEST", debt=1_000_000, cash=500_000,
                               revenue=10_000_000, mkt_cap=20_000_000,
                               prohibited_income=1_000_000)  # 10% impure
        with self._no_manual(), \
             patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("RATIOTEST")

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


class TestAllowlistExchangeResolution(unittest.TestCase):
    """L3: allowlist branches must resolve a real exchange code via
    infer_exchange_from_symbol, not echo the yfinance suffix ('L' → US/USD default)."""

    def _settings(self):
        return patch("ibkr_core.features.compliance.screening._load_settings",
                     return_value={"ratio_buffer": 0.0, "sector_exclusion": []})

    def test_gold_etc_lse_resolves_to_exchange_code(self):
        with self._settings():
            result = _live_shariah_screen_uncached("SGLN.L")  # GOLD_ETC_ALLOWLIST
        self.assertTrue(result.is_compliant)
        self.assertEqual(result.exchange, "LSE")

    def test_gold_etc_us_no_suffix_resolves_nms(self):
        with self._settings():
            result = _live_shariah_screen_uncached("RMAU")  # GOLD_ETC_ALLOWLIST, US
        self.assertEqual(result.exchange, "NMS")

    def test_shariah_etf_lse_resolves_to_exchange_code(self):
        with self._settings():
            result = _live_shariah_screen_uncached("ISDU.L")  # SHARIAH_ETF_ALLOWLIST
        self.assertTrue(result.is_compliant)
        self.assertEqual(result.exchange, "LSE")

    def test_shariah_etf_us_no_suffix_resolves_nms(self):
        with self._settings():
            result = _live_shariah_screen_uncached("SPUS")  # SHARIAH_ETF_ALLOWLIST, US
        self.assertEqual(result.exchange, "NMS")


class TestBusinessSlugScreenLive(unittest.TestCase):
    """H4: live screen blocks via yfinance industryKey/sectorKey slugs even when the
    human-readable sector string never substring-matches the prohibited keyword."""

    def _run(self, symbol, data):
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            return _live_shariah_screen_uncached(symbol)

    def test_diageo_alcohol_slug_blocks(self):
        # Clean ratios (5% debt) — Diageo would screen COMPLIANT on ratios alone;
        # the alcohol slug must block it (a buyback dropping debt must not free it).
        data = _financial_data(
            symbol="DGE.L", debt=1_000_000, cash=500_000, revenue=10_000_000,
            mkt_cap=20_000_000,
            sector="Consumer Defensive / Beverages - Wineries & Distilleries",
        )
        data["industry_key"] = "beverages-wineries-distilleries"
        data["sector_key"] = "consumer-defensive"
        result = self._run("DGE.L", data)
        self.assertFalse(result.is_compliant)
        self.assertEqual(result.verdict, "NON_COMPLIANT")
        self.assertIn("Prohibited sector (slug)", result.reason)

    def test_casino_slug_blocks(self):
        data = _financial_data(symbol="LVS", debt=1_000_000, cash=500_000,
                               sector="Consumer Cyclical / Resorts & Casinos")
        data["industry_key"] = "resorts-casinos"
        result = self._run("LVS", data)
        self.assertFalse(result.is_compliant)
        self.assertIn("Prohibited sector (slug)", result.reason)

    def test_conventional_bank_slug_blocks(self):
        data = _financial_data(symbol="JPM", debt=1_000_000, cash=500_000,
                               sector="Financial Services / Banks - Diversified")
        data["industry_key"] = "banks-diversified"
        result = self._run("JPM", data)
        self.assertFalse(result.is_compliant)
        self.assertIn("Prohibited sector (slug)", result.reason)

    def test_coca_cola_non_alcoholic_passes(self):
        data = _financial_data(symbol="KO", debt=1_000_000, cash=500_000,
                               sector="Consumer Defensive / Beverages - Non-Alcoholic")
        data["industry_key"] = "beverages-non-alcoholic"
        result = self._run("KO", data)
        self.assertTrue(result.is_compliant)

    def test_al_rajhi_islamic_bank_exempt_passes(self):
        # Bank slug but intentionally-seeded Islamic bank → exempt from the slug block;
        # clean ratios → COMPLIANT.
        data = _financial_data(symbol="1120.SR", debt=1_000_000, cash=500_000,
                               sector="Financial Services / Banks - Regional")
        data["industry_key"] = "banks-regional"
        result = self._run("1120.SR", data)
        self.assertTrue(result.is_compliant)


class TestImpureIncomeUndeterminable(unittest.TestCase):
    """M6: prohibited_income==0 from ABSENT income statements must not silently pass
    the AAOIFI 5% purity screen."""

    def test_absent_financials_no_certifier_blocks(self):
        data = _financial_data(symbol="EU.PA", debt=1_000_000, cash=500_000,
                               prohibited_income=0.0)
        data["financials_available"] = False
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("EU.PA")
        self.assertFalse(result.is_compliant)
        self.assertIn("impure-income statements absent", result.reason)

    def test_absent_financials_with_compliant_certifier_passes(self):
        data = _financial_data(symbol="EU.PA", debt=1_000_000, cash=500_000,
                               prohibited_income=0.0)
        data["financials_available"] = False
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=_zoya_verdict(compliant=True)), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("EU.PA")
        self.assertTrue(result.is_compliant)

    def test_present_financials_genuine_zero_passes(self):
        # financials present + genuine 0 impure → passes (no false block).
        data = _financial_data(symbol="AAPL", debt=1_000_000, cash=500_000,
                               prohibited_income=0.0)
        data["financials_available"] = True
        with patch("ibkr_core.features.compliance.screening.fetch_shariah_verdict",
                   return_value=None), \
             patch("ibkr_core.features.compliance.screening.fetch_financial_data",
                   return_value=data), \
             patch("ibkr_core.features.compliance.screening._load_settings",
                   return_value={"ratio_buffer": 0.0, "sector_exclusion": []}):
            result = _live_shariah_screen_uncached("AAPL")
        self.assertTrue(result.is_compliant)


if __name__ == "__main__":
    unittest.main()
