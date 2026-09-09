"""Strategy loader.

Picks Strategy implementation at runtime from `STRATEGY_CLASS` env var.
Falls back to bundled SMA crossover reference.
"""
from __future__ import annotations

import importlib
import logging
import os
from functools import lru_cache

from ibkr_core.core.strategy.base import Strategy

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY = "ibkr_core.strategies.sma_crossover:SMACrossover"


def load_strategy(import_path: str, _is_fallback: bool = False) -> Strategy:
    """Load a Strategy by `module.path:ClassName` import string.

    Raises ImportError if module/class missing or not a Strategy subclass.
    When `_is_fallback` is True, errors are fatal (to avoid infinite recursion
    if even the default strategy is broken).
    """
    if ":" not in import_path:
        raise ImportError(
            f"STRATEGY_CLASS must be 'module.path:ClassName', got: {import_path!r}"
        )
    module_path, class_name = import_path.split(":", 1)
    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        if _is_fallback:
            raise
        logger.critical(
            "Strategy module %s failed to import: %s — falling back to default",
            module_path, e
        )
        return load_strategy(DEFAULT_STRATEGY, _is_fallback=True)

    cls = getattr(module, class_name, None)
    if cls is None:
        if _is_fallback:
            raise ImportError(f"{class_name} not found in {module_path}")
        logger.critical(
            "Strategy class %s not found in %s — falling back to default",
            class_name, module_path
        )
        return load_strategy(DEFAULT_STRATEGY, _is_fallback=True)

    if not (isinstance(cls, type) and issubclass(cls, Strategy)):
        if _is_fallback:
            raise ImportError(f"{import_path} does not subclass Strategy")
        logger.critical(
            "Strategy %s does not subclass Strategy — falling back to default",
            import_path
        )
        return load_strategy(DEFAULT_STRATEGY, _is_fallback=True)

    try:
        instance = cls()
    except Exception as e:
        if _is_fallback:
            raise
        logger.critical(
            "Strategy %s failed to instantiate: %s — falling back to default",
            import_path, e
        )
        return load_strategy(DEFAULT_STRATEGY, _is_fallback=True)

    logger.info("Loaded strategy: %s (%s)", instance.name, import_path)
    return instance


@lru_cache(maxsize=1)
def get_active_strategy() -> Strategy:
    """Return the singleton active Strategy, picked from STRATEGY_CLASS env."""
    path = os.getenv("STRATEGY_CLASS", DEFAULT_STRATEGY)
    return load_strategy(path)


def reload_strategy() -> Strategy:
    """Clear the cached strategy and reload from STRATEGY_CLASS env.

    Use sparingly — changes take effect on next get_active_strategy() call.
    """
    get_active_strategy.cache_clear()
    return get_active_strategy()
