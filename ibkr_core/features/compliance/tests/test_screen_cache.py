"""Tests for the TTL cache wrapping live_shariah_screen."""
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import ibkr_core.features.compliance.screening as screening_mod
from ibkr_core.features.compliance.screening import (
    ComplianceStatus,
    invalidate_screen_cache,
    live_shariah_screen,
)


def _make_status(symbol: str) -> ComplianceStatus:
    return ComplianceStatus(
        symbol=symbol,
        sector="Technology",
        is_compliant=True,
        verdict="COMPLIANT",
        debt_to_mkt_cap=0.1,
        cash_to_mkt_cap=0.1,
        impure_revenue_pct=0.01,
        reason=None,
    )


_TARGET = "ibkr_core.features.compliance.screening._live_shariah_screen_uncached"


class TestScreenCache(unittest.TestCase):
    def setUp(self):
        invalidate_screen_cache()  # start each test with a clean cache

    def tearDown(self):
        invalidate_screen_cache()  # avoid cross-test pollution

    # ── 1. First call hits the real (uncached) function ───────────────────────
    def test_first_call_hits_underlying(self):
        status = _make_status("AAPL")
        with patch(_TARGET, return_value=status) as mock_fn:
            result = live_shariah_screen("AAPL")
            mock_fn.assert_called_once_with("AAPL", None)
            self.assertEqual(result.symbol, "AAPL")

    # ── 2. Second call returns cached result without re-fetching ──────────────
    def test_second_call_is_cached(self):
        status = _make_status("MSFT")
        with patch(_TARGET, return_value=status) as mock_fn:
            live_shariah_screen("MSFT")
            live_shariah_screen("MSFT")
            mock_fn.assert_called_once()  # only one real fetch

    # ── 3. Expired entry triggers re-fetch ────────────────────────────────────
    def test_expired_entry_refetches(self):
        status = _make_status("GOOG")
        with patch(_TARGET, return_value=status) as mock_fn:
            # Manually plant a stale cache entry (timestamp in the past)
            with screening_mod._cache_lock:
                screening_mod._screen_cache["GOOG"] = (status, time.time() - screening_mod._CACHE_TTL_SECONDS - 1)
            live_shariah_screen("GOOG")
            mock_fn.assert_called_once_with("GOOG", None)

    # ── 4. invalidate_screen_cache(symbol) clears one symbol ─────────────────
    def test_invalidate_single_symbol(self):
        status_a = _make_status("AMZN")
        status_b = _make_status("META")
        with patch(_TARGET, side_effect=lambda s, b=None: _make_status(s)) as mock_fn:
            live_shariah_screen("AMZN")
            live_shariah_screen("META")
            invalidate_screen_cache("AMZN")
            live_shariah_screen("AMZN")  # should re-fetch
            live_shariah_screen("META")  # still cached, no re-fetch
            # AMZN called twice (initial + after invalidation), META only once
            calls = [c.args[0] for c in mock_fn.call_args_list]
            self.assertEqual(calls.count("AMZN"), 2)
            self.assertEqual(calls.count("META"), 1)

    # ── 5. invalidate_screen_cache() (no arg) clears all ─────────────────────
    def test_invalidate_all(self):
        with patch(_TARGET, side_effect=lambda s, b=None: _make_status(s)) as mock_fn:
            live_shariah_screen("NVDA")
            live_shariah_screen("TSLA")
            invalidate_screen_cache()
            live_shariah_screen("NVDA")
            live_shariah_screen("TSLA")
            self.assertEqual(mock_fn.call_count, 4)

    # ── 6. Thread safety: concurrent calls for same uncached symbol ───────────
    def test_thread_safety(self):
        status = _make_status("INTC")
        results = []

        with patch(_TARGET, return_value=status):
            def worker():
                results.append(live_shariah_screen("INTC"))

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(len(results), 10)
        for r in results:
            self.assertEqual(r.symbol, "INTC")

    # ── 7. Cache endpoint returns correct JSON ────────────────────────────────
    def test_cache_clear_endpoint_all(self):
        from fastapi.testclient import TestClient
        from ibkr_core.main import app

        client = TestClient(app)
        response = client.post("/api/compliance/screen/cache/clear")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"cleared": "all"})

    def test_cache_clear_endpoint_single_symbol(self):
        from fastapi.testclient import TestClient
        from ibkr_core.main import app

        client = TestClient(app)
        response = client.post("/api/compliance/screen/cache/clear?symbol=AAPL")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"cleared": "AAPL"})


if __name__ == "__main__":
    unittest.main()
