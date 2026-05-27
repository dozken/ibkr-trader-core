import asyncio
import os
import time
import logging
from datetime import date
from threading import Lock
from dotenv import load_dotenv
from ibkr_core.features.compliance.schemas import ComplianceStatus, SourceResult
from ibkr_core.features.compliance.data_fetcher import (
    fetch_financial_data,
    fetch_shariah_verdict,
    normalize_ticker,
    GOLD_ETC_ALLOWLIST,
    SHARIAH_ETF_ALLOWLIST,
    ZOYA_API_KEY,
)
from ibkr_core.features.settings.service import load_settings as _load_settings

logger = logging.getLogger(__name__)

load_dotenv()

_STALENESS_DAYS = int(os.getenv("COMPLIANCE_STALENESS_DAYS", 90))

_screen_cache: dict[str, tuple["ComplianceStatus", float]] = {}
_cache_lock = Lock()
_CACHE_TTL_SECONDS = 86400  # 24 hours

_PROHIBITED_SECTORS = {
    "Conventional Finance", "Conventional Insurance", "Alcohol", "Tobacco",
    "Gambling", "Adult Content", "Pork", "Defense", "Weapons",
    "Entertainment", "Interest-bearing",
}


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
) -> ComplianceStatus:
    reasons = []
    effective_sectors = _PROHIBITED_SECTORS | set(extra_excluded_sectors)
    for ps in effective_sectors:
        if ps.lower() in sector.lower():
            reasons.append(f"Prohibited sector: {sector}")
            break

    debt_ratio    = debt / mkt_cap
    cash_ratio    = cash / mkt_cap
    revenue_ratio = prohibited_income / revenue if revenue > 0 else 0.0

    debt_threshold    = 0.33 - ratio_buffer / 100
    cash_threshold    = 0.33 - ratio_buffer / 100
    impure_threshold  = 0.05 - ratio_buffer / 100

    if debt_ratio    >= debt_threshold:   reasons.append(f"Debt ratio ({debt_ratio:.2%}) >= {debt_threshold:.0%}")
    if cash_ratio    >= cash_threshold:   reasons.append(f"Cash ratio ({cash_ratio:.2%}) >= {cash_threshold:.0%}")
    if revenue_ratio >= impure_threshold: reasons.append(f"Prohibited income ({revenue_ratio:.2%}) >= {impure_threshold:.0%}")

    return ComplianceStatus(
        symbol=symbol, sector=sector,
        is_compliant=len(reasons) == 0,
        debt_to_mkt_cap=debt_ratio,
        cash_to_mkt_cap=cash_ratio,
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
                exchange=normalized.split(".", 1)[1] if "." in normalized else "Unknown",
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
                exchange=normalized.split(".", 1)[1] if "." in normalized else "NMS",
                sources_detail=sources_detail,
            )

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

        # ── AAOIFI ratio screening (our own independent assessment) ───────────────
        mkt_cap  = financial_data["mkt_cap"]
        debt_r   = financial_data["debt"] / mkt_cap
        cash_r   = financial_data["cash"] / mkt_cap
        rev      = financial_data.get("revenue") or 0
        imp_r    = financial_data["prohibited_income"] / rev if rev > 0 else 0.0

        # Interest-bearing securities / market cap (AAOIFI Standard 21)
        ibs = financial_data.get("interest_bearing_securities", 0)
        ibs_r = ibs / mkt_cap if mkt_cap > 0 and ibs > 0 else 0.0

        ratio_parts = [f"Debt {debt_r:.1%}", f"Cash {cash_r:.1%}", f"Impure {imp_r:.2%}"]
        if ibs_r > 0:
            ratio_parts.append(f"Interest-bearing securities {ibs_r:.1%} of mktcap")
        ratio_note = " · ".join(ratio_parts)

        ratio_reasons = []
        if debt_r >= (0.33 - ratio_buffer / 100):
            ratio_reasons.append(f"Debt ratio {debt_r:.1%} >= {0.33 - ratio_buffer / 100:.0%}")
        if cash_r >= (0.33 - ratio_buffer / 100):
            ratio_reasons.append(f"Cash ratio {cash_r:.1%} >= {0.33 - ratio_buffer / 100:.0%}")
        if imp_r >= (0.05 - ratio_buffer / 100):
            ratio_reasons.append(f"Impure revenue {imp_r:.2%} >= {0.05 - ratio_buffer / 100:.0%}")
        if ibs_r >= 0.33:
            ratio_reasons.append(f"Interest-bearing securities {ibs_r:.1%} >= 33% of market cap")

        ratio_verdict = "COMPLIANT" if len(ratio_reasons) == 0 else "NON_COMPLIANT"
        for src in financial_data.get("sources", ["YahooFinance"]):
            sources_detail.append(SourceResult(source=src, verdict=ratio_verdict, note=ratio_note))

        if verdict:
            zoya_is_live = ZOYA_API_KEY and not ZOYA_API_KEY.startswith("sandbox-")
            if zoya_is_live:
                # Live Zoya key — authoritative, trust their verdict
                is_compliant = verdict["compliant"] and not verdict.get("doubtful")
                v = "COMPLIANT" if is_compliant else ("DOUBTFUL" if verdict.get("doubtful") else "NON_COMPLIANT")
                return ComplianceStatus(
                    symbol=symbol, company_name=company_name, sector=financial_data["sector"],
                    is_compliant=is_compliant, verdict=v,
                    debt_to_mkt_cap=debt_r, cash_to_mkt_cap=cash_r, impure_revenue_pct=imp_r,
                    reason=verdict.get("status") if not is_compliant else None,
                    data_source="+".join([*verdict["sources"], *financial_data.get("sources", [])]),
                    exchange=financial_data.get("exchange", "NMS"),
                    sources_detail=sources_detail,
                )
            # Sandbox Zoya — advisory only, our AAOIFI ratios decide

        # ── Staleness check ───────────────────────────────────────────────────────
        data_as_of_str = financial_data.get("data_as_of")
        data_stale = False
        staleness_note: str | None = None
        if data_as_of_str:
            try:
                filing_date = date.fromisoformat(data_as_of_str)
                age_days = (date.today() - filing_date).days
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
        for ps in effective_sectors:
            if ps.lower() in sector_str.lower():
                ratio_reasons.insert(0, f"Prohibited sector: {sector_str}")
                break

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
            cash_to_mkt_cap=cash_r,
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
