import os
import httpx
import yfinance as yf
from typing import Dict, Any, Optional
import logging
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from ibkr_core.core.monitoring import API_REQUESTS, API_LATENCY

load_dotenv()

logger = logging.getLogger(__name__)

ZOYA_API_KEY    = os.getenv("ZOYA_API_KEY")
MUSAFFA_API_KEY = os.getenv("MUSAFFA_API_KEY")
AV_API_KEY      = os.getenv("ALPHA_VANTAGE_API_KEY", "demo")
FMP_API_KEY     = os.getenv("FMP_API_KEY")

# FX rate cache: {(from_ccy, to_ccy): (rate, fetched_at_epoch)}
_FX_CACHE: Dict[tuple, tuple] = {}
_FX_TTL_SECONDS = 3600  # 1 hour


def _get_fx_rate(from_ccy: str, to_ccy: str) -> Optional[float]:
    """
    Yahoo Finance FX rate for {from_ccy}{to_ccy}=X (e.g. TWDUSD=X).
    Returns rate to multiply a value-in-from_ccy by to convert to to_ccy.
    """
    if not from_ccy or not to_ccy or from_ccy == to_ccy:
        return 1.0
    key = (from_ccy.upper(), to_ccy.upper())
    cached = _FX_CACHE.get(key)
    if cached and (time.time() - cached[1]) < _FX_TTL_SECONDS:
        return cached[0]
    try:
        rate = yf.Ticker(f"{key[0]}{key[1]}=X").fast_info.last_price
        if isinstance(rate, (int, float)) and rate > 0:
            _FX_CACHE[key] = (float(rate), time.time())
            return float(rate)
    except Exception as e:
        logger.debug("FX fetch %s%s=X failed: %s", key[0], key[1], e)
    return None

# Maps exchange suffix → Yahoo Finance dot suffix
_EXCHANGE_SUFFIX = {
    # Japan
    "TYO": "T", "TSE": "T", "OSE": "T", "XJPX": "T",
    # Hong Kong
    "HKG": "HK", "HKEX": "HK", "XHKG": "HK",
    # Korea
    "KRX": "KS", "XKRX": "KS", "KOSDAQ": "KQ",
    # Taiwan
    "TWO": "TW", "TWSE": "TW", "TAI": "TW", "XTAI": "TW",
    # China — Shanghai (.SS) and Shenzhen (.SZ)
    "SHA": "SS", "SSE": "SS", "XSHG": "SS",
    "SHE": "SZ", "SZSE": "SZ", "XSHE": "SZ",
    # Singapore
    "SGX": "SI", "XSES": "SI",
    # India
    "BOM": "BO", "BSE": "BO", "XBOM": "BO",
    "NSE": "NS", "XNSE": "NS",
    # Southeast Asia
    "IDX": "JK", "XIDX": "JK",             # Indonesia
    "BURSA": "KL", "XKLS": "KL",           # Malaysia
    "SET": "BK", "XBKK": "BK",             # Thailand
    "XPHS": "PS",                           # Philippines (PSE)
    # Oceania
    "ASX": "AX", "XASX": "AX",             # Australia
    "NZX": "NZ", "XNZE": "NZ",             # New Zealand
    # Americas
    "TSX": "TO", "XTSX": "TO",             # Canada Toronto
    "TSXV": "V",                            # Canada Venture
    "BVMF": "SA", "B3": "SA",              # Brazil B3
    "MERVAL": "BA", "BCBA": "BA",          # Argentina
    "BCS": "SN",                            # Chile
    "BVC": "BC",                            # Colombia
    "BMV": "MX", "XMEX": "MX",             # Mexico
    # South Asia
    "PSX": "KA",                            # Pakistan
    # Africa
    "JSE": "JO", "XJSE": "JO",             # South Africa
    "EGX": "CA",                            # Egypt
    # Europe
    "LSE": "L",                             # London
    "HEL": "HE", "XHEL": "HE",             # Helsinki
    "STO": "ST", "XSTO": "ST",             # Stockholm
    "CPH": "CO", "XCPH": "CO",             # Copenhagen
    "OSL": "OL", "XOSL": "OL",             # Oslo
    "FRA": "F", "XFRA": "F",               # Frankfurt
    "XETRA": "DE", "ETR": "DE",            # XETRA
    "AMS": "AS", "XAMS": "AS",             # Amsterdam
    "PAR": "PA", "XPAR": "PA", "EPA": "PA", # Paris
    "BIT": "MI", "MIL": "MI", "XMIL": "MI", # Milan
    "MCE": "MC", "XMCE": "MC",             # Madrid
    "LIS": "LS", "XLIS": "LS",             # Lisbon
    "VIE": "VI", "XWBO": "VI",             # Vienna
    "ZUR": "SW", "SWX": "SW", "XSWX": "SW", # Swiss Exchange
    "BRU": "BR", "XBRU": "BR",             # Brussels
    "BIST": "IS", "XIST": "IS",             # Turkey Borsa Istanbul
    "KASE": "KZ", "AIX": "KZ",              # Kazakhstan
    "ATHEX": "AT", "XATH": "AT",            # Greece Athens
    "GPW": "WA", "WSE": "WA", "XWAR": "WA", # Poland Warsaw
    "XPRA": "PR",                           # Czech Republic Prague
    "XBUD": "BD",                           # Hungary Budapest
    "BVB": "RO",                            # Romania Bucharest
    # GCC / MENA
    "ADX": "AD", "ABU": "AD",              # Abu Dhabi (UAE)
    "DFM": "DU",                            # Dubai (UAE)
    "TADAWUL": "SR", "SAU": "SR",          # Saudi Arabia
    "QSE": "QA",                            # Qatar
    "MSM": "OM",                            # Oman
    "BHB": "BH",                            # Bahrain
    "ASE": "AM",                            # Amman (Jordan)
    "BOURSA": "KW",                         # Kuwait
}

