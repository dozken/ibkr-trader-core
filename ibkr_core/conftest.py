"""
Root conftest: pre-stub ib_insync so tests never trigger eventkit's
asyncio.get_event_loop() at module-import time (fails without a running loop).
"""
import os
import sys
from unittest.mock import MagicMock

# Enable dev mode for tests (bypasses API key auth requirement).
# This must be set BEFORE auth module is imported.
os.environ.setdefault("DEV_MODE", "true")

if "ib_insync" not in sys.modules:
    _ib_mock = MagicMock()
    sys.modules["ib_insync"] = _ib_mock
    sys.modules["eventkit"] = MagicMock()
    # Expose names worker.py imports lazily
    _ib_mock.IB = MagicMock
    _ib_mock.Stock = MagicMock
    _ib_mock.MarketOrder = MagicMock
    _ib_mock.LimitOrder = MagicMock
    _ib_mock.StopOrder = MagicMock
