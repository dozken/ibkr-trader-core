import pytest

from ibkr_core.core.strategy.base import MarketContext, Strategy
from ibkr_core.strategies.buy_and_hold import BuyAndHold


def test_subclasses_strategy():
    assert issubclass(BuyAndHold, Strategy)
    assert BuyAndHold().name == "BuyAndHold"


@pytest.mark.asyncio
async def test_emits_buy_per_symbol():
    s = BuyAndHold()
    out = await s.generate_signals(MarketContext(watchlist=["AAPL", "MSFT", "GOOGL"]))
    assert {sig.symbol for sig in out} == {"AAPL", "MSFT", "GOOGL"}
    assert all(sig.action == "BUY" for sig in out)


@pytest.mark.asyncio
async def test_default_rebalance_empty():
    s = BuyAndHold()
    assert await s.get_rebalance_sells([], []) == []


@pytest.mark.asyncio
async def test_default_discover_empty():
    s = BuyAndHold()
    assert await s.discover_halal_buys() == []
