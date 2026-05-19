# Glossary of Terms

A bridge between Islamic Finance and Algo-Trading terminology.

## 1. Shariah/Financial Terms
- **Riba**: Interest. The system is hard-coded to avoid interest-bearing margin and securities.
- **Gharar**: Excessive uncertainty/speculation. This is why we avoid complex derivatives and futures.
- **Maysir**: Gambling. Used to identify high-frequency "churn" patterns that resemble gambling rather than investing.
- **Qabd (Possession)**: The legal ownership of a security. This is addressed by our **Settlement Guard (T+2)** logic.
- **Purification**: The removal of minor non-compliant income (e.g., <5% revenue from prohibited sources) via charitable donation.
- **AAOIFI**: Accounting and Auditing Organization for Islamic Financial Institutions. The standard-setter for our 33% and 5% ratios.

## 2. Technical Trading Terms
- **TWS/Gateway**: The IBKR software we connect to via sockets.
- **Paper Account**: The simulated trading environment used for all integration tests.
- **T+2 Settlement**: The standard two-business-day cycle for stock ownership transfer.
- **Shadow Trading**: A local execution mode where no orders are sent to IBKR, used for "Dry Run" testing.
- **Circuit Breaker**: A safety mechanism that stops all trading if a compliance data source fails.
