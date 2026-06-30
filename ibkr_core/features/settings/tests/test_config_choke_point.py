"""Tests for the per-account settings choke point (config-drift hardening).

Three guarantees:
  (a) PARITY   — the signal path and the execution path load the SAME effective
                 per-account config, and a per-account overlay differs from global.
  (b) SCHEMA   — a type-invalid known key falls back to its default + logs CRITICAL
                 (never raises); an unknown plugin key is preserved + warned.
  (c) STATIC   — no bare load_settings()/_load_settings() survives in trading code.
"""

import json
import logging
import os
import re

import ibkr_core.features.settings.service as service
from ibkr_core.features.settings.service import Settings, load_settings

# The exec path (Trader.execute_trade) and the signal path (loops.main_loop /
# halal_drip_loop) both resolve to this one choke point. Grab the literal names
# they use so the parity test exercises the real references, not a copy.
from ibkr_core.features.trading.trader import _load_settings as exec_load_settings
from ibkr_core.features.trading.loops import load_settings as signal_load_settings


# ---------------------------------------------------------------------------
# (a) Parity — signal path == exec path, per-account overlay != global
# ---------------------------------------------------------------------------

def test_alias_resolves_to_single_choke_point():
    """Both trading entry points must be the SAME callable as the loader."""
    assert exec_load_settings is load_settings
    assert signal_load_settings is load_settings


def test_per_account_overlay_differs_from_global(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "SETTINGS_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({"min_trade_size": 200.0}))
    (tmp_path / "settings_4.json").write_text(
        json.dumps({"min_trade_size": 500.0, "trading_capital_cap": 436.0})
    )

    account = load_settings(account_id=4)
    glob = load_settings(account_id=None)

    assert account["min_trade_size"] == 500.0
    assert account["trading_capital_cap"] == 436.0
    assert glob["min_trade_size"] == 200.0
    assert account != glob


def test_active_account_context_resolves_bare_load(tmp_path, monkeypatch):
    """set_active_account binds a bare load_settings() to that account's overlay.

    Without this, account-agnostic plugin call sites (e.g. the AI strategy's
    _buy_threshold) read global settings.json — so settings_4's buy_threshold=60
    was shadowed by global 85 and no ride-winners BUY ever fired.
    """
    from ibkr_core.features.settings.service import set_active_account
    monkeypatch.setattr(service, "SETTINGS_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({"buy_threshold": 85}))
    (tmp_path / "settings_4.json").write_text(json.dumps({"buy_threshold": 60}))
    (tmp_path / "settings_7.json").write_text(json.dumps({"buy_threshold": 50}))
    try:
        # No context bound ⇒ global.
        set_active_account(None)
        assert load_settings()["buy_threshold"] == 85
        # Bound ⇒ that account's overlay, even with no explicit arg.
        set_active_account(4)
        assert load_settings()["buy_threshold"] == 60
        # An explicit account_id still wins over the bound context.
        assert load_settings(account_id=7)["buy_threshold"] == 50
    finally:
        set_active_account(None)  # never leak context into other tests


def test_signal_and_exec_paths_load_identical_effective_settings(tmp_path, monkeypatch):
    """The dispatch/signal layer and Trader.execute_trade must agree byte-for-byte
    for the same account_id — the property that prevents B1-style cap/stop drift."""
    monkeypatch.setattr(service, "SETTINGS_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({"min_trade_size": 100.0}))
    (tmp_path / "settings_4.json").write_text(
        json.dumps({"min_trade_size": 500.0, "trading_capital_cap": 436.0,
                    "trailing_stop_pct": 25.0, "stop_loss_pct": 8.0})
    )

    assert signal_load_settings(4) == exec_load_settings(4)
    # And both reflect the per-account overlay, not the global file.
    assert exec_load_settings(4)["trading_capital_cap"] == 436.0


# ---------------------------------------------------------------------------
# (b) Schema validation — type-invalid known key + unknown plugin key
# ---------------------------------------------------------------------------

def test_type_invalid_known_key_falls_back_to_default_and_logs(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(service, "SETTINGS_DIR", str(tmp_path))
    (tmp_path / "settings_9.json").write_text(json.dumps({"trailing_stop_pct": "oops"}))

    with caplog.at_level(logging.CRITICAL, logger="ibkr_core.features.settings.service"):
        result = load_settings(account_id=9)  # must NOT raise

    # Bad value reverts to the field default rather than halting the loop.
    assert result["trailing_stop_pct"] == Settings().trailing_stop_pct
    assert any(
        rec.levelno == logging.CRITICAL and "trailing_stop_pct" in rec.getMessage()
        for rec in caplog.records
    )


def test_loader_never_raises_on_multiple_bad_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "SETTINGS_DIR", str(tmp_path))
    (tmp_path / "settings_9.json").write_text(
        json.dumps({"trailing_stop_pct": "oops", "max_positions": "lots",
                    "min_trade_size": "free"})
    )

    result = load_settings(account_id=9)

    assert result["trailing_stop_pct"] == Settings().trailing_stop_pct
    assert result["max_positions"] == Settings().max_positions
    assert result["min_trade_size"] == Settings().min_trade_size


def test_unknown_plugin_key_preserved_and_warned(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(service, "SETTINGS_DIR", str(tmp_path))
    # supervised_active / ev_auto_tune are written by the private AI plugin and are
    # NOT in core's Settings model — they must survive a core load untouched.
    (tmp_path / "settings_9.json").write_text(
        json.dumps({"supervised_active": True, "ev_auto_tune": True})
    )
    service._warned_unknown_keys.clear()  # ensure the once-per-process warning fires

    with caplog.at_level(logging.WARNING, logger="ibkr_core.features.settings.service"):
        result = load_settings(account_id=9)

    assert result["supervised_active"] is True
    assert result["ev_auto_tune"] is True
    assert any(
        rec.levelno == logging.WARNING and "supervised_active" in rec.getMessage()
        for rec in caplog.records
    )


def test_promoted_atr_fields_are_first_class(tmp_path, monkeypatch):
    """atr_stop_multiplier / atr_regime_scaling are now model fields (core read
    them off-model before). Defaults present and overlays honored + type-checked."""
    monkeypatch.setattr(service, "SETTINGS_DIR", str(tmp_path))
    result = load_settings(account_id=None)
    assert result["atr_stop_multiplier"] == 2.5
    assert result["atr_regime_scaling"] is True

    (tmp_path / "settings_4.json").write_text(json.dumps({"atr_stop_multiplier": 3.0}))
    assert load_settings(account_id=4)["atr_stop_multiplier"] == 3.0


# ---------------------------------------------------------------------------
# (c) Static guard — no bare loader call in trading code
# ---------------------------------------------------------------------------

_BARE_LOADER = re.compile(r"_?load_settings\(\s*\)")


def test_no_bare_loader_call_in_trading_code():
    """Every settings read in trading/ must pass account_id. Tests are excluded:
    the only bare-form occurrence is a docstring in trading/tests/test_trader.py."""
    trading_dir = os.path.join(
        os.path.dirname(os.path.dirname(service.__file__)), "trading"
    )
    offenders = []
    for root, dirs, files in os.walk(trading_dir):
        if "tests" in root.split(os.sep):
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path) as f:
                for lineno, line in enumerate(f, start=1):
                    if _BARE_LOADER.search(line):
                        offenders.append(f"{path}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Bare load_settings()/_load_settings() in trading code — pass account_id:\n"
        + "\n".join(offenders)
    )
