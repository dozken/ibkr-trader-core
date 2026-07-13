"""
Unit tests for compliance data_fetcher utilities.
All network calls mocked — no live API required.
"""
import unittest
from unittest.mock import patch, MagicMock
from ibkr_core.features.compliance.data_fetcher import (
    normalize_ticker,
    _is_shariah_etf,
    fetch_financial_data,
    fetch_shariah_verdict,
)


class TestNormalizeTicker(unittest.TestCase):
    def test_us_ticker_unchanged(self):
        self.assertEqual(normalize_ticker("AAPL"), "AAPL")

    def test_colon_separator_with_known_exchange(self):
        self.assertEqual(normalize_ticker("7203:TYO"), "7203.T")
        self.assertEqual(normalize_ticker("0700:HKG"), "0700.HK")
        self.assertEqual(normalize_ticker("005930:KRX"), "005930.KS")

    def test_slash_separator(self):
        self.assertEqual(normalize_ticker("TCS/NSE"), "TCS.NS")

    def test_unknown_exchange_passthrough(self):
        result = normalize_ticker("XYZ:UNKNOWN")
        self.assertEqual(result, "XYZ.UNKNOWN")

    def test_lowercase_input_normalised(self):
        self.assertEqual(normalize_ticker("aapl"), "AAPL")

    def test_already_dotted_passthrough(self):
        self.assertEqual(normalize_ticker("7203.T"), "7203.T")


class TestIsShariahETF(unittest.TestCase):
    def test_allowlist_ticker_certified(self):
        self.assertTrue(_is_shariah_etf("", "", symbol="SPUS"))
        self.assertTrue(_is_shariah_etf("", "", symbol="HLAL"))
        self.assertTrue(_is_shariah_etf("", "", symbol="UMMA"))

    def test_allowlist_case_insensitive(self):
        self.assertTrue(_is_shariah_etf("", "", symbol="spus"))

    def test_known_family_wahed(self):
        self.assertTrue(_is_shariah_etf("Wahed Invest", "Wahed FTSE USA Shariah ETF"))

    def test_known_family_saturna(self):
        self.assertTrue(_is_shariah_etf("Saturna Capital", "Amana Income Fund"))

    def test_sharia_keyword_in_family(self):
        self.assertTrue(_is_shariah_etf("Sharia Capital", "Some Fund"))

    def test_islamic_keyword_alone_rejected(self):
        # "islamic" alone no longer sufficient — prevents name spoofing
        self.assertFalse(_is_shariah_etf("Unknown", "Global Islamic Finance ETF"))

    def test_conventional_fund_rejected(self):
        self.assertFalse(_is_shariah_etf("Vanguard", "S&P 500 ETF"))

    def test_empty_strings_rejected(self):
        self.assertFalse(_is_shariah_etf("", ""))


