# Best Practices for Shariah Trading

## 1. Automated Liquidation (The Kill-Switch)
A stock's compliance status is dynamic. If a held position fails a daily check (e.g., Debt >= 30% Market Cap, per AAOIFI Shari'ah Standard No. 21), the system must react.
- **Immediate Alert**: Notify user via high-priority channel (SMS/Push).
- **Grace Period**: Default to 24-hour liquidation window to avoid flash-crash sell-offs, unless the violation is business-activity related (e.g., merging with a bank), which requires immediate exit.
- **Audit Log**: Record the exact ratio violation that triggered the sell.

## 2. Purification Ledger Math
Purification is the process of removing "impure" income (non-compliant revenue) from your gains.
- **Formula**: `Purification_Amount = (Total_Dividend) * (Non_Compliant_Revenue_Percentage)`
- **Execution**: The app should automatically subtract this amount from the "Realized PnL" view and move it to a "Purification Pending" bucket.
- **Charity API**: (Optional) Integration with payment gateways to simplify the donation of purified funds.

## 3. The "Settlement Guard" (Qabd)
Selling before T+2 settlement is a risk of selling "what you do not own."
- **Strict Mode**: The app should query the `settlement_date` from IBKR and keep the security locked in the UI until `current_date >= settlement_date`.
- **Intraday Wash**: If a user accidentally buys/sells the same stock in minutes, the system should flag it for manual review to ensure no "Maysir" (gambling) patterns are emerging.

## 4. Financial Data Integrity
Compliance is only as good as the data.
- **Multi-Source Verification**: Compare ratios between two providers (e.g., Zoya and Yahoo Finance) if the ratio is close to the 30% threshold (e.g., between 28% and 30%). Our AAOIFI screen stays canonical — a certifier may only tighten (block on doubt), never loosen the verdict.
- **Cache Policy**: Financial ratios should be cached for 24 hours, but Business Activity status should be checked against the latest quarterly reports.

## 5. Testing & Quality (TDD)
- **100% Coverage**: Every branch of the compliance logic must be tested.
- **Paper Trading Sandbox**: All integration tests must be executed against the IBKR Paper Trading gateway. This validates real-world order status transitions (Submitted -> PreSubmitted -> Filled -> Settled).
- **Property-Based Testing**: Use `Hypothesis` (Python) or `Proptest` (Rust) to verify compliance math against extreme edge cases.

## 6. System Resilience (Error Handling)
- **Circuit Breakers**: If the compliance data source (e.g., Zoya API) is down, the system must "Fail-Closed" and disable all Buy orders.
- **Graceful Reconnection**: The IBKR worker must implement exponential backoff for socket reconnections.
- **Atomic Trades**: Use database transactions to ensure a trade is only logged if the execution is confirmed by IBKR.

## 7. Micro-Investing & Commissions
- **Efficiency Guard**: For small deposits (e.g., $1), the Portfolio Allocator must check if the transaction fee (e.g., $0.35 on IBKR Pro) makes the trade mathematically viable.
- **Accumulation Logic**: If fees are too high for a $1 trade, the bot should "queue" the cash and deploy it only when the total idle balance reaches a viable threshold (e.g., $10).
