import asyncio
import json
import os
import time
import logging
from datetime import date, timedelta
from pathlib import Path
from threading import Lock
from dotenv import load_dotenv
from ibkr_core.features.compliance.schemas import ComplianceStatus, SourceResult
from ibkr_core.features.compliance.data_fetcher import (
    fetch_financial_data,
    fetch_shariah_verdict,
    normalize_ticker,
    GOLD_ETC_ALLOWLIST,
    SHARIAH_ETF_ALLOWLIST,
)
from ibkr_core.features.settings.service import load_settings as _load_settings
from ibkr_core.core.market_hours import infer_exchange_from_symbol
from ibkr_core.core.clock import utc_today

logger = logging.getLogger(__name__)

load_dotenv()

_STALENESS_DAYS = int(os.getenv("COMPLIANCE_STALENESS_DAYS", 90))
_MANUAL_VERIFY_TTL_DAYS = int(os.getenv("MANUAL_VERIFY_TTL_DAYS", 90))

_screen_cache: dict[str, tuple["ComplianceStatus", float]] = {}
_cache_lock = Lock()
_CACHE_TTL_SECONDS = 86400  # 24 hours

# ── AAOIFI Shari'ah Standard No. 21 — canonical thresholds (see COMPLIANCE.md §1) ──
# A symbol fails if any ratio reaches its threshold. The VIX ratio_buffer only tightens
# these (subtracts pp), never loosens. 30% is AAOIFI; 33% is Dow Jones Islamic / S&P.
AAOIFI_DEBT_MAX = 0.30       # interest-based debt / market cap
AAOIFI_LIQUIDITY_MAX = 0.30  # (cash + interest-bearing securities) / market cap  [COMBINED]
AAOIFI_IMPURE_MAX = 0.05     # prohibited income / total revenue

_DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
_MANUAL_FILE = _DATA_DIR / "manual_compliance.json"


def _load_manual_verifications() -> dict:
    try:
        if _MANUAL_FILE.exists():
            return json.loads(_MANUAL_FILE.read_text())
    except Exception as e:
        logger.debug("Failed to load manual_compliance.json: %s", e)
    return {}


def _save_manual_verifications(data: dict) -> None:
    _MANUAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MANUAL_FILE.write_text(json.dumps(data, indent=2))


def manual_verify(symbol: str, source: str = "Zoya App", note: str = "",
                  ttl_days: int | None = None) -> dict:
    """Mark a symbol as manually verified halal. Returns the entry."""
    data = _load_manual_verifications()
    ttl = ttl_days if ttl_days is not None else _MANUAL_VERIFY_TTL_DAYS
    entry = {
        "status": "COMPLIANT",
        "source": source,
        "note": note,
        "verified_at": utc_today().isoformat(),
        "expires_at": (utc_today() + timedelta(days=ttl)).isoformat(),
    }
    data[symbol.upper()] = entry
    _save_manual_verifications(data)
    _invalidate_cache(symbol)
    return entry


def manual_unverify(symbol: str) -> bool:
    """Remove manual verification for a symbol."""
    data = _load_manual_verifications()
    if symbol.upper() in data:
        del data[symbol.upper()]
        _save_manual_verifications(data)
        _invalidate_cache(symbol)
        return True
    return False


def list_manual_verifications() -> dict:
    """Return all manual verifications with expiry status."""
    data = _load_manual_verifications()
    today = utc_today()
    for sym, entry in data.items():
        try:
            exp = date.fromisoformat(entry["expires_at"])
            entry["expired"] = today > exp
            entry["days_remaining"] = (exp - today).days
        except (KeyError, ValueError):
            entry["expired"] = True
            entry["days_remaining"] = 0
    return data


