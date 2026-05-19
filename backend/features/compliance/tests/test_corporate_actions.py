"""
TDD tests for Phase 5.1B — Corporate Action Awareness.
yfinance mocked throughout — no live network calls.
"""
import unittest
from unittest.mock import MagicMock, patch


def _make_news(titles: list[str]) -> list[dict]:
    return [{"title": t, "link": "http://example.com"} for t in titles]


class TestCorporateActionDetection(unittest.TestCase):

    def _check(self, news_titles, news_limit=20):
        from backend.features.compliance.corporate_actions import check_corporate_actions
        mock_ticker = MagicMock()
        mock_ticker.news = _make_news(news_titles)
        with patch("backend.features.compliance.corporate_actions.yf.Ticker", return_value=mock_ticker):
            return check_corporate_actions("AAPL", news_limit=news_limit)

    def test_merger_keyword_triggers_alert(self):
        alerts = self._check(["Apple and Microsoft announce merger agreement"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].action_type, "MERGER")
        self.assertEqual(alerts[0].symbol, "AAPL")

    def test_acquisition_keyword_triggers_merger_alert(self):
        alerts = self._check(["Apple completes acquisition of startup"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].action_type, "MERGER")

    def test_takeover_keyword_triggers_merger_alert(self):
        alerts = self._check(["Hostile takeover bid for Apple rejected"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].action_type, "MERGER")

    def test_spinoff_keyword_triggers_spinoff_alert(self):
        alerts = self._check(["Apple announces spin-off of services division"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].action_type, "SPINOFF")

    def test_spinoff_no_hyphen_detected(self):
        alerts = self._check(["Company plans spinoff of finance unit"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].action_type, "SPINOFF")

    def test_divestiture_keyword_triggers_spinoff_alert(self):
        alerts = self._check(["Apple confirms divestiture of ad business"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].action_type, "SPINOFF")

    def test_irrelevant_news_returns_empty(self):
        alerts = self._check(["Apple reports record quarterly earnings", "New iPhone model leaked"])
        self.assertEqual(alerts, [])

    def test_multiple_relevant_items_all_captured(self):
        alerts = self._check([
            "Apple merger talks with Google confirmed",
            "Apple plans spinoff of hardware unit",
            "AAPL stock rises 2%",
        ])
        self.assertEqual(len(alerts), 2)

    def test_news_limit_respected(self):
        titles = [f"Apple merger deal #{i}" for i in range(30)]
        alerts = self._check(titles, news_limit=5)
        self.assertEqual(len(alerts), 5)

    def test_case_insensitive_matching(self):
        alerts = self._check(["Apple MERGER With Google"])
        self.assertEqual(len(alerts), 1)

    def test_headline_preserved_in_alert(self):
        headline = "Apple and Tesla announce merger"
        alerts = self._check([headline])
        self.assertEqual(alerts[0].headline, headline)

    def test_empty_news_returns_empty(self):
        alerts = self._check([])
        self.assertEqual(alerts, [])

    def test_none_news_returns_empty(self):
        from backend.features.compliance.corporate_actions import check_corporate_actions
        mock_ticker = MagicMock()
        mock_ticker.news = None
        with patch("backend.features.compliance.corporate_actions.yf.Ticker", return_value=mock_ticker):
            alerts = check_corporate_actions("AAPL")
        self.assertEqual(alerts, [])

    def test_yfinance_exception_returns_empty(self):
        from backend.features.compliance.corporate_actions import check_corporate_actions
        with patch(
            "backend.features.compliance.corporate_actions.yf.Ticker",
            side_effect=Exception("network error"),
        ):
            alerts = check_corporate_actions("AAPL")
        self.assertEqual(alerts, [])

    def test_missing_title_key_skipped(self):
        from backend.features.compliance.corporate_actions import check_corporate_actions
        mock_ticker = MagicMock()
        mock_ticker.news = [{"link": "http://example.com"}]  # no "title"
        with patch("backend.features.compliance.corporate_actions.yf.Ticker", return_value=mock_ticker):
            alerts = check_corporate_actions("AAPL")
        self.assertEqual(alerts, [])

    @patch("backend.features.compliance.corporate_actions.httpx.get")
    def test_fmp_merger_detected(self, mock_get):
        from backend.features.compliance.corporate_actions import check_corporate_actions
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"title": "AAPL to acquire Tesla in massive deal", "text": "..."},
            {"title": "Unrelated deal", "text": "..."}
        ]
        mock_get.return_value = mock_resp
        
        with patch("backend.features.compliance.corporate_actions.FMP_API_KEY", "test-key"):
            with patch("backend.features.compliance.corporate_actions.yf.Ticker") as mock_yf:
                mock_yf.return_value.news = []
                alerts = check_corporate_actions("AAPL")
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].source, "FMP")
        self.assertEqual(alerts[0].action_type, "MERGER")

    @patch("backend.features.compliance.corporate_actions.httpx.get")
    def test_fmp_and_yf_deduplicated(self, mock_get):
        from backend.features.compliance.corporate_actions import check_corporate_actions
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"title": "AAPL merger with MSFT", "text": "..."}]
        mock_get.return_value = mock_resp
        
        with patch("backend.features.compliance.corporate_actions.FMP_API_KEY", "test-key"):
            with patch("backend.features.compliance.corporate_actions.yf.Ticker") as mock_yf:
                mock_yf.return_value.news = [{"title": "AAPL merger with MSFT", "link": "..."}]
                alerts = check_corporate_actions("AAPL")
        
        # Should only have FMP alert if titles are similar
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].source, "FMP")


class TestCorporateActionAlertFields(unittest.TestCase):

    def test_alert_dataclass_fields(self):
        from backend.features.compliance.corporate_actions import CorporateActionAlert
        alert = CorporateActionAlert(symbol="AAPL", action_type="MERGER", headline="Big merger deal")
        self.assertEqual(alert.symbol, "AAPL")
        self.assertEqual(alert.action_type, "MERGER")
        self.assertEqual(alert.headline, "Big merger deal")
        self.assertEqual(alert.source, "YahooFinance")
        self.assertIsNone(alert.event_date)


if __name__ == "__main__":
    unittest.main()
