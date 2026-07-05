"""Canonical symbol identity: yfinance-suffixed ⇄ IBKR contract symbols.

The bot's canonical symbol format everywhere (universe, SignalLog,
TradeHistory, compliance, settings) is the yfinance suffixed ticker
("ASML.AS", "ATCO-A.ST"). IBKR wants a bare local symbol ("ASML",
"ATCO A") plus an exchange/currency. Before this module the two keyspaces
split after any foreign fill: positions came back bare, so every
suffix-keyed guard (no-short, Qabd possession, exit scan) stopped seeing
the position — an unsellable holding.

to_ibkr()   canonical → IBKR symbol (suffix stripped, hyphen class shares
            to IBKR's space form: "ATCO-A.ST" → "ATCO A").
from_ibkr() IBKR (symbol, primaryExchange) → canonical, via the venue →
            suffix inversion of market_hours' tables. Unknown venues map
            to the bare US form (logged) — the Qabd guard's
            external-acquisition path still allows divestment for those.
"""
import logging

from ibkr_core.core.market_hours import EXCHANGE_CONFIG, _SUFFIX_TO_EXCHANGE

logger = logging.getLogger(__name__)

# exchange code → canonical yfinance suffix. _SUFFIX_TO_EXCHANGE is
# many-to-one (KS/KQ → KSC); first-listed suffix per exchange wins, with
# explicit picks for the ambiguous ones.
_EXCHANGE_TO_SUFFIX: dict = {}
for _sfx, _exch in _SUFFIX_TO_EXCHANGE.items():
    _EXCHANGE_TO_SUFFIX.setdefault(_exch, _sfx)
_EXCHANGE_TO_SUFFIX.update({"KSC": "KS", "BSE": "NS", "TAI": "TW"})

# IBKR venue string (contract.primaryExchange) → canonical yfinance suffix.
# Built from EXCHANGE_CONFIG's ibkr_exchange column. Collisions resolved to
# the market the bot can actually trade: "KSE" is Korea in IBKR terms (the
# Kuwait/Pakistan rows reusing it are config bugs and untradable anyway);
# "IBIS" is XETRA (the DFM row reusing it is wrong).
_IBKR_TO_SUFFIX: dict = {}
for _code, (_tz, _sessions, _ibkr_ex, _ccy) in EXCHANGE_CONFIG.items():
    _sfx = _EXCHANGE_TO_SUFFIX.get(_code)
    if _sfx is not None:
        _IBKR_TO_SUFFIX.setdefault(_ibkr_ex, _sfx)
_IBKR_TO_SUFFIX.update({"KSE": "KS", "IBIS": "DE", "TSE": "TO", "TSEJ": "T"})

# IBKR venues that mean "US listing" → canonical form has NO suffix.
_US_VENUES = {
    "", "SMART", "NASDAQ", "NYSE", "ARCA", "AMEX", "BATS", "IEX",
    "ISLAND", "PSE", "CBOE", "NYSENAT", "LTSE", "MEMX", "OTC", "PINK",
}


def to_ibkr(symbol: str) -> str:
    """Canonical yfinance symbol → bare IBKR symbol.

    Strips a KNOWN exchange suffix and converts hyphen class shares to
    IBKR's space form. Unknown suffixes are left intact (fail-safe: the
    qualify check at order time rejects garbage cleanly).
    """
    stem = symbol
    if "." in symbol:
        head, _, sfx = symbol.rpartition(".")
        if sfx.upper() in _SUFFIX_TO_EXCHANGE:
            stem = head
    return stem.replace("-", " ")


def from_ibkr(ibkr_symbol: str, primary_exchange: str = "") -> str:
    """IBKR (symbol, primaryExchange) → canonical yfinance symbol."""
    stem = (ibkr_symbol or "").replace(" ", "-")
    venue = (primary_exchange or "").upper()
    if venue in _US_VENUES:
        return stem
    sfx = _IBKR_TO_SUFFIX.get(venue)
    if sfx is None:
        logger.warning(
            "from_ibkr: unknown IBKR venue %r for %s — treating as US symbol",
            primary_exchange, ibkr_symbol,
        )
        return stem
    return f"{stem}.{sfx}"


# Exchanges that quote in MINOR units — divide a raw price by this before any
# FX/notional math. LSE = pence, JSE = cents. This is the EXCHANGE's quoting
# convention, so it holds for BOTH data feeds we use: yfinance AND IBKR
# get_last_price/avgCost were empirically confirmed to return pence for LSE
# (AZN.L = 14456 on both, 2026-07-05). Keyed by exchange code (market_hours).
_MINOR_UNIT_DIVISOR: dict = {"LSE": 100, "JNB": 100}


def minor_unit_divisor(symbol: str, exchange: str = "") -> int:
    """Minor-unit price divisor for the symbol's home exchange (1 if major-unit)."""
    from ibkr_core.core.market_hours import resolve_exchange
    return _MINOR_UNIT_DIVISOR.get(resolve_exchange(symbol, exchange), 1)


def to_usd(local_price, symbol: str, exchange: str = ""):
    """Convert a price in the symbol's quote currency to USD.

    Applies the exchange's minor-unit divisor (LSE pence, JSE cents) — correct
    for both yfinance and IBKR feeds, which both quote LSE in pence — then the
    FX leg (quote-ccy → USD). USD symbols return the price unchanged (no FX
    lookup). Returns None when a required non-USD FX rate is unavailable —
    callers MUST fail closed (never size or value a position on a blind rate).
    """
    if local_price is None:
        return None
    from ibkr_core.core.market_hours import get_exchange_config, resolve_exchange
    exch = resolve_exchange(symbol, exchange)
    ccy = get_exchange_config(exch)[3]
    major = float(local_price) / _MINOR_UNIT_DIVISOR.get(exch, 1)
    if ccy == "USD":
        return major
    from ibkr_core.features.compliance.data_fetcher import _get_fx_rate
    fx = _get_fx_rate(ccy, "USD")
    if not fx:
        return None
    return major * fx