def _check_manual_verification(symbol: str) -> ComplianceStatus | None:
    """Check if symbol has a valid (non-expired) manual verification."""
    data = _load_manual_verifications()
    sym = symbol.strip().upper().split(".")[0]
    entry = data.get(sym)
    if not entry:
        return None
    try:
        expires = date.fromisoformat(entry["expires_at"])
        if utc_today() > expires:
            logger.info("Manual verification expired for %s (was %s)", sym, entry["expires_at"])
            return None
    except (KeyError, ValueError):
        return None
    days_left = (expires - utc_today()).days
    return ComplianceStatus(
        symbol=symbol, sector="Manual",
        is_compliant=True, verdict="COMPLIANT",
        debt_to_mkt_cap=0.0, cash_to_mkt_cap=0.0, impure_revenue_pct=0.0,
        reason=None,
        data_source=f"Manual ({entry.get('source', 'user')})",
        sources_detail=[SourceResult(
            source="Manual", verdict="COMPLIANT",
            note=f"Verified via {entry.get('source', 'user')} on {entry['verified_at']}. "
                 f"Expires {entry['expires_at']} ({days_left}d remaining). {entry.get('note', '')}".strip(),
        )],
    )


def _invalidate_cache(symbol: str) -> None:
    with _cache_lock:
        for key in list(_screen_cache.keys()):
            if symbol.upper() in key.upper():
                del _screen_cache[key]

_PROHIBITED_SECTORS = {
    "Conventional Finance", "Conventional Insurance", "Alcohol", "Tobacco",
    "Gambling", "Adult Content", "Pork", "Defense", "Weapons",
    "Entertainment", "Interest-bearing",
}

# ── Prohibited business slugs (H4) ────────────────────────────────────────────
# The human-readable sector string does NOT reliably substring-match yfinance's
# compound labels ("Alcohol" ∉ "Consumer Defensive / Beverages - Wineries &
# Distilleries"; "Gambling" ∉ "Resorts & Casinos"; "Conventional Finance" ∉
# "Banks - Regional"). We therefore key the business screen off yfinance's stable
# machine slugs (industryKey/sectorKey). Non-alcoholic beverages
# ("beverages-non-alcoholic", Coca-Cola/Pepsi) are intentionally NOT listed.
_PROHIBITED_INDUSTRY_SLUGS = frozenset({
    # Alcohol
    "beverages-wineries-distilleries", "beverages-brewers",
    # Gambling
    "gambling", "resorts-casinos",
    # Tobacco
    "tobacco",
    # Conventional (riba-based) finance — non-bank
    "capital-markets", "credit-services", "mortgage-finance",
    "financial-conglomerates",
})
# Any industryKey under these prefixes is conventional interest-based finance
# (banks-regional/banks-diversified/…; insurance-life/insurance-property-casualty/…).
_PROHIBITED_SLUG_PREFIXES = ("banks-", "insurance-")

# Tickers intentionally seeded as Shariah-native institutions (fully Islamic banks)
# that would otherwise trip the banks-* slug block. They still undergo the full
# AAOIFI ratio screen — only the business-slug exclusion is waived for them.
_SECTOR_SLUG_EXEMPT_TICKERS = frozenset({
    "1120.SR",  # Al Rajhi Bank — world's largest Islamic bank
    "1180.SR",  # Alinma Bank — Shariah-compliant by charter
})


def _sector_haystack(sector: str) -> str:
    """Lower-cased sector text for human substring matching, with the "non-alcoholic"
    token stripped so the "Alcohol" keyword doesn't false-match "Beverages -
    Non-Alcoholic" (Coca-Cola/Pepsi). A genuine "Alcohol"/"Alcoholic" label still matches."""
    return sector.lower().replace("non-alcoholic", "").replace("nonalcoholic", "")


def _industry_slug_prohibited(industry_key: str | None, sector_key: str | None) -> bool:
    """True if a yfinance industryKey/sectorKey slug denotes a prohibited business."""
    for key in (industry_key, sector_key):
        if not key:
            continue
        k = key.strip().lower()
        if k in _PROHIBITED_INDUSTRY_SLUGS:
            return True
        if any(k.startswith(p) for p in _PROHIBITED_SLUG_PREFIXES):
            return True
    return False


