from datetime import datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo
from typing import Optional

# yfinance exchange code -> (IANA timezone, [(open, close), ...], ibkr_exchange, currency)
# Multiple sessions = lunch break markets (Japan, China, HK)
EXCHANGE_CONFIG = {
    # United States
    "NMS":  ("America/New_York",      [(time(9,30),  time(16,0))],              "SMART",  "USD"),
    "NYQ":  ("America/New_York",      [(time(9,30),  time(16,0))],              "SMART",  "USD"),
    "PCX":  ("America/New_York",      [(time(9,30),  time(16,0))],              "SMART",  "USD"),
    "NGM":  ("America/New_York",      [(time(9,30),  time(16,0))],              "SMART",  "USD"),
    # Japan (TSE lunch 11:30-12:30) — yfinance returns "JPX" for .T symbols
    "TKS":  ("Asia/Tokyo",            [(time(9,0),   time(11,30)), (time(12,30), time(15,30))], "TSEJ", "JPY"),
    "OSA":  ("Asia/Tokyo",            [(time(9,0),   time(11,30)), (time(12,30), time(15,30))], "TSEJ", "JPY"),
    "JPX":  ("Asia/Tokyo",            [(time(9,0),   time(11,30)), (time(12,30), time(15,30))], "TSEJ", "JPY"),
    # China Shanghai (lunch 11:30-13:00)
    "SHH":  ("Asia/Shanghai",         [(time(9,30),  time(11,30)), (time(13,0),  time(15,0))],  "SEHKNTL", "CNY"),
    # China Shenzhen (lunch 11:30-13:00)
    "SHZ":  ("Asia/Shanghai",         [(time(9,30),  time(11,30)), (time(13,0),  time(15,0))],  "SEHKSZSE", "CNY"),
    # Hong Kong (lunch 12:00-13:00)
    "HKG":  ("Asia/Hong_Kong",        [(time(9,30),  time(12,0)),  (time(13,0),  time(16,0))],  "SEHK",   "HKD"),
    # South Korea
    "KSC":  ("Asia/Seoul",            [(time(9,0),   time(15,30))],             "KSE",    "KRW"),
    "KOE":  ("Asia/Seoul",            [(time(9,0),   time(15,30))],             "KSE",    "KRW"),
    # Taiwan
    "TAI":  ("Asia/Taipei",           [(time(9,0),   time(13,30))],             "TSEM",   "TWD"),
    # Singapore
    "SGX":  ("Asia/Singapore",        [(time(9,0),   time(17,0))],              "SGX",    "SGD"),
    # Malaysia (Bursa)
    "KLS":  ("Asia/Kuala_Lumpur",     [(time(9,0),   time(17,0))],              "BURSA",  "MYR"),
    # India
    "BSE":  ("Asia/Kolkata",          [(time(9,15),  time(15,30))],             "NSE",    "INR"),
    "NSI":  ("Asia/Kolkata",          [(time(9,15),  time(15,30))],             "NSE",    "INR"),
    # Indonesia
    "JKT":  ("Asia/Jakarta",          [(time(9,0),   time(16,15))],             "IDX",    "IDR"),
    # Saudi Arabia (Tadawul) — Sun-Thu
    "SAU":  ("Asia/Riyadh",           [(time(10,0),  time(15,0))],              "MSE",    "SAR"),
    # UAE (DFM/ADX) — Sun-Thu
    "DFM":  ("Asia/Dubai",            [(time(10,0),  time(14,0))],              "IBIS",   "AED"),
    # United Kingdom
    "LSE":  ("Europe/London",         [(time(8,0),   time(16,30))],             "LSE",    "GBP"),
    # Netherlands / Euronext Amsterdam — yfinance returns "AMS" for .AS symbols
    "AMS":  ("Europe/Amsterdam",      [(time(9,0),   time(17,30))],             "AEB",    "EUR"),
    # Germany (Xetra)
    "GER":  ("Europe/Berlin",         [(time(9,0),   time(17,30))],             "IBIS",   "EUR"),
    "XET":  ("Europe/Berlin",         [(time(9,0),   time(17,30))],             "IBIS",   "EUR"),
    # France (Euronext Paris)
    "PAR":  ("Europe/Paris",          [(time(9,0),   time(17,30))],             "SBF",    "EUR"),
    # Italy (Borsa Italiana / Euronext Milan)
    "MIL":  ("Europe/Rome",           [(time(9,0),   time(17,30))],             "BVME",   "EUR"),
    "BIT":  ("Europe/Rome",           [(time(9,0),   time(17,30))],             "BVME",   "EUR"),
    # Spain (BME / Bolsa de Madrid)
    "MCE":  ("Europe/Madrid",         [(time(9,0),   time(17,30))],             "BM",     "EUR"),
    "MAD":  ("Europe/Madrid",         [(time(9,0),   time(17,30))],             "BM",     "EUR"),
    # Switzerland (SIX)
    "EBS":  ("Europe/Zurich",         [(time(9,0),   time(17,30))],             "EBS",    "CHF"),
    "SWX":  ("Europe/Zurich",         [(time(9,0),   time(17,30))],             "EBS",    "CHF"),
    "VTX":  ("Europe/Zurich",         [(time(9,0),   time(17,30))],             "EBS",    "CHF"),
    # Sweden (Nasdaq Stockholm)
    "STO":  ("Europe/Stockholm",      [(time(9,0),   time(17,30))],             "SFB",    "SEK"),
    # Norway (Oslo Børs)
    "OSL":  ("Europe/Oslo",           [(time(9,0),   time(16,30))],             "OSE",    "NOK"),
    # Denmark (Nasdaq Copenhagen)
    "CPH":  ("Europe/Copenhagen",     [(time(9,0),   time(17,0))],              "CPH",    "DKK"),
    # Finland (Nasdaq Helsinki)
    "HEL":  ("Europe/Helsinki",       [(time(10,0),  time(18,30))],             "HEX",    "EUR"),
    # Belgium (Euronext Brussels)
    "BRU":  ("Europe/Brussels",       [(time(9,0),   time(17,30))],             "ENEXT.BE", "EUR"),
    # Austria (Wiener Börse)
    "VIE":  ("Europe/Vienna",         [(time(9,0),   time(17,30))],             "VSE",    "EUR"),
    # Portugal (Euronext Lisbon)
    "LIS":  ("Europe/Lisbon",         [(time(8,0),   time(16,30))],             "BVL",    "EUR"),
    # Greece (Athens Exchange)
    "ATH":  ("Europe/Athens",         [(time(10,15), time(17,20))],             "ATH",    "EUR"),
    # Ireland (Euronext Dublin)
    "ISE":  ("Europe/Dublin",         [(time(8,0),   time(16,30))],             "ISED",   "EUR"),

    # Canada (TSX + TSX Venture)
    "TOR":  ("America/Toronto",       [(time(9,30),  time(16,0))],              "TSE",    "CAD"),
    "TSX":  ("America/Toronto",       [(time(9,30),  time(16,0))],              "TSE",    "CAD"),
    "VAN":  ("America/Toronto",       [(time(9,30),  time(16,0))],              "VENTURE","CAD"),
    # Mexico (BMV)
    "MEX":  ("America/Mexico_City",   [(time(8,30),  time(15,0))],              "MEXI",   "MXN"),
    # Brazil (B3)
    "SAO":  ("America/Sao_Paulo",     [(time(10,0),  time(17,0))],              "BOVESPA","BRL"),

    # Australia (ASX)
    "ASX":  ("Australia/Sydney",      [(time(10,0),  time(16,0))],              "ASX",    "AUD"),
    # New Zealand (NZX)
    "NZE":  ("Pacific/Auckland",      [(time(10,0),  time(16,45))],             "NZX",    "NZD"),

    # South Africa (JSE)
    "JNB":  ("Africa/Johannesburg",   [(time(9,0),   time(17,0))],              "JSE",    "ZAR"),
    # Egypt (EGX) — Sun-Thu
    "CAI":  ("Africa/Cairo",          [(time(10,0),  time(14,30))],             "EGX",    "EGP"),

    # Turkey (Borsa Istanbul)
    "IST":  ("Europe/Istanbul",       [(time(10,0),  time(18,0))],              "BIST",   "TRY"),
    # Qatar (QSE) — Sun-Thu
    "DOH":  ("Asia/Qatar",            [(time(9,30),  time(13,15))],             "QSE",    "QAR"),
    # Kuwait (Boursa Kuwait) — Sun-Thu
    "KWT":  ("Asia/Kuwait",           [(time(9,30),  time(12,30))],             "KSE",    "KWD"),
    # Pakistan (PSX)
    "KAR":  ("Asia/Karachi",          [(time(9,30),  time(15,30))],             "KSE",    "PKR"),

    # Thailand (SET) — lunch 12:30-14:30
    "SET":  ("Asia/Bangkok",          [(time(10,0),  time(12,30)), (time(14,30), time(16,30))], "SET", "THB"),
    "BKK":  ("Asia/Bangkok",          [(time(10,0),  time(12,30)), (time(14,30), time(16,30))], "SET", "THB"),
    # Philippines (PSE) — lunch 12:00-13:30
    "PHS":  ("Asia/Manila",           [(time(9,30),  time(12,0)), (time(13,30),  time(15,30))], "PSE", "PHP"),
    "PHP":  ("Asia/Manila",           [(time(9,30),  time(12,0)), (time(13,30),  time(15,30))], "PSE", "PHP"),
    # Vietnam (HOSE) — lunch 11:30-13:00
    "VNM":  ("Asia/Ho_Chi_Minh",      [(time(9,0),   time(11,30)), (time(13,0),  time(15,0))], "HOSE", "VND"),
    "HSX":  ("Asia/Ho_Chi_Minh",      [(time(9,0),   time(11,30)), (time(13,0),  time(15,0))], "HOSE", "VND"),
}

