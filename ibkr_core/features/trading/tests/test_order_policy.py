"""
Unit tests for OrderPolicy — pure, no ib_insync / DB / broker mocks required.

Table-driven over (data_state, order_type, side, price) -> expected order_type /
limit_price / raise, covering: delayed buy/sell marketable-limit math, realtime
passthrough, the price<=0 ValueError guard, and the use_limit_orders interaction.
"""
import unittest

from ibkr_core.features.trading.order_policy import (
    BRACKET_ENTRY_PREMIUM_PCT,
    COARSE_NONUS_TICK,
    LIVE_PORTS,
    PAPER_PORTS,
    DataState,
    OrderPolicy,
    cold_boot_arming,
    marketable_limit,
    quantize_to_increment,
    select_tick_increment,
    subscription_for_port,
)


class TestSubscriptionForPort(unittest.TestCase):
    def test_live_ports_are_realtime(self):
        for port in (7496, 4001, 4003):
            with self.subTest(port=port):
                self.assertIs(subscription_for_port(port), DataState.REALTIME)

    def test_other_ports_are_delayed(self):
        # 7497 = TWS paper, 4002 = gateway paper, 4004 = gnzsnz paper API, 0 = unset.
        for port in (7497, 4002, 4004, 0, 12345):
            with self.subTest(port=port):
                self.assertIs(subscription_for_port(port), DataState.DELAYED)

    def test_live_ports_constant_is_canonical_set(self):
        self.assertEqual(LIVE_PORTS, frozenset({7496, 4001, 4003}))


class TestMarketableLimit(unittest.TestCase):
    def test_buy_pays_up_sell_gives_up(self):
        self.assertEqual(marketable_limit(100.0, "BUY", 0.1), 100.1)
        self.assertEqual(marketable_limit(100.0, "SELL", 0.1), 99.9)

    def test_custom_slippage(self):
        self.assertEqual(marketable_limit(200.0, "BUY", 0.3), 200.6)
        self.assertEqual(marketable_limit(200.0, "SELL", 0.3), 199.4)

    def test_rounds_to_two_decimals(self):
        # 33.333 * 1.001 = 33.36633... -> 33.37
        self.assertEqual(marketable_limit(33.333, "BUY", 0.1), 33.37)
        self.assertEqual(marketable_limit(33.333, "SELL", 0.1), 33.30)

    def test_bracket_premium_matches_legacy_1_005(self):
        # place_bracket_order previously used round(signal_price * 1.005, 2); the
        # helper with BRACKET_ENTRY_PREMIUM_PCT must reproduce it exactly.
        self.assertEqual(BRACKET_ENTRY_PREMIUM_PCT, 0.5)
        for px in (100.0, 12.34, 987.65):
            with self.subTest(px=px):
                self.assertEqual(
                    marketable_limit(px, "BUY", BRACKET_ENTRY_PREMIUM_PCT),
                    round(px * 1.005, 2),
                )


class TestSelectTickIncrement(unittest.TestCase):
    # MiFID II style bands: 0.01 below 50, 0.05 in [50,100), 0.1 at/above 100.
    BANDS = [(0.0, 0.01), (50.0, 0.05), (100.0, 0.1)]

    def test_picks_band_containing_price(self):
        self.assertEqual(select_tick_increment(10.0, self.BANDS), 0.01)
        self.assertEqual(select_tick_increment(49.99, self.BANDS), 0.01)
        self.assertEqual(select_tick_increment(50.0, self.BANDS), 0.05)  # low_edge inclusive
        self.assertEqual(select_tick_increment(75.0, self.BANDS), 0.05)
        self.assertEqual(select_tick_increment(100.0, self.BANDS), 0.1)
        self.assertEqual(select_tick_increment(9999.0, self.BANDS), 0.1)

    def test_unsorted_input_is_handled(self):
        shuffled = [(100.0, 0.1), (0.0, 0.01), (50.0, 0.05)]
        self.assertEqual(select_tick_increment(75.0, shuffled), 0.05)

    def test_empty_returns_none(self):
        self.assertIsNone(select_tick_increment(100.0, []))

    def test_price_below_all_edges_returns_none(self):
        # No band starts at/below price 5 when the lowest edge is 50.
        self.assertIsNone(select_tick_increment(5.0, [(50.0, 0.05), (100.0, 0.1)]))


class TestQuantizeToIncrement(unittest.TestCase):
    def test_buy_rounds_up_sell_rounds_down(self):
        # price 100.12 on a 0.1 tick: BUY -> 100.2, SELL -> 100.1.
        self.assertAlmostEqual(quantize_to_increment(100.12, "BUY", 0.1), 100.2)
        self.assertAlmostEqual(quantize_to_increment(100.12, "SELL", 0.1), 100.1)

    def test_five_cent_tick(self):
        self.assertAlmostEqual(quantize_to_increment(73.33, "BUY", 0.05), 73.35)
        self.assertAlmostEqual(quantize_to_increment(73.33, "SELL", 0.05), 73.30)

    def test_price_already_on_tick_is_unchanged_both_sides(self):
        # Float noise (100.1/0.05 == 2001.9999…) must not bump an on-tick price.
        self.assertAlmostEqual(quantize_to_increment(100.10, "BUY", 0.05), 100.10)
        self.assertAlmostEqual(quantize_to_increment(100.10, "SELL", 0.05), 100.10)
        self.assertAlmostEqual(quantize_to_increment(95.0, "BUY", 0.05), 95.0)
        self.assertAlmostEqual(quantize_to_increment(95.0, "SELL", 0.05), 95.0)

    def test_non_positive_tick_returns_price_unchanged(self):
        self.assertEqual(quantize_to_increment(100.123, "BUY", 0.0), 100.123)
        self.assertEqual(quantize_to_increment(100.123, "SELL", None), 100.123)

    def test_coarse_nonus_fallback_tick_value(self):
        self.assertEqual(COARSE_NONUS_TICK, 0.05)