# ── Shariah ETF allowlist ─────────────────────────────────────────────────────
# Tickers verified against fund prospectus / AAOIFI mandate.
# Allowlist takes priority over keyword matching to prevent name spoofing.
SHARIAH_ETF_ALLOWLIST: frozenset = frozenset({
    # SP Funds — Shariah Advisory: Ratings Intelligence (AAOIFI-certified)
    "SPUS",   # SP Funds S&P 500 Sharia ETF — tracks S&P 500 Shariah Index
    "SPSK",   # SP Funds S&P Sukuk ETF — sukuk bond fund, no riba
    "SPRE",   # SP Funds S&P Global REIT Sharia — Shariah-screened REITs
    # Wahed Invest — Shariah Board: independent panel per wahedinvest.com/shariah
    "HLAL",   # Wahed FTSE USA Shariah ETF — tracks FTSE USA Shariah Index
    "UMMA",   # Wahed Dow Jones Islamic World ETF — global, DJ Islamic Market Index
    # iShares MSCI Islamic — Screening: MSCI Islamic Index methodology (AAOIFI-based)
    "ISDE",   # iShares MSCI EM Islamic UCITS ETF
    "ISDW",   # iShares MSCI World Islamic UCITS ETF (US listing)
    "ISDU.L", # iShares MSCI USA Islamic UCITS ETF (LSE)
    "ISEW.L", # iShares MSCI World Islamic UCITS ETF (LSE)
    "ISWD.L", # iShares MSCI World Islamic UCITS ETF (Acc, LSE)
    "ISDW.L", # iShares MSCI World Islamic UCITS ETF (Dist, GBP, LSE)
    "ISDE.L", # iShares MSCI EM Islamic UCITS ETF (LSE)
    # Saturna Capital — Shariah: Amana Mutual Funds Trust, screened by Saturna
    "AMAL",   # Amal Invest Shariah ETF
    "AMAGX",  # Amana Growth Fund
    "AMANX",  # Amana Income Fund
    "AMDWX",  # Amana Developing World Fund
})

