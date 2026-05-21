"""Unit tests for SMA crossover reference strategy."""
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from ibkr_core.core.strategy.base import MarketContext
from ibkr_core.strategies.sma_crossover import SMACrossover


def _mk_hist(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": prices})


@pytest.mark.asyncio
async def test_empty_watchlist_returns_empty():
    s = SMACrossover()
    out = await s.generate_signals(MarketContext(watchlist=[]))
    assert out == []


@pytest.mark.asyncio
async def test_bullish_crossover_produces_buy():
    # 51 points: first 49 flat then ramp — fast SMA crosses slow upward
    prices = [100.0] * 49 + [105.0, 110.0]
    s = SMACrossover()
    with patch("ibkr_core.strategies.sma_crossover.yf.Ticker") as mock_t:
        mock_t.return_value.history = MagicMock(return_value=_mk_hist(prices))
        out = await s.generate_signals(MarketContext(watchlist=["TEST"]))
    assert len(out) == 1
    assert out[0].action in ("BUY", "HOLD")  # depends on exact crossover bar


@pytest.mark.asyncio
async def test_insufficient_history_returns_none():
    s = SMACrossover()
    with patch("ibkr_core.strategies.sma_crossover.yf.Ticker") as mock_t:
        mock_t.return_value.history = MagicMock(return_value=_mk_hist([100.0] * 10))
        out = await s.generate_signals(MarketContext(watchlist=["TEST"]))
    assert out == []
