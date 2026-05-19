import logging
import os
from dataclasses import dataclass
from datetime import date

import yfinance as yf
import httpx

logger = logging.getLogger(__name__)

FMP_API_KEY = os.getenv("FMP_API_KEY")

_MA_KEYWORDS = frozenset(["merger", "acquisition", "acqui", "takeover", "buyout"])
_SPINOFF_KEYWORDS = frozenset(["spin-off", "spinoff", "spinout", "divestiture", "divest"])
_ALL_KEYWORDS = _MA_KEYWORDS | _SPINOFF_KEYWORDS


@dataclass
class CorporateActionAlert:
    symbol: str
    action_type: str  # "MERGER" | "SPINOFF"
    headline: str
    event_date: date | None = None
    source: str = "YahooFinance"


def _check_fmp_mergers(symbol: str) -> list[CorporateActionAlert]:
    """Reliable M&A feed via FMP. Ref: Phase 4.1."""
    if not FMP_API_KEY:
        return []
    try:
        # FMP Mergers and Acquisitions RSS feed
        r = httpx.get(
            "https://financialmodelingprep.com/api/v4/mergers-acquisitions-rss",
            params={"page": 0, "apikey": FMP_API_KEY},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        alerts = []
        base_symbol = symbol.split(".")[0]
        for item in data:
            # item looks for symbol in title or text
            title = item.get("title", "")
            if base_symbol in title or symbol in title:
                alerts.append(CorporateActionAlert(
                    symbol=symbol,
                    action_type="MERGER",
                    headline=title,
                    source="FMP",
                ))
        return alerts
    except Exception as e:
        logger.debug(f"FMP merger check failed for {symbol}: {e}")
        return []


def check_corporate_actions(symbol: str, news_limit: int = 20) -> list[CorporateActionAlert]:
    """
    Scans for M&A/spin-off events using FMP (reliable) and yfinance (broad).
    Best-effort informational only — never used to block trades (fail-open).
    """
    alerts: list[CorporateActionAlert] = []
    
    # 1. Reliable FMP feed
    fmp_alerts = _check_fmp_mergers(symbol)
    alerts.extend(fmp_alerts)

    # 2. Broad yfinance news scan
    try:
        news = yf.Ticker(symbol).news or []
        for item in news[:news_limit]:
            title = (item.get("title") or "").lower()
            if not any(kw in title for kw in _ALL_KEYWORDS):
                continue
            
            # Skip if we already have an FMP alert for a similar headline
            if any(title[:30] in a.headline.lower() for a in fmp_alerts):
                continue

            action_type = "MERGER" if any(kw in title for kw in _MA_KEYWORDS) else "SPINOFF"
            alerts.append(CorporateActionAlert(
                symbol=symbol,
                action_type=action_type,
                headline=item.get("title", ""),
                source="YahooFinance",
            ))
    except Exception as exc:
        logger.warning("Corporate action news scan failed for %s: %s", symbol, exc)
    
    return alerts
