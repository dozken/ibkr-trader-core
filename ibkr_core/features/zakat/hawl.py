"""
Hawl (حول) tracking — the lunar year condition for Zakat.

Rules:
- Hawl starts the day the portfolio first exceeds Nisab.
- If portfolio drops below Nisab, the hawl clock resets.
- Zakat is due when 354 days have elapsed (one lunar year).
- Once paid/acknowledged, hawl can be reset to start a new cycle.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# CWD-relative (DATA_DIR convention) — __file__-relative lands in read-only
# site-packages when ibkr_core is wheel-installed and breaks writes.
_HAWL_FILE = os.path.join(os.getenv("DATA_DIR", "data"), "hawl.json")
_LUNAR_YEAR_DAYS = 354


def _load() -> dict:
    if os.path.exists(_HAWL_FILE):
        try:
            with open(_HAWL_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"hawl_start": None, "last_checked": None}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_HAWL_FILE), exist_ok=True)
    with open(_HAWL_FILE, "w") as f:
        json.dump(data, f, indent=2)


def update_hawl(portfolio_value: float, nisab: float) -> dict:
    """
    Call daily. Updates hawl state based on current portfolio vs nisab.
    Returns current hawl status dict.
    """
    data = _load()
    now = datetime.now().isoformat()
    above = portfolio_value >= nisab

    if above:
        if not data.get("hawl_start"):
            data["hawl_start"] = now
            logger.info(f"Hawl started — portfolio ${portfolio_value:,.0f} above nisab ${nisab:,.0f}")
    else:
        if data.get("hawl_start"):
            logger.info(f"Hawl reset — portfolio ${portfolio_value:,.0f} dropped below nisab ${nisab:,.0f}")
        data["hawl_start"] = None

    data["last_checked"] = now
    _save(data)
    return data


def get_hawl_status(portfolio_value: float, nisab: float) -> dict:
    """Return full hawl status without mutating state."""
    data = _load()
    hawl_start_iso: Optional[str] = data.get("hawl_start")
    above_nisab = portfolio_value >= nisab

    if not hawl_start_iso or not above_nisab:
        return {
            "hawl_start": None,
            "hawl_end": None,
            "days_elapsed": 0,
            "days_remaining": _LUNAR_YEAR_DAYS,
            "is_due": False,
            "is_overdue": False,
            "above_nisab": above_nisab,
            "nisab_usd": nisab,
            "portfolio_value": portfolio_value,
            "lunar_year_days": _LUNAR_YEAR_DAYS,
            "pct_complete": 0.0,
        }

    hawl_start = datetime.fromisoformat(hawl_start_iso)
    hawl_end = hawl_start + timedelta(days=_LUNAR_YEAR_DAYS)
    now = datetime.now()
    days_elapsed = (now - hawl_start).days
    days_remaining = max(0, (hawl_end - now).days)
    is_due = now >= hawl_end
    pct_complete = min(100.0, (days_elapsed / _LUNAR_YEAR_DAYS) * 100)

    return {
        "hawl_start": hawl_start.date().isoformat(),
        "hawl_end": hawl_end.date().isoformat(),
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "is_due": is_due,
        "is_overdue": is_due,
        "above_nisab": above_nisab,
        "nisab_usd": nisab,
        "portfolio_value": portfolio_value,
        "lunar_year_days": _LUNAR_YEAR_DAYS,
        "pct_complete": round(pct_complete, 1),
    }


def reset_hawl() -> None:
    """Call after Zakat is paid to start a new Hawl cycle."""
    _save({"hawl_start": None, "last_checked": datetime.now().isoformat()})
    logger.info("Hawl reset — new cycle begins after next Nisab check.")
