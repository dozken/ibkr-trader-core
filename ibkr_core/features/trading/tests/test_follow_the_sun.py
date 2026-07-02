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
        ]
        with patch("yfinance.download", side_effect=Exception("offline")):
            positions = w.get_positions()
        symbols = {p["symbol"] for p in positions}
        self.assertEqual(symbols, {"ASML.AS", "ATCO-A.ST", "AAPL"})


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
