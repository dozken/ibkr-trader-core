"""Regression tests for connect_secondary_workers().

The bug this pins (live 2026-08-14): secondary accounts were connected in one
sequential loop that retried each account forever before moving on. Account 3
pointed at a deliberately-stopped live gateway, so account 4 — the paper test,
whose gateway was healthy and accepting API connections the whole time — never
got a single connect attempt in 13.5 h. Nothing logged the stall.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock


def _make_worker(connect_result=True):
    """Worker whose connect() returns `connect_result`, or raises if it's an
    exception instance. Each worker gets a distinct .ib so dedup doesn't fire."""
    w = MagicMock()
    w.ib = MagicMock()
    if isinstance(connect_result, BaseException):
        w.connect = AsyncMock(side_effect=connect_result)
    elif connect_result is False:
        w.connect = AsyncMock(return_value=False)
    else:
        w.connect = AsyncMock(return_value=True)
    return w


def _make_account_manager(workers: dict):
    m = MagicMock()
    m.list_account_ids.return_value = list(workers)
    m.get_worker_by_id.side_effect = workers.get
    return m


async def _run(am, primary_id, primary_worker=None, ticks=50):
    """Run the connector concurrently and let it spin, then cancel.

    It never returns while any account is still retrying (by design — it is a
    long-lived startup task), so drive it with sleep(0) turns and cancel.
    """
    from ibkr_core.main import connect_secondary_workers

    task = asyncio.create_task(
        connect_secondary_workers(am, primary_id, primary_worker=primary_worker,
                                  retry_seconds=0)
    )
    for _ in range(ticks):
        await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


class TestConnectSecondaryWorkers(unittest.IsolatedAsyncioTestCase):
    async def test_dead_account_does_not_starve_later_accounts(self):
        """THE regression: account 3 never connects, account 4 still must."""
        dead = _make_worker(OSError("Name or service not known"))
        alive = _make_worker(True)
        am = _make_account_manager({2: _make_worker(), 3: dead, 4: alive})

        await _run(am, primary_id=2)

        alive.connect.assert_awaited()
        self.assertGreater(dead.connect.await_count, 1, "dead account should keep retrying")

    async def test_account_returning_false_does_not_starve_later_accounts(self):
        """connect() returning False (not raising) must not block others either."""
        refusing = _make_worker(False)
        alive = _make_worker(True)
        am = _make_account_manager({2: _make_worker(), 3: refusing, 4: alive})

        await _run(am, primary_id=2)

        alive.connect.assert_awaited()
        self.assertGreater(refusing.connect.await_count, 1)

    async def test_healthy_account_connects_exactly_once(self):
        alive = _make_worker(True)
        am = _make_account_manager({2: _make_worker(), 4: alive})

        await _run(am, primary_id=2)

        self.assertEqual(alive.connect.await_count, 1)

    async def test_primary_account_is_skipped(self):
        primary = _make_worker(True)
        am = _make_account_manager({2: primary, 4: _make_worker(True)})

        await _run(am, primary_id=2, primary_worker=primary)

        primary.connect.assert_not_awaited()

    async def test_shared_ib_connection_is_connected_once(self):
        """Accounts sharing one IB object must not both dial it."""
        first = _make_worker(True)
        second = _make_worker(True)
        second.ib = first.ib  # same underlying connection
        am = _make_account_manager({2: _make_worker(), 3: first, 4: second})

        await _run(am, primary_id=2)

        self.assertEqual(first.connect.await_count, 1)
        second.connect.assert_not_awaited()

    async def test_worker_sharing_primary_connection_is_skipped(self):
        primary = _make_worker(True)
        secondary = _make_worker(True)
        secondary.ib = primary.ib
        am = _make_account_manager({2: primary, 3: secondary})

        await _run(am, primary_id=2, primary_worker=primary)

        secondary.connect.assert_not_awaited()

    async def test_missing_worker_is_skipped(self):
        alive = _make_worker(True)
        am = _make_account_manager({2: _make_worker(), 3: None, 4: alive})

        await _run(am, primary_id=2)

        alive.connect.assert_awaited()


if __name__ == "__main__":
    unittest.main()
