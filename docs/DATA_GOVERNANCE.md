# Data Governance & Integrity

Shariah compliance is only as strong as the data used for screening.

## 1. Multi-Source Consensus
- **Conflict Resolution**: If two data providers (e.g., Zoya and Yahoo Finance) disagree on a ticker's compliance status, the system must **Default to Non-Compliant** (Haram) until human review.
- **Strict Ratios**: If a ratio (e.g., Debt/Mkt Cap) is within a 2% "Danger Zone" of the 33% limit, the ticker is flagged as "Risky" and Buy orders are restricted.

## 2. Data Freshness (Stale-Data Guard)
- **Financial Snapshots**: If a company's financial data is older than 120 days (missing a quarterly update), the system soft-locks the ticker.
- **Business Screening**: Business activity descriptions must be re-validated after any M&A (Merger & Acquisition) news event.

## 3. Manual Overrides
- **The "Fatwa" Override**: In rare cases where a scholar provides a specific ruling on a complex instrument (e.g., a specific REIT), a human-signed override can be applied.
- **Audit Requirement**: Every manual override must be linked to a PDF document justifying the decision.

## 4. Error Handling
- **Missing Data**: If a ratio cannot be calculated (e.g., total revenue is 0), the stock is treated as Non-Compliant.
- **Zero-Value Protection**: Hard guards against `NaN` or `Infinite` results in math functions to prevent "Glitched" compliance passes.
