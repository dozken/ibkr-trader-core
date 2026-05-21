"""Example momentum strategy — third-party plugin for ibkr-trader-core."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List

import yfinance as yf

from ibkr_core.core.strategy.base import MarketContext, Strategy
from ibkr_core.features.trading.schemas import TradeSignal

logger = logging.getLogger(__name__)

FAST = 20
SLOW = 50


class MomentumStrategy(Strategy):
    name = "Momentum(20>50 trend)"

    async def generate_signals(self, ctx: MarketContext) -> List[TradeSignal]:
        if not ctx.watchlist:
            return []
        results = await asyncio.gather(
            *(self._signal(sym) for sym in ctx.watchlist),
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, TradeSignal)]

    async def _signal(self, symbol: str) -> TradeSignal | None:
        try:
            hist = await asyncio.to_thread(
                lambda: yf.Ticker(symbol).history(period="3mo", auto_adjust=True)
            )
        except Exception as e:
            logger.warning("fetch %s: %s", symbol, e)
            return None
        if hist is None or len(hist) < SLOW + 1:
            return None

        close = hist["Close"]
        fast = close.rolling(FAST).mean()
        slow = close.rolling(SLOW).mean()
        last = float(close.iloc[-1])
        fast_now, slow_now = float(fast.iloc[-1]), float(slow.iloc[-1])
        fast_prev, slow_prev = float(fast.iloc[-2]), float(slow.iloc[-2])

        trend_up = last > fast_now and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        if trend_up and fast_prev <= slow_prev:
            action, conf, reason = "BUY", 70, "fresh 20/50 crossover with price above fast"
        elif crossed_down:
            action, conf, reason = "SELL", 70, "20/50 crossover down"
        elif trend_up:
            action, conf, reason = "HOLD", 55, "trend up — hold"
        else:
            action, conf, reason = "HOLD", 50, "no trend"

        return TradeSignal(
            symbol=symbol,
            sentiment_score=0.0,
            confidence=conf,
            action=action,
            reasoning=reason,
            t_score=conf,
            vix_tier="CALM",
            timestamp=datetime.now(),
        )
