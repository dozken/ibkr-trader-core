"""Bollinger z-score mean-reversion strategy.

Measures how many standard deviations the latest price sits from its rolling
mean (the z-score / Bollinger position). Buy when price is stretched far below
the mean (z <= -threshold), sell (close longs) when it reverts above the mean
(z >= +threshold). No shorting, no leverage.
"""
from __future__ import annotations

import asyncio

import pandas as pd
import yfinance as yf

from ibkr_core.core.strategy import MarketContext, Strategy, TradeSignal


def zscore(closes: pd.Series, window: int = 20) -> float:
    """Latest z-score of price vs its rolling mean."""
    ma = closes.rolling(window).mean().iloc[-1]
    sd = closes.rolling(window).std().iloc[-1]
    if not sd or pd.isna(sd):
        return 0.0
    return float((closes.iloc[-1] - ma) / sd)


class MeanReversionStrategy(Strategy):
    name = "MeanReversion"

    def __init__(self, window: int = 20, threshold: float = 2.0):
        self.window = window
        self.threshold = threshold

    async def generate_signals(self, ctx: MarketContext) -> list[TradeSignal]:
        signals: list[TradeSignal] = []
        for symbol in ctx.watchlist:
            df = await asyncio.to_thread(lambda s=symbol: yf.Ticker(s).history(period="6mo"))
            if df is None or len(df) < self.window + 1:
                continue
            z = zscore(df["Close"], self.window)
            if z <= -self.threshold:
                # More stretched → higher conviction (int 0-100, clamped).
                conf = min(90, 70 + int((abs(z) - self.threshold) * 10))
                signals.append(TradeSignal(
                    symbol=symbol, action="BUY", confidence=conf,
                    sentiment_score=0.0, t_score=float(conf), vix_tier="CALM",
                    reasoning=f"z={z:.2f} <= -{self.threshold} (stretched below mean)",
                ))
            elif z >= self.threshold:
                signals.append(TradeSignal(
                    symbol=symbol, action="SELL", confidence=65,
                    sentiment_score=0.0, t_score=65.0, vix_tier="CALM",
                    reasoning=f"z={z:.2f} >= {self.threshold} (reverted above mean)",
                ))
        return signals


__all__ = ["MeanReversionStrategy", "zscore"]
