# System Monitoring & Health

A trading bot must be observable in real-time to ensure both technical and Shariah integrity.

## 1. Heartbeat & Connectivity
- **Socket Watchdog**: The system must monitor the IBKR TWS/Gateway socket. If disconnected for >60 seconds, trigger a high-priority alert (PagerDuty/Slack).
- **Compliance Latency**: Track the time taken to fetch and validate a symbol. If latency > 5s, flag for investigation.

## 2. Technical Metrics (Prometheus/Grafana)
- **Memory/CPU**: Monitor for leaks in the persistent Python/Rust worker.
- **API Rate Limits**: Track IBKR and Financial Data provider usage to avoid throttling during volatile markets.

## 3. Compliance Metrics
- **Portfolio Health %**: Percentage of total AUM currently in "Compliant" vs "Pending Audit" status.
- **Liquidation Success Rate**: Percentage of non-compliant stocks sold within the 24h grace period.
- **Purification Velocity**: Real-time tracking of pending vs. donated purification funds.

## 4. Alerting Levels
- **INFO**: Trade executed, compliance check passed.
- **WARNING**: Compliance data source is lagging; using cached data (older than 12h).
- **CRITICAL**: IBKR connection lost, or a position has become non-compliant with no successful liquidation.