# Gulf/MENA exchanges trade Sun-Thu instead of Mon-Fri
SUNDAY_THURSDAY_EXCHANGES = {"SAU", "DFM", "DOH", "KWT", "CAI"}

DEFAULT_CONFIG = ("America/New_York", [(time(9,30), time(16,0))], "SMART", "USD")

# Map yfinance exchange code → exchange_calendars ISO MIC for holiday lookup.
# Missing entries fall back to weekday-only check (no holiday filtering).
_EXCHANGE_TO_CALENDAR: dict = {
    "NMS": "XNYS", "NYQ": "XNYS", "PCX": "XNYS", "NGM": "XNYS",
    "TKS": "XTKS", "OSA": "XTKS", "JPX": "XTKS",
    "SHH": "XSHG", "SHZ": "XSHE",
    "HKG": "XHKG",
    "KSC": "XKRX", "KOE": "XKRX",
    "TAI": "XTAI",
    "SGX": "XSES",
    "BSE": "XBOM", "NSI": "XNSE",
    "JKT": "XIDX",
    "SAU": "XSAU",
    "LSE": "XLON",
    "AMS": "XAMS",
    "GER": "XETR", "XET": "XETR",
    "PAR": "XPAR",
    "MIL": "XMIL",
    "MCE": "XMAD",
    "EBS": "XSWX",
    "STO": "XSTO",
    "OSL": "XOSL",
    "CPH": "XCSE",
    "HEL": "XHEL",
    "BRU": "XBRU",
    "VIE": "XWBO",
    "LIS": "XLIS",
    "ATH": "XATH",
    "ISE": "XDUB",
    "TOR": "XTSE",
    "MEX": "XMEX",
    "SAO": "BVMF",
    "ASX": "XASX",
    "NZE": "XNZE",
    "JNB": "XJSE",
    "IST": "XIST",
}


