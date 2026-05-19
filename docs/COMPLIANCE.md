# Shariah Compliance Framework

This document outlines the strict rules and screening methodologies applied by the application.

## 1. Primary Screening (Sector/Business)
All symbols must pass a business activity screen. Prohibited sectors include:
- **Conventional Finance**: Banks, insurance (except Takaful), and interest-based lending.
- **Alcohol & Tobacco**: Production and sale.
- **Entertainment**: Gambling, casinos, and adult content.
- **Pork-related products**: Production and distribution.
- **Defense/Weapons**: Specifically those deemed unethical or offensive.

## 2. Financial Ratio Screening (AAOIFI Standard)
Positions must be checked daily/monthly against these maximum thresholds:
- **Interest-Bearing Debt**: Debt / Market Cap < 33%
- **Interest-Bearing Securities/Cash**: (Cash + Interest-bearing securities) / Market Cap < 33%
- **Non-Compliant Income**: (Prohibited income) / Total Revenue < 5%

## 3. Transactional Prohibitions
The system is hard-coded to prevent:
- **Zero Leverage/Margin**: Only Cash Accounts allowed. The app must verify `AvailableFunds >= OrderValue`.
- **Short Selling**: Selling what you do not own (forbidden).
- **Conventional Options/Futures**: Deemed speculative (Gharar) or interest-based.

## 4. Possession & Settlement (Qabd)
To address the "Selling before owning" concern (T+2 settlement):
- **Constructive Possession**: The app treats the trade execution as the transfer of risk.
- **Settlement Guard (Optional Strict Mode)**: A configurable setting to prevent selling a security until it has fully settled in the account (typically 1-2 business days).

## 4. Monitoring & Re-Screening
- **Initial Check**: Performed before any `BUY` order is placed.
- **Daily Check**: Financial ratios updated based on market cap fluctuations.
- **Monthly/Quarterly Check**: Full fundamental review when new financial statements are released.

## 5. Purification Process
If a company generates <5% non-compliant income, the system will:
- Calculate the percentage of dividends/gains attributable to non-compliant sources.
- Log these amounts in a "Purification Ledger" for charitable donation.
- **Automatic Sell Trigger**: If a company's debt or business activity crosses the compliance threshold, the system must trigger a liquidation order within a defined "grace period" (e.g., 30 days or immediate depending on volatility).
