# System Architecture (Pro Hybrid Stack)

## Tech Stack
- **Backend Engine**: Python 3.10+ with **FastAPI**.
- **Trading SDK**: `ib_insync` (Asynchronous IBKR integration).
- **Compliance/Data**: `pandas` (Analysis), `pydantic` (Schemas).
- **Frontend UI**: **React (TypeScript)** via Vite.
- **Styling**: **Tailwind CSS** & **Shadcn/UI**.
- **Database**: **PostgreSQL** or **SQLite** with SQLAlchemy.
- **Communication**: **WebSockets** for real-time data streaming; **REST** for configuration.

## Testing Stack
- **Backend Testing**: `pytest` + `pytest-asyncio` (Python) or `cargo test` + `tokio-test` (Rust).
- **Environment**: **IBKR Paper Trading (Port 7497/4002)**. All tests must be performed against a running TWS/Gateway instance in Paper Mode.
- **Coverage**: `coverage.py` or `cargo-tarpaulin`.
- **Frontend Testing**: `Vitest` and `React Testing Library`.
- **E2E**: `Playwright` for verifying the full "Trade -> Compliance -> Execute" flow.
## Module Breakdown
0. **Config Engine (Python)**: Loads and validates user "taste" settings (Risk, Thresholds, Buffers) from `config.yaml` or Database.
1. **Trading Worker (Python)**: Persistent background process managing the IBKR connection.
2. **Compliance Engine (Python)**: Validates symbols and ratios against Shariah rules.
3. **AI Strategy Agent (Python)**: Analyzes market signals using a **Hybrid Consensus Model** (Traditional Factor Heuristics + Random Forest ML) to generate trade recommendations.
4. **Portfolio Allocator (Python)**: Monitors account cash balance and autonomously decides position sizing.
5. **API Gateway (FastAPI)**: Bridges the Python engine to the React frontend, including a **Prometheus /metrics** endpoint.
6. **Trading Dashboard (React)**: High-performance **PWA** UI for monitoring and updating User Settings.
7. **Audit & Reporting**: Daily tasks for Zakat, Purification, and compliance re-screening.

## Data Flow
1. **Trigger**: System detects newly deposited idle cash OR AI Strategy Agent identifies an opportunity.
2. **Signal Generation**: AI suggests top 3 high-conviction compliant assets based on the **Risk Profile** in Config.
3. **Compliance Guard**: Queries Compliance Engine for current AAOIFI status, applying the **Ratio Buffer** from Config.
4. **Validation & Sizing**: If compliant, Portfolio Allocator calculates safe position sizes, respecting **min_trade_size** and **max_commission_pct**.
5. **Execution**: Trading Worker sends order to IBKR.
6. **Persistence**: Log trade and compliance snapshot to Database.
7. **Continuous Audit**: Scheduler re-checks assets daily. If an asset becomes Non-Compliant, alert/sell.

## Security
- Use `.env` for `IB_PAPER_ACCOUNT` and `IB_LIVE_ACCOUNT` credentials.
- Ensure "Read-Only" API tokens are used for testing.