class TestFetchFinancialData(unittest.TestCase):
    def _mock_info(self, overrides=None):
        base = {
            "quoteType": "EQUITY",
            "exchange": "NMS",
            "marketCap": 1_000_000,
            "totalDebt": 100_000,
            "totalCash": 50_000,
            "totalRevenue": 500_000,
            "sector": "Technology",
            "industry": "Software",
            "mostRecentQuarter": 1700000000,
        }
        if overrides:
            base.update(overrides)
        return base

    @patch("yfinance.Ticker")
    def test_equity_returns_expected_fields(self, MockTicker):
        MockTicker.return_value.info = self._mock_info()
        result = fetch_financial_data("AAPL")
        self.assertIsNotNone(result)
        self.assertEqual(result["quote_type"], "EQUITY")
        self.assertEqual(result["debt"], 100_000)
        self.assertEqual(result["cash"], 50_000)
        self.assertEqual(result["revenue"], 500_000)
        self.assertEqual(result["prohibited_income"], 0.0)
        self.assertIn("data_as_of", result)

    @patch("yfinance.Ticker")
    def test_industry_and_sector_slugs_plumbed(self, MockTicker):
        # H4/M6: yfinance industryKey/sectorKey slugs + financials_available flag
        # must be carried on the fundamentals dict.
        MockTicker.return_value.info = self._mock_info({
            "industryKey": "Beverages-Wineries-Distilleries",  # mixed case → lowered
            "sectorKey": "consumer-defensive",
        })
        result = fetch_financial_data("DGE.L")
        self.assertEqual(result["industry_key"], "beverages-wineries-distilleries")
        self.assertEqual(result["sector_key"], "consumer-defensive")
        self.assertIn("financials_available", result)

    @patch("yfinance.Ticker")
    def test_missing_slugs_default_empty(self, MockTicker):
        MockTicker.return_value.info = self._mock_info()
        result = fetch_financial_data("AAPL")
        self.assertEqual(result["industry_key"], "")
        self.assertEqual(result["sector_key"], "")

    @patch("yfinance.Ticker")
    def test_no_market_cap_returns_none(self, MockTicker):
        MockTicker.return_value.info = self._mock_info({"marketCap": None})
        result = fetch_financial_data("AAPL")
        self.assertIsNone(result)

    @patch("yfinance.Ticker")
    def test_etf_path_returns_etf_fields(self, MockTicker):
        MockTicker.return_value.info = {
            "quoteType": "ETF",
            "exchange": "NMS",
            "fundFamily": "Wahed Invest",
            "longName": "Wahed FTSE USA Shariah ETF",
            "totalAssets": 500_000,
        }
        result = fetch_financial_data("HLAL")
        self.assertIsNotNone(result)
        self.assertEqual(result["quote_type"], "ETF")
        self.assertTrue(result["etf_shariah_certified"])

    @patch("yfinance.Ticker")
    def test_conventional_etf_not_certified(self, MockTicker):
        MockTicker.return_value.info = {
            "quoteType": "ETF",
            "exchange": "NMS",
            "fundFamily": "Vanguard",
            "longName": "Vanguard S&P 500 ETF",
            "totalAssets": 1_000_000,
        }
        result = fetch_financial_data("VOO")
        self.assertIsNotNone(result)
        self.assertFalse(result["etf_shariah_certified"])

    @patch("yfinance.Ticker")
    def test_exception_returns_none(self, MockTicker):
        MockTicker.return_value.info = property(lambda self: (_ for _ in ()).throw(Exception("network")))
        result = fetch_financial_data("FAIL")
        self.assertIsNone(result)

    @patch("yfinance.Ticker")
    def test_fmp_fallback_when_yfinance_ratios_zero(self, MockTicker):
        """When yfinance returns 0 for debt/cash, FMP should be used to supplement."""
        MockTicker.return_value.info = self._mock_info({
            "totalDebt": 0, "totalCash": 0, "totalRevenue": 500_000
        })

        fmp_fundamentals = {
            "debt": 250_000.0, "cash": 120_000.0, "revenue": 500_000.0, "source": "FMP"
        }

        with patch("ibkr_core.features.compliance.data_fetcher.FMP_API_KEY", "test-key"):
            with patch("ibkr_core.features.compliance.data_fetcher._fetch_fmp_fundamentals", 
                       return_value=fmp_fundamentals):
                result = fetch_financial_data("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result["debt"], 250_000.0)
        self.assertEqual(result["cash"], 120_000.0)
        self.assertIn("FMP", result["sources"])

    @patch("yfinance.Ticker")
    def test_av_fallback_for_us_tickers_when_fmp_missing(self, MockTicker):
        """US tickers should fallback to AV if FMP also fails to provide debt/revenue."""
        MockTicker.return_value.info = self._mock_info({
            "totalDebt": 0, "totalRevenue": 0
        })

        av_fundamentals = {
            "debt": 300_000.0, "revenue": 600_000.0, "source": "AlphaVantage"
        }

        with patch("ibkr_core.features.compliance.data_fetcher.FMP_API_KEY", None):
            with patch("ibkr_core.features.compliance.data_fetcher.AV_API_KEY", "test-key"):
                with patch("ibkr_core.features.compliance.data_fetcher._fetch_av_fundamentals",
                           return_value=av_fundamentals):
                    result = fetch_financial_data("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result["debt"], 300_000.0)
        self.assertEqual(result["revenue"], 600_000.0)
        self.assertIn("AlphaVantage", result["sources"])


class TestCurrencyConversion(unittest.TestCase):
    """yfinance balance-sheet (financialCurrency) vs marketCap (trading currency)."""

    def _ticker(self, info):
        m = MagicMock()
        m.info = info
        fi = MagicMock()
        fi.shares = None
        fi.last_price = None
        m.fast_info = fi
        return m

    @patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate")
    @patch("yfinance.Ticker")
    def test_adr_converts_financials_to_trading_ccy(self, MockTicker, mock_fx):
        # TSM-like: USD market cap, TWD balance sheet
        MockTicker.return_value = self._ticker({
            "quoteType": "EQUITY", "exchange": "NYQ",
            "marketCap": 2_000_000_000_000,    # USD
            "totalDebt": 1_000_000_000_000,    # TWD
            "totalCash": 3_000_000_000_000,    # TWD
            "totalRevenue": 4_000_000_000_000, # TWD
            "currency": "USD", "financialCurrency": "TWD",
            "sector": "Technology", "industry": "Semiconductors",
        })
        mock_fx.return_value = 0.032  # 1 TWD ≈ 0.032 USD
        result = fetch_financial_data("TSM")
        self.assertIsNotNone(result)
        mock_fx.assert_called_once_with("TWD", "USD")
        self.assertAlmostEqual(result["debt"],    32_000_000_000.0)
        self.assertAlmostEqual(result["cash"],    96_000_000_000.0)
        self.assertAlmostEqual(result["revenue"], 128_000_000_000.0)

    @patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate")
    @patch("yfinance.Ticker")
    def test_same_currency_no_fx_call(self, MockTicker, mock_fx):
        MockTicker.return_value = self._ticker({
            "quoteType": "EQUITY", "exchange": "NMS",
            "marketCap": 1_000_000, "totalDebt": 100_000,
            "totalCash": 50_000, "totalRevenue": 500_000,
            "currency": "USD", "financialCurrency": "USD",
            "sector": "Technology", "industry": "SW",
        })
        result = fetch_financial_data("AAPL")
        self.assertEqual(result["debt"], 100_000)
        mock_fx.assert_not_called()

    @patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate")
    @patch("yfinance.Ticker")
    def test_missing_currency_metadata_no_conversion(self, MockTicker, mock_fx):
        MockTicker.return_value = self._ticker({
            "quoteType": "EQUITY", "exchange": "NMS",
            "marketCap": 1_000_000, "totalDebt": 100_000,
            "totalCash": 50_000, "totalRevenue": 500_000,
            "sector": "Technology", "industry": "SW",
        })
        result = fetch_financial_data("XYZ")
        self.assertEqual(result["debt"], 100_000)
        mock_fx.assert_not_called()

    @patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate")
    @patch("yfinance.Ticker")
    def test_fx_unavailable_returns_none(self, MockTicker, mock_fx):
        """Fail closed: bad FX data is worse than no data — caller falls back to FMP."""
        MockTicker.return_value = self._ticker({
            "quoteType": "EQUITY", "exchange": "NYQ",
            "marketCap": 2_000_000_000_000,
            "totalDebt": 1_000_000_000_000, "totalCash": 3_000_000_000_000,
            "totalRevenue": 4_000_000_000_000,
            "currency": "USD", "financialCurrency": "TWD",
            "sector": "Technology", "industry": "SW",
        })
        mock_fx.return_value = None
        with patch("ibkr_core.features.compliance.data_fetcher._fetch_morningstar", return_value=None), \
             patch("ibkr_core.features.compliance.data_fetcher._fetch_fmp_profile", return_value=None):
            result = fetch_financial_data("TSM")
        self.assertIsNone(result)


class TestFetchShariahVerdict(unittest.TestCase):
    def test_returns_none_when_no_api_keys(self):
        import os
        with patch.dict(os.environ, {"ZOYA_API_KEY": "", "MUSAFFA_API_KEY": ""}):
            result = fetch_shariah_verdict("AAPL")
            self.assertIsNone(result)


class TestYfinanceFastInfoFallback(unittest.TestCase):
    """When yfinance info has no marketCap, fast_info shares×price should be used."""

    def _mock_ticker(self, info_overrides=None, shares=None, last_price=None):
        info = {
            "quoteType": "EQUITY", "exchange": "NMS",
            "marketCap": None,
            "totalDebt": 100_000, "totalCash": 50_000, "totalRevenue": 500_000,
            "sector": "Technology", "industry": "Software",
        }
        if info_overrides:
            info.update(info_overrides)
        mock_ticker = MagicMock()
        mock_ticker.info = info
        fi = MagicMock()
        fi.shares = shares
        fi.last_price = last_price
        mock_ticker.fast_info = fi
        return mock_ticker

    @patch("yfinance.Ticker")
    def test_fast_info_estimate_used_when_mkt_cap_missing(self, MockTicker):
        MockTicker.return_value = self._mock_ticker(shares=1_000_000, last_price=150.0)
        result = fetch_financial_data("AAPL")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["mkt_cap"], 150_000_000.0)

    @patch("yfinance.Ticker")
    def test_fast_info_zero_shares_returns_none(self, MockTicker):
        MockTicker.return_value = self._mock_ticker(shares=0, last_price=150.0)
        result = fetch_financial_data("AAPL")
        self.assertIsNone(result)

    @patch("yfinance.Ticker")
    def test_fast_info_none_shares_returns_none(self, MockTicker):
        MockTicker.return_value = self._mock_ticker(shares=None, last_price=150.0)
        result = fetch_financial_data("AAPL")
        self.assertIsNone(result)

    @patch("yfinance.Ticker")
    def test_fast_info_mock_object_not_treated_as_valid(self, MockTicker):
        """MagicMock attributes must not satisfy the isinstance(shares, float) check."""
        ticker = MagicMock()
        ticker.info = {"quoteType": "EQUITY", "exchange": "NMS", "marketCap": None,
                       "totalDebt": 0, "totalCash": 0, "totalRevenue": 0,
                       "sector": "Technology", "industry": "Software"}
        # fast_info is a MagicMock — its .shares will also be a MagicMock (truthy but not numeric)
        MockTicker.return_value = ticker
        result = fetch_financial_data("AAPL")
        self.assertIsNone(result)


class TestFMPProfileFallback(unittest.TestCase):
    """When yfinance AND Morningstar fail, FMP profile should be tried."""

    def _yf_none(self):
        mock = MagicMock()
        mock.info = {"quoteType": "EQUITY", "exchange": "NMS", "marketCap": None}
        fi = MagicMock()
        fi.shares = None
        fi.last_price = None
        mock.fast_info = fi
        return mock

    @patch("yfinance.Ticker")
    def test_fmp_profile_used_when_yfinance_fails(self, MockTicker):
        MockTicker.return_value = self._yf_none()

        fmp_data = {
            "symbol": "2222.SR", "company_name": "Saudi Aramco",
            "quote_type": "EQUITY", "debt": 0.0, "cash": 0.0, "revenue": 0.0,
            "prohibited_income": 0.0, "mkt_cap": 2_000_000_000_000.0,
            "sector": "Energy", "exchange": "SAU", "sources": ["FMP"],
        }
        with patch("ibkr_core.features.compliance.data_fetcher._fetch_fmp_profile",
                   return_value=fmp_data):
            result = fetch_financial_data("2222.SR")

        self.assertIsNotNone(result)
        self.assertEqual(result["sector"], "Energy")
        self.assertAlmostEqual(result["mkt_cap"], 2_000_000_000_000.0)

    @patch("yfinance.Ticker")
    def test_fmp_profile_not_called_when_yfinance_succeeds(self, MockTicker):
        MockTicker.return_value.info = {
            "quoteType": "EQUITY", "exchange": "NMS", "marketCap": 1_000_000,
            "totalDebt": 0, "totalCash": 0, "totalRevenue": 100_000,
            "sector": "Tech", "industry": "SW",
        }
        with patch("ibkr_core.features.compliance.data_fetcher._fetch_fmp_profile") as mock_fmp:
            fetch_financial_data("AAPL")
        mock_fmp.assert_not_called()

    @patch("yfinance.Ticker")
    def test_all_sources_fail_returns_none(self, MockTicker):
        MockTicker.return_value = self._yf_none()
        with patch("ibkr_core.features.compliance.data_fetcher._fetch_fmp_profile",
                   return_value=None):
            result = fetch_financial_data("UNKNOWN_TICKER")
        self.assertIsNone(result)


class TestFetchFMPProfile(unittest.TestCase):
    """Unit tests for _fetch_fmp_profile."""

    def test_returns_none_when_no_fmp_key(self):
        from ibkr_core.features.compliance.data_fetcher import _fetch_fmp_profile
        import os
        with patch.dict(os.environ, {"FMP_API_KEY": ""}):
            with patch("ibkr_core.features.compliance.data_fetcher.FMP_API_KEY", None):
                result = _fetch_fmp_profile("AAPL")
        self.assertIsNone(result)

    def test_returns_profile_data(self):
        from ibkr_core.features.compliance.data_fetcher import _fetch_fmp_profile
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{
            "symbol": "2222.SR",
            "companyName": "Saudi Aramco",
            "mktCap": 2_000_000_000_000.0,
            "sector": "Energy",
            "exchangeShortName": "SAU",
        }]
        with patch("ibkr_core.features.compliance.data_fetcher.httpx.get",
                   return_value=mock_resp):
            with patch("ibkr_core.features.compliance.data_fetcher.FMP_API_KEY", "test-key"):
                result = _fetch_fmp_profile("2222.SR")

        self.assertIsNotNone(result)
        self.assertEqual(result["sector"], "Energy")
        self.assertAlmostEqual(result["mkt_cap"], 2_000_000_000_000.0)
        self.assertEqual(result["sources"], ["FMP"])

    def test_returns_none_when_mkt_cap_zero(self):
        from ibkr_core.features.compliance.data_fetcher import _fetch_fmp_profile
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"symbol": "XYZ", "companyName": "X", "mktCap": 0}]
        with patch("ibkr_core.features.compliance.data_fetcher.httpx.get",
                   return_value=mock_resp):
            with patch("ibkr_core.features.compliance.data_fetcher.FMP_API_KEY", "test-key"):
                result = _fetch_fmp_profile("XYZ")
        self.assertIsNone(result)

    def test_returns_none_on_exception(self):
        from ibkr_core.features.compliance.data_fetcher import _fetch_fmp_profile
        with patch("ibkr_core.features.compliance.data_fetcher.httpx.get",
                   side_effect=Exception("network")):
            with patch("ibkr_core.features.compliance.data_fetcher.FMP_API_KEY", "test-key"):
                result = _fetch_fmp_profile("AAPL")
        self.assertIsNone(result)

    def test_returns_none_on_empty_response(self):
        from ibkr_core.features.compliance.data_fetcher import _fetch_fmp_profile
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        with patch("ibkr_core.features.compliance.data_fetcher.httpx.get",
                   return_value=mock_resp):
            with patch("ibkr_core.features.compliance.data_fetcher.FMP_API_KEY", "test-key"):
                result = _fetch_fmp_profile("AAPL")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
