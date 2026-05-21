"""
Unit tests for vix.py — vix_to_tier + tier-change notification helper.
No live network calls.
"""
import unittest
from ibkr_core.features.compliance.vix import vix_to_tier, vix_to_ratio_buffer


class TestVixToTier(unittest.TestCase):
    def test_below_20_calm(self):
        self.assertEqual(vix_to_tier(15.0), "CALM")

    def test_at_boundary_20_elevated(self):
        self.assertEqual(vix_to_tier(20.0), "ELEVATED")

    def test_between_20_30_elevated(self):
        self.assertEqual(vix_to_tier(25.5), "ELEVATED")

    def test_at_boundary_30_crisis(self):
        self.assertEqual(vix_to_tier(30.0), "CRISIS")

    def test_above_30_crisis(self):
        self.assertEqual(vix_to_tier(45.0), "CRISIS")

    def test_tier_aligns_with_buffer(self):
        """Tier and buffer thresholds must match."""
        self.assertEqual(vix_to_ratio_buffer(15.0), 0.0)
        self.assertEqual(vix_to_ratio_buffer(22.0), 2.0)
        self.assertEqual(vix_to_ratio_buffer(35.0), 5.0)
        self.assertEqual(vix_to_tier(15.0), "CALM")
        self.assertEqual(vix_to_tier(22.0), "ELEVATED")
        self.assertEqual(vix_to_tier(35.0), "CRISIS")


if __name__ == "__main__":
    unittest.main()
