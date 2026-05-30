# Write your first strategy

`ibkr-trader-core` ships with reference strategies (SMA crossover, buy-and-hold)
and loads any `Strategy` implementation you point it at via the `STRATEGY_CLASS`
env var — no fork required. This tutorial builds a tiny one end-to-end.

For the full extension contract (routers, loops, universe seam) see
[PLUGINS.md](PLUGINS.md). Complete working packages live in
[`../examples/`](../examples): `momentum_strategy`, `rsi_strategy`,
`mean_reversion_strategy`.

## 1. The `Strategy` interface

```python
from ibkr_core.core.strategy.base import Strategy, MarketContext
from ibkr_core.features.trading.schemas import TradeSignal

class Strategy:
    name: str
    async def generate_signals(self, ctx: MarketContext) -> list[TradeSignal]:
        ...
```

- `ctx: MarketContext` — what the engine knows right now (e.g. `ctx.watchlist`).
- `TradeSignal(symbol, action, confidence, sentiment_score, t_score, vix_tier, reasoning)`
  — `action` is `"BUY"`, `"SELL"`, or `"HOLD"`; `confidence` is an **int 0–100**;
  `reasoning` is a human-readable string shown in logs and the UI. `timestamp`
  defaults to now. **No shorting/leverage** — `SELL` only closes existing longs,
  keeping the bot halal.

The engine takes your signals and runs them through compliance screening,
position sizing, and order routing. You only decide *what looks good*.

## 2. Scaffold a package

```
my_alpha/
├── pyproject.toml
├── my_alpha/
│   ├── __init__.py        # exports MyAlpha
│   └── strategy.py
└── tests/
    └── test_my_alpha.py
```

`pyproject.toml`:

```toml
[project]
name = "my-alpha"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["ibkr-trader-core", "yfinance", "pandas"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["my_alpha*"]
```

## 3. Implement it

```python
# my_alpha/strategy.py
import yfinance as yf
from ibkr_core.core.strategy.base import MarketContext, Strategy
from ibkr_core.features.trading.schemas import TradeSignal

class MyAlpha(Strategy):
    name = "MyAlpha"

    async def generate_signals(self, ctx: MarketContext) -> list[TradeSignal]:
        signals: list[TradeSignal] = []
        for symbol in ctx.watchlist:
            df = yf.Ticker(symbol).history(period="3mo")
            if len(df) < 50:
                continue
            price = df["Close"].iloc[-1]
            sma50 = df["Close"].rolling(50).mean().iloc[-1]
            if price > sma50:
                signals.append(TradeSignal(
                    symbol=symbol, action="BUY", confidence=65,
                    sentiment_score=0.0, t_score=65.0, vix_tier="CALM",
                    reasoning="Above 50-day SMA",
                ))
        return signals
```

```python
# my_alpha/__init__.py
from my_alpha.strategy import MyAlpha
__all__ = ["MyAlpha"]
```

## 4. Test the pure logic

Keep the math in a helper so you can unit-test it without network or IBKR:

```python
# tests/test_my_alpha.py
import pandas as pd

def test_sma():
    closes = pd.Series([float(i) for i in range(1, 60)])
    assert closes.rolling(50).mean().iloc[-1] < closes.iloc[-1]
```

```bash
pip install -e . && pytest
```

## 5. Run the bot with your strategy

```bash
pip install -e .
STRATEGY_CLASS=my_alpha:MyAlpha \
  uvicorn ibkr_core.main:app --host 0.0.0.0 --port 8000
```

Or via Docker, mount it and set the env var in `docker-compose.override.yml`:

```yaml
services:
  backend:
    environment:
      STRATEGY_CLASS: my_alpha:MyAlpha
    volumes:
      - ./my_alpha:/home/trader/app/my_alpha:ro
```

Open <http://localhost:8000/docs> for the API and the dashboard for signals.

## 6. Where to go next

- Tune parameters via `__init__` (see `rsi_strategy` / `mean_reversion_strategy`).
- Add background loops or API routes — [PLUGINS.md](PLUGINS.md) (`create_app`).
- Swap the tradeable universe — `HALAL_UNIVERSE_MODULE` in [PLUGINS.md](PLUGINS.md).
- Keep it compliant — [COMPLIANCE.md](COMPLIANCE.md). PRs with riba/leverage/shorting are closed.
