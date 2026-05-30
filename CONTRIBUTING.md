# Contributing

Thanks for your interest! A few ground rules.

## Scope

This repo is the open framework. The strategy interface (`ibkr_core/core/strategy/`) is the right place to extend trading logic; please don't PR proprietary alpha — your strategy belongs in your own repo, loaded via `STRATEGY_CLASS`.

## What we want

- Bug fixes
- New reference strategies (must be public/standard — e.g. mean-reversion, momentum, pairs)
- Compliance improvements (must cite AAOIFI / scholarly source)
- New brokers (currently IBKR-only)
- Better observability, tests, docs
- Frontend polish

## Dev setup

```bash
# Backend
pip install -e ".[dev]"
pre-commit install            # ruff + gitleaks on every commit
PYTHONPATH=. pytest ibkr_core/

# Frontend
cd frontend && bun install
bun run typecheck && bun run test --run
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

## Release (maintainers)

PyPI publish runs on GitHub release publish events via Trusted Publishing (`.github/workflows/release-pypi.yml`).

1. Configure Trusted Publisher on PyPI:
   - <https://pypi.org/manage/account/publishing/> → add `dozken/ibkr-trader-core`, workflow `release-pypi.yml`, environment `pypi`
   - <https://test.pypi.org/manage/account/publishing/> → same with environment `testpypi`
2. Create release in GitHub: `gh release create v0.1.x --generate-notes`

Manual publish from local (alternative):
```bash
python -m build
twine check dist/*
twine upload --repository testpypi dist/*   # smoke test first
twine upload dist/*                          # then prod
```
