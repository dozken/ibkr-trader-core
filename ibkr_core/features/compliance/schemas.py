from typing import Literal, List, Optional

from pydantic import BaseModel

from ibkr_core.core.websocket import WSBaseMessage


class SourceResult(BaseModel):
    source:  str            # "Zoya" | "Musaffa" | "YahooFinance" | "FMP" | "AlphaVantage" | "Morningstar"
    verdict: str            # "COMPLIANT" | "NON_COMPLIANT" | "DOUBTFUL" | "UNKNOWN" | "ERROR"
    note:    Optional[str] = None


class ComplianceStatus(BaseModel):
    symbol:             str
    company_name:       Optional[str] = None
    sector:             str
    country:            Optional[str] = None
    is_compliant:       bool
    verdict:            str = "NON_COMPLIANT"   # "COMPLIANT" | "NON_COMPLIANT" | "DOUBTFUL" | "UNKNOWN"
    debt_to_mkt_cap:    float
    cash_to_mkt_cap:    float
    impure_revenue_pct: float
    reason:             Optional[str] = None
    data_source:        Optional[str] = None
    exchange:           Optional[str] = "NMS"
    sources_detail:     List[SourceResult] = []
    data_as_of:         Optional[str] = None   # ISO date of most recent financial filing
    data_stale:         bool = False            # True when data_as_of > 90 days old


class ComplianceResultPayload(BaseModel):
    symbol: str
    is_compliant: bool
    reason: str
    debt_to_mkt_cap: float
    cash_to_mkt_cap: float
    impure_revenue_pct: float
    sector: str
    country: Optional[str] = None
    exchange: str


class ComplianceResultMessage(WSBaseMessage):
    type: Literal["compliance_result"] = "compliance_result"
    payload: ComplianceResultPayload


class ComplianceViolationPayload(BaseModel):
    symbol: str
    reason: str
    auto_liquidate: bool


class ComplianceViolationMessage(WSBaseMessage):
    type: Literal["compliance_violation"] = "compliance_violation"
    payload: ComplianceViolationPayload
