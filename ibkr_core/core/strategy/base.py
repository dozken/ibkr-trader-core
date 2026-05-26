"""Strategy plugin interface.

Implement `Strategy` to provide trading logic. The framework calls your
strategy via this interface only — no other coupling. Swap implementations
by setting the `STRATEGY_CLASS` env var to an import path.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from ibkr_core.features.trading.schemas import TradeSignal


@dataclass
class MarketContext:
    """Inputs handed to a Strategy on each invocation.

    Strategies should treat this as read-only.
    """
    watchlist: List[str] = field(default_factory=list)
    positions: list = field(default_factory=list)
    vix_buffer: float = 0.0
    held_symbols: Optional[set] = None


class Strategy(ABC):
    """Trading strategy plugin.

    Override `generate_signals` to produce buy/sell signals. Optionally
    override the rebalance / discovery hooks to refine portfolio mgmt.
    """

    name: str = "unnamed"

    @abstractmethod
    async def generate_signals(self, ctx: MarketContext) -> List[TradeSignal]:
        """Produce signals for symbols in `ctx.watchlist`."""
        ...

    async def get_rebalance_sells(
        self, positions: list, signals: List[TradeSignal]
    ) -> list:
        """Suggest positions to trim/exit. Default: no rebalance."""
        return []

    async def discover_halal_buys(
        self,
        min_score: int = 70,
        chunk_size: int = 5,
        open_markets_only: bool = True,
    ) -> List[TradeSignal]:
        """Scan universe for new buy candidates. Default: empty."""
        return []

    async def get_guarded_signals(
        self, held_symbols: Optional[set] = None
    ) -> List[TradeSignal]:
        """Signals filtered against currently held positions. Default: empty."""
        return []

    async def get_multi_factor_score(
        self, symbol: str, vix_buffer: float = 0.0
    ) -> Optional[dict]:
        """Score a single symbol for position rerating. Default: None (skip)."""
        return None

    def get_portfolio_sector_weights(self) -> Optional[dict]:
        """Current portfolio sector allocation weights. Default: None (sort by confidence only)."""
        return None
