import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from backend.main import app
from backend.core.database import get_db
from backend.core.models import TradeHistory, PositionCompliance, PurificationHistory
from backend.core.state import TradeState

client = TestClient(app)

@pytest.fixture
def mock_db():
    db = MagicMock()
    yield db

def test_get_purification_liabilities_empty(mock_db):
    # Mocking get_db dependency
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_db.query.return_value.filter.return_value.all.return_value = []
    mock_db.query.return_value.order_by.return_value.all.return_value = []
    mock_db.query.return_value.all.return_value = []
    
    response = client.get("/api/zakat/purification/liabilities")
    assert response.status_code == 200
    assert response.json() == []
    
    app.dependency_overrides.clear()

def test_get_purification_liabilities_with_data(mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db
    
    # 1. Mock TradeHistory (Realized Profit)
    # 10 shares of AAPL bought at 100, sold at 150 -> 500 profit
    trade1 = TradeHistory(symbol="AAPL", side="BUY", fill_price=100.0, quantity=10, state=TradeState.FILLED)
    trade2 = TradeHistory(symbol="AAPL", side="SELL", fill_price=150.0, quantity=10, state=TradeState.FILLED)
    
    # Mock the filter().all() call for TradeHistory
    mock_db.query.return_value.filter.return_value.all.return_value = [trade1, trade2]
    
    # 2. Mock PositionCompliance (Impure Revenue %)
    # AAPL has 2% impure revenue
    comp = PositionCompliance(symbol="AAPL", metrics={"impure_revenue_pct": 0.02}, timestamp=datetime.now(timezone.utc))
    
    # 3. Mock PurificationHistory (Already purified)
    # Already purified 5.0 for AAPL
    pur = PurificationHistory(symbol="AAPL", purification_amount=5.0)
    
    # We need to handle multiple queries in sequence
    def side_effect(model):
        mock_q = MagicMock()
        if model == TradeHistory:
            mock_q.filter.return_value.all.return_value = [trade1, trade2]
            return mock_q
        if model == PositionCompliance:
            mock_q.order_by.return_value.all.return_value = [comp]
            return mock_q
        if model == PurificationHistory:
            mock_q.all.return_value = [pur]
            return mock_q
        return mock_q

    mock_db.query.side_effect = side_effect
    
    response = client.get("/api/zakat/purification/liabilities")
    assert response.status_code == 200
    data = response.json()
    
    # 500 profit * 0.02 = 10.0 purification due
    # 10.0 - 5.0 already paid = 5.0 remaining
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["realized_profit"] == 500.0
    assert data[0]["impure_revenue_pct"] == 0.02
    assert data[0]["purification_due"] == 10.0
    assert data[0]["purified_already"] == 5.0
    assert data[0]["remaining_liability"] == 5.0
    
    app.dependency_overrides.clear()
