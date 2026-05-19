"""Strategy loader.

Picks Strategy implementation at runtime from `STRATEGY_CLASS` env var.
Falls back to bundled SMA crossover reference.
"""
from __future__ import annotations

import importlib
import logging
import os
from functools import lru_cache

from backend.core.strategy.base import Strategy

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY = "backend.strategies.sma_crossover:SMACrossover"


def load_strategy(import_path: str) -> Strategy:
    """Load a Strategy by `module.path:ClassName` import string.

    Raises ImportError if module/class missing or not a Strategy subclass.
    """
    if ":" not in import_path:
        raise ImportError(
            f"STRATEGY_CLASS must be 'module.path:ClassName', got: {import_path!r}"
        )
    module_path, class_name = import_path.split(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ImportError(f"{class_name} not found in {module_path}")
    if not (isinstance(cls, type) and issubclass(cls, Strategy)):
        raise ImportError(f"{import_path} does not subclass Strategy")
    instance = cls()
    logger.info("Loaded strategy: %s (%s)", instance.name, import_path)
    return instance


@lru_cache(maxsize=1)
def get_active_strategy() -> Strategy:
    """Return the singleton active Strategy, picked from STRATEGY_CLASS env."""
    path = os.getenv("STRATEGY_CLASS", DEFAULT_STRATEGY)
    return load_strategy(path)
