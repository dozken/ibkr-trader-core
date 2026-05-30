import asyncio
from unittest.mock import MagicMock, patch

import pandas as pd

from ibkr_core.core.strategy.base import MarketContext
from mean_reversion_strategy import MeanReversionStrategy
from mean_reversion_strategy.strategy import zscore


def test_zscore_below_mean_is_negative():
    # Flat series then a sharp drop → strongly negative z
    closes = pd.Series([100.0] * 19 + [80.0])
    assert zscore(closes, 20) < -2


def test_zscore_above_mean_is_positive():
    closes = pd.Series([100.0] * 19 + [120.0])
    assert zscore(closes, 20) > 2


def test_zscore_flat_is_zero():
    closes = pd.Series([100.0] * 20)
    assert zscore(closes, 20) == 0.0


def test_emits_valid_buy_when_below_band():
    # Flat then sharp drop → z <= -2 → a valid BUY TradeSignal
    df = pd.DataFrame({"Close": [100.0] * 19 + [70.0]})
    with patch("mean_reversion_strategy.strategy.yf.Ticker") as mock_t:
        mock_t.return_value.history = MagicMock(return_value=df)
        out = asyncio.run(MeanReversionStrategy().generate_signals(MarketContext(watchlist=["TEST"])))
    assert len(out) == 1
    sig = out[0]
    assert sig.symbol == "TEST"
    assert sig.action == "BUY"
    assert 0 <= sig.confidence <= 100
