from prometheus_client import Gauge, Counter, Summary, Histogram

# Technical Metrics
IBKR_CONNECTED = Gauge("ibkr_connected", "IBKR connection status (1=connected, 0=disconnected)")
API_REQUESTS = Counter("api_requests_total", "Total API requests to external providers", ["provider"])
API_LATENCY = Summary("api_request_latency_seconds", "Latency of external API requests", ["provider"])

# Compliance Metrics
PORTFOLIO_COMPLIANCE_PCT = Gauge("portfolio_compliance_percent", "Percentage of AUM that is compliant")
PURIFICATION_PENDING = Gauge("purification_pending_usd", "Total purification liabilities pending donation")
ZAKAT_LIABILITY = Gauge("zakat_liability_usd", "Calculated Zakat liability based on current NLV")

# Trading Metrics
TOTAL_NLV = Gauge("portfolio_net_liquidation_value_usd", "Total Net Liquidation Value of the portfolio")
CASH_AVAILABLE = Gauge("cash_available_usd", "Total available cash in the account")
ACTIVE_POSITIONS = Gauge("active_positions_count", "Total number of open positions")
TRADES_EXECUTED = Counter("trades_executed_total", "Total number of trades executed", ["side"])
