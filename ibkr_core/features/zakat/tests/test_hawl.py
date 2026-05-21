"""Tests for Hawl (lunar year) tracking logic."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch


def _hawl_module():
    from ibkr_core.features.zakat import hawl
    return hawl


class TestHawlUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hawl_file = os.path.join(self.tmp, "hawl.json")

    def _patch(self, mod):
        mod._HAWL_FILE = self.hawl_file

    def test_starts_hawl_when_above_nisab(self):
        mod = _hawl_module()
        self._patch(mod)
        mod.update_hawl(portfolio_value=100_000, nisab=5_000)
        with open(self.hawl_file) as f:
            data = json.load(f)
        self.assertIsNotNone(data["hawl_start"])

    def test_no_hawl_when_below_nisab(self):
        mod = _hawl_module()
        self._patch(mod)
        mod.update_hawl(portfolio_value=1_000, nisab=5_000)
        with open(self.hawl_file) as f:
            data = json.load(f)
        self.assertIsNone(data["hawl_start"])

    def test_hawl_resets_if_drops_below_nisab(self):
        mod = _hawl_module()
        self._patch(mod)
        mod.update_hawl(portfolio_value=100_000, nisab=5_000)
        mod.update_hawl(portfolio_value=1_000, nisab=5_000)
        with open(self.hawl_file) as f:
            data = json.load(f)
        self.assertIsNone(data["hawl_start"])

    def test_hawl_preserved_if_stays_above_nisab(self):
        mod = _hawl_module()
        self._patch(mod)
        mod.update_hawl(portfolio_value=100_000, nisab=5_000)
        first_start = json.load(open(self.hawl_file))["hawl_start"]
        mod.update_hawl(portfolio_value=200_000, nisab=5_000)
        second_start = json.load(open(self.hawl_file))["hawl_start"]
        self.assertEqual(first_start, second_start)


class TestHawlStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hawl_file = os.path.join(self.tmp, "hawl.json")

    def _patch(self, mod):
        mod._HAWL_FILE = self.hawl_file

    def test_status_no_hawl_below_nisab(self):
        mod = _hawl_module()
        self._patch(mod)
        status = mod.get_hawl_status(portfolio_value=1_000, nisab=5_000)
        self.assertIsNone(status["hawl_start"])
        self.assertFalse(status["is_due"])
        self.assertFalse(status["above_nisab"])
        self.assertEqual(status["days_elapsed"], 0)

    def test_status_hawl_in_progress(self):
        mod = _hawl_module()
        self._patch(mod)
        start = (datetime.now() - timedelta(days=100)).isoformat()
        with open(self.hawl_file, "w") as f:
            json.dump({"hawl_start": start, "last_checked": start}, f)
        status = mod.get_hawl_status(portfolio_value=100_000, nisab=5_000)
        self.assertIn(status["days_elapsed"], (99, 100))
        self.assertIn(status["days_remaining"], (253, 254, 255))
        self.assertFalse(status["is_due"])
        self.assertGreater(status["pct_complete"], 27.0)
        self.assertLess(status["pct_complete"], 30.0)

    def test_status_is_due_after_354_days(self):
        mod = _hawl_module()
        self._patch(mod)
        start = (datetime.now() - timedelta(days=355)).isoformat()
        with open(self.hawl_file, "w") as f:
            json.dump({"hawl_start": start, "last_checked": start}, f)
        status = mod.get_hawl_status(portfolio_value=100_000, nisab=5_000)
        self.assertTrue(status["is_due"])
        self.assertTrue(status["is_overdue"])
        self.assertEqual(status["days_remaining"], 0)

    def test_reset_clears_hawl(self):
        mod = _hawl_module()
        self._patch(mod)
        start = datetime.now().isoformat()
        with open(self.hawl_file, "w") as f:
            json.dump({"hawl_start": start, "last_checked": start}, f)
        mod.reset_hawl()
        with open(self.hawl_file) as f:
            data = json.load(f)
        self.assertIsNone(data["hawl_start"])

    def test_pct_complete_capped_at_100(self):
        mod = _hawl_module()
        self._patch(mod)
        start = (datetime.now() - timedelta(days=500)).isoformat()
        with open(self.hawl_file, "w") as f:
            json.dump({"hawl_start": start, "last_checked": start}, f)
        status = mod.get_hawl_status(portfolio_value=100_000, nisab=5_000)
        self.assertEqual(status["pct_complete"], 100.0)


if __name__ == "__main__":
    unittest.main()
