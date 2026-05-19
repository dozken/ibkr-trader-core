import unittest
from backend.features.compliance.screening import check_shariah_compliance

class TestCompliance(unittest.TestCase):
    def test_aaoifi_debt_ratio_fail(self):
        # TEST: Stock with > 33% debt should fail
        # Citing COMPLIANCE.md Section 2
        result = check_shariah_compliance(
            "DEBT_HEAVY_CO", debt=40, cash=5, revenue=100, 
            prohibited_income=1, mkt_cap=100, sector="Technology"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Debt ratio", result.reason)

    def test_aaoifi_cash_ratio_fail(self):
        # TEST: (Cash + Interest-bearing securities) / Market Cap < 33%
        result = check_shariah_compliance(
            "CASH_HEAVY_CO", debt=10, cash=35, revenue=100, 
            prohibited_income=1, mkt_cap=100, sector="Technology"
        )
        self.assertFalse(result.is_compliant)
        self.assertIn("Cash ratio", result.reason)

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
