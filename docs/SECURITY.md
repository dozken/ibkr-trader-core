# Security Policy

## 1. Secret Management
- **No Plaintext Keys**: IBKR credentials, API keys, and database passwords must NEVER be stored in plaintext.
- **Local Dev**: Use `.env` with a strictly ignored `.gitignore` entry.
- **Production**: Use a secure vault (e.g., AWS Secrets Manager, HashiCorp Vault, or encrypted GitHub Secrets).

## 2. Network Isolation
- **IP Whitelisting**: The IBKR TWS/Gateway must be configured to only accept incoming socket connections from the specific IP address of the application server.
- **VPN/Tunneling**: If the bot is running on a remote server, use an SSH tunnel or VPN to connect to the IBKR Gateway port.

## 3. Data Protection
- **Encryption at Rest**: The database (SQLite/PostgreSQL) containing trade logs and compliance snapshots must be encrypted.
- **API Permissions**: Use "Read-Only" credentials for the UI. Only the background Worker process should have "Trade" permissions.

## 4. Transactional Safety
- **Manual Approval Toggle**: The system must support a "Manual Confirmation" mode where no trade is sent to IBKR without a human signature (web button click), even if the bot logic triggers a buy.
- **Hard Limits**: Maximum position size per ticker and maximum total portfolio exposure must be hard-coded as a secondary guardrail.
