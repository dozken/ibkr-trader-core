"""
Unit tests for OrderPolicy — pure, no ib_insync / DB / broker mocks required.

Table-driven over (data_state, order_type, side, price) -> expected order_type /
limit_price / raise, covering: delayed buy/sell marketable-limit math, realtime
passthrough, the price<=0 ValueError guard, and the use_limit_orders interaction.
"""
import unittest

from ibkr_core.features.trading.order_policy import (
    BRACKET_ENTRY_PREMIUM_PCT,
    LIVE_PORTS,
    DataState,
    OrderPolicy,
    marketable_limit,
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
