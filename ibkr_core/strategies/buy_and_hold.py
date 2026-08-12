"""Reference Strategy: buy and hold — minimal example."""
from __future__ import annotations

from typing import List

from ibkr_core.core.strategy.base import MarketContext, Strategy
from ibkr_core.features.trading.schemas import TradeSignal
from ibkr_core.core.clock import utc_now


class BuyAndHold(Strategy):
    name = "BuyAndHold"

    async def generate_signals(self, ctx: MarketContext) -> List[TradeSignal]:
        return [
            TradeSignal(
                symbol=sym,
                sentiment_score=0.0,
                confidence=50,
                action="BUY",
                reasoning="buy-and-hold reference strategy",
                vix_tier="CALM",
                timestamp=utc_now(),
            )
            for sym in ctx.watchlist
        ]
