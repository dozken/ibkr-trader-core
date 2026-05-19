import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app

class TestIBKRHealth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("backend.features.trading.router.os.getenv")
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

if __name__ == "__main__":
    unittest.main()
