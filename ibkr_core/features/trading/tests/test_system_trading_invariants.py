"""Tests for GET /api/system/trading account selection + coexistence violation.

Two bugs pinned here, both found live 2026-08-16 with a read-only LIVE account
(id 2) active alongside the armed PAPER account (id 4) actually running the test:

  1. The endpoint reported the LOWEST-ID active account unconditionally, so every
     field describing the trading posture (cap, cap_budget, exits_armed,
     data_mode, main_loop_healthy) belonged to the read-only, disconnected live
     account while the paper account traded unmonitored.
  2. The coexistence violation fired whenever ANY live account was active,
     including read-only ones — a posture ``_assert_paper_test_safety``
     explicitly ALLOWS. `ok` was therefore pinned false forever and the daily
     health check emitted a CRITICAL every single day, which is alert fatigue on
     the one signal meant to catch a real outage.
"""
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ibkr_core.core.models import Account, Base


class SystemTradingInvariantsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def _add(self, label, port, is_paper, is_active=True, read_only=False):
        db = self.Session()
        try:
            db.add(Account(
                label=label, host="127.0.0.1", port=port, client_id=1,
                ibkr_account_id="X", is_paper=is_paper,
                is_active=is_active, read_only=read_only,
            ))
            db.commit()
        finally:
            db.close()

    def _call(self, account_id=None, settings=None, connected=True):
        from ibkr_core.main import system_trading

        worker = MagicMock()
        worker.ib.isConnected.return_value = connected
        worker.port = 4004
        worker._market_data_type = 3          # delayed
        worker.get_positions.return_value = []

        am = MagicMock()
        am.list_account_ids.return_value = []
        am.get_worker_by_id.return_value = worker

        request = MagicMock()
        request.app.state.account_manager = am
        request.app.state.worker = worker
        request.app.state.loop_health = {
            "main_loop_2": {"status": "running", "last_run": None},
            "main_loop_4": {"status": "running", "last_run": None},
        }

        with patch("ibkr_core.main.SessionLocal", self.Session), \
             patch("ibkr_core.features.settings.service.load_settings",
                   return_value=settings or {}), \
             patch("ibkr_core.main._loop_ok", return_value=True):
            return system_trading(request, account_id=account_id)

    # ── account selection ────────────────────────────────────────────────────
    def test_defaults_to_the_account_that_can_trade_not_the_lowest_id(self):
        self._add("Live Personal", port=4003, is_paper=False, read_only=True)
        self._add("Paper Test", port=4004, is_paper=True)

        result = self._call()

        self.assertEqual(result.active_account.id, 2, "should pick the armed paper account")
        self.assertTrue(result.active_account.is_paper)

    def test_explicit_account_id_wins(self):
        self._add("Live Personal", port=4003, is_paper=False, read_only=True)
        self._add("Paper Test", port=4004, is_paper=True)

        result = self._call(account_id=1)

        self.assertEqual(result.active_account.id, 1)
        self.assertFalse(result.active_account.is_paper)

    def test_unknown_account_id_is_404(self):
        from fastapi import HTTPException
        self._add("Paper Test", port=4004, is_paper=True)

        with self.assertRaises(HTTPException) as ctx:
            self._call(account_id=999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_single_account_setup_is_unchanged(self):
        self._add("Paper Test", port=4004, is_paper=True)

        result = self._call()

        self.assertEqual(result.active_account.id, 1)

    def test_falls_back_to_lowest_id_when_every_account_is_read_only(self):
        self._add("Live Personal", port=4003, is_paper=False, read_only=True)
        self._add("Live Joint", port=4003, is_paper=False, read_only=True)

        result = self._call()

        self.assertEqual(result.active_account.id, 1)

    # ── coexistence violation ────────────────────────────────────────────────
    def test_read_only_live_beside_paper_is_not_a_violation(self):
        """THE regression: this is the supported posture, not a fault."""
        self._add("Live Personal", port=4003, is_paper=False, read_only=True)
        self._add("Paper Test", port=4004, is_paper=True)

        result = self._call(settings={
            "use_trailing_stop": True, "trailing_stop_pct": 25.0, "stop_loss_pct": 8.0,
        })

        self.assertEqual(
            [v for v in result.violations if "coexist" in v], [],
            f"read-only live must not raise a coexistence violation: {result.violations}",
        )
        self.assertTrue(result.any_live_account_active, "still reported, just not a violation")

    def test_armed_live_beside_paper_is_still_a_violation(self):
        self._add("Live Personal", port=4003, is_paper=False, read_only=False)
        self._add("Paper Test", port=4004, is_paper=True)

        result = self._call(settings={
            "use_trailing_stop": True, "trailing_stop_pct": 25.0, "stop_loss_pct": 8.0,
        })

        self.assertTrue(
            any("coexist" in v for v in result.violations),
            f"armed live + paper must violate: {result.violations}",
        )
        self.assertFalse(result.ok)

    def test_paper_flagged_account_on_a_live_port_counts_as_live(self):
        """Fail-safe, mirroring _assert_paper_test_safety._is_live."""
        self._add("Mislabelled", port=4003, is_paper=True, read_only=False)
        self._add("Paper Test", port=4004, is_paper=True)

        result = self._call(settings={
            "use_trailing_stop": True, "trailing_stop_pct": 25.0, "stop_loss_pct": 8.0,
        })

        self.assertTrue(result.any_live_account_active)
        self.assertTrue(any("coexist" in v for v in result.violations))


if __name__ == "__main__":
    unittest.main()
