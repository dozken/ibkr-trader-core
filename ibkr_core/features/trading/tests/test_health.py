import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from ibkr_core.main import app

class TestIBKRHealth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("ibkr_core.features.trading.router.os.getenv")
    def test_health_disconnected(self, mock_getenv):
        mock_getenv.side_effect = lambda k, d=None: {"IBKR_PORT": "7497"}.get(k, d)
        
        # Mock app.state.worker as None
        with patch.object(app.state, "worker", None, create=True):
            response = self.client.get("/api/trades/ibkr/health")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data["connected"])
            self.assertEqual(data["port_type"], "PAPER")

    def test_health_connected_paper(self):
        mock_worker = MagicMock()
        mock_worker.ib.isConnected.return_value = True
        mock_worker.host = "127.0.0.1"
        mock_worker.port = 7497
        mock_worker.get_account_summary.return_value = {
            "account_id": "DU123",
            "account_type": "INDIVIDUAL",
            "warnings": []
        }

        with patch.object(app.state, "worker", mock_worker, create=True):
            response = self.client.get("/api/trades/ibkr/health")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["connected"])
            self.assertEqual(data["port_type"], "PAPER")
            self.assertEqual(len(data["warnings"]), 0)

    def test_health_connected_live_warning(self):
        mock_worker = MagicMock()
        mock_worker.ib.isConnected.return_value = True
        mock_worker.host = "127.0.0.1"
        mock_worker.port = 7496 # LIVE PORT
        mock_worker.get_account_summary.return_value = {
            "account_id": "U123",
            "account_type": "INDIVIDUAL",
            "warnings": []
        }

        with patch.object(app.state, "worker", mock_worker, create=True):
            response = self.client.get("/api/trades/ibkr/health")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["connected"])
            self.assertEqual(data["port_type"], "LIVE")
            self.assertIn("LIVE port connected", data["warnings"][0])

class TestReadinessMultiAccount(unittest.TestCase):
    """Regression: readiness hardcoded the "main_loop" key, which stays
    "starting" forever in multi-account mode (primary runs as main_loop_<id>),
    so /api/system/readiness always reported not-ready despite healthy loops."""

    def setUp(self):
        self.client = TestClient(app)

    def _ready(self, health):
        mock_worker = MagicMock()
        mock_worker.ib.isConnected.return_value = True
        with patch.object(app.state, "loop_health", health, create=True), \
             patch.object(app.state, "worker", mock_worker, create=True):
            return self.client.get("/api/system/readiness").json()["gates"]["loops_healthy"]

    def test_multi_account_primary_under_suffixed_key_is_ready(self):
        health = {
            "main_loop": {"last_run": None, "status": "starting"},  # vestigial seed
            "main_loop_1": {"last_run": "2026-06-04T16:00:00", "status": "running"},
            "main_loop_2": {"last_run": "2026-06-04T16:00:00", "status": "running"},
            "compliance_audit_loop": {"status": "running"},
            "portfolio_snapshot_loop": {"status": "running"},
        }
        self.assertTrue(self._ready(health))

    def test_no_trading_loop_running_is_not_ready(self):
        health = {
            "main_loop": {"last_run": None, "status": "starting"},
            "main_loop_1": {"status": "error: TypeError"},
            "compliance_audit_loop": {"status": "running"},
            "portfolio_snapshot_loop": {"status": "running"},
        }
        self.assertFalse(self._ready(health))


if __name__ == "__main__":
    unittest.main()
