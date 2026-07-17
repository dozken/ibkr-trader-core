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

# Names whose IBKR localSymbol is NOT derivable by the suffix-strip +
# hyphen→space rule. LSE trailing-dot EPICs keep the dot as part of the
# ticker (RR.L → IBKR localSymbol "RR."), which the generic rule would drop.
# Keyed canonical → (ibkr_localSymbol, ibkr_primaryExchange). Verified on the
# live paper gateway (2026-07-13).
_LOCAL_OVERRIDE: dict = {
    "RR.L": ("RR.", "LSE"),
    "BA.L": ("BA.", "LSE"),
    "NG.L": ("NG.", "LSE"),
}
_OVERRIDE_INVERSE: dict = {(loc, ex): canon for canon, (loc, ex) in _LOCAL_OVERRIDE.items()}

# IBKR venues (contract.primaryExchange) where the qualifiable identity is the
# `symbol` field, NOT localSymbol. Numeric-ticker Asia markets put a SUFFIXED
# value in localSymbol ("7203.T") so a bare-localSymbol contract fails Error 200,
# while the plain code lives in `symbol` ("7203"). EU stays on the localSymbol
# path — its class shares (VOLV B) need it. Verified on the live paper gateway
# (2026-07-17): TSEJ/SEHK/SGX/ASX/NSE all qualify via the symbol field.
# Perms-gated venues (KSE/TSEM/SEHKNTL/SEHKSZSE/MSE/BURSA/SET/IDX) return
# "destination Invalid"/"no security definition" on this account — untradable and
# their exact shape is unverified, so they are NOT wired here; add on perms+probe.
_SYMBOL_FIELD_VENUES = {"TSEJ", "SEHK", "SGX", "ASX", "NSE"}
# Venues whose IBKR code drops leading zeros (HK 0700 → 700). Canonical yfinance
# keeps the 4-digit pad, so to_ibkr strips and from_ibkr re-pads.
_HK_VENUES = {"SEHK"}


def to_ibkr(symbol: str) -> str:
    """Canonical yfinance symbol → IBKR local symbol.

    Strips a KNOWN exchange suffix and converts hyphen class shares to
    IBKR's space form ("ATCO-A.ST" → "ATCO A"). This value goes into the
    contract's localSymbol field for foreign listings (see Worker._stock_contract).
    Explicit overrides handle tickers the generic rule can't (LSE trailing-dot);
    HK numeric codes drop their leading zeros ("0700.HK" → "700"). Unknown
    suffixes are left intact (fail-safe: the qualify check at order time rejects
    garbage cleanly).
    """
    if symbol in _LOCAL_OVERRIDE:
        return _LOCAL_OVERRIDE[symbol][0]
    stem = symbol
    sfx = ""
    if "." in symbol:
        head, _, sfx = symbol.rpartition(".")
        if sfx.upper() in _SUFFIX_TO_EXCHANGE:
            stem = head
    stem = stem.replace("-", " ")
    if sfx.upper() == "HK" and stem.isdigit():
        stem = stem.lstrip("0") or stem
    return stem


def uses_symbol_field(ibkr_exchange: str) -> bool:
    """True if this IBKR venue qualifies via the `symbol` field, not localSymbol."""
    return (ibkr_exchange or "").upper() in _SYMBOL_FIELD_VENUES


def from_ibkr(ibkr_symbol: str, primary_exchange: str = "") -> str:
    """IBKR (localSymbol, primaryExchange) → canonical yfinance symbol.

    Pass the contract's localSymbol (NOT the internal `symbol` field): IBKR's
    `symbol` is an internal ticker that diverges from the local ticker for
    class shares (VOLV.B) and cross-listed names (SAN→SAN1, AMP→AMP2), which
    would not round-trip. localSymbol is the exchange-local ticker and inverts
    cleanly (space→hyphen + venue suffix), with explicit overrides for the
    LSE trailing-dot EPICs.
    """
    venue = (primary_exchange or "").upper()
    key = (ibkr_symbol or "", venue)
    if key in _OVERRIDE_INVERSE:
        return _OVERRIDE_INVERSE[key]
    stem = (ibkr_symbol or "").replace(" ", "-")
    if venue in _US_VENUES:
        return stem
    sfx = _IBKR_TO_SUFFIX.get(venue)
    if sfx is None:
        logger.warning(
            "from_ibkr: unknown IBKR venue %r for %s — treating as US symbol",
            primary_exchange, ibkr_symbol,
        )
        return stem
    # localSymbol for numeric Asia venues already carries the suffix ("7203.T");
    # strip it so we don't double-append (→ "7203.T.T").
    if stem.upper().endswith("." + sfx.upper()):
        stem = stem[: -(len(sfx) + 1)]
    # HK drops leading zeros in IBKR; canonical yfinance re-pads to 4 digits.
    if venue in _HK_VENUES and stem.isdigit():
        stem = stem.zfill(4)
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
