# Example: Bollinger z-score mean-reversion Strategy plugin

Out-of-tree `Strategy` plugin. Trades reversion to a rolling mean using a
z-score (Bollinger position). No fork of `ibkr-trader-core` required.

## Install

```bash
# from this dir, in your project venv
pip install -e .
```

## Run the bot with this strategy

```bash
STRATEGY_CLASS=mean_reversion_strategy:MeanReversionStrategy \
  uvicorn ibkr_core.main:app --host 0.0.0.0 --port 8000
```

or in `docker-compose.override.yml`:
```yaml
services:
  backend:
    environment:
      STRATEGY_CLASS: mean_reversion_strategy:MeanReversionStrategy
    volumes:
      - ./examples/mean_reversion_strategy:/home/trader/app/mean_reversion_strategy:ro
```

## Logic

Computes the 20-day z-score (`(price − mean) / std`) per watchlist symbol.
**BUY** when z ≤ −2 (price stretched well below its mean — conviction scales
with the stretch), **SELL** (close longs only) when z ≥ +2 (reverted above the
mean). No leverage, no shorting.

## Files

- `pyproject.toml` — package metadata
- `mean_reversion_strategy/__init__.py` — exports `MeanReversionStrategy`
- `mean_reversion_strategy/strategy.py` — implementation (+ reusable `zscore()` helper)
- `tests/test_mean_reversion.py` — unit tests
