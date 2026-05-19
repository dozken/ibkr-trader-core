from backend.core.database import SessionLocal
from backend.core.models import PositionCompliance
from backend.features.compliance.schemas import ComplianceStatus


def persist_compliance(symbol: str, status: ComplianceStatus) -> None:
    """Write compliance snapshot to DB. Called from both HTTP endpoints and audit loop."""
    db = SessionLocal()
    try:
        db.add(PositionCompliance(
            symbol=symbol,
            shariah_status=status.verdict or ("COMPLIANT" if status.is_compliant else "NON_COMPLIANT"),
            metrics={
                "debt_to_mkt_cap":    status.debt_to_mkt_cap,
                "cash_to_mkt_cap":    status.cash_to_mkt_cap,
                "impure_revenue_pct": status.impure_revenue_pct,
                "sector":             status.sector,
                "country":            status.country,
                "company_name":       status.company_name,
                "reason":             status.reason,
                "data_source":        status.data_source,
                "data_as_of":         status.data_as_of,
                "data_stale":         status.data_stale,
                "sources_detail":     [s.model_dump() for s in status.sources_detail],
            },
            is_active_holding=True,
        ))
        db.commit()
    finally:
        db.close()
