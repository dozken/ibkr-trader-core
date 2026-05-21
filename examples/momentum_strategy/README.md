# Example: third-party momentum Strategy plugin

Minimal example of an out-of-tree Strategy plugin. Shows how to package and load your own alpha without forking `ibkr-trader-core`.

## Install

```bash
# from this dir, in your project venv
pip install -e .
```

## Run the bot with this strategy

```bash
STRATEGY_CLASS=momentum_strategy:MomentumStrategy \
  uvicorn ibkr_core.main:app --host 0.0.0.0 --port 8000
```

or in `docker-compose.override.yml`:
```yaml
services:
  backend:
    environment:
      STRATEGY_CLASS: momentum_strategy:MomentumStrategy
    volumes:
      - ./examples/momentum_strategy:/home/trader/app/momentum_strategy:ro
```

## Logic

Buys symbols whose latest close > 20-day SMA AND 20-day SMA > 50-day SMA (trend filter). Sells when fast crosses below slow. No leverage, no shorts.

## Files

- `pyproject.toml` — package metadata
- `momentum_strategy/__init__.py` — exports `MomentumStrategy`
- `momentum_strategy/strategy.py` — implementation
- `tests/test_momentum.py` — unit test