def get_exchange_config(exchange_code: str) -> tuple:
    return EXCHANGE_CONFIG.get(exchange_code, DEFAULT_CONFIG)


@lru_cache(maxsize=64)
def _get_calendar(cal_code: str):
    """Cached exchange_calendars.get_calendar — calendar construction is expensive."""
    try:
        from exchange_calendars import get_calendar
        return get_calendar(cal_code)
    except Exception:
        return None


def is_trading_day(exchange_code: str, day=None) -> bool:
    """True if `day` is a regular session for the exchange (weekend AND holidays filtered).
    Falls back to weekday-only check if no calendar mapping or exchange_calendars unavailable."""
    tz_name, _, _, _ = get_exchange_config(exchange_code)
    if day is None:
        day = datetime.now(ZoneInfo(tz_name)).date()

    cal_code = _EXCHANGE_TO_CALENDAR.get(exchange_code)
    if cal_code is not None:
        cal = _get_calendar(cal_code)
        if cal is not None:
            try:
                import pandas as pd
                return bool(cal.is_session(pd.Timestamp(day)))
            except Exception:
                pass

    # Fallback: weekday-only
    if exchange_code in SUNDAY_THURSDAY_EXCHANGES:
        return day.weekday() in (0, 1, 2, 3, 6)
    return day.weekday() < 5


