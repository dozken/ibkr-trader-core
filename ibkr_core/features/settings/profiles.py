"""
Canonical named strategy profiles — the single source of truth for the
"ride-winners" (and any future) deployment shape.

Both the live settings layer (settings_{id}.json overlays) and the backtest
harness (PortfolioBacktestRequest in the private AI plugin) are projections of
these profiles, so changing a profile propagates to both, and a parity test can
assert that a deployed account's settings still match its named profile.

Field names mirror the Settings model (service.py) so a profile maps onto a
settings overlay with NO renaming. The backtest harness happens to use a couple
of differently-named fields (sell_threshold, sizing_mode); those two mismatches
are resolved in ONE place by ``to_backtest_kwargs``.

CORE is the right home: the live trader (core) and the backtest (private,
depends on core) both already import from core, so a single registry here is
importable by everything without a new dependency edge.
"""
from typing import Optional

from pydantic import BaseModel


class StrategyProfile(BaseModel):
    """A named strategy identity, expressed in Settings field names.

    All fields are required so every registered profile is fully specified and
    self-documenting; a missing knob is a loud construction error rather than a
    silent default.
    """

    # Entry / exit thresholds
    buy_threshold: int
    rerate_sell_threshold: int
    auto_execute_threshold: int
    require_pullback_entry: bool
    # Stops / exits
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop_pct: float
    use_trailing_stop: bool
    use_atr_stops: bool
    bracket_exits: bool
    # Sizing
    trading_capital_cap: Optional[float]
    max_positions: int
    max_position_size_pct: float
    position_size_pct: float
    use_kelly_sizing: bool
    # Order routing
    use_limit_orders: bool
    limit_order_slippage_pct: float

    def to_settings_overlay(self) -> dict:
        """Return the profile as a settings_{id}.json overlay.

        Keys already use Settings field names, so this is a plain dump that can
        be layered onto load_settings output / validated against Settings.
        """
        return self.model_dump()

    def to_backtest_kwargs(self) -> dict:
        """Map the profile onto PortfolioBacktestRequest field names.

        Resolves the two name/semantic mismatches between the canonical
        (Settings-named) profile and the backtest request in one place:
            rerate_sell_threshold      -> sell_threshold
            use_kelly_sizing (bool)    -> sizing_mode ("kelly" | "flat")

        Only emits the subset of knobs the backtest engine actually consumes.
        NOTE: trailing_stop_pct, trading_capital_cap and bracket_exits are part
        of the live profile but are NOT modeled by the sim, so they are
        deliberately absent here — param parity does not imply behavioral parity.
        """
        return {
            "buy_threshold": float(self.buy_threshold),
            "sell_threshold": float(self.rerate_sell_threshold),
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_positions": self.max_positions,
            "max_position_size_pct": self.max_position_size_pct,
            "sizing_mode": "kelly" if self.use_kelly_sizing else "flat",
        }


# ── registry ────────────────────────────────────────────────────────────────
# The deployed "ride-winners" profile (paper acct id4 — let winners run on a
# wide trailing stop with a tight hard-stop floor, loop-managed exits, capped
# sizing capital). Mirrors data/settings_4.json; the parity test guards drift.
RIDE_WINNERS = StrategyProfile(
    buy_threshold=60,
    rerate_sell_threshold=35,
    auto_execute_threshold=60,
    require_pullback_entry=False,
    stop_loss_pct=8.0,
    take_profit_pct=500.0,
    trailing_stop_pct=25.0,
    use_trailing_stop=True,
    use_atr_stops=False,
    bracket_exits=False,
    # Whole-share smoke-test cap: with IBKR fractional shares disabled
    # (allow_fractional_shares=false), a $436 cap can't buy 1 whole share of a
    # $200+ mega-cap without breaching the 35% concentration limit, so the test
    # runs at $5000. Restore to 436.0 in lockstep with settings_4.json once
    # fractional shares are enabled for a faithful $436 test.
    trading_capital_cap=5000.0,
    max_positions=4,
    max_position_size_pct=35.0,
    position_size_pct=25.0,
    use_kelly_sizing=True,
    use_limit_orders=True,
    limit_order_slippage_pct=0.3,
)

PROFILES: dict[str, StrategyProfile] = {
    "ride_winners": RIDE_WINNERS,
}


def get_profile(name: str) -> StrategyProfile:
    """Look up a profile by name with a helpful error for typos."""
    try:
        return PROFILES[name]
    except KeyError:
        raise KeyError(
            f"unknown strategy profile {name!r}; known: {sorted(PROFILES)}"
        ) from None
