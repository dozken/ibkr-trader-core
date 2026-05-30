# Plugin / Extension Architecture

`ibkr-trader-core` is the open-core framework: it owns the entire FastAPI
application, the trading worker, the compliance/zakat/portfolio engines, the
background loops, and the default reference strategy. Proprietary forks (e.g.
`ibkr-trader-ai`) install core as a dependency and extend it **without forking
the app** — they inject their own routers and background loops and swap the
strategy through documented seams.

This keeps the private repo thin: an entrypoint plus the alpha (ML/RL models,
sentiment, halal universe). Everything else lives in core.

---

## 1. `create_app()` — the application factory

Defined in `ibkr_core/main.py`:

```python
def create_app(extra_routers=(), extra_loops=(), title="IBKR Shariah Trader") -> FastAPI:
    ...
```

It builds the `FastAPI` instance, mounts middleware (request-id, CORS), includes
all core routers, then includes any caller-supplied routers, then the system
router (`/`, `/health`, `/api/system/*`, `/metrics`, WS `/ws/tickers`). The
`lifespan` context starts every core background loop plus any caller-supplied
loops.

Core's own standalone deployment uses the module-level default:

```python
# uvicorn ibkr_core.main:app
app = create_app()
```

An extension builds its own app instead of re-declaring one:

```python
# backend/app.py in ibkr-trader-ai — uvicorn backend.app:app
from ibkr_core.main import create_app
from backend.features.ai.router import router as ai_router
from backend.features.ai.loops import ml_retraining_loop
from backend.features.ai.signal_outcome_checker import signal_outcome_loop
from backend.features.ai.halal_universe import halal_universe_refresh_loop

app = create_app(
    extra_routers=[ai_router],
    extra_loops=[ml_retraining_loop, signal_outcome_loop, halal_universe_refresh_loop],
    title="IBKR Shariah Trader (AI)",
)
```

### `extra_routers`
Iterable of `fastapi.APIRouter`. Each is `app.include_router(...)`-ed after the
core routers and before the system router. Carry their own `prefix`/`tags`.

### `extra_loops`
Iterable of async callables invoked once at startup as `loop_fn(health)` where
`health` is the shared loop-health dict surfaced at `/api/system/health`. Each
loop is responsible for its own `while True` + sleep + `asyncio.CancelledError`
handling, and should pre-register its status:

```python
async def my_loop(health: dict) -> None:
    health["my_loop"] = {"status": "running", "last_run": None}
    while True:
        try:
            ...  # do work
            health["my_loop"]["last_run"] = datetime.now().isoformat()
            await asyncio.sleep(INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("my_loop: %s", e)
            await asyncio.sleep(60)
```

`create_app()` pre-seeds each extra loop's health entry by `__name__`, so the
loop appears in `/api/system/health` even before its first run.

---

## 2. Strategy seam — `STRATEGY_CLASS`

The signal generator is pluggable via `ibkr_core.core.strategy` (Strategy ABC +
registry). Select the implementation with the `STRATEGY_CLASS` env var
(dotted import path). When unset, core uses its bundled reference strategy
(SMA crossover). The AI fork points it at its ML/RL consensus strategy.

```bash
STRATEGY_CLASS=backend.features.ai.strategy.AIStrategy
```

---

## 3. Halal universe seam — `HALAL_UNIVERSE_MODULE`

`/api/system/markets` needs the tradeable universe. Core cannot import the
private `backend.*` package, so it resolves the universe in this order
(`system_markets` in `main.py`):

1. `HALAL_UNIVERSE_MODULE` env var — dotted path to a module exposing
   `SEED_UNIVERSE` and `REGIONAL_HALAL`. Extension dists set this.
2. `ibkr_core.features.ai.halal_universe` (namespace-package extension), if present.
3. Bundled reference seed list (`ibkr_core.strategies.halal_universe_seed`) for
   the public standalone build.

```bash
HALAL_UNIVERSE_MODULE=backend.features.ai.halal_universe
```

---

## 4. Optional in-tree AI module — `HAS_AI_MODULE`

As a transitional path, `main.py` also tries to import
`ibkr_core.features.ai.*` directly (router + `ml_retraining_loop` +
`signal_outcome_loop` + `halal_universe_refresh_loop`). If the import succeeds
(`HAS_AI_MODULE = True`) those are wired automatically; if not, core falls back
to the reference strategy. New extensions should prefer the explicit
`create_app(extra_routers=..., extra_loops=...)` path over relying on this
implicit import.

---

## 5. What stays in core vs. an extension

| Concern | Lives in |
| --- | --- |
| FastAPI app, middleware, lifespan | core (`create_app`) |
| Trading worker, IBKR connection, multi-account runtime | core |
| Compliance / zakat / portfolio / settings / accounts / gateway routers | core |
| Reference strategy (SMA), reference halal seed list | core |
| Docker compose + paper IB gateway | core |
| ML/RL/sentiment models, signal outcome tracking | extension (`ibkr-trader-ai`) |
| Proprietary halal universe | extension |
| Custom Strategy implementation | extension (via `STRATEGY_CLASS`) |

### Future seams (not yet abstracted)
Broker and screener are concrete in core today. They are candidates for ABCs +
entry-point discovery so a future `ibkr-trader-broker` could run in parallel
with, or substitute for, the bundled IBKR broker. Deferred until there is a
second implementation to design against.
