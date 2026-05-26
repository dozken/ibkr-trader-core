from datetime import date
from unittest.mock import patch

from ibkr_core.core import market_hours
from ibkr_core.core.market_hours import is_trading_day, is_market_open


def test_us_memorial_day_2026_not_trading_day():
    # Mon May 25 2026 = Memorial Day (NYSE closed)
    assert is_trading_day("NMS", date(2026, 5, 25)) is False


def test_us_regular_weekday_is_trading_day():
    # Tue May 26 2026 — normal session
    assert is_trading_day("NMS", date(2026, 5, 26)) is True


def test_us_weekend_not_trading_day():
    # Sat May 23 2026
    assert is_trading_day("NMS", date(2026, 5, 23)) is False


def test_saudi_friday_not_trading_day():
    # Fri May 22 2026 — Tadawul closed Fri
    assert is_trading_day("SAU", date(2026, 5, 22)) is False


def test_saudi_sunday_is_trading_day():
    # Sun Jun 7 2026 — Tadawul regular session
    assert is_trading_day("SAU", date(2026, 6, 7)) is True


def test_unknown_exchange_falls_back_to_weekday():
    # No calendar mapping → weekday-only check
    assert is_trading_day("UNKNOWN_XX", date(2026, 5, 25)) is True  # Mon
    assert is_trading_day("UNKNOWN_XX", date(2026, 5, 23)) is False  # Sat


def test_is_market_open_blocks_us_holiday():
    # Patch now() to 10:00 ET on Memorial Day 2026
    import datetime as _dt
    fake_now = _dt.datetime(2026, 5, 25, 10, 0, tzinfo=_dt.timezone.utc)

    class _FakeDateTime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now.astimezone(tz) if tz else fake_now

    with patch.object(market_hours, "datetime", _FakeDateTime):
        assert is_market_open("NMS") is False
