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


def test_patch_read_only_reconnects_worker_in_new_mode(client):
    """Arming must flip the live worker too — a readonly IB connection cannot
    transmit orders, so the DB flag alone would leave the account mute."""
    c, db = client
    acc = Account(label="Live", host="127.0.0.1", port=4003, client_id=2,
                  is_paper=False, is_active=True, read_only=True)
    db.add(acc)
    db.commit()
    db.refresh(acc)

    class FakeWorker:
        def __init__(self):
            self.readonly = True
            self.ib = object()
            self.disconnected = False
            self.connected_as = None

        def disconnect(self):
            self.disconnected = True

        async def connect(self):
            self.connected_as = self.readonly
            return True

    class FakeManager:
        def __init__(self, w, aid):
            self._w, self._aid = w, aid

        def get_worker_by_id(self, account_id):
            return self._w if account_id == self._aid else None

        def list_account_ids(self):
            return [self._aid]

    worker = FakeWorker()
    prev = getattr(c.app.state, "account_manager", None)
    c.app.state.account_manager = FakeManager(worker, acc.id)
    try:
        r = c.patch(f"/api/accounts/{acc.id}", json={"read_only": False})
    finally:
        c.app.state.account_manager = prev

    assert r.status_code == 200
    assert r.json()["read_only"] is False
    assert worker.readonly is False
    assert worker.disconnected is True
    assert worker.connected_as is False


def test_cannot_arm_live_while_a_paper_account_is_active(client):
    """The boot guard tolerates read-only live beside paper; arming would put
    simulated and real orders in one process, so the API refuses it."""
    c, db = client
    live = Account(label="Live", host="h", port=4003, client_id=1,
                   is_paper=False, is_active=True, read_only=True)
    paper = Account(label="Paper", host="h", port=4004, client_id=2,
                    is_paper=True, is_active=True, read_only=False)
    db.add_all([live, paper])
    db.commit()
    db.refresh(live)

    r = c.patch(f"/api/accounts/{live.id}", json={"read_only": False})
    assert r.status_code == 409
    db.refresh(live)
    assert live.read_only is True  # rejected call left the DB untouched


def test_cannot_activate_paper_beside_an_armed_live_account(client):
    c, db = client
    live = Account(label="Live", host="h", port=4003, client_id=1,
                   is_paper=False, is_active=True, read_only=False)
    paper = Account(label="Paper", host="h", port=4004, client_id=2,
                    is_paper=True, is_active=False, read_only=False)
    db.add_all([live, paper])
    db.commit()
    db.refresh(paper)

    r = c.patch(f"/api/accounts/{paper.id}", json={"is_active": True})
    assert r.status_code == 409
    db.refresh(paper)
    assert paper.is_active is False


def test_paper_may_activate_beside_read_only_live(client):
    c, db = client
    live = Account(label="Live", host="h", port=4003, client_id=1,
                   is_paper=False, is_active=True, read_only=True)
    paper = Account(label="Paper", host="h", port=4004, client_id=2,
                    is_paper=True, is_active=False, read_only=False)
    db.add_all([live, paper])
    db.commit()
    db.refresh(paper)

    r = c.patch(f"/api/accounts/{paper.id}", json={"is_active": True})
    assert r.status_code == 200
    assert r.json()["is_active"] is True


def test_create_armed_live_beside_active_paper_rejected(client):
    c, db = client
    db.add(Account(label="Paper", host="h", port=4004, client_id=2,
                   is_paper=True, is_active=True))
    db.commit()
    r = c.post("/api/accounts", json={"label": "Live", "host": "h", "port": 4003,
                                      "client_id": 9, "is_paper": False,
                                      "read_only": False})
    assert r.status_code == 409
    r = c.post("/api/accounts", json={"label": "Live RO", "host": "h", "port": 4003,
                                      "client_id": 9, "is_paper": False,
                                      "read_only": True})
    assert r.status_code == 201


def test_patch_unrelated_field_leaves_worker_alone(client):
    c, db = client
    acc = Account(label="Live", host="127.0.0.1", port=4003, client_id=2,
                  is_paper=False, is_active=True, read_only=True)
    db.add(acc)
    db.commit()
    db.refresh(acc)

    touched = []

    class FakeManager:
        def get_worker_by_id(self, account_id):
            touched.append(account_id)
            return None

        def list_account_ids(self):
            return []

    prev = getattr(c.app.state, "account_manager", None)
    c.app.state.account_manager = FakeManager()
    try:
        r = c.patch(f"/api/accounts/{acc.id}", json={"label": "Renamed"})
    finally:
        c.app.state.account_manager = prev

    assert r.status_code == 200
    assert touched == []


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
