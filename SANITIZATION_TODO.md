# Sanitization TODO — items deferred from open-core split

Phase 4 of the open-core split. Public skeleton is up and runs with the bundled SMA strategy. These items still need attention before / after first public release.

## Verified clean
- No real secrets in private git history (all placeholders).
- `features/ai/` not copied to public.
- `ibkr_core/main.py` — AI imports wrapped in try/except, AI loops + router gated on `HAS_AI_MODULE`.
- `ibkr_core/features/trading/loops.py` — top-level AI imports replaced with Strategy plugin shims; lazy AI imports inside loops gated.
- `ibkr_core/features/alerts/telegram_bot.py` — `get_guarded_signals` now goes through `get_active_strategy()`.
- `ibkr_core/features/portfolio/router.py` — `/rerate` endpoint returns 501 if AI module missing.
- `ibkr_core/features/alerts/tests/test_telegram_bot.py` — patches Strategy interface, not `features.ai.strategy`.
- `ibkr_core/features/trading/tests/test_institutional_enhancements.py` — deleted (private).
- `ibkr_core/requirements.txt` — torch / xgboost / onnx / scikit-learn removed (private only).

## Still TODO before publishing

### Frontend AI pages
Files: `frontend/src/features/ai/{SignalsPage,SignalLogPage,SignalQualityPage,BacktestPage,ScannerPage}.tsx` hit `/api/ai/*` endpoints that don't exist in public build.

**Options:**
1. **Recommended:** keep pages, render an "AI module not installed — runs with reference SMA strategy" banner when 404 from API.
2. Strip pages entirely, remove routes.
3. Gate via build-time flag.

### Halal universe in `/api/system/markets` endpoint
`ibkr_core/main.py:320` falls back to empty SEED_UNIVERSE / REGIONAL_HALAL when AI module missing. Markets page will show empty regions. Either:
- Ship a small public halal seed list (e.g. 20 US large-caps that pass AAOIFI by default).
- Refactor endpoint to derive symbols from compliance screening cache instead of static list.

### Docs review pass
Public docs may reference RL / ML / private internals. Review each:
- `docs/ARCHITECTURE.md`
- `docs/HOW_THE_BOT_WORKS.md`
- `docs/STATE_MACHINE.md`
- `docs/MONITORING.md`
- `docs/SECURITY.md`
- `docs/COMPLIANCE.md`

Search command: `grep -rn -iE "rl|reinforcement|xgboost|torch|onnx|ML model" docs/`

### Tests that depend on AI module
Run `pytest ibkr_core/` in the public repo and catch import errors. Skip / refactor any test that needs `features.ai`.

### docker-compose.yml sanity
- Default `STRATEGY_CLASS` env present in env_file.
- No private container references.
- Optional: split into `docker-compose.yml` (public) + `docker-compose.override.yml` (private adds AI deps + STRATEGY_CLASS override).

### Phase 1 / 5 — refactor private to depend on public
**Blocked by user having uncommitted WIP on `main` in private repo.** Once committed:
1. Add `pyproject.toml` to private repo with `ibkr-trader-core` as git dep.
2. Delete all files in private that are duplicated in public.
3. Add `backend/private_strategies/{rl_strategy,ml_strategy}.py` that wrap existing `features/ai/*` into the `Strategy` interface.
4. Set `STRATEGY_CLASS` to private impl via `docker-compose.override.yml`.

## Phase 6 — security pass (before push)

```bash
cd ~/personal/ibkr-trader-core
# personal info
grep -rE "(dozken|dosmukhamed|gmail|U[0-9]{7,8}|DU[0-9]{7})" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.md" --include="*.yml" .

# secret patterns
grep -rE "(api[_-]?key|secret|token|password|bearer)[[:space:]]*=[[:space:]]*[\"'][^\"'<]" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.yml" .

# trufflehog
trufflehog filesystem .

# leftover ai imports
grep -rn "features\.ai" --include="*.py" . | grep -v "type: ignore" | grep -v SANITIZATION_TODO
```

All must be zero.
