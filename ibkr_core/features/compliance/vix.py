import logging

import yfinance as yf

logger = logging.getLogger(__name__)

_VIX_TICKER = "^VIX"
_FALLBACK_VIX = 20.0


def get_current_vix() -> float:
    """Fetch latest VIX close. Returns _FALLBACK_VIX on any failure."""
    try:
        hist = yf.Ticker(_VIX_TICKER).history(period="1d")
        if hist.empty:
            return _FALLBACK_VIX
        return float(hist["Close"].iloc[-1])
    except Exception as exc:
        logger.warning("VIX fetch failed: %s — using fallback %.1f", exc, _FALLBACK_VIX)
        return _FALLBACK_VIX


def vix_to_tier(vix: float) -> str:
    """Maps VIX level to a named volatility tier."""
    if vix < 20.0:
        return "CALM"
    elif vix < 30.0:
        return "ELEVATED"
    else:
        return "CRISIS"


def vix_to_ratio_buffer(vix: float) -> float:
    """
    Maps VIX level to AAOIFI ratio buffer (percentage points to subtract from thresholds).

    Applied to AAOIFI base thresholds 30% / 30% / 5% (debt / liquidity / impure).
    VIX < 20  → 0.0%  (calm — use static setting only)
    20 ≤ VIX < 30 → 2.0%  (elevated vol — thresholds tighten to 28%/28%/3%)
    VIX ≥ 30  → 5.0%  (crisis — thresholds tighten to 25%/25%/0%)
    """
    if vix < 20.0:
        return 0.0
    elif vix < 30.0:
        return 2.0
    else:
        return 5.0
