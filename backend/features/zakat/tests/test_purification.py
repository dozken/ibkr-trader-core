import pytest
from backend.features.zakat.purification import calculate_purification_amount

def test_calculate_purification_amount():
    """
    Test purification math based on BEST_PRACTICES.md.
    Formula: Purification_Amount = (Total_Dividend) * (Non_Compliant_Revenue_Percentage)
    """
    dividend = 100.0
    impure_ratio = 0.012  # 1.2%
    
    expected = 1.2
    actual = calculate_purification_amount(dividend, impure_ratio)
    
    assert actual == expected

def test_calculate_purification_zero_impure():
    assert calculate_purification_amount(100.0, 0.0) == 0.0

def test_calculate_purification_zero_dividend():
    assert calculate_purification_amount(0.0, 0.05) == 0.0
