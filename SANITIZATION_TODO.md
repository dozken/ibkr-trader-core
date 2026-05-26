# Sanitization TODO — items deferred from open-core split

Phase 4 of the open-core split. Public skeleton is up and runs with the bundled SMA strategy. These items still need attention before / after first public release.

## Verified clean (Completed 2026-05-25)
- ✅ No real secrets in private git history (all placeholders).
- ✅ `features/ai/` not copied to public.
- ✅ `ibkr_core/main.py` — AI imports wrapped in try/except, AI loops + router gated on `HAS_AI_MODULE`.
- ✅ `ibkr_core/features/trading/loops.py` — top-level AI imports replaced with Strategy plugin shims; lazy AI imports inside loops gated.
- ✅ `ibkr_core/features/alerts/telegram_bot.py` — `get_guarded_signals` now goes through `get_active_strategy()`.
- ✅ `ibkr_core/features/portfolio/router.py` — `/rerate` endpoint returns 501 if AI module missing.
- ✅ `ibkr_core/features/alerts/tests/test_telegram_bot.py` — patches Strategy interface, not `features.ai.strategy`.
- ✅ `ibkr_core/features/trading/tests/test_institutional_enhancements.py` — deleted (private).
- ✅ `ibkr_core/requirements.txt` — torch / xgboost / onnx / scikit-learn removed (private only).

### ✅ Frontend AI pages
Wrapped all AI pages (`SignalsPage`, `SignalLogPage`, `SignalQualityPage`, `BacktestPage`, `ScannerPage`) in `<AIModuleGate>`. They cleanly render an "AI module not installed" fallback banner when run publicly.

### ✅ Halal universe fallback
`ibkr_core/main.py:320` is actively falling back to `halal_universe_seed.py` (which contains 20 US large-caps). Comment in seed file updated to remove `features.ai` reference.

### ✅ Docs review pass
Ran `grep -rn -iE "rl|reinforcement|xgboost|torch|onnx|ML model" docs/`. All public docs are clean and free of proprietary AI terms.

### ✅ Tests that depend on AI module
Ran `pytest ibkr_core/`. Suite completed successfully (448 passed).

### ✅ Security Pass
Fixed lingering AI import in `scripts/smoke_test.py`. Smoke tests ran and passed.

## ✅ Completed (2026-05-26)

### Phase 1 / 5 — refactor private to depend on public
1. ✅ `pyproject.toml` in private repo with `ibkr-trader-core` as git dep.
2. ✅ Deleted 15k+ lines of duplicated code from private repo.
3. ✅ `backend/private_strategies/{rl_strategy,ml_strategy}.py` wrap `features/ai/*` into Strategy interface.
4. ✅ `STRATEGY_CLASS` set in Dockerfile ENV.
5. ✅ 131 private tests + 448 public tests all passing.
