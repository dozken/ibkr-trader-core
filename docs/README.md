# Documentation

Start here. Docs are grouped by what you're trying to do.

## Understand the system
- [ARCHITECTURE.md](ARCHITECTURE.md) — tech stack, module breakdown, data flow, open-core model
- [HOW_THE_BOT_WORKS.md](HOW_THE_BOT_WORKS.md) — end-to-end walkthrough of a trading cycle
- [STATE_MACHINE.md](STATE_MACHINE.md) — order/position lifecycle states
- [GLOSSARY.md](GLOSSARY.md) — domain terms (AAOIFI, hawl, purification, nisab, …)

## Extend it
- [PLUGINS.md](PLUGINS.md) — `create_app()`, `extra_routers`/`extra_loops`, `STRATEGY_CLASS`, `HALAL_UNIVERSE_MODULE`
- [STRATEGY_TUTORIAL.md](STRATEGY_TUTORIAL.md) — write & load your first strategy (start here to add alpha)
- Working examples: [`../examples/`](../examples) — momentum, RSI, mean-reversion

## Run it in production
- [DEPLOYMENT.md](DEPLOYMENT.md) — deploy the stack
- [MONITORING.md](MONITORING.md) — Prometheus metrics + Grafana
- [NOTIFICATIONS.md](NOTIFICATIONS.md) — Telegram / email / Slack alerts
- [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) — backups, recovery drills
- [DATA_GOVERNANCE.md](DATA_GOVERNANCE.md) — what data is stored and where

## Compliance & safety
- [COMPLIANCE.md](COMPLIANCE.md) — AAOIFI screening rules, ratio buffers
- [SECURITY.md](SECURITY.md) — operational security guidance (see also root [SECURITY.md](../SECURITY.md) for reporting)
- [BEST_PRACTICES.md](BEST_PRACTICES.md) — engineering conventions

## Other
- [MOBILE_STRATEGY.md](MOBILE_STRATEGY.md) — mobile/PWA notes

---
Contributing? See [../CONTRIBUTING.md](../CONTRIBUTING.md) and [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).
