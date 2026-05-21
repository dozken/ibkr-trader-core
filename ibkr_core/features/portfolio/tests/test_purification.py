"""
Tests for purification calculation helper (FR-Purification).

Covers:
- Basic pending calculation from dividends * impure_pct
- Already-purified amount deducted from pending
- Pending never goes negative (over-donated)
- Zero impure_pct → no purification needed
- Missing dividends → no purification needed
- Multiple positions computed independently
"""
import unittest
from ibkr_core.features.portfolio.router import _compute_pending_purification


class TestComputePendingPurification(unittest.TestCase):
    def test_basic_pending_computed_from_dividend_and_impure_pct(self):
        positions = [{"symbol": "AAPL"}]
        dividends_map = {"AAPL": 100.0}
        compliance_map = {"AAPL": 0.05}  # 5% impure
        purified_map = {}
        result = _compute_pending_purification(positions, dividends_map, compliance_map, purified_map)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["purification_needed"], 5.0)
        self.assertAlmostEqual(result[0]["pending"], 5.0)

    def test_already_purified_deducted_from_pending(self):
        positions = [{"symbol": "AAPL"}]
        dividends_map = {"AAPL": 100.0}
        compliance_map = {"AAPL": 0.05}
        purified_map = {"AAPL": 3.0}
        result = _compute_pending_purification(positions, dividends_map, compliance_map, purified_map)
        self.assertAlmostEqual(result[0]["already_purified"], 3.0)
        self.assertAlmostEqual(result[0]["pending"], 2.0)

    def test_pending_never_negative_when_over_donated(self):
        positions = [{"symbol": "AAPL"}]
        dividends_map = {"AAPL": 100.0}
        compliance_map = {"AAPL": 0.05}
        purified_map = {"AAPL": 999.0}
        result = _compute_pending_purification(positions, dividends_map, compliance_map, purified_map)
        self.assertEqual(result[0]["pending"], 0.0)

    def test_zero_impure_pct_means_no_purification_needed(self):
        positions = [{"symbol": "AAPL"}]
        dividends_map = {"AAPL": 500.0}
        compliance_map = {"AAPL": 0.0}
        purified_map = {}
        result = _compute_pending_purification(positions, dividends_map, compliance_map, purified_map)
        self.assertAlmostEqual(result[0]["purification_needed"], 0.0)
        self.assertAlmostEqual(result[0]["pending"], 0.0)

    def test_no_dividends_means_no_purification_needed(self):
        positions = [{"symbol": "AAPL"}]
        dividends_map = {}
        compliance_map = {"AAPL": 0.05}
        purified_map = {}
        result = _compute_pending_purification(positions, dividends_map, compliance_map, purified_map)
        self.assertAlmostEqual(result[0]["purification_needed"], 0.0)
        self.assertAlmostEqual(result[0]["pending"], 0.0)

    def test_multiple_positions_computed_independently(self):
        positions = [{"symbol": "AAPL"}, {"symbol": "MSFT"}]
        dividends_map = {"AAPL": 200.0, "MSFT": 100.0}
        compliance_map = {"AAPL": 0.03, "MSFT": 0.0}
        purified_map = {}
        result = _compute_pending_purification(positions, dividends_map, compliance_map, purified_map)
        self.assertEqual(len(result), 2)
        aapl = next(r for r in result if r["symbol"] == "AAPL")
        msft = next(r for r in result if r["symbol"] == "MSFT")
        self.assertAlmostEqual(aapl["pending"], 6.0)   # 200 * 0.03
        self.assertAlmostEqual(msft["pending"], 0.0)


if __name__ == "__main__":
    unittest.main()