def check_shariah_compliance(
    symbol: str,
    debt: float,
    cash: float,
    revenue: float,
    prohibited_income: float,
    mkt_cap: float,
    sector: str,
    ratio_buffer: float = 0.0,
    extra_excluded_sectors: list[str] = [],
    interest_bearing_securities: float = 0.0,
    industry_key: str = "",
    sector_key: str = "",
) -> ComplianceStatus:
    """AAOIFI Standard 21 ratio screen (see COMPLIANCE.md §1).

    Liquidity screen B is COMBINED: (cash + interest_bearing_securities) / mkt_cap
    against a single 30% limit — not two separate gates. `cash_to_mkt_cap` in the
    returned status therefore carries this combined liquidity ratio.
    """
    reasons = []
    ratio_buffer = max(0.0, ratio_buffer)  # a negative buffer must never LOOSEN thresholds
    # Fail-closed on undeterminable data (COMPLIANCE.md §1): a positive market cap but
    # missing fundamentals must BLOCK, not pass all-zero ratios as COMPLIANT.
    if mkt_cap <= 0:
        reasons.append("Undeterminable: market cap <= 0")
    if revenue <= 0:
        reasons.append("Undeterminable: revenue data missing (cannot screen impure income)")
    # Fail-closed on undeterminable balance sheet (M5). yfinance frequently returns
    # totalDebt=None→0 for thin EU coverage while cash is present, so requiring ALL of
    # debt/cash/ibs to be 0 lets debt==0 pass the most important AAOIFI gate on MISSING
    # data. Fail closed on debt<=0 alone, and close the symmetric liquidity hole.
    # Genuinely debt-free firms are whitelisted via the manual_verify path.
    if debt <= 0:
        reasons.append("Undeterminable: debt data missing (totalDebt<=0 — cannot verify AAOIFI debt screen)")
    if cash <= 0 and interest_bearing_securities <= 0:
        reasons.append("Undeterminable: liquidity data missing (cash+interest-bearing all 0)")
    effective_sectors = _PROHIBITED_SECTORS | set(extra_excluded_sectors)
    _sector_hay = _sector_haystack(sector)
    for ps in effective_sectors:
        if ps.lower() in _sector_hay:
            reasons.append(f"Prohibited sector: {sector}")
            break
    # Business screen via yfinance machine slugs (H4) — the human substring loop
    # above misses compound labels. Islamic-native institutions are exempted.
    if symbol.strip().upper() not in _SECTOR_SLUG_EXEMPT_TICKERS and \
            _industry_slug_prohibited(industry_key, sector_key):
        reasons.append(f"Prohibited sector (slug): {industry_key or sector_key}")

    debt_ratio      = debt / mkt_cap if mkt_cap > 0 else 0.0
    liquidity_ratio = (cash + interest_bearing_securities) / mkt_cap if mkt_cap > 0 else 0.0
    revenue_ratio   = prohibited_income / revenue if revenue > 0 else 0.0

    debt_threshold      = AAOIFI_DEBT_MAX - ratio_buffer / 100
    liquidity_threshold = AAOIFI_LIQUIDITY_MAX - ratio_buffer / 100
    # Floor the impure threshold so a crisis VIX buffer (5pp) can't drive the 5% limit
    # to 0 and block every name via imp_r >= 0.0.
    impure_threshold    = max(0.005, AAOIFI_IMPURE_MAX - ratio_buffer / 100)

    if debt_ratio >= debt_threshold:
        reasons.append(f"Debt ratio ({debt_ratio:.2%}) >= {debt_threshold:.0%}")
    if liquidity_ratio >= liquidity_threshold:
        reasons.append(f"Liquidity ratio ({liquidity_ratio:.2%}) >= {liquidity_threshold:.0%} (cash+interest-bearing)")
    if revenue_ratio >= impure_threshold:
        reasons.append(f"Prohibited income ({revenue_ratio:.2%}) >= {impure_threshold:.0%}")

    return ComplianceStatus(
        symbol=symbol, sector=sector,
        is_compliant=len(reasons) == 0,
        debt_to_mkt_cap=debt_ratio,
        cash_to_mkt_cap=liquidity_ratio,
        impure_revenue_pct=revenue_ratio,
        reason="; ".join(reasons) if reasons else None,
    )


