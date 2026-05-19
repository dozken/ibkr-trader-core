from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.core.strategy.base import MarketContext, Strategy
from momentum_strategy import MomentumStrategy


def test_subclasses_strategy():
    assert issubclass(MomentumStrategy, Strategy)


@pytest.mark.asyncio
async def test_empty_watchlist():
    assert await MomentumStrategy().generate_signals(MarketContext()) == []


@pytest.mark.asyncio
async def test_emits_signal_for_valid_data():
    prices = [100.0] * 60
    df = pd.DataFrame({"Close": prices})
    with patch("momentum_strategy.strategy.yf.Ticker") as mock_t:
        mock_t.return_value.history = MagicMock(return_value=df)
        out = await MomentumStrategy().generate_signals(MarketContext(watchlist=["TEST"]))
    assert len(out) == 1
    assert out[0].symbol == "TEST"