SHARIAH_ETF_FAMILIES: frozenset = frozenset({
    "sp funds", "wahed", "saturna", "amana", "iman",
    "hsbc amanah", "ishares msci world islamic",
})

# Physical gold ETCs — fully allocated, no riba, spot-settled.
# Halal per majority scholarly view (AAOIFI Standard 57 on Gold):
#   Gold is a ribawi commodity; physical-backed ETCs with full allocation
#   and no leverage are permissible. Source: AAOIFI Shari'ah Standard No. 57
#   "Sale of Debt and Securities", and OIC Fiqh Academy Resolution 153 (2006).
GOLD_ETC_ALLOWLIST: frozenset = frozenset({
    "RMAU",     # Royal Mint Responsibly Sourced Physical Gold ETC (US/intl listing)
    "RMAU.L",   # Royal Mint Responsibly Sourced Physical Gold ETC (LSE)
    "SGLN.L",   # iShares Physical Gold ETC (LSE) — fully backed by allocated gold bars
    "PHAU.L",   # WisdomTree Physical Gold (LSE) — backed by London Good Delivery bars
    "SGLD.L",   # Invesco Physical Gold ETC (LSE) — JP Morgan custodied allocated gold
    "GLDA.L",   # Amundi Physical Gold ETC (LSE) — allocated gold, London vaults
    "IGLN.L",   # iShares Physical Gold ETC (LSE, alt ticker)
    "PHGP.L",   # WisdomTree Physical Gold GBP-hedged (LSE)
})


def normalize_ticker(symbol: str) -> str:
    symbol = symbol.strip().upper()
    for sep in (":", "/"):
        if sep in symbol:
            left, right = [p.strip() for p in symbol.split(sep, 1)]
            # Handle both TICKER:EXCHANGE and EXCHANGE:TICKER
            if left in _EXCHANGE_SUFFIX:
                exchange, ticker = left, right
            else:
                ticker, exchange = left, right
            suffix = _EXCHANGE_SUFFIX.get(exchange)
            if suffix:
                return f"{ticker}.{suffix}"
            return f"{ticker}.{exchange}"
    return symbol


def _is_shariah_etf(fund_family: str, long_name: str, symbol: str = "") -> bool:
    # 1. Allowlist — authoritative, no false positives
    if symbol.upper() in SHARIAH_ETF_ALLOWLIST:
        return True
    # 2. Zoya verdict — trust over keyword match when key is configured
    if ZOYA_API_KEY and symbol:
        verdict = _fetch_zoya(symbol)
        if verdict is not None:
            return verdict.get("status") == "COMPLIANT"
    # 3. Known fund family names — lower false-positive risk than raw keywords
    text = f"{fund_family} {long_name}".lower()
    if any(f in text for f in SHARIAH_ETF_FAMILIES):
        return True
    # 4. Explicit Shariah keyword only — "islamic" alone removed (too broad)
    return "shariah" in text or "sharia" in text


# ── Zoya ──────────────────────────────────────────────────────────────────────

_ZOYA_GRAPHQL_QUERY = """
query ComplianceReport($symbol: String!) {
  advancedCompliance {
    report(input: { symbol: $symbol, methodology: AAOIFI }) {
      symbol name exchange status
      businessScreen financialScreen
      compliantRevenue nonCompliantRevenue questionableRevenue
      purificationRatio reportDate
    }
  }
}
"""

_ZOYA_BASIC_QUERY = """
query BasicReport($symbol: String!) {
  basicCompliance {
    report(symbol: $symbol) {
      symbol name exchange status purificationRatio reportDate
    }
  }
}
"""


