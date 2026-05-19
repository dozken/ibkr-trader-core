# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `AIModuleGate` wraps `features/ai/*` pages with a graceful 404 banner pointing to the open-core split docs.
- `backend/strategies/halal_universe_seed.py` — reference seed list (20 US large-caps) so `/api/system/markets` renders without the private AI module.
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
- Strategy plugin interface at `backend/core/strategy/` — `Strategy` ABC + `load_strategy()` import-by-string loader. Pick implementation via `STRATEGY_CLASS` env var.
- Reference strategies: `SMACrossover` (20/50) and `BuyAndHold` at `backend/strategies/`.
- FastAPI backend + React frontend.
- AAOIFI Shariah compliance screening (debt/cash/revenue ratios, dynamic VIX-aware buffer).
- Zakat calculator (hawl tracking, purification of haram income).
- IBKR integration via `ib-insync`.
- Alerts: Telegram, email, Slack.
- Prometheus metrics + Grafana provisioning.
- Alembic migrations.
- 438 backend tests pass.
- MIT license.
