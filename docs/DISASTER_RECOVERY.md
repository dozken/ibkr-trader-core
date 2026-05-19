# Disaster Recovery & Emergency Procedures

"Plan for the worst, build for the best."

## 1. The "Kill-Switch" (Emergency Liquidation)
- **Manual Trigger**: The UI must have a prominent "Panic Button" that cancels all active orders and liquidates all positions at market price.
- **API Failure**: If the bot loses connection to the IBKR Gateway and cannot reconnect within 5 minutes, it must send a "Critical Shutdown" alert to the user's mobile device.

## 2. State Recovery (Post-Crash)
- **Persistence**: The database stores the exact state of every order (`SUBMITTED`, `FILLED`, etc.).
- **Reconciliation**: Upon reboot, the bot must sync with IBKR's `executions()` and `positions()` lists to ensure the local database matches reality before resuming activity.
- **No Double-Buy**: The bot must verify existing positions before executing any "Pending" Buy orders from before the crash.

## 3. Database Failure
- **Daily Backups**: Automated daily backups of the `audit_logs` and `purification_ledger`.
- **Secondary Node**: Documentation on how to quickly spin up a replica of the bot on a new server using the same `.env` and database backup.

## 4. Emergency Contacts
- **Interactive Brokers Desk**: Keep the direct phone number for the IBKR Trade Desk in this document for manual order cancellation if the API is totally unreachable.
- **Provider Support**: Contact info for your Shariah data provider.