def _fetch_zoya(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Zoya Shariah screening — GraphQL API with AAOIFI methodology.
    Returns business + financial screen breakdown and revenue split.
    Docs: https://zoya.finance/docs
    """
    if not ZOYA_API_KEY:
        return None
    start_time = time.time()
    try:
        API_REQUESTS.labels(provider="Zoya").inc()
        base = symbol.split(".")[0]
        zoya_host = "sandbox-api.zoya.finance" if ZOYA_API_KEY.startswith("sandbox-") else "api.zoya.finance"
        headers = {"Authorization": ZOYA_API_KEY}

        r = httpx.post(
            f"https://{zoya_host}/graphql",
            json={"query": _ZOYA_GRAPHQL_QUERY, "variables": {"symbol": base}},
            headers=headers,
            timeout=10,
        )
        API_LATENCY.labels(provider="Zoya").observe(time.time() - start_time)

        if r.status_code != 200:
            return None

        body = r.json()
        report = (body.get("data") or {}).get("advancedCompliance", {}).get("report")

        if not report:
            r2 = httpx.post(
                f"https://{zoya_host}/graphql",
                json={"query": _ZOYA_BASIC_QUERY, "variables": {"symbol": base}},
                headers=headers,
                timeout=10,
            )
            if r2.status_code == 200:
                report = (r2.json().get("data") or {}).get("basicCompliance", {}).get("report")
            if not report:
                return None

        status = (report.get("status") or "").upper()
        biz_screen = (report.get("businessScreen") or "").upper()
        fin_screen = (report.get("financialScreen") or "").upper()

        return {
            "compliant":            status == "COMPLIANT",
            "doubtful":             status == "DOUBTFUL",
            "status":               status,
            "business_screen":      biz_screen,
            "financial_screen":     fin_screen,
            "compliant_revenue":    report.get("compliantRevenue"),
            "non_compliant_revenue": report.get("nonCompliantRevenue"),
            "questionable_revenue": report.get("questionableRevenue"),
            "purification_pct":     float(report.get("purificationRatio") or 0),
            "report_date":          report.get("reportDate"),
            "source":               "Zoya",
        }
    except Exception as e:
        logger.debug(f"Zoya fetch failed for {symbol}: {e}")
        return None


# ── Musaffa ───────────────────────────────────────────────────────────────────

def _fetch_musaffa(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Musaffa Shariah compliance API.
    Docs: https://musaffa.com/api-docs
    """
    if not MUSAFFA_API_KEY:
        return None
    start_time = time.time()
    try:
        API_REQUESTS.labels(provider="Musaffa").inc()
        base = symbol.split(".")[0]
        r = httpx.get(
            f"https://api.musaffa.com/v1/stocks/{base}/compliance",
            headers={"x-api-key": MUSAFFA_API_KEY},
            timeout=8,
        )
        API_LATENCY.labels(provider="Musaffa").observe(time.time() - start_time)
        if r.status_code != 200:
            return None
        data = r.json()
        status = (data.get("complianceStatus") or data.get("status") or "").upper()
        if not status:
            return None
        return {
            "compliant":        status == "HALAL",
            "doubtful":         status == "DOUBTFUL",
            "status":           status,
            "purification_pct": float(data.get("purificationRatio") or 0),
            "source":           "Musaffa",
        }
    except Exception as e:
        logger.debug(f"Musaffa fetch failed for {symbol}: {e}")
        return None


# ── Alpha Vantage fundamentals ────────────────────────────────────────────────

def _fetch_av_fundamentals(symbol: str) -> Optional[Dict[str, float]]:
    """
    Supplement yfinance with Alpha Vantage OVERVIEW for US tickers.
    Only used if yfinance debt/cash/revenue are missing.
    """
    if AV_API_KEY == "demo":
        return None
    # AV only covers US-listed; skip exchange-suffixed tickers
    if "." in symbol:
        return None
    start_time = time.time()
    try:
        API_REQUESTS.labels(provider="AlphaVantage").inc()
        r = httpx.get(
            "https://www.alphavantage.co/query",
            params={"function": "OVERVIEW", "symbol": symbol, "apikey": AV_API_KEY},
            timeout=10,
        )
        API_LATENCY.labels(provider="AlphaVantage").observe(time.time() - start_time)
        data = r.json()
        if "Symbol" not in data:
            return None
        def _f(key: str) -> float:
            v = data.get(key)
            return float(v) if v and v != "None" else 0.0
        return {
            "debt":    _f("TotalDebtToTotalEquity"),   # ratio proxy
            "revenue": _f("RevenueTTM"),
            "source":  "AlphaVantage",
        }
    except Exception as e:
        logger.debug(f"Alpha Vantage fundamentals failed for {symbol}: {e}")
        return None


# ── FMP fundamentals ──────────────────────────────────────────────────────────

def _fetch_fmp_fundamentals(symbol: str) -> Optional[Dict[str, float]]:
    """
    Financial Modeling Prep — better global coverage than yfinance for balance sheets.
    Free tier: 250 calls/day. Docs: https://financialmodelingprep.com/developer/docs
    """
    if not FMP_API_KEY:
        return None
    start_time = time.time()
    try:
        API_REQUESTS.labels(provider="FMP").inc()
        bs_resp = httpx.get(
            f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{symbol}",
            params={"limit": 1, "apikey": FMP_API_KEY},
            timeout=10,
        )
        inc_resp = httpx.get(
            f"https://financialmodelingprep.com/api/v3/income-statement/{symbol}",
            params={"limit": 1, "apikey": FMP_API_KEY},
            timeout=10,
        )
        API_LATENCY.labels(provider="FMP").observe(time.time() - start_time)
        bs = bs_resp.json()
        inc = inc_resp.json()
        if not bs or not inc:
            return None
        b, i = bs[0], inc[0]
        return {
            "debt":    float(b.get("totalDebt") or 0),
            "cash":    float(b.get("cashAndCashEquivalents") or 0),
            "revenue": float(i.get("revenue") or 0),
            "source":  "FMP",
        }
    except Exception as e:
        logger.debug(f"FMP fundamentals failed for {symbol}: {e}")
        return None


# ── FMP company profile ───────────────────────────────────────────────────────

def _fetch_fmp_profile(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Financial Modeling Prep profile endpoint — market cap + sector for global tickers.
    Used as fallback when yfinance has no marketCap data (e.g. Gulf/regional exchanges).
    """
    if not FMP_API_KEY:
        return None
    try:
        r = httpx.get(
            f"https://financialmodelingprep.com/api/v3/profile/{symbol}",
            params={"apikey": FMP_API_KEY},
            timeout=10,
        )
        data = r.json()
        if not data:
            return None
        p = data[0]
        mkt_cap = float(p.get("mktCap") or 0)
        if not mkt_cap:
            return None
        return {
            "symbol":            symbol,
            "company_name":      p.get("companyName"),
            "quote_type":        "EQUITY",
            "debt":              0.0,
            "cash":              0.0,
            "revenue":           0.0,
            "prohibited_income": 0.0,
            "mkt_cap":           mkt_cap,
            "sector":            p.get("sector") or p.get("industry") or "Unknown",
            "exchange":          p.get("exchangeShortName", "Unknown"),
            # FMP profile carries no income statement → impure income undeterminable,
            # and no machine slug for the business screen.
            "financials_available": False,
            "industry_key":      "",
            "sector_key":        "",
            "sources":           ["FMP"],
        }
    except Exception as e:
        logger.debug(f"FMP profile failed for {symbol}: {e}")
        return None


# ── Yahoo Finance fundamentals ────────────────────────────────────────────────

def _fetch_yfinance(symbol: str) -> Optional[Dict[str, Any]]:
    start_time = time.time()
    for attempt in range(2):
        try:
            API_REQUESTS.labels(provider="YahooFinance").inc()
            ticker = yf.Ticker(symbol)
            info   = ticker.info
            break  # success
        except Exception as e:
            if attempt == 0 and ("401" in str(e) or "crumb" in str(e).lower() or "Unauthorized" in str(e)):
                logger.warning("yfinance 401 for %s — resetting cookie cache and retrying", symbol)
                try:
                    from yfinance.data import YfData
                    YfData.cache_get.cache_clear()
                    cookie_cache = yf.cache.get_cookie_cache()
                    if cookie_cache is not None:
                        cookie_cache.clear()
                except Exception:
                    pass
                import time as _time
                _time.sleep(2)
                continue
            logger.debug("yfinance fetch failed for %s: %s", symbol, e)
            return None
    else:
        return None
    try:
        API_LATENCY.labels(provider="YahooFinance").observe(time.time() - start_time)

        quote_type = info.get("quoteType", "EQUITY")
        exchange   = info.get("exchange", "NMS")

        if quote_type == "ETF":
            fund_family  = info.get("fundFamily") or ""
            long_name    = info.get("longName") or ""
            total_assets = info.get("totalAssets") or 0
            return {
                "symbol":              symbol,
                "company_name":        long_name or None,
                "quote_type":          "ETF",
                "debt": 0.0, "cash": 0.0, "revenue": 1.0, "prohibited_income": 0.0,
                "mkt_cap":             float(total_assets) if total_assets else 1.0,
                "sector":              f"ETF / {fund_family or 'Unknown Fund Family'}",
                "exchange":            exchange,
                "sources":             ["YahooFinance"],
                "etf_shariah_certified": _is_shariah_etf(fund_family, long_name, symbol),
                "etf_long_name":       long_name,
            }

        mkt_cap = info.get("marketCap")
        if not mkt_cap:
            try:
                fi = ticker.fast_info
                shares = fi.shares
                price = fi.last_price
                if (isinstance(shares, (int, float)) and isinstance(price, (int, float))
                        and shares > 0 and price > 0):
                    mkt_cap = float(shares * price)
            except Exception as e:
                logger.debug("fast_info mkt_cap fallback failed for %s: %s", symbol, e)
        if not mkt_cap:
            return None

        company_name = info.get("longName") or info.get("shortName") or None
        industry = info.get("industry") or "Unknown"
        sector   = info.get("sector") or info.get("industry") or "Unknown"
        # Machine-readable slugs power the business screen (H4): the human-readable
        # sector string does NOT reliably substring-match yfinance's compound labels
        # (e.g. "Alcohol" is absent from "Consumer Defensive / Beverages - Wineries
        # & Distilleries"). industryKey/sectorKey are stable slugs the screen keys off.
        industry_key = (info.get("industryKey") or "").strip().lower()
        sector_key   = (info.get("sectorKey") or "").strip().lower()
        country  = info.get("country") or None
        debt     = float(info.get("totalDebt")    or 0)
        cash     = float(info.get("totalCash")    or 0)
        revenue  = float(info.get("totalRevenue") or 0)

        # yfinance returns marketCap in trading currency but balance sheet
        # (totalDebt/totalCash/totalRevenue) in financialCurrency. For ADRs
        # of foreign companies (e.g. TSM: USD market cap, TWD financials)
        # this inflates ratios by the FX factor. Convert to trading currency.
        trade_ccy = (info.get("currency") or "").upper()
        fin_ccy   = (info.get("financialCurrency") or "").upper()
        if trade_ccy and fin_ccy and trade_ccy != fin_ccy:
            fx = _get_fx_rate(fin_ccy, trade_ccy)
            if fx and fx > 0:
                debt    *= fx
                cash    *= fx
                revenue *= fx
            else:
                logger.warning(
                    "%s: no FX %s→%s — ratios may be wrong, skipping",
                    symbol, fin_ccy, trade_ccy,
                )
                return None
        # Extract interest/non-operating income from financial statements
        # for AAOIFI impure revenue screening (Standard 21)
        interest_income = 0.0
        other_non_operating = 0.0
        interest_bearing_securities = 0.0
        # Determinability flag (M6): the impure-income screen's SOLE source is
        # ticker.financials, which is often empty for IFRS EU filers. A resulting
        # prohibited_income==0 is then indistinguishable from a genuine zero, silently
        # passing the AAOIFI 5% purity gate on MISSING data. Record whether the income
        # statement was actually present so screening can fail closed on absence.
        financials_available = False
        try:
            import math as _math
            _fs = ticker.financials
            if _fs is not None and not _fs.empty:
                financials_available = True
                _col = _fs.iloc[:, 0]
                _ii = _col.get("Interest Income Non Operating") or _col.get("Interest Income")
                if _ii is not None and not (_math.isnan(_ii) if isinstance(_ii, float) else False):
                    interest_income = abs(float(_ii))
                _ono = _col.get("Other Non Operating Income Expenses")
                if _ono is not None and not (_math.isnan(_ono) if isinstance(_ono, float) else False):
                    other_non_operating = abs(float(_ono))
            _bs = ticker.balance_sheet
            if _bs is not None and not _bs.empty:
                _bcol = _bs.iloc[:, 0]
                _afs = _bcol.get("Available For Sale Securities") or _bcol.get("Investmentin Financial Assets")
                if _afs is not None and not (_math.isnan(_afs) if isinstance(_afs, float) else False):
                    interest_bearing_securities = float(_afs)
        except Exception as _e:
            logger.debug("Financial statement extraction failed for %s: %s", symbol, _e)

        prohibited_income = interest_income if interest_income > 0 else other_non_operating

        # Staleness: mostRecentQuarter is a Unix timestamp of latest filing
        mrq = info.get("mostRecentQuarter")
        data_as_of: Optional[str] = None
        if mrq:
            try:
                data_as_of = datetime.fromtimestamp(mrq, tz=timezone.utc).date().isoformat()
            except Exception as e:
                logger.debug("mostRecentQuarter parse failed for %s: %s", symbol, e)

        return {
            "symbol":           symbol,
            "company_name":     company_name,
            "quote_type":       "EQUITY",
            "debt":             debt,
            "cash":             cash,
            "revenue":          revenue,
            "prohibited_income": prohibited_income,
            "mkt_cap":          float(mkt_cap),
            "sector":           f"{sector} / {industry}",
            "country":          country,
            "exchange":         exchange,
            "sources":          ["YahooFinance"],
            "data_as_of":       data_as_of,
            "interest_income":  interest_income,
            "interest_bearing_securities": interest_bearing_securities,
            "financials_available": financials_available,
            "industry_key":     industry_key,
            "sector_key":       sector_key,
        }
    except Exception as e:
        logger.error(f"YahooFinance fetch failed for {symbol}: {e}")
        return None


# ── Morningstar mutual fund data ──────────────────────────────────────────────

def _fetch_morningstar(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Morningstar data for 0P-prefixed fund IDs (mutual funds not covered by yfinance).
    Uses Morningstar category classification (e.g. "Islamic Equity") as compliance signal —
    more reliable than name-check because Morningstar assigns categories from fund mandate docs.
    """
    if not symbol.upper().startswith("0P"):
        return None
    try:
        import mstarpy  # optional dep — only needed for mutual funds
        f = mstarpy.Funds(term=symbol)
        meta = f.metaData()
        snap = f.snapshot()

        name = meta.get("name") or symbol
        isin = meta.get("isin")
        domicile = meta.get("domicileCountryId", "Unknown")

        # Morningstar category is the authoritative Islamic signal (assigned from mandate docs)
        category = ""
        try:
            pi = f.productInvolvement()
            category = pi.get("categoryName", "")
        except Exception as e:
            logger.debug("Morningstar productInvolvement failed for %s: %s", symbol, e)

        benchmark = meta.get("primaryProspectusBenchmarkIndex") or ""

        is_islamic = (
            "islamic" in category.lower()
            or "shariah" in category.lower()
            or "shariah" in benchmark.lower()
            or "islamic" in benchmark.lower()
        )

        # AUM (EUR NAV) as market-cap proxy
        aum = 0.0
        for nav in snap.get("NetAssetValues", []):
            v = nav.get("DayEndValue") or nav.get("MonthEndValue")
            if v:
                aum = float(v)
                break

        return {
            "symbol":                symbol,
            "company_name":          name,
            "quote_type":            "MUTUALFUND",
            "debt": 0.0, "cash": 0.0, "revenue": 1.0, "prohibited_income": 0.0,
            "mkt_cap":               aum if aum > 0 else 1.0,
            "sector":                category or "Unknown",
            "exchange":              domicile,
            "sources":               ["Morningstar"],
            "fund_shariah_certified": is_islamic,
            "fund_long_name":        name,
            "fund_category":         category,
            "isin":                  isin,
        }
    except Exception as e:
        logger.debug(f"Morningstar fetch failed for {symbol}: {e}")
        return None


# ── Public interface ──────────────────────────────────────────────────────────

def fetch_shariah_verdict(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Try dedicated Shariah APIs first (Zoya → Musaffa).
    Returns {compliant, doubtful, purification_pct, sources} or None.
    """
    symbol = normalize_ticker(symbol)
    sources = []
    verdict = None

    zoya = _fetch_zoya(symbol)
    if zoya:
        sources.append("Zoya")
        verdict = zoya

    musaffa = _fetch_musaffa(symbol)
    if musaffa:
        sources.append("Musaffa")
        if verdict is None:
            verdict = musaffa
        else:
            # Both available: mark doubtful if they disagree
            if verdict["compliant"] != musaffa["compliant"]:
                verdict = {**verdict, "compliant": False, "doubtful": True,
                           "status": "DOUBTFUL (sources disagree)"}

    if verdict:
        verdict["sources"] = sources
    return verdict


def fetch_financial_data(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch fundamental data for AAOIFI ratio calculation.
    Cascade: YahooFinance → Morningstar (0P funds) → FMP (if missing) → AlphaVantage (US only, if missing).
    """
    symbol = normalize_ticker(symbol)
    base   = _fetch_yfinance(symbol)

    if base is None:
        mstar = _fetch_morningstar(symbol)
        if mstar:
            return mstar
        fmp = _fetch_fmp_profile(symbol)
        if fmp:
            bs = _fetch_fmp_fundamentals(symbol)
            if bs:
                fmp["debt"] = bs["debt"]
                fmp["cash"] = bs.get("cash", 0.0)
                fmp["revenue"] = bs["revenue"]
            return fmp
        return None

    if base.get("quote_type") == "ETF":
        return base

    sources = list(base["sources"])

    # Supplement missing or zero ratio data from FMP or Alpha Vantage
    # Many ex-US markets in yfinance return marketCap but 0 for totalDebt/totalCash
    if (base["revenue"] == 0 or base["debt"] == 0 or base["cash"] == 0) and not base.get("quote_type") == "ETF":
        fmp = _fetch_fmp_fundamentals(symbol)
        if fmp:
            if base["debt"] == 0:
                base["debt"] = fmp["debt"]
            if base["cash"] == 0:
                base["cash"] = fmp.get("cash", 0.0)
            if base["revenue"] == 0:
                base["revenue"] = fmp["revenue"]
            if fmp["source"] not in sources:
                sources.append(fmp["source"])
        elif "." not in symbol:  # US ticker — try AV fallback for revenue/debt
            av = _fetch_av_fundamentals(symbol)
            if av:
                if base["revenue"] == 0 and av.get("revenue", 0) > 0:
                    base["revenue"] = av["revenue"]
                if base["debt"] == 0 and av.get("debt", 0) > 0:
                    base["debt"] = av["debt"]
                if av["source"] not in sources:
                    sources.append(av["source"])

    base["sources"] = sources
    return base


def search_symbol(q: str, max_results: int = 8) -> list[Dict[str, Any]]:
    """Return [{symbol, company_name, exchange, type}] matching query string."""
    try:
        results = yf.Search(q, max_results=max_results)
        out = []
        for item in results.quotes:
            symbol = item.get("symbol", "")
            if not symbol:
                continue
            out.append({
                "symbol":       symbol,
                "company_name": item.get("longname") or item.get("shortname") or symbol,
                "exchange":     item.get("exchDisp") or item.get("exchange") or "",
                "type":         item.get("typeDisp") or item.get("quoteType") or "equity",
            })
        return out
    except Exception as e:
        logger.error(f"Symbol search failed for '{q}': {e}")
        return []
