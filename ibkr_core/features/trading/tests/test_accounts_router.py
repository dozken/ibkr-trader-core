"""Tests for /api/accounts CRUD and account_id filtering on /api/trades."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ibkr_core.core.models import Base, Account, TradeHistory
from ibkr_core.core.state import TradeState
from ibkr_core.core.database import get_db
from ibkr_core.main import app

# ---------------------------------------------------------------------------
# In-memory DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()

    def override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    c = TestClient(app)
    yield c, session
    app.dependency_overrides.pop(get_db, None)
    session.close()


# ---------------------------------------------------------------------------
# /api/accounts — list
# ---------------------------------------------------------------------------

def test_list_accounts_empty(client):
    c, _ = client
    r = c.get("/api/accounts")
    assert r.status_code == 200
    assert r.json() == []


def test_list_accounts_returns_active_only(client):
    c, db = client
    db.add(Account(label="Paper", host="127.0.0.1", port=7497, client_id=1,
                   is_paper=True, is_active=True))
    db.add(Account(label="Inactive", host="127.0.0.1", port=7499, client_id=3,
                   is_paper=True, is_active=False))
    db.commit()
    r = c.get("/api/accounts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["label"] == "Paper"


def test_list_accounts_all_param_includes_inactive(client):
    c, db = client
    db.add(Account(label="Paper", host="127.0.0.1", port=7497, client_id=1,
                   is_paper=True, is_active=True))
    db.add(Account(label="Inactive", host="127.0.0.1", port=7499, client_id=3,
                   is_paper=True, is_active=False))
    db.commit()
    r = c.get("/api/accounts?include_inactive=true")
    assert len(r.json()) == 2


# ---------------------------------------------------------------------------
# /api/accounts — create
# ---------------------------------------------------------------------------

def test_create_account(client):
    c, db = client
    payload = {
        "label": "Live Account",
        "host": "127.0.0.1",
        "port": 7496,
        "client_id": 2,
        "ibkr_account_id": "U9876543",
        "is_paper": False,
    }
    r = c.post("/api/accounts", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["label"] == "Live Account"
    assert body["port"] == 7496
    assert body["is_active"] is True


def test_create_account_duplicate_client_id_rejected(client):
    c, db = client
    db.add(Account(label="Paper", host="127.0.0.1", port=7497, client_id=1,
                   is_paper=True, is_active=True))
    db.commit()
    payload = {"label": "Another", "host": "127.0.0.1", "port": 7497, "client_id": 1,
               "is_paper": True}
    r = c.post("/api/accounts", json=payload)
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# /api/accounts/{id} — patch / deactivate
# ---------------------------------------------------------------------------

def test_patch_account_label(client):
    c, db = client
    acc = Account(label="Old", host="127.0.0.1", port=7497, client_id=1,
                  is_paper=True, is_active=True)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    r = c.patch(f"/api/accounts/{acc.id}", json={"label": "New Label"})
    assert r.status_code == 200
    assert r.json()["label"] == "New Label"


def test_deactivate_account(client):
    c, db = client
    acc = Account(label="Paper", host="127.0.0.1", port=7497, client_id=1,
                  is_paper=True, is_active=True)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    r = c.delete(f"/api/accounts/{acc.id}")
    assert r.status_code == 200
    db.refresh(acc)
    assert acc.is_active is False


def test_deactivate_nonexistent_account_returns_404(client):
    c, _ = client
    r = c.delete("/api/accounts/9999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/trades?account_id= filtering
# ---------------------------------------------------------------------------

def test_list_trades_filtered_by_account_id(client):
    c, db = client
    acc1 = Account(label="A1", host="127.0.0.1", port=7497, client_id=1,
                   is_paper=True, is_active=True)
    acc2 = Account(label="A2", host="127.0.0.1", port=7496, client_id=2,
                   is_paper=False, is_active=True)
    db.add_all([acc1, acc2])
    db.commit()
    db.refresh(acc1); db.refresh(acc2)

    db.add(TradeHistory(symbol="AAPL", quantity=10, side="BUY", order_type="MKT",
                        state=TradeState.FILLED, account_id=acc1.id))
    db.add(TradeHistory(symbol="MSFT", quantity=5, side="BUY", order_type="MKT",
                        state=TradeState.FILLED, account_id=acc2.id))
    db.commit()

    r = c.get(f"/api/trades?account_id={acc1.id}")
    assert r.status_code == 200
    symbols = [t["symbol"] for t in r.json()]
    assert "AAPL" in symbols
    assert "MSFT" not in symbols


def test_list_trades_no_account_id_returns_all(client):
    c, db = client
    acc = Account(label="A1", host="127.0.0.1", port=7497, client_id=1,
                  is_paper=True, is_active=True)
    db.add(acc)
    db.commit()
    db.refresh(acc)

    db.add(TradeHistory(symbol="AAPL", quantity=10, side="BUY", order_type="MKT",
                        state=TradeState.FILLED, account_id=acc.id))
    db.add(TradeHistory(symbol="MSFT", quantity=5, side="BUY", order_type="MKT",
                        state=TradeState.FILLED, account_id=None))
    db.commit()

    r = c.get("/api/trades")
    assert len(r.json()) == 2