def _live_shariah_screen_uncached(symbol: str, ratio_buffer_override: float | None = None) -> ComplianceStatus:
    try:
        sources_detail: list[SourceResult] = []
        settings = _load_settings()
        ratio_buffer: float = settings.get("ratio_buffer", 0.0)
        if ratio_buffer_override is not None:
            ratio_buffer = max(ratio_buffer, ratio_buffer_override)
        ratio_buffer = max(0.0, ratio_buffer)  # a negative buffer must never LOOSEN thresholds
        extra_excluded_sectors: list[str] = settings.get("sector_exclusion", [])

        # ── Static allowlists — short-circuit before any network call ─────────────
        normalized = normalize_ticker(symbol)
        sym_upper = symbol.strip().upper()
        if normalized in GOLD_ETC_ALLOWLIST or sym_upper in GOLD_ETC_ALLOWLIST:
            sources_detail.append(SourceResult(
                source="Allowlist", verdict="COMPLIANT",
                note="Physical gold ETC — fully allocated, no leverage, spot-settled. "
                     "Halal per AAOIFI Shari'ah Standard No. 57 and OIC Fiqh Academy Resolution 153 (2006).",
            ))
            return ComplianceStatus(
                symbol=symbol, sector="Commodity-Gold",
                is_compliant=True, verdict="COMPLIANT",
                debt_to_mkt_cap=0.0, cash_to_mkt_cap=0.0, impure_revenue_pct=0.0,
                reason=None, data_source="Allowlist",
                exchange=infer_exchange_from_symbol(normalized),
                sources_detail=sources_detail,
            )
        if normalized in SHARIAH_ETF_ALLOWLIST or sym_upper in SHARIAH_ETF_ALLOWLIST:
            sources_detail.append(SourceResult(
                source="Allowlist", verdict="COMPLIANT",
                note="Shariah-certified ETF — fund mandates AAOIFI/MSCI Islamic screening. "
                     "Verified against fund prospectus and Shariah board certification.",
            ))
            return ComplianceStatus(
                symbol=symbol, sector="Shariah-ETF",
                is_compliant=True, verdict="COMPLIANT",
                debt_to_mkt_cap=0.0, cash_to_mkt_cap=0.0, impure_revenue_pct=0.0,
                reason=None, data_source="Allowlist",
                exchange=infer_exchange_from_symbol(normalized),
                sources_detail=sources_detail,
            )

        # ── Manual verification — user-confirmed halal with TTL ──────────────────
        manual_result = _check_manual_verification(symbol)
        if manual_result is not None:
            return manual_result

        # ── Step 1: dedicated Shariah APIs (Zoya, Musaffa) ────────────────────────
        verdict = fetch_shariah_verdict(symbol)
        for src in (verdict or {}).get("sources", []):
            v = "COMPLIANT" if verdict["compliant"] else ("DOUBTFUL" if verdict.get("doubtful") else "NON_COMPLIANT")
            sources_detail.append(SourceResult(source=src, verdict=v))

        # ── Step 2: financial data for ratios ─────────────────────────────────────
        financial_data = fetch_financial_data(symbol)

        if not financial_data:
            sources_detail.append(SourceResult(
                source="YahooFinance", verdict="ERROR",
                note="Failed to fetch — symbol may be delisted or unsupported by yfinance (e.g. ADX/DFM/Gulf markets)"
            ))
            if verdict:
                # Financial data unavailable but Zoya/Musaffa gave verdict — return it
                is_compliant = verdict["compliant"] and not verdict.get("doubtful")
                v = "COMPLIANT" if is_compliant else ("DOUBTFUL" if verdict.get("doubtful") else "NON_COMPLIANT")
                return ComplianceStatus(
                    symbol=symbol, sector="Unknown",
                    is_compliant=is_compliant, verdict=v,
                    debt_to_mkt_cap=0.0, cash_to_mkt_cap=0.0, impure_revenue_pct=0.0,
                    reason=verdict.get("status") if not is_compliant else "Compliant per Zoya/Musaffa (no ratio data available for this exchange)",
                    data_source="+".join(verdict["sources"]),
                    exchange="Unknown",
                    sources_detail=sources_detail,
                )
            # No financial data, no Shariah verdict — cannot verify, block trading
            sources_detail.append(SourceResult(
                source="System", verdict="UNKNOWN",
                note="No data source could provide financial or Shariah verdict for this symbol"
            ))
            return ComplianceStatus(
                symbol=symbol, sector="Unknown",
                is_compliant=False, verdict="UNKNOWN",
                debt_to_mkt_cap=0.0, cash_to_mkt_cap=0.0, impure_revenue_pct=0.0,
                reason="Cannot verify compliance — no financial data or Shariah verdict available for this symbol.",
                data_source=None, exchange="Unknown",
                sources_detail=sources_detail,
            )

        company_name = financial_data.get("company_name")

        # ── Step 3: pure ratio screening ──────────────────────────────────────────

        # ── ETF path ──────────────────────────────────────────────────────────────
        if financial_data.get("quote_type") == "ETF":
            certified = financial_data.get("etf_shariah_certified", False)
            name      = financial_data.get("etf_long_name", symbol)
            sources_detail.append(SourceResult(
                source="YahooFinance",
                verdict="COMPLIANT" if certified else "NON_COMPLIANT",
                note=f"ETF fund family: {financial_data['sector']}",
            ))
            return ComplianceStatus(
                symbol=symbol, company_name=company_name, sector=financial_data["sector"],
                is_compliant=certified,
                verdict="COMPLIANT" if certified else "NON_COMPLIANT",
                debt_to_mkt_cap=0.0, cash_to_mkt_cap=0.0, impure_revenue_pct=0.0,
                reason=None if certified else f"ETF '{name}' has no verified Shariah mandate.",
                data_source="+".join(financial_data.get("sources", ["YahooFinance"])),
                exchange=financial_data.get("exchange", "NMS"),
                sources_detail=sources_detail,
            )

        # ── Mutual fund path (Morningstar) ────────────────────────────────────────
        if financial_data.get("quote_type") == "MUTUALFUND":
            certified = financial_data.get("fund_shariah_certified", False)
            name      = financial_data.get("fund_long_name", symbol)
            category  = financial_data.get("fund_category", "Unknown")
            isin      = financial_data.get("isin")
            note = f"Morningstar category: {category}" + (f" · ISIN: {isin}" if isin else "")
            sources_detail.append(SourceResult(
                source="Morningstar",
                verdict="COMPLIANT" if certified else "UNKNOWN",
                note=note,
            ))
            return ComplianceStatus(
                symbol=symbol, company_name=company_name, sector=category,
                is_compliant=certified,
                verdict="COMPLIANT" if certified else "UNKNOWN",
                debt_to_mkt_cap=0.0, cash_to_mkt_cap=0.0, impure_revenue_pct=0.0,
                reason=None if certified else f"Mutual fund '{name}' not classified as Islamic Equity by Morningstar.",
                data_source="+".join(financial_data.get("sources", ["Morningstar"])),
                exchange=financial_data.get("exchange", "Unknown"),
                sources_detail=sources_detail,
            )

        # ── AAOIFI Standard 21 ratio screening — our CANONICAL assessment ─────────
        # See COMPLIANCE.md §1/§3. Liquidity screen B is COMBINED (cash + int-bearing),
        # 30% thresholds, and our screen is authoritative (certifier is advisory below).
        mkt_cap  = financial_data["mkt_cap"]
        debt     = financial_data.get("debt", 0) or 0
        rev      = financial_data.get("revenue") or 0
        imp_r    = financial_data["prohibited_income"] / rev if rev > 0 else 0.0
        cash     = financial_data.get("cash", 0) or 0
        ibs      = financial_data.get("interest_bearing_securities", 0) or 0
        debt_r   = debt / mkt_cap if mkt_cap > 0 else 0.0
        liq_r    = (cash + ibs) / mkt_cap if mkt_cap > 0 else 0.0

        debt_thr = AAOIFI_DEBT_MAX - ratio_buffer / 100
        liq_thr  = AAOIFI_LIQUIDITY_MAX - ratio_buffer / 100
        # Floor thresholds at a small epsilon so the VIX buffer can't drive a limit to 0
        # (impure base is only 5% — a 5pp crisis buffer would otherwise make imp_r>=0.0
        # block EVERY name). The buffer still tightens, just never to a block-all zero.
        imp_thr  = max(0.005, AAOIFI_IMPURE_MAX - ratio_buffer / 100)

        ratio_note = " · ".join([
            f"Debt {debt_r:.1%}", f"Liquidity {liq_r:.1%} (cash+int-bearing)", f"Impure {imp_r:.2%}",
        ])

        ratio_reasons = []
        # Fail-closed on undeterminable data (COMPLIANCE.md §1): a positive market cap but
        # missing fundamentals must BLOCK, not silently pass all-zero ratios as COMPLIANT.
        # A real operating equity has revenue AND some cash/debt on its balance sheet;
        # all-zero means the data wasn't retrieved (common for foreign/regional tickers
        # when FMP/AV keys are unset and no certifier verdict exists).
        if mkt_cap <= 0:
            ratio_reasons.append("Undeterminable: market cap <= 0")
        if rev <= 0:
            ratio_reasons.append("Undeterminable: revenue data missing (cannot screen impure income)")
        # Fail-closed on undeterminable balance sheet (M5): yfinance often returns
        # totalDebt=None→0 for thin EU coverage while cash is present, so requiring ALL
        # of debt/cash/ibs to be 0 let debt==0 silently pass the most important AAOIFI
        # gate on MISSING data. Fail closed on debt<=0 alone + the symmetric liquidity
        # hole. Genuinely debt-free names are whitelisted via manual_verify (upstream).
        if debt <= 0:
            ratio_reasons.append("Undeterminable: debt data missing (totalDebt<=0 — cannot verify AAOIFI debt screen)")
        if cash <= 0 and ibs <= 0:
            ratio_reasons.append("Undeterminable: liquidity data missing (cash+interest-bearing all 0)")
        if debt_r >= debt_thr:
            ratio_reasons.append(f"Debt ratio {debt_r:.1%} >= {debt_thr:.0%}")
        if liq_r >= liq_thr:
            ratio_reasons.append(f"Liquidity ratio {liq_r:.1%} >= {liq_thr:.0%} (cash+interest-bearing)")
        if imp_r >= imp_thr:
            ratio_reasons.append(f"Impure revenue {imp_r:.2%} >= {imp_thr:.0%}")
        elif not financial_data.get("financials_available", True):
            # imp_r==0 here came from ABSENT income statements (common for IFRS EU
            # filers), not a genuine zero — the AAOIFI 5% purity screen is
            # undeterminable (M6). Fail closed UNLESS a certifier corroborates
            # COMPLIANT (manual_verify is handled upstream). This does not
            # blanket-block: certifier-covered names still pass.
            certifier_ok = bool(verdict and verdict.get("compliant") and not verdict.get("doubtful"))
            if not certifier_ok:
                ratio_reasons.append(
                    "Undeterminable: impure-income statements absent "
                    "(no certifier corroboration — cannot verify AAOIFI 5% purity screen)")

        ratio_verdict = "COMPLIANT" if len(ratio_reasons) == 0 else "NON_COMPLIANT"
        for src in financial_data.get("sources", ["YahooFinance"]):
            sources_detail.append(SourceResult(source=src, verdict=ratio_verdict, note=ratio_note))

        # Certifier (Zoya/Musaffa) is ADVISORY (COMPLIANCE.md §3): our AAOIFI screen is the
        # canonical verdict, but a certifier may only TIGHTEN it (fail-closed on doubt), never
        # loosen it. Record corroboration; on conflict log a DISAGREEMENT, and if the certifier
        # flags non-compliant/doubtful while our ratios pass, block anyway (fail-closed).
        if verdict:
            certifier_compliant = verdict["compliant"] and not verdict.get("doubtful")
            our_compliant = ratio_verdict == "COMPLIANT"
            if certifier_compliant != our_compliant:
                srcs = "+".join(verdict.get("sources", [])) or "certifier"
                logger.warning(
                    "Shariah DISAGREEMENT %s: certifier(%s)=%s, our AAOIFI screen=%s",
                    symbol, srcs,
                    "COMPLIANT" if certifier_compliant else "NON_COMPLIANT", ratio_verdict,
                )
                sources_detail.append(SourceResult(
                    source="DISAGREEMENT", verdict="REVIEW",
                    note=(f"Certifier ({srcs}) says "
                          f"{'COMPLIANT' if certifier_compliant else 'NON_COMPLIANT/DOUBTFUL'}, "
                          f"our AAOIFI screen says {ratio_verdict}. Our screen is canonical; "
                          "a non-compliant certifier verdict blocks fail-closed."),
                ))
                if our_compliant and not certifier_compliant:
                    ratio_reasons.append(
                        f"Certifier ({srcs}) flags non-compliant — blocked fail-closed "
                        "(our ratios passed; COMPLIANCE.md §3)")

        # ── Staleness check ───────────────────────────────────────────────────────
        data_as_of_str = financial_data.get("data_as_of")
        data_stale = False
        staleness_note: str | None = None
        if data_as_of_str:
            try:
                filing_date = date.fromisoformat(data_as_of_str)
                age_days = (utc_today() - filing_date).days
                if age_days > _STALENESS_DAYS:
                    data_stale = True
                    staleness_note = f"Data from {data_as_of_str} ({age_days}d old — ratios may be stale)"
                    sources_detail.append(SourceResult(
                        source="DataQuality", verdict="STALE", note=staleness_note
                    ))
            except ValueError:
                pass

        # ── Sector + ratio screening ─────────────────────────────────────────────
        effective_sectors = _PROHIBITED_SECTORS | set(extra_excluded_sectors)
        sector_str = financial_data["sector"]
        _sector_hay = _sector_haystack(sector_str)
        for ps in effective_sectors:
            if ps.lower() in _sector_hay:
                ratio_reasons.insert(0, f"Prohibited sector: {sector_str}")
                break
        # Business screen via yfinance machine slugs (H4) — the human substring loop
        # above misses compound labels ("Alcohol" ∉ "…/Beverages - Wineries &
        # Distilleries", "Conventional Finance" ∉ "Banks - Regional"). Islamic-native
        # institutions (Al Rajhi/Alinma) are exempted so intentional seeds still pass.
        is_slug_exempt = (normalized in _SECTOR_SLUG_EXEMPT_TICKERS
                          or sym_upper in _SECTOR_SLUG_EXEMPT_TICKERS)
        if not is_slug_exempt and _industry_slug_prohibited(
                financial_data.get("industry_key"), financial_data.get("sector_key")):
            slug = financial_data.get("industry_key") or financial_data.get("sector_key")
            ratio_reasons.insert(0, f"Prohibited sector (slug): {slug}")

        is_compliant = len(ratio_reasons) == 0
        reason_str = "; ".join(ratio_reasons) if ratio_reasons else None
        if data_stale and staleness_note:
            reason_str = "; ".join(filter(None, [reason_str, staleness_note]))

        return ComplianceStatus(
            symbol=symbol,
            company_name=company_name,
            sector=sector_str,
            is_compliant=is_compliant,
            verdict="COMPLIANT" if is_compliant else "NON_COMPLIANT",
            debt_to_mkt_cap=debt_r,
            cash_to_mkt_cap=liq_r,
            impure_revenue_pct=imp_r,
            reason=reason_str,
            data_source="+".join(financial_data.get("sources", ["YahooFinance"])),
            exchange=financial_data.get("exchange", "NMS"),
            country=financial_data.get("country"),
            sources_detail=sources_detail,
            data_as_of=data_as_of_str,
            data_stale=data_stale,
        )

    except Exception as e:
        logger.error(f"Error in _live_shariah_screen_uncached for {symbol}: {e}")
        return ComplianceStatus(
            symbol=symbol, sector="Unknown", is_compliant=False,
            debt_to_mkt_cap=0.0, cash_to_mkt_cap=0.0, impure_revenue_pct=0.0,
            reason=f"System error during screening: {str(e)}",
            sources_detail=[SourceResult(source="System", verdict="ERROR", note=str(e))]
        )


def live_shariah_screen(symbol: str, ratio_buffer_override: float | None = None) -> ComplianceStatus:
    if ratio_buffer_override is None:
        with _cache_lock:
            cached = _screen_cache.get(symbol)
            if cached is not None:
                result, ts = cached
                if time.time() - ts < _CACHE_TTL_SECONDS:
                    return result
    result = _live_shariah_screen_uncached(symbol, ratio_buffer_override)
    if ratio_buffer_override is None:
        with _cache_lock:
            _screen_cache[symbol] = (result, time.time())
    return result


def invalidate_screen_cache(symbol: str | None = None) -> None:
    """Clear cache for one symbol, or all symbols if symbol is None."""
    with _cache_lock:
        if symbol is None:
            _screen_cache.clear()
        else:
            _screen_cache.pop(symbol, None)


async def async_shariah_screen(symbol: str, ratio_buffer_override: float | None = None) -> ComplianceStatus:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, live_shariah_screen, symbol, ratio_buffer_override)


async def screen_many(symbols: list[str]) -> list[ComplianceStatus]:
    return await asyncio.gather(*[async_shariah_screen(s) for s in symbols])
