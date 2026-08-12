"""Unit tests for the paper-test startup safety assertion in ibkr_core.main.

Guards the open-core split safety invariant: a paper test must never silently
boot alongside a real-money (LIVE) account. See
``ibkr_core.main._assert_paper_test_safety``.
"""

import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ibkr_core.core.models import Base, Account
from ibkr_core.main import _assert_paper_test_safety


class PaperTestGuardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        # A stray PAPER_TEST in the shell env must not leak into tests that
        # assume it is unset; restore the original environment on teardown.
        self._env_patch = patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("PAPER_TEST", None)

    def tearDown(self):
        self._env_patch.stop()

    def _add(self, label, port, is_paper, is_active=True, read_only=False):
        db = self.Session()
        try:
            acc = Account(
                label=label, host="127.0.0.1", port=port, client_id=1,
                ibkr_account_id="X", is_paper=is_paper,
                is_active=is_active, read_only=read_only,
            )
            db.add(acc)
            db.commit()
        finally:
            db.close()

    def _run(self):
        # Patch the module-level SessionLocal the helper queries through.
        with patch("ibkr_core.main.SessionLocal", self.Session):
            _assert_paper_test_safety()

    def test_raises_on_coexistence(self):
        self._add("Live", port=4003, is_paper=False)
        self._add("Paper", port=4004, is_paper=True)
        with self.assertRaises(RuntimeError):
            self._run()

    def test_read_only_live_may_coexist_with_paper(self):
        # A read-only live account has no order path (execute_trade rejects
        # pre-IBKR, the worker connects in IBKR readonly mode), so it can be
        # watched during a paper test. Arming it is refused by the API.
        self._add("Live", port=4003, is_paper=False, read_only=True)
        self._add("Paper", port=4004, is_paper=True)
        self._run()

    def test_raises_when_one_of_several_live_accounts_is_armed(self):
        self._add("Live RO", port=4003, is_paper=False, read_only=True)
        self._add("Live armed", port=4003, is_paper=False, read_only=False)
        self._add("Paper", port=4004, is_paper=True)
        with self.assertRaises(RuntimeError):
            self._run()

    def test_raises_on_flag_with_active_live(self):
        self._add("Live", port=4003, is_paper=False)
        os.environ["PAPER_TEST"] = "true"
        with self.assertRaises(RuntimeError):
            self._run()

    def test_flag_stays_strict_even_for_read_only_live(self):
        # PAPER_TEST marks a dedicated paper run — no live account at all.
        self._add("Live", port=4003, is_paper=False, read_only=True)
        os.environ["PAPER_TEST"] = "true"
        with self.assertRaises(RuntimeError):
            self._run()

    def test_passes_when_only_paper_active(self):
        self._add("Paper", port=4004, is_paper=True)
        # No live account, PAPER_TEST unset -> must not raise.
        self._run()

    def test_passes_when_only_live_active_and_no_flag(self):
        self._add("Live", port=4003, is_paper=False)
        # Single live account, PAPER_TEST unset -> normal live op, must not raise.
        self._run()

    def test_inactive_live_does_not_count(self):
        # An inactive (is_active=false) live account is the documented way to
        # deactivate real money during a paper test — it must not block boot.
        self._add("Live", port=4003, is_paper=False, is_active=False)
        self._add("Paper", port=4004, is_paper=True)
        self._run()


if __name__ == "__main__":
    unittest.main()
