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


def test_fallback_on_unknown_module():
    """Unknown module falls back to default strategy instead of raising."""
    s = load_strategy("no.such.module:Anything")
    assert isinstance(s, Strategy)
    assert "SMA" in s.name  # fell back to default


def test_fallback_on_missing_class():
    """Missing class falls back to default strategy instead of raising."""
    s = load_strategy("ibkr_core.strategies.sma_crossover:DoesNotExist")
    assert isinstance(s, Strategy)
    assert "SMA" in s.name  # fell back to default


def test_fallback_on_non_strategy_class():
    """Non-Strategy class falls back to default instead of raising."""
    s = load_strategy("ibkr_core.core.strategy.base:MarketContext")
    assert isinstance(s, Strategy)
    assert "SMA" in s.name  # fell back to default


def test_active_strategy_singleton():
    get_active_strategy.cache_clear()
    a = get_active_strategy()
    b = get_active_strategy()
    assert a is b
