# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.28] - 2026-08-12

### Changed
- **A read-only live account may now run alongside a paper test.** The startup guard refused any live/paper coexistence, which meant watching real positions and running a paper test were mutually exclusive. It now blocks only an *armed* live account beside an active paper account — a `read_only` live account has no order path at all (`execute_trade` rejects pre-IBKR, and the worker connects in IBKR readonly mode). Coexistence is logged as a warning. The `PAPER_TEST` env flag stays strict: it marks a dedicated paper run and still refuses any live account.
- `POST`/`PATCH` on `/api/accounts` reject (409) any change that would produce an armed live account beside an active paper account — arming one, or activating paper next to one. Without this the forbidden state was reachable at runtime and would only surface as a crash at the next restart. The check runs against the state the write *would* produce, so a rejected call leaves the DB untouched.

## [0.3.27] - 2026-08-12

### Added
- **Arm / disarm an account from the header.** The account chip now shows whether the selected account is `READ-ONLY` or `ARMED`, with an inline toggle. Arming goes through a confirmation dialog naming the IBKR account; disarming back to read-only is one click, since that direction only removes risk.
- `PATCH /api/accounts/{id}` now applies a `read_only` change to the running worker. `execute_trade` already re-read the flag per order, but a worker connected in IBKR readonly mode cannot transmit orders at all, so the flag alone left an armed account mute until the next restart. The worker is now reconnected in the new mode. Accounts sharing one IBKR connection (same host/port/client_id) share the mode — that case is logged as a warning.

### Security
- `POST`/`PATCH`/`DELETE` on `/api/accounts` now require `X-API-Key`. Creating an account, flipping `read_only`, and deactivating were previously unauthenticated, so anything that could reach the API could arm real-money trading.

## [0.3.24] - 2026-08-08

### Fixed
- **BUY sizing could spend margin (Rule #1).** Position sizing used IBKR `AvailableFunds`, which is NetLiquidation minus the margin requirement — on a margin-enabled account that exceeds settled cash (measured 1,068,625 vs 998,592), so a BUY could be funded with borrowed money. The budget is now bounded by `TotalCashValue`. On a cash account the two are equal, making this a no-op there. A `trading_capital_cap` below the cash balance already masked this; accounts running without a cap were exposed.
- **`/api/portfolio/summary` overstated NAV by the margin cushion.** `total_value` added `AvailableFunds` to position market value, double-counting margin capacity and inflating the dashboard's portfolio total by $70,033 (+6.4%) on the paper account. Now uses settled cash, matching the `NetLiquidation` figure that `portfolio_snapshots` has been recording all along. `cash_available` likewise reports cash rather than buying power.

### Added
- `IBKRWorker.get_total_cash()` — IBKR `TotalCashValue` in account-base currency, the no-margin counterpart to `get_available_funds()`.

## [0.2.0] - 2026-05-21

### Changed (BREAKING)
- Top-level Python package renamed `backend` → `ibkr_core` to prevent namespace shadowing when used as a library. All imports change from `from backend.X import Y` to `from ibkr_core.X import Y`. Downstream users must update imports + any `backend/` paths in their Dockerfiles / scripts.

## [0.3.9] - 2026-06-13

### Added
- `signal_logs.benchmark_7d_pct` / `benchmark_30d_pct` — SPY return over the same forward window as each outcome, enabling market-relative (alpha) labels downstream. Migration `d7a2b9c41e08`.

### Fixed
- Restored missing migration `a1f7c2d83b90` (add `signal_logs.features`): `b2e9d4f17a3c` referenced it as parent but the file was absent from this repo, breaking `alembic upgrade head` for fresh installs.

## [Unreleased]

### Added
- `AIModuleGate` wraps `features/ai/*` pages with a graceful 404 banner pointing to the open-core split docs.
- `ibkr_core/strategies/halal_universe_seed.py` — reference seed list (20 US large-caps) so `/api/system/markets` renders without the private AI module.
- README badges (license / Python / FastAPI / React) + screenshots placeholder.
- GitHub repo metadata (topics, description, Discussions enabled).
- `.github/ISSUE_TEMPLATE/` — bug, feature, strategy-question, security-disclosure link.
- `_deferred/release-pypi.yml.template` — Trusted Publishing workflow for PyPI + TestPyPI.
- `_deferred/ci.yml.template` — backend + frontend CI workflow.
- Dependabot config for python / npm / actions monthly updates.
- Example third-party Strategy package at `examples/momentum_strategy/`.

### Changed
- `Dockerfile`: dropped `COPY AGENT.md` (private file).
- `docker-compose.yml`: removed obsolete `version: '3.8'`.
- `docs/DEPLOYMENT.md`: `/api/ai/ml-status` clarified as private-module-only.

### Fixed
- `frontend/src/router` renamed `.ts` → `.tsx` to allow inline JSX wrappers.

## [0.1.0] — 2026-05-19

### Added
- Initial public release.
- Strategy plugin interface at `ibkr_core/core/strategy/` — `Strategy` ABC + `load_strategy()` import-by-string loader. Pick implementation via `STRATEGY_CLASS` env var.
- Reference strategies: `SMACrossover` (20/50) and `BuyAndHold` at `ibkr_core/strategies/`.
- FastAPI backend + React frontend.
- AAOIFI Shariah compliance screening (debt/cash/revenue ratios, dynamic VIX-aware buffer).
- Zakat calculator (hawl tracking, purification of haram income).
- IBKR integration via `ib-insync`.
- Alerts: Telegram, email, Slack.
- Prometheus metrics + Grafana provisioning.
- Alembic migrations.
- 438 backend tests pass.
- MIT license.
