"""
Zakat Calculator.
Calculates zakat on zakatable assets (cash and tradeable securities).
Track C: Trading & Infrastructure.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# Nisab = 85g of gold. Fetched live; this is the fallback if fetch fails.
_NISAB_FALLBACK_USD: float = 5500.0
_NISAB_GOLD_GRAMS: float = 85.0

_nisab_cache: dict = {"value": None, "fetched_at": None}
_NISAB_CACHE_TTL_SECONDS = 86400  # 1 day


def fetch_nisab_usd() -> float:
    """Return nisab threshold in USD = 85g gold × live spot price. Caches 24h."""
    cached = _nisab_cache
    if cached["value"] is not None and cached["fetched_at"] is not None:
        age = (datetime.now(timezone.utc) - cached["fetched_at"]).total_seconds()
        if age < _NISAB_CACHE_TTL_SECONDS:
            return cached["value"]
    try:
        info = yf.Ticker("GC=F").info
        # price is per troy oz (31.1035g)
        price_per_oz = info.get("regularMarketPrice") or info.get("previousClose")
        if not price_per_oz:
            raise ValueError("no price")
        price_per_gram = price_per_oz / 31.1035
        nisab = round(_NISAB_GOLD_GRAMS * price_per_gram, 2)
        _nisab_cache["value"] = nisab
        _nisab_cache["fetched_at"] = datetime.now(timezone.utc)
        logger.info(f"Nisab updated: ${nisab:.2f} (gold ${price_per_oz:.2f}/oz)")
        return nisab
    except Exception as e:
        logger.warning(f"Nisab fetch failed, using fallback ${_NISAB_FALLBACK_USD}: {e}")
        return _NISAB_FALLBACK_USD


def calculate_zakat(
    zakatable_assets_value: float,
    rate: float = 0.025,
    nisab: Optional[float] = None,
) -> float:
    """
    Calculates zakat based on the value of zakatable assets.
    Returns 0.0 if assets are below the nisab threshold.
    Default rate is 2.5% (Lunar year standard).
    """
    if zakatable_assets_value < 0:
        raise ValueError("Zakatable assets value cannot be negative")
    if rate < 0 or rate > 1:
        raise ValueError("Zakat rate must be between 0 and 1")

    resolved_nisab = nisab if nisab is not None else fetch_nisab_usd()

    if resolved_nisab < 0:
        raise ValueError("Nisab cannot be negative")

    if zakatable_assets_value < resolved_nisab:
        return 0.0

    return zakatable_assets_value * rate
