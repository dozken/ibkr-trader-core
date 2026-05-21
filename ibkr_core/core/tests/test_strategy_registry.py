import pytest

from ibkr_core.core.strategy import Strategy, load_strategy, get_active_strategy
from ibkr_core.core.strategy.registry import DEFAULT_STRATEGY


def test_default_path_resolves():
    s = load_strategy(DEFAULT_STRATEGY)
    assert isinstance(s, Strategy)
    assert "SMA" in s.name


def test_rejects_missing_colon():
    with pytest.raises(ImportError, match="module.path:ClassName"):
        load_strategy("ibkr_core.strategies.sma_crossover.SMACrossover")


def test_rejects_unknown_module():
    with pytest.raises(ModuleNotFoundError):
        load_strategy("no.such.module:Anything")


def test_rejects_missing_class():
    with pytest.raises(ImportError, match="not found"):
        load_strategy("ibkr_core.strategies.sma_crossover:DoesNotExist")


def test_rejects_non_strategy_class():
    with pytest.raises(ImportError, match="does not subclass"):
        load_strategy("ibkr_core.core.strategy.base:MarketContext")


def test_active_strategy_singleton():
    get_active_strategy.cache_clear()
    a = get_active_strategy()
    b = get_active_strategy()
    assert a is b
