import pytest
from unittest.mock import patch
from ibkr_core.features.zakat.zakat import calculate_zakat, fetch_nisab_usd, _NISAB_FALLBACK_USD

_FIXED_NISAB = 5500.0


def test_calculate_zakat_above_nisab():
    """2.5% applies when assets exceed nisab."""
    result = calculate_zakat(10000.0, nisab=_FIXED_NISAB)
    assert result == pytest.approx(250.0)


def test_calculate_zakat_custom_rate():
    result = calculate_zakat(10000.0, rate=0.03, nisab=_FIXED_NISAB)
    assert result == pytest.approx(300.0)


def test_calculate_zakat_below_nisab_returns_zero():
    """No zakat due when assets are below nisab threshold."""
    result = calculate_zakat(1000.0, nisab=_FIXED_NISAB)
    assert result == 0.0


def test_calculate_zakat_exactly_at_nisab():
    """Zakat applies at exactly nisab — boundary is inclusive for compliance."""
    result = calculate_zakat(_FIXED_NISAB, nisab=_FIXED_NISAB)
    assert result == pytest.approx(_FIXED_NISAB * 0.025)


def test_calculate_zakat_zero_assets():
    assert calculate_zakat(0.0, nisab=_FIXED_NISAB) == 0.0


def test_calculate_zakat_negative_raises():
    with pytest.raises(ValueError):
        calculate_zakat(-100.0, nisab=_FIXED_NISAB)


def test_calculate_zakat_invalid_rate_raises():
    with pytest.raises(ValueError):
        calculate_zakat(10000.0, rate=1.5, nisab=_FIXED_NISAB)


def test_fetch_nisab_uses_gold_price():
    """fetch_nisab_usd returns 85g × price_per_gram."""
    mock_info = {"regularMarketPrice": 3110.35}  # $3110.35/oz → $100/g → nisab = $8500
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.info = mock_info
        import ibkr_core.features.zakat.zakat as z
        z._nisab_cache["value"] = None  # bust cache
        result = fetch_nisab_usd()
    assert result == pytest.approx(85 * (3110.35 / 31.1035), rel=1e-3)


def test_fetch_nisab_fallback_on_error():
    """Falls back to _NISAB_FALLBACK_USD when yfinance fails."""
    with patch("yfinance.Ticker", side_effect=Exception("network error")):
        import ibkr_core.features.zakat.zakat as z
        z._nisab_cache["value"] = None
        result = fetch_nisab_usd()
    assert result == _NISAB_FALLBACK_USD


def test_nisab_fallback_is_positive():
    assert _NISAB_FALLBACK_USD > 0