class TestOrderPolicyDecide(unittest.TestCase):
    # (data_state, base order_type, side, price, slippage_pct)
    #   -> (expected order_type, expected limit_price)
    CASES = [
        # Realtime + plain market intent -> straight MARKET passthrough.
        ((DataState.REALTIME, "MKT", "BUY", 0.0, 0.1), ("MKT", None)),
        ((DataState.REALTIME, "MKT", "SELL", 150.0, 0.1), ("MKT", None)),
        # Delayed + market intent -> auto marketable-limit (the IBKR 10349 fix).
        ((DataState.DELAYED, "MKT", "BUY", 100.0, 0.1), ("LMT", 100.1)),
        ((DataState.DELAYED, "MKT", "SELL", 100.0, 0.1), ("LMT", 99.9)),
        # use_limit_orders (base LMT) on realtime data -> marketable-limit both sides.
        ((DataState.REALTIME, "LMT", "BUY", 100.0, 0.1), ("LMT", 100.1)),
        ((DataState.REALTIME, "LMT", "SELL", 100.0, 0.1), ("LMT", 99.9)),
        # Custom slippage honoured.
        ((DataState.REALTIME, "LMT", "BUY", 100.0, 0.3), ("LMT", 100.3)),
        # Delayed + use_limit_orders -> still a marketable-limit.
        ((DataState.DELAYED, "LMT", "BUY", 50.0, 0.2), ("LMT", 50.1)),
    ]

    def test_decide_table(self):
        for args, (exp_type, exp_price) in self.CASES:
            with self.subTest(args=args):
                d = OrderPolicy.decide(*args)
                self.assertEqual(d.order_type, exp_type)
                self.assertEqual(d.limit_price, exp_price)
                self.assertTrue(d.reason)  # always carries a human-readable reason

    def test_market_decision_has_no_limit_price(self):
        d = OrderPolicy.decide(DataState.REALTIME, "MKT", "BUY", 123.0, 0.1)
        self.assertEqual(d.order_type, "MKT")
        self.assertIsNone(d.limit_price)

    def test_zero_price_raises_when_limit_required(self):
        # Both routes into a required limit must fail-closed on a junk price.
        bad_prices = [0.0, -1.0, None]
        limit_routes = [
            (DataState.DELAYED, "MKT"),   # delayed forces limit
            (DataState.REALTIME, "LMT"),  # use_limit_orders forces limit
        ]
        for price in bad_prices:
            for data_state, base in limit_routes:
                with self.subTest(price=price, data_state=data_state, base=base):
                    with self.assertRaises(ValueError):
                        OrderPolicy.decide(data_state, base, "BUY", price, 0.1)

    def test_zero_price_ok_for_realtime_market(self):
        # A market order never needs a price, so 0.0 must not raise here.
        d = OrderPolicy.decide(DataState.REALTIME, "MKT", "BUY", 0.0, 0.1)
        self.assertEqual(d.order_type, "MKT")


if __name__ == "__main__":
    unittest.main()


class TestColdBootArming(unittest.TestCase):
    """A first boot on an empty DB must never come up able to place real orders."""

    def test_paper_ports_seed_active_and_writable(self):
        # 7497 TWS paper, 4002 IBGW raw paper, 4004 gnzsnz paper API.
        for port in (7497, 4002, 4004):
            with self.subTest(port=port):
                is_active, read_only = cold_boot_arming(port)
                self.assertTrue(is_active)
                self.assertFalse(read_only)

    def test_live_ports_seed_inert(self):
        # 4003 is the compose default for IBKR_PORT, so this is the real case:
        # seeding it active-and-writable armed real-money trading on cold boot.
        for port in (7496, 4001, 4003):
            with self.subTest(port=port):
                is_active, read_only = cold_boot_arming(port)
                self.assertFalse(is_active)
                self.assertTrue(read_only)

    def test_unrecognised_ports_seed_inert(self):
        # Absence of evidence is not proof of paper — arm nothing.
        for port in (0, 1, 4000, 4005, 8000, 65535):
            with self.subTest(port=port):
                is_active, read_only = cold_boot_arming(port)
                self.assertFalse(is_active)
                self.assertTrue(read_only)

    def test_paper_and_live_port_sets_are_disjoint(self):
        self.assertEqual(LIVE_PORTS & PAPER_PORTS, frozenset())
