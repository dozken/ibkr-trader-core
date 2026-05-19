# Contributing

Thanks for your interest! A few ground rules.

## Scope

This repo is the open framework. The strategy interface (`backend/core/strategy/`) is the right place to extend trading logic; please don't PR proprietary alpha — your strategy belongs in your own repo, loaded via `STRATEGY_CLASS`.

## What we want

- Bug fixes
- New reference strategies (must be public/standard — e.g. mean-reversion, momentum, pairs)
- Compliance improvements (must cite AAOIFI / scholarly source)
- New brokers (currently IBKR-only)
- Better observability, tests, docs
- Frontend polish

## Dev setup

```bash
cd backend && pip install -r requirements.txt && pytest
cd ../frontend && bun install && bun test
```

## PR checklist

- [ ] Tests added/updated for changed behavior
- [ ] `pytest` passes locally
- [ ] `bun run typecheck` passes
- [ ] No proprietary data, no trained model files, no secrets
- [ ] Docs updated if user-facing
- [ ] One topic per PR

## Commit style

Conventional Commits — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.

## Shariah compliance

If your change touches order routing, screening, sizing, or instruments — explain why it's still halal. PRs introducing interest, leverage, or shorting will be closed.
