import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.core.models import Base, AuditLog
from backend.init_db import initialize_system

@pytest.fixture
def test_db():
    # Use an in-memory database for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_initialize_system_creates_genesis_log(test_db, monkeypatch):
    """
    Verifies that system initialization creates a GENESIS audit log.
    Ref: AUDIT_LOG.md Section 2 - Verification/Immutable Ledger.
    """
    # Mock init_db to do nothing since tables are already created in fixture
    monkeypatch.setattr("backend.init_db.init_db", lambda: None)
    
    # Run initialization logic
    initialize_system(db_session=test_db)
    
    # Verify Genesis log
    genesis = test_db.query(AuditLog).filter(AuditLog.symbol == "GENESIS").first()
    assert genesis is not None
    assert genesis.action == "SYSTEM_INIT"
    assert genesis.shariah_status == "VERIFIED"
    assert genesis.metrics["version"] == "1.0.0"

def test_initialize_system_idempotent(test_db, monkeypatch):
    """
    Verifies that running initialization multiple times doesn't duplicate GENESIS.
    """
    monkeypatch.setattr("backend.init_db.init_db", lambda: None)
    
    initialize_system(db_session=test_db)
    initialize_system(db_session=test_db)
    
    count = test_db.query(AuditLog).filter(AuditLog.symbol == "GENESIS").count()
    assert count == 1
