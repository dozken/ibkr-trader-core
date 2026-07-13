"""Tests for the follow-the-sun foundations (global expansion, 2026-07-02):
symbol identity (yfinance ⇄ IBKR), exchange resolution, canonical position
keys, order qualify fail-closed guard, FX-aware sizing.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from ibkr_core.core.market_hours import resolve_exchange
from ibkr_core.core.symbols import from_ibkr, to_ibkr
from ibkr_core.core.state import TradeState
from ibkr_core.features.compliance.schemas import ComplianceStatus
from ibkr_core.features.trading.schemas import TradeCreate
from ibkr_core.features.trading.trader import Trader
from ibkr_core.features.trading.worker import IBKRWorker


class TestSymbolIdentity(unittest.TestCase):
    def test_to_ibkr_strips_known_suffixes(self):
        self.assertEqual(to_ibkr("ASML.AS"), "ASML")
        self.assertEqual(to_ibkr("RIO.L"), "RIO")
        self.assertEqual(to_ibkr("7203.T"), "7203")
        self.assertEqual(to_ibkr("BIMAS.IS"), "BIMAS")     # previously unstripped
        self.assertEqual(to_ibkr("GMEXICOB.MX"), "GMEXICOB")

    def test_to_ibkr_hyphen_class_shares_to_space(self):
        self.assertEqual(to_ibkr("ATCO-A.ST"), "ATCO A")
        self.assertEqual(to_ibkr("BRK-B"), "BRK B")

    def test_to_ibkr_leaves_us_and_unknown_suffix_intact(self):
        self.assertEqual(to_ibkr("AAPL"), "AAPL")
        self.assertEqual(to_ibkr("FOO.XX"), "FOO.XX")  # unknown suffix → untouched

    def test_from_ibkr_us_venues_bare(self):
        self.assertEqual(from_ibkr("AAPL", "NASDAQ"), "AAPL")
        self.assertEqual(from_ibkr("BRK B", "NYSE"), "BRK-B")
        self.assertEqual(from_ibkr("AAPL", ""), "AAPL")

    def test_from_ibkr_unknown_venue_falls_back_to_bare(self):
        self.assertEqual(from_ibkr("FOO", "XWEIRD"), "FOO")

    def test_round_trip_foreign_listings(self):
        # (canonical, IBKR primaryExchange) pairs — the venues IBKR reports.
        cases = [
            ("ASML.AS", "AEB"),
            ("RIO.L", "LSE"),
            ("7203.T", "TSEJ"),
            ("NOVN.SW", "EBS"),
            ("ATCO-A.ST", "SFB"),
            ("GMEXICOB.MX", "MEXI"),
            ("SU.PA", "SBF"),
            ("IFX.DE", "IBIS"),
            ("005930.KS", "KSE"),
            ("SHOP.TO", "TSE"),
        ]
        for canonical, venue in cases:
            with self.subTest(symbol=canonical):
                self.assertEqual(from_ibkr(to_ibkr(canonical), venue), canonical)

    def test_to_ibkr_lse_trailing_dot_overrides(self):
        # LSE EPICs whose ticker includes a trailing dot — the generic
        # suffix-strip would drop it. Verified on the live gateway 2026-07-13.
        self.assertEqual(to_ibkr("RR.L"), "RR.")
        self.assertEqual(to_ibkr("BA.L"), "BA.")
        self.assertEqual(to_ibkr("NG.L"), "NG.")

    def test_from_ibkr_lse_trailing_dot_inverse(self):
        self.assertEqual(from_ibkr("RR.", "LSE"), "RR.L")
        self.assertEqual(from_ibkr("BA.", "LSE"), "BA.L")
        self.assertEqual(from_ibkr("NG.", "LSE"), "NG.L")

    def test_round_trip_localsymbol_recovered_eu_names(self):
        # localSymbol ⇄ canonical for the EU names fixed by the localSymbol
        # contract builder (B1). from_ibkr takes the exchange-LOCAL ticker
        # (contract.localSymbol), which for these resolves the intended company:
        # SAN→Sanofi (not Banco Santander), AMP→Amplifon (not Amper).
        cases = [
            ("VOLV-B.ST", "SFB"),
            ("ERIC-B.ST", "SFB"),
            ("ASSA-B.ST", "SFB"),
            ("HEXA-B.ST", "SFB"),
            ("SAN.PA", "SBF"),
            ("AMP.MI", "BVME"),
            ("RR.L", "LSE"),
            ("BA.L", "LSE"),
            ("NG.L", "LSE"),
        ]
        for canonical, venue in cases:
            with self.subTest(symbol=canonical):
                self.assertEqual(from_ibkr(to_ibkr(canonical), venue), canonical)


class TestResolveExchange(unittest.TestCase):
    def test_suffixed_symbol_with_us_default_infers_home(self):
        self.assertEqual(resolve_exchange("ASML.AS", "NMS"), "AMS")
        self.assertEqual(resolve_exchange("ASML.AS", None), "AMS")
        self.assertEqual(resolve_exchange("ASML.AS", ""), "AMS")

    def test_explicit_exchange_respected(self):
        self.assertEqual(resolve_exchange("ASML.AS", "AMS"), "AMS")
        self.assertEqual(resolve_exchange("AAPL", "LSE"), "LSE")

    def test_us_symbol_stays_us(self):
        self.assertEqual(resolve_exchange("AAPL", "NMS"), "NMS")
        self.assertEqual(resolve_exchange("AAPL", None), "NMS")


def _mk_worker() -> IBKRWorker:
    w = IBKRWorker(host="127.0.0.1", port=4002, client_id=99)
    w.ib = MagicMock()
    IBKRWorker._positions_cache.clear()
    return w


class TestCanonicalPositions(unittest.TestCase):
    def test_get_positions_returns_canonical_suffixed_symbols(self):
        """IBKR returns bare local symbols; get_positions must key them back to
        the canonical yfinance form so Qabd/no-short/exit guards see them."""
        w = _mk_worker()
        w.ib.portfolio.return_value = []
        w.ib.positions.return_value = [
            SimpleNamespace(
                account="DU1",
                contract=SimpleNamespace(symbol="ASML", primaryExchange="AEB", exchange=""),
                position=2.0, avgCost=500.0,
            ),
            SimpleNamespace(
                account="DU1",
                contract=SimpleNamespace(symbol="ATCO A", primaryExchange="SFB", exchange=""),
                position=4.0, avgCost=150.0,
            ),
            SimpleNamespace(
                account="DU1",
                contract=SimpleNamespace(symbol="AAPL", primaryExchange="NASDAQ", exchange=""),
                position=3.0, avgCost=290.0,
            ),
            # IBKR returns the DOTTED internal symbol for class shares ("VOLV.B")
            # but the space-form localSymbol; keying off `symbol` would yield the
            # bogus "VOLV.B.ST" and orphan the position. Must use localSymbol.
            SimpleNamespace(
                account="DU1",
                contract=SimpleNamespace(symbol="VOLV.B", localSymbol="VOLV B",
                                         primaryExchange="SFB", exchange=""),
                position=5.0, avgCost=250.0,
            ),
        ]
        with patch("yfinance.download", side_effect=Exception("offline")):
            positions = w.get_positions()
        symbols = {p["symbol"] for p in positions}
        self.assertEqual(symbols, {"ASML.AS", "ATCO-A.ST", "AAPL", "VOLV-B.ST"})


class TestQualifyFailClosed(unittest.IsolatedAsyncioTestCase):
    async def test_place_order_refuses_unqualified_contract(self):
        w = _mk_worker()
        w.ib.qualifyContractsAsync = AsyncMock(return_value=[])
        trade = SimpleNamespace(symbol="BIMAS.IS", side="BUY", quantity=1.0)
        with self.assertRaisesRegex(ValueError, "qualification failed"):
            await w.place_order(trade, exchange="IST")

    async def test_place_bracket_refuses_unqualified_contract(self):
        w = _mk_worker()
        w.ib.qualifyContractsAsync = AsyncMock(return_value=[])
        trade = SimpleNamespace(symbol="BIMAS.IS", side="BUY", quantity=1.0, signal_price=100.0)
        with self.assertRaisesRegex(ValueError, "qualification failed"):
            await w.place_bracket_order(trade, stop_price=92.0,
                                        take_profit_price=150.0, exchange="IST")


_FX_SETTINGS = {
    "min_trade_size": 10.0,
    "cash_reserve_pct": 5.0,
    "max_position_size_pct": 10.0,
    "risk_profile": "CONSERVATIVE",
    "stop_loss_pct": None,
    "take_profit_pct": None,
    "twap_threshold_pct": 100.0,
    "use_kelly_sizing": False,
    "dry_run": True,   # stop before broker call — sizing is what's under test
}


def _compliant(symbol: str) -> ComplianceStatus:
    return ComplianceStatus(
        symbol=symbol, sector="Technology", is_compliant=True,
        debt_to_mkt_cap=0.1, cash_to_mkt_cap=0.1, impure_revenue_pct=0.01,
    )


class TestFxAwareSizing(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_worker = MagicMock()
        self.mock_worker.get_available_funds.return_value = 10_000.0
        self.mock_worker.get_net_liquidation.return_value = 10_000.0
        self.mock_worker.get_positions.return_value = []
        self.mock_worker.get_market_data = AsyncMock(
            return_value={"bid": 99.9, "ask": 100.1, "last": 100.0, "volume": 1_000_000})
        self.mock_worker.get_avg_volume_20d = AsyncMock(return_value=5_000_000)
        self.mock_worker.get_last_price = AsyncMock(return_value=100.0)  # LOCAL ccy
        self.trader = Trader(self.mock_worker)
        for target, kw in [
            ("ibkr_core.features.trading.trader.SessionLocal", {}),
            ("ibkr_core.features.trading.trader._load_settings",
             {"return_value": _FX_SETTINGS}),
            ("ibkr_core.features.trading.trader._get_vix_size_factor",
             {"return_value": 1.0}),
        ]:
            p = patch(target, **kw)
            p.start()
            self.addCleanup(p.stop)

    async def test_foreign_buy_sizes_on_usd_price(self):
        """CHF-priced name at 100 CHF with CHF→USD=1.25: budget math must use
        $125, not 100 — qty = $1000 max-position / $125 = 8 (not 10)."""
        with patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate",
                   return_value=1.25):
            req = TradeCreate(symbol="NOVN.SW", quantity=0, side="BUY")
            trade = await self.trader.execute_trade(req, pre_screened=_compliant("NOVN.SW"))
        self.assertEqual(trade.state, TradeState.DRY_RUN)
        self.assertAlmostEqual(trade.quantity, 8.0, places=4)

    async def test_us_buy_unaffected(self):
        req = TradeCreate(symbol="AAPL", quantity=0, side="BUY")
        trade = await self.trader.execute_trade(req, pre_screened=_compliant("AAPL"))
        self.assertEqual(trade.state, TradeState.DRY_RUN)
        self.assertAlmostEqual(trade.quantity, 10.0, places=4)  # $1000 / $100

    async def test_missing_fx_rate_fails_closed(self):
        with patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate",
                   return_value=None):
            req = TradeCreate(symbol="NOVN.SW", quantity=0, side="BUY")
            trade = await self.trader.execute_trade(req, pre_screened=_compliant("NOVN.SW"))
        self.assertEqual(trade.state, TradeState.IBKR_ERROR)
        self.assertIn("FX rate", trade.error_message)
        self.mock_worker.place_order.assert_not_called()
        self.mock_worker.place_bracket_order.assert_not_called()


class TestToUsd(unittest.TestCase):
    """Shared price→USD normalization (symbols.to_usd). yfinance-sourced prices
    get the minor-unit divisor (LSE pence); source='ibkr' skips it (broker unit
    unverified) but still applies FX. Missing non-USD rate → None (fail closed).
    """

    def test_usd_symbol_passthrough_no_fx(self):
        from ibkr_core.core.symbols import to_usd
        # No FX lookup should happen for a USD name; patch to explode if called.
        with patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate",
                   side_effect=AssertionError("FX must not be called for USD")):
            self.assertAlmostEqual(to_usd(100.0, "AAPL"), 100.0)

    def test_eur_applies_fx_no_divisor(self):
        from ibkr_core.core.symbols import to_usd
        with patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate",
                   return_value=1.1):
            self.assertAlmostEqual(to_usd(100.0, "ASML.AS"), 110.0)

    def test_lse_yfinance_divides_pence_then_fx(self):
        from ibkr_core.core.symbols import to_usd
        with patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate",
                   return_value=1.27):
            # 14456 pence → 144.56 GBP → * 1.27 = 183.59 USD
            self.assertAlmostEqual(to_usd(14456.0, "AZN.L"), 144.56 * 1.27, places=4)

    def test_lse_divisor_applies_to_both_feeds(self):
        from ibkr_core.core.symbols import to_usd
        with patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate",
                   return_value=1.27):
            # IBKR get_last_price returns pence for LSE too (confirmed AZN.L=14456),
            # so the divisor applies regardless of feed.
            self.assertAlmostEqual(to_usd(14456.0, "AZN.L"), 144.56 * 1.27, places=4)

    def test_missing_fx_returns_none(self):
        from ibkr_core.core.symbols import to_usd
        with patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate",
                   return_value=None):
            self.assertIsNone(to_usd(100.0, "ASML.AS"))

    def test_none_price_returns_none(self):
        from ibkr_core.core.symbols import to_usd
        self.assertIsNone(to_usd(None, "AAPL"))

    def test_minor_unit_divisor_lookup(self):
        from ibkr_core.core.symbols import minor_unit_divisor
        self.assertEqual(minor_unit_divisor("AZN.L"), 100)
        self.assertEqual(minor_unit_divisor("ASML.AS"), 1)
        self.assertEqual(minor_unit_divisor("AAPL"), 1)


class TestGetPositionsUsd(unittest.TestCase):
    """get_positions must report avg_cost/market_value in one currency (USD):
    IBKR gives avgCost in the contract quote unit (EUR, LSE pence) but
    marketValue in base USD — mixing them broke foreign exit math."""

    def test_avg_cost_normalized_to_usd(self):
        w = _mk_worker()
        w.ib.portfolio.return_value = []          # force the local-price / avgCost path
        w.ib.positions.return_value = [
            SimpleNamespace(account="DU1",
                contract=SimpleNamespace(symbol="ASML", primaryExchange="AEB", exchange=""),
                position=2.0, avgCost=500.0),                # EUR major
            SimpleNamespace(account="DU1",
                contract=SimpleNamespace(symbol="AZN", primaryExchange="LSE", exchange=""),
                position=10.0, avgCost=14456.0),             # GBP pence
            SimpleNamespace(account="DU1",
                contract=SimpleNamespace(symbol="AAPL", primaryExchange="NASDAQ", exchange=""),
                position=3.0, avgCost=290.0),                # USD
        ]

        def _fx(frm, to):
            return {"EUR": 1.1, "GBP": 1.27}.get(frm, 1.0)

        with patch("yfinance.download", side_effect=Exception("offline")), \
             patch("ibkr_core.features.compliance.data_fetcher._get_fx_rate", side_effect=_fx):
            positions = w.get_positions()

        by = {p["symbol"]: p for p in positions}
        self.assertAlmostEqual(by["ASML.AS"]["avg_cost"], 500.0 * 1.1, places=2)
        self.assertAlmostEqual(by["AZN.L"]["avg_cost"], 144.56 * 1.27, places=2)  # pence/100 then FX
        self.assertAlmostEqual(by["AAPL"]["avg_cost"], 290.0, places=2)           # USD no-op
        # else-branch market_value = qty * avg_cost_usd (consistent unit)
        self.assertAlmostEqual(by["ASML.AS"]["market_value"], 2.0 * 500.0 * 1.1, places=2)