def is_market_open(exchange_code: str = "NMS") -> bool:
    tz_name, sessions, _, _ = get_exchange_config(exchange_code)
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)

    if not is_trading_day(exchange_code, now.date()):
        return False

    return any(open_ <= now.time() < close for open_, close in sessions)


def is_in_trading_window(
    exchange_code: str = "NMS",
    start_offset_min: int = 30,
    end_offset_min: int = 30,
) -> bool:
    """Returns True if market is open AND we're past the open/close buffer windows.
    Avoids low-liquidity first/last 30 min of the session."""
    from datetime import timedelta

    tz_name, sessions, _, _ = get_exchange_config(exchange_code)
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)

    if not is_trading_day(exchange_code, now.date()):
        return False

    for open_, close in sessions:
        open_dt = now.replace(hour=open_.hour, minute=open_.minute, second=0, microsecond=0)
        close_dt = now.replace(hour=close.hour, minute=close.minute, second=0, microsecond=0)
        window_start = (open_dt + timedelta(minutes=start_offset_min)).time()
        window_end = (close_dt - timedelta(minutes=end_offset_min)).time()
        if window_start <= now.time() < window_end:
            return True
    return False


# yfinance ticker suffix → EXCHANGE_CONFIG key
_SUFFIX_TO_EXCHANGE: dict = {
    "TO": "TOR", "V": "VAN", "MX": "MEX", "SA": "SAO",
    "L": "LSE", "DE": "GER", "PA": "PAR", "AS": "AMS",
    "SW": "EBS", "MI": "MIL", "MC": "MCE", "ST": "STO",
    "OL": "OSL", "CO": "CPH", "HE": "HEL", "BR": "BRU",
    "VI": "VIE", "LS": "LIS", "AT": "ATH", "IR": "ISE",
    "AX": "ASX", "NZ": "NZE", "JO": "JNB", "CA": "CAI",
    "IS": "IST", "QA": "DOH", "KW": "KWT", "KA": "KAR",
    "SR": "SAU", "AE": "DFM", "T": "TKS", "HK": "HKG",
    "SS": "SHH", "SZ": "SHZ", "KS": "KSC", "KQ": "KSC",
    "TW": "TAI", "TWO": "TAI", "SI": "SGX", "KL": "KLS",
    "NS": "BSE", "BO": "BSE", "JK": "JKT", "BK": "SET",
    "PS": "PHS", "VN": "VNM",
}


def infer_exchange_from_symbol(symbol: str) -> str:
    """yfinance suffix → exchange code. No suffix → NMS (US)."""
    if "." in symbol:
        suffix = symbol.rsplit(".", 1)[1].upper()
        return _SUFFIX_TO_EXCHANGE.get(suffix, "NMS")
    return "NMS"


def any_market_open(exchange_codes: Optional[list] = None) -> bool:
    """True if any tracked exchange is open. Used to gate global discovery."""
    if exchange_codes is None:
        exchange_codes = list(EXCHANGE_CONFIG.keys())
    return any(is_market_open(code) for code in exchange_codes)


def market_status(exchange_code: str = "NMS") -> dict:
    tz_name, sessions, ibkr_exchange, currency = get_exchange_config(exchange_code)
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    open_ = is_market_open(exchange_code)
    return {
        "exchange": exchange_code,
        "ibkr_exchange": ibkr_exchange,
        "currency": currency,
        "timezone": tz_name,
        "local_time": now.strftime("%a %H:%M"),
        "is_open": open_,
        "sessions": [f"{o.strftime('%H:%M')}-{c.strftime('%H:%M')}" for o, c in sessions],
    }
