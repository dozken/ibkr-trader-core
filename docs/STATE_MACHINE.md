# Trade State Machine

The life-cycle of a trade is managed by a strict state machine to prevent race conditions and non-compliant execution.

## 1. State Definitions
- `IDLE`: No active order.
- `AI_ANALYSIS`: AI Strategy Agent analyzing signals and sentiment.
- `SCREENING`: Fetching financial data and business activity.
- `HALAL_CERTIFIED`: Symbol passed all checks. Valid for 24 hours.
- `PRE_ORDER`: Calculating position size and verifying cash balance.
- `SUBMITTED`: Order sent to IBKR. Waiting for acknowledgement.
- `FILLED`: Order executed.
- `RE_SCREENING`: Periodic audit of held positions against updated financial data.
- `LIQUIDATING`: Automated sell-off process for assets that failed re-screening.
- `PENDING_SETTLEMENT`: Stock owned, but T+2 settlement not complete.
- `SETTLED`: Full legal possession (Qabd). Ready for sale if needed.

## 2. Invalid Transitions (The Guardrails)
- **Blocked**: `IDLE` -> `SUBMITTED` (Must go through `SCREENING`).
- **Blocked**: `PENDING_SETTLEMENT` -> `IDLE` (Cannot sell what is not settled).
- **Blocked**: `FILLED` -> `SCREENING` (Cannot re-screen a filled order; it must be a new state).

## 3. Failure States
- `REJECTED_COMPLIANCE`: Symbol failed Shariah screen.
- `REJECTED_FUNDS`: Insufficient cash (no margin allowed).
- `IBKR_ERROR`: Network or API failure. Triggers "Safe Shutdown."
