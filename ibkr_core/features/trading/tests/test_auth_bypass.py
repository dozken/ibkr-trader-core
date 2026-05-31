import pytest
from fastapi.testclient import TestClient
from ibkr_core.main import app

client = TestClient(app)

def test_approve_fails_when_no_api_key_and_not_dev_mode():
    # Force DEV_MODE=false and empty IBKR_API_KEY
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("DEV_MODE", "false")
        mp.setenv("IBKR_API_KEY", "")
        
        # We need to reload the auth module or the variables it already loaded
        import ibkr_core.core.auth
        from importlib import reload
        reload(ibkr_core.core.auth)
        
        response = client.post("/api/trades/approve", json={"symbol": "AAPL", "side": "BUY"})
        assert response.status_code == 500
        assert response.json()["detail"] == "IBKR_API_KEY environment variable is not set."

def test_approve_succeeds_bypass_in_dev_mode():
    # Force DEV_MODE=true and empty IBKR_API_KEY
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("DEV_MODE", "true")
        mp.setenv("IBKR_API_KEY", "")
        
        import ibkr_core.core.auth
        from importlib import reload
        reload(ibkr_core.core.auth)
        
        # Note: This might still fail for other reasons (e.g. IBKR connection),
        # but it should at least pass the auth check.
        response = client.post("/api/trades/approve", json={"symbol": "AAPL", "side": "BUY"})
        # It shouldn't be the auth error
        if response.status_code == 500:
            assert response.json()["detail"] != "IBKR_API_KEY environment variable is not set."
        else:
            # If it's not 500, it passed the auth check (might be 503 if worker not connected)
            assert response.status_code in (200, 503, 400, 404)
