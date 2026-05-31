"""Tests for PATCH /api/settings — partial settings update."""

import json
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from ibkr_core.main import app
from ibkr_core.features.settings.service import Settings

client = TestClient(app)


def _make_settings_file(tmp_dir: str, overrides: dict) -> str:
    """Write a settings.json file inside tmp_dir and return its path."""
    path = os.path.join(tmp_dir, "settings.json")
    data = Settings().model_dump()
    data.update(overrides)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

class TestPatchSettings:
    """Group all PATCH /api/settings tests."""

    def test_patch_watchlist_only_updates_watchlist(self, tmp_path):
        """PATCH with just `watchlist` must update watchlist and leave everything else unchanged."""
        _make_settings_file(
            str(tmp_path),
            {"signal_min_confidence": 55, "trading_mode": "AUTO"},
        )

        with patch("ibkr_core.features.settings.service.SETTINGS_DIR", str(tmp_path)):
            new_watchlist = ["AAPL", "TSLA", "NVDA"]
            response = client.patch("/api/settings", json={"watchlist": new_watchlist})

        assert response.status_code == 200
        body = response.json()
        assert body["watchlist"] == new_watchlist
        # Fields NOT in the payload must be preserved
        assert body["signal_min_confidence"] == 55
        assert body["trading_mode"] == "AUTO"

    def test_patch_multiple_fields_updates_all_provided(self, tmp_path):
        """PATCH with several fields must update each of them."""
        _make_settings_file(str(tmp_path), {})

        with patch("ibkr_core.features.settings.service.SETTINGS_DIR", str(tmp_path)):
            payload = {
                "signal_min_confidence": 75,
                "cash_reserve_pct": 20.0,
                "rebalance_frequency": "DAILY",
            }
            response = client.patch("/api/settings", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["signal_min_confidence"] == 75
        assert body["cash_reserve_pct"] == 20.0
        assert body["rebalance_frequency"] == "DAILY"

    def test_patch_preserves_fields_not_in_payload(self, tmp_path):
        """Fields absent from the PATCH body must keep their persisted values."""
        settings_file = _make_settings_file(
            str(tmp_path),
            {
                "watchlist": ["7203.T", "6758.T"],
                "min_trade_size": 250.0,
                "auto_compliance_check": False,
            },
        )

        with patch("ibkr_core.features.settings.service.SETTINGS_DIR", str(tmp_path)):
            # Only update one field
            response = client.patch("/api/settings", json={"signal_min_confidence": 40})

        assert response.status_code == 200
        body = response.json()
        # The patched field is updated
        assert body["signal_min_confidence"] == 40
        # All other persisted fields are untouched
        assert body["watchlist"] == ["7203.T", "6758.T"]
        assert body["min_trade_size"] == 250.0
        assert body["auto_compliance_check"] is False

    def test_patch_empty_body_returns_current_settings(self, tmp_path):
        """An empty PATCH body must return settings unchanged (no clobber)."""
        settings_file = _make_settings_file(
            str(tmp_path),
            {"signal_min_confidence": 60},
        )

        with patch("ibkr_core.features.settings.service.SETTINGS_DIR", str(tmp_path)):
            response = client.patch("/api/settings", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["signal_min_confidence"] == 60

    def test_patch_returns_full_settings_object(self, tmp_path):
        """The PATCH response must be a complete Settings object (all fields present)."""
        _make_settings_file(str(tmp_path), {})
        expected_fields = set(Settings.model_fields.keys())

        with patch("ibkr_core.features.settings.service.SETTINGS_DIR", str(tmp_path)):
            response = client.patch("/api/settings", json={"cash_sweep_enabled": False})

        assert response.status_code == 200
        body = response.json()
        assert expected_fields.issubset(set(body.keys()))
