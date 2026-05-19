"""
Purification Ledger Math.
Ref: BEST_PRACTICES.md Section 2.
Track C: Trading & Infrastructure.
"""

def calculate_purification_amount(total_dividend: float, non_compliant_revenue_pct: float) -> float:
    """
    Calculates the purification amount for a dividend based on non-compliant revenue percentage.
    Formula: Purification_Amount = (Total_Dividend) * (Non_Compliant_Revenue_Percentage)
    Ref: BEST_PRACTICES.md Section 2.
    """
    if total_dividend < 0:
        raise ValueError("Dividend cannot be negative")
    if non_compliant_revenue_pct < 0 or non_compliant_revenue_pct > 1:
        raise ValueError("Non-compliant revenue percentage must be between 0 and 1")
        
    return total_dividend * non_compliant_revenue_pct
