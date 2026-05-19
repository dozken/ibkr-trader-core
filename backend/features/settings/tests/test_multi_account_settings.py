"""Tests for per-account settings support."""

import json
import os
import pytest
from backend.features.settings.service import load_settings, save_settings, Settings


def test_load_settings_no_account_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.features.settings.service.SETTINGS_DIR", str(tmp_path))
    result = load_settings()
    assert result["min_trade_size"] == Settings().min_trade_size


def test_load_settings_account_id_returns_account_file(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.features.settings.service.SETTINGS_DIR", str(tmp_path))
    account_file = tmp_path / "settings_2.json"
    account_file.write_text(json.dumps({"min_trade_size": 500.0}))
    result = load_settings(account_id=2)
    assert result["min_trade_size"] == 500.0


def test_load_settings_account_missing_falls_back_to_global(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.features.settings.service.SETTINGS_DIR", str(tmp_path))
    global_file = tmp_path / "settings.json"
    global_file.write_text(json.dumps({"min_trade_size": 250.0}))
    # No settings_5.json exists
    result = load_settings(account_id=5)
    assert result["min_trade_size"] == 250.0


def test_load_settings_account_inherits_global_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.features.settings.service.SETTINGS_DIR", str(tmp_path))
    global_file = tmp_path / "settings.json"
    global_file.write_text(json.dumps({"min_trade_size": 200.0, "dry_run": True}))
    account_file = tmp_path / "settings_3.json"
    account_file.write_text(json.dumps({"min_trade_size": 300.0}))
    result = load_settings(account_id=3)
    # Account-specific overrides global
    assert result["min_trade_size"] == 300.0
    # But inherits unset keys from global
    assert result["dry_run"] is True


def test_save_settings_no_account_writes_global(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.features.settings.service.SETTINGS_DIR", str(tmp_path))
    save_settings({"min_trade_size": 150.0})
    path = tmp_path / "settings.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["min_trade_size"] == 150.0


def test_save_settings_with_account_id_writes_account_file(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.features.settings.service.SETTINGS_DIR", str(tmp_path))
    save_settings({"min_trade_size": 999.0}, account_id=7)
    path = tmp_path / "settings_7.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["min_trade_size"] == 999.0


def test_load_settings_account_id_zero_treated_as_global(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.features.settings.service.SETTINGS_DIR", str(tmp_path))
    global_file = tmp_path / "settings.json"
    global_file.write_text(json.dumps({"min_trade_size": 111.0}))
    result = load_settings(account_id=None)
    assert result["min_trade_size"] == 111.0
