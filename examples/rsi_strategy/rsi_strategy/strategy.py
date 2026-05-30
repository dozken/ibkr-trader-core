"""RSI mean-reversion strategy: buy oversold, trim overbought.

Wilder's RSI. Buy when RSI dips below an oversold floor (mean reversion),
sell (close longs) when RSI runs above an overbought ceiling. No shorting,
no leverage — SELL only reduces existing exposure, keeping it halal.
"""
from __future__ import annotations

import asyncio

import pandas as pd
import yfinance as yf

from ibkr_core.core.strategy import MarketContext, Strategy, TradeSignal


def rsi(closes: pd.Series, period: int = 14) -> float:
    """Latest Wilder RSI value for a close-price series."""
    delta = closes.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    return float((100 - 100 / (1 + rs)).iloc[-1])


class RSIStrategy(Strategy):
    name = "RSI"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    async def generate_signals(self, ctx: MarketContext) -> list[TradeSignal]:
        signals: list[TradeSignal] = []
        for symbol in ctx.watchlist:
            df = await asyncio.to_thread(lambda s=symbol: yf.Ticker(s).history(period="6mo"))
            if df is None or len(df) < self.period + 1:
                continue
            value = rsi(df["Close"], self.period)
            if value <= self.oversold:
                # Deeper oversold → higher conviction (int 0-100, clamped).
                conf = min(90, 70 + int(self.oversold - value))
                signals.append(TradeSignal(
                    symbol=symbol, action="BUY", confidence=conf,
                    sentiment_score=0.0, t_score=float(conf), vix_tier="CALM",
                    reasoning=f"RSI {value:.0f} <= {self.oversold:.0f} (oversold)",
                ))
            elif value >= self.overbought:
                signals.append(TradeSignal(
                    symbol=symbol, action="SELL", confidence=65,
                    sentiment_score=0.0, t_score=65.0, vix_tier="CALM",
                    reasoning=f"RSI {value:.0f} >= {self.overbought:.0f} (overbought)",
                ))
        return signals


__all__ = ["RSIStrategy", "rsi"]
