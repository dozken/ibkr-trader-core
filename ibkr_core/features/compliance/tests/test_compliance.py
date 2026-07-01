import unittest
from ibkr_core.features.compliance.screening import check_shariah_compliance

class TestCompliance(unittest.TestCase):
    def test_aaoifi_debt_ratio_fail(self):
        # TEST: debt / mkt_cap >= 30% should fail (AAOIFI Std 21; COMPLIANCE.md §1-A)
        result = check_shariah_compliance(
            "DEBT_HEAVY_CO", debt=40, cash=5, revenue=100,
            prohibited_income=1, mkt_cap=100, sector="Technology"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Debt ratio", result.reason)

    def test_aaoifi_cash_ratio_fail(self):
        # TEST: (cash + interest-bearing securities) / mkt_cap >= 30% should fail
        # (combined AAOIFI liquidity screen; COMPLIANCE.md §1-B)
        result = check_shariah_compliance(
            "CASH_HEAVY_CO", debt=10, cash=35, revenue=100,
            prohibited_income=1, mkt_cap=100, sector="Technology"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Liquidity ratio", result.reason)

    def test_aaoifi_liquidity_is_combined_cash_plus_interest_bearing(self):
        # Cash 20% alone passes; interest-bearing securities 15% alone passes;
        # but COMBINED 35% >= 30% must FAIL (COMPLIANCE.md §1-B — single combined gate).
        passes = check_shariah_compliance(
            "LIQ_CASH_ONLY", debt=10, cash=20, revenue=100,
            prohibited_income=1, mkt_cap=100, sector="Technology",
            interest_bearing_securities=0,
        )
        self.assertTrue(passes.is_compliant)
        fails = check_shariah_compliance(
            "LIQ_COMBINED", debt=10, cash=20, revenue=100,
            prohibited_income=1, mkt_cap=100, sector="Technology",
            interest_bearing_securities=15,
        )
        self.assertFalse(fails.is_compliant)
        self.assertIn("Liquidity ratio", fails.reason)

    def test_aaoifi_debt_30pct_boundary_fails(self):
        # Exactly 30% debt must FAIL (threshold is inclusive: ratio must be < 30%).
        result = check_shariah_compliance(
            "BOUNDARY30", debt=30, cash=5, revenue=100,
            prohibited_income=1, mkt_cap=100, sector="Technology",
        )
        self.assertFalse(result.is_compliant)
        # 29% debt passes.
        ok = check_shariah_compliance(
            "BOUNDARY29", debt=29, cash=5, revenue=100,
            prohibited_income=1, mkt_cap=100, sector="Technology",
        )
        self.assertTrue(ok.is_compliant)

    def test_mkt_cap_zero_blocks_fail_closed(self):
        # Non-positive market cap → undeterminable → BLOCKED (not a silent pass).
        result = check_shariah_compliance(
            "NO_MKTCAP", debt=0, cash=0, revenue=100,
            prohibited_income=0, mkt_cap=0, sector="Technology",
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("market cap", result.reason)

    def test_negative_ratio_buffer_cannot_loosen(self):
        # A negative buffer must NEVER loosen thresholds. 32% debt fails at AAOIFI 30%
        # and must still fail even if a negative buffer tries to widen the limit.
        result = check_shariah_compliance(
            "NEG_BUFFER", debt=32, cash=5, revenue=100,
            prohibited_income=1, mkt_cap=100, sector="Technology",
            ratio_buffer=-10.0,
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Debt ratio", result.reason)

    def test_missing_revenue_blocks_fail_closed(self):
        # Positive mkt_cap but no revenue → cannot screen impure income → BLOCKED
        # (must NOT pass all-zero ratios as COMPLIANT).
        result = check_shariah_compliance(
            "NO_REV", debt=10, cash=10, revenue=0,
            prohibited_income=0, mkt_cap=100, sector="Technology",
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("revenue data missing", result.reason)

    def test_missing_balance_sheet_blocks_fail_closed(self):
        # Revenue present but debt+cash+interest-bearing all 0 → balance sheet not
        # retrieved → BLOCKED (a leveraged name whose fundamentals were missing must
        # not read as COMPLIANT via zero ratios).
        result = check_shariah_compliance(
            "NO_BALANCE", debt=0, cash=0, revenue=100,
            prohibited_income=0, mkt_cap=100, sector="Technology",
            interest_bearing_securities=0,
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("balance-sheet data missing", result.reason)

    def test_crisis_vix_buffer_does_not_block_clean_name(self):
        # At VIX>=30 the 5pp buffer would drive the 5% impure threshold to 0, making
        # imp_r>=0.0 block EVERY name. The floor prevents that: a clean name (0 impure,
        # low debt/liquidity) must still pass at buffer=5.
        result = check_shariah_compliance(
            "CLEAN_CRISIS", debt=5, cash=5, revenue=100,
            prohibited_income=0, mkt_cap=100, sector="Technology",
            ratio_buffer=5.0,
        )
        self.assertTrue(result.is_compliant)

    def test_aaoifi_revenue_ratio_fail(self):
        # TEST: (Prohibited income) / Total Revenue < 5%
        result = check_shariah_compliance(
            "HARAM_REVENUE_CO", debt=10, cash=5, revenue=100, 
            prohibited_income=6, mkt_cap=100, sector="Technology"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Prohibited income", result.reason)

    def test_aaoifi_all_pass(self):
        # TEST: Clean stock
        result = check_shariah_compliance(
            "HALAL_CO", debt=10, cash=10, revenue=100, 
            prohibited_income=2, mkt_cap=100, sector="Technology"
        )
        self.assertTrue(result.is_compliant)
        self.assertIsNone(result.reason)

    def test_prohibited_sector_alcohol(self):
        # TEST: Alcohol sector should fail
        # Citing COMPLIANCE.md Section 1
        result = check_shariah_compliance(
            "BEER_CO", debt=0, cash=0, revenue=100, 
            prohibited_income=0, mkt_cap=100, sector="Alcohol"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Prohibited sector: Alcohol", result.reason)

    def test_prohibited_sector_gambling(self):
        # TEST: Gambling sector should fail
        result = check_shariah_compliance(
            "CASINO_CO", debt=0, cash=0, revenue=100, 
            prohibited_income=0, mkt_cap=100, sector="Gambling"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Prohibited sector: Gambling", result.reason)

    def test_prohibited_sector_finance(self):
        # TEST: Conventional Finance sector should fail
        result = check_shariah_compliance(
            "BANK_CO", debt=0, cash=0, revenue=100, 
            prohibited_income=0, mkt_cap=100, sector="Conventional Finance"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Prohibited sector: Conventional Finance", result.reason)

    def test_prohibited_sector_tobacco(self):
        # TEST: Tobacco sector should fail
        # Citing COMPLIANCE.md Section 1
        result = check_shariah_compliance(
            "SMOKE_CO", debt=0, cash=0, revenue=100, 
            prohibited_income=0, mkt_cap=100, sector="Tobacco"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Prohibited sector: Tobacco", result.reason)

    def test_prohibited_sector_weapons(self):
        # TEST: Weapons sector should fail
        # Citing COMPLIANCE.md Section 1
        result = check_shariah_compliance(
            "BOMB_CO", debt=0, cash=0, revenue=100, 
            prohibited_income=0, mkt_cap=100, sector="Weapons"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Prohibited sector: Weapons", result.reason)

if __name__ == '__main__':
    unittest.main()
