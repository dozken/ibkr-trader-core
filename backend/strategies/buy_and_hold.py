"""Reference Strategy: buy and hold — minimal example."""
from __future__ import annotations

from datetime import datetime
from typing import List

from backend.core.strategy.base import MarketContext, Strategy
from backend.features.trading.schemas import TradeSignal


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
                timestamp=datetime.now(),
            )
            for sym in ctx.watchlist
        ]
