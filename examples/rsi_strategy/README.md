# Example: RSI mean-reversion Strategy plugin

Out-of-tree `Strategy` plugin using Wilder's RSI. Buy oversold, trim overbought.
No fork of `ibkr-trader-core` required.

## Install

```bash
# from this dir, in your project venv
pip install -e .
```

## Run the bot with this strategy

```bash
STRATEGY_CLASS=rsi_strategy:RSIStrategy \
  uvicorn ibkr_core.main:app --host 0.0.0.0 --port 8000
```

or in `docker-compose.override.yml`:
```yaml
services:
  backend:
    environment:
      STRATEGY_CLASS: rsi_strategy:RSIStrategy
    volumes:
      - ./examples/rsi_strategy:/home/trader/app/rsi_strategy:ro
```

## Logic

Computes 14-period Wilder RSI per watchlist symbol. **BUY** when RSI ≤ 30
(oversold — conviction scales with depth), **SELL** (close longs only) when
RSI ≥ 70 (overbought). No leverage, no shorting.

## Files

- `pyproject.toml` — package metadata
- `rsi_strategy/__init__.py` — exports `RSIStrategy`
- `rsi_strategy/strategy.py` — implementation (+ reusable `rsi()` helper)
- `tests/test_rsi.py` — unit tests
