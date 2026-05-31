"""Tests for _exceeds_concentration_limit: sector normalization, 30% hard cap, min_sector_count."""
import unittest
from unittest.mock import MagicMock, patch
from ibkr_core.features.trading.trader import _exceeds_concentration_limit

_BASE_SETTINGS = {
    "max_position_size_pct": 100.0,  # disable position cap — isolate sector logic
    "max_sector_exposure_pct": 30.0,
    "min_sector_count": 4,
}

# Disable min_sector_count to isolate cap/normalization logic in those tests
_NO_MIN_SECTOR = {**_BASE_SETTINGS, "min_sector_count": 1}


def _make_worker(positions=None):
    w = MagicMock()
    w.get_positions.return_value = positions or []
    return w


def _make_compliance_rec(sector: str):
    rec = MagicMock()
    rec.metrics = {"sector": sector}
    return rec


def _make_db(target_sector: str, peer_sectors: list[str]):
    """
    Returns a mock SessionLocal context manager.
    First query (for the incoming symbol) → target_sector.
    Subsequent queries (peers) → peer_sectors in order.
    """
    target_rec = _make_compliance_rec(target_sector)
    peer_recs = [_make_compliance_rec(s) for s in peer_sectors]

    query_mock = MagicMock()
    # chain: .filter().order_by().first() — each call to .first() pops next peer
    side_effects = [target_rec] + peer_recs

    def make_query(*_args, **_kwargs):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.side_effect = side_effects[:1]
        side_effects.pop(0)
        return q

    db = MagicMock()
    db.query.side_effect = make_query
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestSectorNormalization(unittest.TestCase):
    """Sector strings like "Technology / Software" must normalize to "Technology"."""

    def test_raw_sublevel_sector_counts_toward_top_level_cap(self):
        # MSFT holds $25k "Technology / Software". New buy 1@$100 → $25.1k < $30k cap → allowed.
        net_liq = 100_000.0
        positions = [{"symbol": "MSFT", "market_value": "25000"}]
        worker = _make_worker(positions)
        db_ctx = _make_db("Technology / Software", ["Technology / Software"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit("AAPL", 1.0, 100.0, net_liq, worker, _NO_MIN_SECTOR)

        self.assertFalse(result)

    def test_sublevel_sector_triggers_cap_when_over_threshold(self):
        # $29.9k tech existing + $200 new = $30.1k > $30k cap → blocked.
        net_liq = 100_000.0
        positions = [{"symbol": "MSFT", "market_value": "29900"}]
        worker = _make_worker(positions)
        db_ctx = _make_db("Technology / Software", ["Technology / Software"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit("AAPL", 2.0, 100.0, net_liq, worker, _NO_MIN_SECTOR)

        self.assertTrue(result)

    def test_mixed_sublevel_and_toplevel_aggregate_correctly(self):
        # AAPL "Technology" $15k + MSFT "Technology / Software" $15k = $30k. New buy → $30.1k → blocked.
        net_liq = 100_000.0
        positions = [
            {"symbol": "AAPL", "market_value": "15000"},
            {"symbol": "MSFT", "market_value": "15000"},
        ]
        worker = _make_worker(positions)
        db_ctx = _make_db("Technology", ["Technology", "Technology / Software"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit("NVDA", 1.0, 100.0, net_liq, worker, _NO_MIN_SECTOR)

        self.assertTrue(result)


class TestSectorHardCap(unittest.TestCase):
    """30% hard cap blocks buys regardless of signal strength."""

    def test_allows_buy_below_cap(self):
        net_liq = 100_000.0
        positions = [{"symbol": "AAPL", "market_value": "20000"}]
        worker = _make_worker(positions)
        db_ctx = _make_db("Technology", ["Technology"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit(
                "MSFT", 1.0, 100.0, net_liq, worker,
                {**_BASE_SETTINGS, "min_sector_count": 1},  # disable min_sector rule
            )

        self.assertFalse(result)

    def test_blocks_buy_at_cap(self):
        net_liq = 100_000.0
        # $30k tech already = exactly at cap. Any new tech buy → over.
        positions = [{"symbol": "AAPL", "market_value": "30000"}]
        worker = _make_worker(positions)
        db_ctx = _make_db("Technology", ["Technology"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit(
                "MSFT", 1.0, 100.0, net_liq, worker,
                {**_BASE_SETTINGS, "min_sector_count": 1},
            )

        self.assertTrue(result)

    def test_non_tech_sector_not_affected_by_tech_cap(self):
        # Tech at cap, but buying Healthcare → allowed.
        net_liq = 100_000.0
        positions = [{"symbol": "AAPL", "market_value": "30000"}]
        worker = _make_worker(positions)
        db_ctx = _make_db("Healthcare", ["Technology"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit(
                "JNJ", 1.0, 100.0, net_liq, worker,
                {**_BASE_SETTINGS, "min_sector_count": 1},
            )

        self.assertFalse(result)

    def test_cap_respects_custom_setting(self):
        # Custom cap of 40% — $35k tech out of $100k should be allowed.
        net_liq = 100_000.0
        positions = [{"symbol": "AAPL", "market_value": "35000"}]
        worker = _make_worker(positions)
        db_ctx = _make_db("Technology", ["Technology"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit(
                "MSFT", 1.0, 100.0, net_liq, worker,
                {**_BASE_SETTINGS, "max_sector_exposure_pct": 40.0, "min_sector_count": 1},
            )

        self.assertFalse(result)


class TestMinSectorCount(unittest.TestCase):
    """min_sector_count=4 blocks buying more of an existing sector until 4 sectors held."""

    def test_blocks_doubling_down_when_below_min_sectors(self):
        # Only 2 sectors held (Tech + Healthcare). Trying to buy more Tech → blocked.
        net_liq = 100_000.0
        positions = [
            {"symbol": "AAPL", "market_value": "5000"},   # Tech
            {"symbol": "JNJ", "market_value": "5000"},    # Healthcare
        ]
        worker = _make_worker(positions)
        db_ctx = _make_db("Technology", ["Technology", "Healthcare"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit("MSFT", 1.0, 100.0, net_liq, worker, _BASE_SETTINGS)

        self.assertTrue(result)

    def test_allows_new_sector_when_below_min(self):
        # Only 2 sectors held. Buying a NEW sector (Industrials) → allowed.
        net_liq = 100_000.0
        positions = [
            {"symbol": "AAPL", "market_value": "5000"},
            {"symbol": "JNJ", "market_value": "5000"},
        ]
        worker = _make_worker(positions)
        db_ctx = _make_db("Industrials", ["Technology", "Healthcare"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit("HON", 1.0, 100.0, net_liq, worker, _BASE_SETTINGS)

        self.assertFalse(result)

    def test_allows_existing_sector_once_min_met(self):
        # 4 sectors held. Adding more Tech → min_sector rule doesn't block (cap check only).
        net_liq = 100_000.0
        positions = [
            {"symbol": "AAPL", "market_value": "5000"},   # Tech
            {"symbol": "JNJ", "market_value": "5000"},    # Healthcare
            {"symbol": "HON", "market_value": "5000"},    # Industrials
            {"symbol": "PG", "market_value": "5000"},     # Consumer Staples
        ]
        worker = _make_worker(positions)
        db_ctx = _make_db(
            "Technology",
            ["Technology", "Healthcare", "Industrials", "Consumer Staples"],
        )

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit("MSFT", 1.0, 100.0, net_liq, worker, _BASE_SETTINGS)

        self.assertFalse(result)

    def test_custom_min_sector_count(self):
        # min_sector_count=2. Portfolio has 2 sectors → min met → adding to existing allowed.
        net_liq = 100_000.0
        positions = [
            {"symbol": "AAPL", "market_value": "5000"},
            {"symbol": "JNJ", "market_value": "5000"},
        ]
        worker = _make_worker(positions)
        db_ctx = _make_db("Technology", ["Technology", "Healthcare"])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit(
                "MSFT", 1.0, 100.0, net_liq, worker,
                {**_BASE_SETTINGS, "min_sector_count": 2},
            )

        self.assertFalse(result)

    def test_empty_portfolio_allows_first_buy(self):
        # No positions at all → no sector data → concentration check skipped → allowed.
        net_liq = 100_000.0
        worker = _make_worker([])
        db_ctx = _make_db("Technology", [])

        with patch("ibkr_core.features.trading.trader.SessionLocal", return_value=db_ctx):
            result = _exceeds_concentration_limit("AAPL", 1.0, 100.0, net_liq, worker, _BASE_SETTINGS)

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
