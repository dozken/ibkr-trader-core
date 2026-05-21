"""Reference Strategy: 20/50 SMA crossover.

Long-only, fixed-fraction sizing, no leverage — Shariah-compatible defaults.
Uses yfinance for price data so it runs out of the box without paid feeds.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List

import yfinance as yf

from ibkr_core.core.strategy.base import MarketContext, Strategy
from ibkr_core.features.trading.schemas import TradeSignal

logger = logging.getLogger(__name__)

FAST_WINDOW = 20
SLOW_WINDOW = 50


class SMACrossover(Strategy):
    name = "SMACrossover(20/50)"

    async def generate_signals(self, ctx: MarketContext) -> List[TradeSignal]:
        if not ctx.watchlist:
            return []

        signals = await asyncio.gather(
            *(self._signal_for(sym) for sym in ctx.watchlist),
            return_exceptions=True,
        )
        return [s for s in signals if isinstance(s, TradeSignal)]

    async def _signal_for(self, symbol: str) -> TradeSignal | None:
        try:
            hist = await asyncio.to_thread(
                lambda: yf.Ticker(symbol).history(period="3mo", auto_adjust=True)
            )
        except Exception as e:
            logger.warning("history fetch failed for %s: %s", symbol, e)
            return None

        if hist is None or len(hist) < SLOW_WINDOW + 1:
            return None

        close = hist["Close"]
        fast = close.rolling(FAST_WINDOW).mean()
        slow = close.rolling(SLOW_WINDOW).mean()

        fast_now, fast_prev = fast.iloc[-1], fast.iloc[-2]
        slow_now, slow_prev = slow.iloc[-1], slow.iloc[-2]

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        if crossed_up:
            action, conf, reason = "BUY", 65, "20-day SMA crossed above 50-day SMA"
        elif crossed_down:
            action, conf, reason = "SELL", 65, "20-day SMA crossed below 50-day SMA"
        elif fast_now > slow_now:
            action, conf, reason = "HOLD", 50, "fast SMA above slow — trend up, no fresh signal"
        else:
            action, conf, reason = "HOLD", 50, "fast SMA below slow — trend down, no fresh signal"

        spread = float((fast_now - slow_now) / slow_now)
        return TradeSignal(
            symbol=symbol,
            sentiment_score=max(-1.0, min(1.0, spread * 10)),
            confidence=conf,
            action=action,
            reasoning=reason,
            f_score=None,
            t_score=conf,
            s_score=None,
            vix_tier="CALM",
            timestamp=datetime.now(),
        )

    async def get_rebalance_sells(self, positions, signals):
        sell_symbols = {s.symbol for s in signals if s.action == "SELL"}
        return [p for p in positions if getattr(p, "symbol", None) in sell_symbols]
