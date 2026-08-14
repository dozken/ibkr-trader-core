"""Tests for the canonical named strategy profiles (profiles.py).

These assert every profile is expressed in valid Settings field names and
round-trips cleanly through the Settings model, plus the ride-winners values
and the backtest-kwargs name mapping.
"""

from ibkr_core.features.settings.profiles import (
    PROFILES,
    RIDE_WINNERS,
    StrategyProfile,
    get_profile,
)
from ibkr_core.features.settings.service import Settings


def test_profiles_use_only_settings_field_names():
    valid = set(Settings.model_fields)
    for name, profile in PROFILES.items():
        unknown = set(profile.to_settings_overlay()) - valid
        assert not unknown, f"{name} overlay has non-Settings keys: {unknown}"


def test_profiles_load_into_settings_and_round_trip():
    for name, profile in PROFILES.items():
        overlay = profile.to_settings_overlay()
        settings = Settings(**overlay)  # must not raise on any known key
        dumped = settings.model_dump()
        for key, value in overlay.items():
            assert dumped[key] == value, f"{name}: {key} {dumped[key]!r} != {value!r}"


def test_ride_winners_overlay_values():
    overlay = RIDE_WINNERS.to_settings_overlay()
    assert overlay["buy_threshold"] == 60
    assert overlay["rerate_sell_threshold"] == 35
    assert overlay["auto_execute_threshold"] == 60
    assert overlay["require_pullback_entry"] is False
    assert overlay["stop_loss_pct"] == 8.0
    assert overlay["take_profit_pct"] == 500.0
    assert overlay["trailing_stop_pct"] == 25.0
    assert overlay["use_trailing_stop"] is True
    assert overlay["use_atr_stops"] is False
    assert overlay["bracket_exits"] is False
    # Backtest-parity sizing (see profiles.py): uncapped capital, 15 x 8%.
    assert overlay["trading_capital_cap"] is None
    assert overlay["max_positions"] == 15
    assert overlay["max_position_size_pct"] == 8.0
    # Target deliberately above the cap: min(target, max) makes it a flat 8%.
    assert overlay["position_size_pct"] == 25.0
    # 3650 == the stale-thesis exit is OFF, matching a backtest that models none.
    assert overlay["time_exit_days"] == 3650
    assert overlay["use_kelly_sizing"] is True
    assert overlay["use_limit_orders"] is True
    assert overlay["limit_order_slippage_pct"] == 0.3


def test_ride_winners_backtest_kwargs_mapping():
    kw = RIDE_WINNERS.to_backtest_kwargs()
    assert kw["buy_threshold"] == 60.0
    assert kw["sell_threshold"] == 35.0           # rerate_sell_threshold -> sell_threshold
    assert kw["sizing_mode"] == "kelly"            # use_kelly_sizing -> sizing_mode
    assert kw["max_positions"] == 15
    assert kw["max_position_size_pct"] == 8.0
    assert kw["stop_loss_pct"] == 8.0
    assert kw["take_profit_pct"] == 500.0


def test_sizing_mode_flat_when_kelly_disabled():
    flat = StrategyProfile(**{**RIDE_WINNERS.model_dump(), "use_kelly_sizing": False})
    assert flat.to_backtest_kwargs()["sizing_mode"] == "flat"


def test_get_profile_known_and_unknown():
    assert get_profile("ride_winners") is RIDE_WINNERS
    try:
        get_profile("does_not_exist")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown profile")
