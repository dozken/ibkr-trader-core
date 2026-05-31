import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ibkr_core.core.models import Base, AuditLog, PurificationHistory, TradeHistory
from ibkr_core.core.state import TradeState

# Use in-memory SQLite for testing
DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture
def db_session():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_create_audit_log(db_session):
    """
    Test creating an AuditLog entry.
    Ref: AUDIT_LOG.md Section 1.
    """
    log = AuditLog(
        symbol="AAPL",
        action="BUY",
        shariah_status="COMPLIANT",
        data_source="Zoya/YahooFinance",
        metrics={
            "debt_to_market_cap": 0.12,
            "cash_to_market_cap": 0.08,
            "impure_revenue_ratio": 0.012
        },
        business_activity="Technology/Consumer Electronics",
        ibkr_order_id=12345
    )
    db_session.add(log)
    db_session.commit()

    retrieved = db_session.query(AuditLog).first()
    assert retrieved.symbol == "AAPL"
    assert retrieved.metrics["debt_to_market_cap"] == 0.12
    assert retrieved.ibkr_order_id == 12345
    assert retrieved.timestamp is not None

def test_create_purification_history(db_session):
    """
    Test creating a PurificationHistory entry.
    Ref: AUDIT_LOG.md Section 3.
    """
    entry = PurificationHistory(
        symbol="MSFT",
        dividend_amount=100.0,
        purification_amount=1.5,
        donation_receipt_link="https://receipts.org/123"
    )
    db_session.add(entry)
    db_session.commit()
    
    retrieved = db_session.query(PurificationHistory).first()
    assert retrieved.symbol == "MSFT"
    assert retrieved.purification_amount == 1.5
    assert retrieved.donation_receipt_link == "https://receipts.org/123"

def test_create_trade_history(db_session):
    """
    Test creating a TradeHistory entry.
    Track C requirement.
    """
    trade = TradeHistory(
        symbol="TSLA",
        quantity=10,
        side="BUY",
        order_type="MKT",
        state=TradeState.FILLED,
        ibkr_order_id=54321,
        fill_price=200.5,
        commission=1.0
    )
    db_session.add(trade)
    db_session.commit()
    
    retrieved = db_session.query(TradeHistory).first()
    assert retrieved.symbol == "TSLA"
    assert retrieved.state == TradeState.FILLED
    assert retrieved.fill_price == 200.5
