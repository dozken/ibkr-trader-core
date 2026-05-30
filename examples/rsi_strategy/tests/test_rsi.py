import asyncio
from unittest.mock import MagicMock, patch

import pandas as pd

from ibkr_core.core.strategy.base import MarketContext
from rsi_strategy import RSIStrategy
from rsi_strategy.strategy import rsi


def test_rsi_all_gains_is_high():
    # Monotonically rising series → RSI near 100
    closes = pd.Series([float(i) for i in range(1, 40)])
    assert rsi(closes, 14) > 90


def test_rsi_all_losses_is_low():
    closes = pd.Series([float(i) for i in range(40, 1, -1)])
    assert rsi(closes, 14) < 10


def test_rsi_in_range():
    closes = pd.Series([10, 11, 10.5, 11.2, 10.8, 11.5, 11.1, 12, 11.7, 12.3,
                        12.0, 12.5, 12.2, 12.8, 12.4, 13.0])
    value = rsi(closes, 14)
    assert 0.0 <= value <= 100.0


def test_emits_valid_buy_when_oversold():
    # Falling series → low RSI → a valid BUY TradeSignal
    df = pd.DataFrame({"Close": [float(i) for i in range(60, 1, -1)]})
    with patch("rsi_strategy.strategy.yf.Ticker") as mock_t:
        mock_t.return_value.history = MagicMock(return_value=df)
        out = asyncio.run(RSIStrategy().generate_signals(MarketContext(watchlist=["TEST"])))
    assert len(out) == 1
    sig = out[0]
    assert sig.symbol == "TEST"
    assert sig.action == "BUY"
    assert 0 <= sig.confidence <= 100
