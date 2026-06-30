import contextvars
import json
import logging
import os
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)

# Unknown keys already warned about, keyed by (account_id, key). Loaders run every
# cycle, so we surface each unknown key once per process instead of spamming logs.
_warned_unknown_keys: set = set()

# Per-task active account. A per-account loop binds this once at startup so that
# account-AGNOSTIC call sites — notably the AI strategy's BUY-threshold gating,
# which has no account_id in scope — resolve a bare load_settings() to that
# account's settings_{id}.json instead of plain global settings.json. ContextVars
# are task-local (and copied into asyncio.to_thread), so each account's loop task
# keeps its own binding with no cross-talk. Unset (e.g. API handlers) ⇒ global.
_active_account_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "_active_account_id", default=None
)


def set_active_account(account_id: Optional[int]) -> None:
    """Bind the active account for the current task's settings context.

    Call once at the top of a per-account loop. A subsequent load_settings() with
    no explicit account_id then layers settings_{account_id}.json over global,
    closing the config-drift gap for code that can't thread account_id (e.g. a
    plugin strategy). Passing an explicit account_id to load_settings still wins.
    """
    _active_account_id.set(account_id)

SETTINGS_DIR = os.environ.get("SETTINGS_DIR", os.path.join(os.path.dirname(__file__), "../../../data"))
# Legacy single-file path — kept for callers that haven't migrated
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

RISK_STOP_TAKE: dict = {
    "CONSERVATIVE": (3.0, 6.0),
    "BALANCED":     (5.0, 10.0),
    "AGGRESSIVE":   (8.0, 16.0),
}


class Settings(BaseModel):
    # extra='allow' preserves keys core does not define — notably the private AI
    # plugin's flags (supervised_active, ev_auto_tune, …). This also fixes the
    # router round-trip that previously dropped them on every settings save.
    model_config = ConfigDict(extra="allow")

    min_trade_size: float = 100.0
    max_commission_pct: float = 0.5
    cash_reserve_pct: float = 10.0
    max_position_size_pct: float = 15.0
    max_sector_exposure_pct: float = 30.0
    min_sector_count: int = 4
    max_positions: int = 15
    target_weights: dict[str, float] = {}
    trading_mode: Literal["MANUAL", "AUTO"] = "AUTO"
    settlement_strictness: Literal["CONSTRUCTIVE", "PHYSICAL_T2"] = "PHYSICAL_T2"
    purification_automation: Literal["MANUAL", "AUTO_CALC"] = "AUTO_CALC"
    ratio_buffer: float = 2.0
    risk_profile: Literal["CONSERVATIVE", "BALANCED", "AGGRESSIVE"] = "BALANCED"
    sector_exclusion: List[str] = [
        "Gambling", "Alcohol", "Tobacco", "Defense", "Weapons",
        "Adult Content", "Pork", "Conventional Finance", "Insurance",
    ]
    rebalance_frequency: Literal["DAILY", "WEEKLY"] = "DAILY"
    critical_auto_sell: bool = True
    alert_channels: List[str] = ["telegram"]
    # Per-account notification toggles. Default True = current behavior.
    # Set False on a paper account's settings_{id}.json to mute its buy/sell pushes.
    notify_trade_fills: bool = True  # 'Order ...', 'Trade Filled', 'Trade Cancelled'
    notify_signals: bool = True      # 'BUY/SELL Signal' recommendation alerts
    enable_halal_drip: bool = True
    watchlist: List[str] = [
        # Technology
        "AAPL", "MSFT", "AMZN",
        # Technology — Asia
        "7203.T", "6758.T", "6367.T", "0700.HK", "9988.HK", "005930.KS",
        # Technology — India
        "TCS.NS", "INFY.NS",
        # Healthcare
        "JNJ", "UNH", "ABT", "4519.T",
        # Industrials
        "HON", "CAT", "6301.T",
        # Consumer Staples
        "PG", "NESN.SW",
        # Energy (halal-screened at runtime)
        "XOM", "2222.SR",
        # Basic Materials
        "NEM", "5401.T",
    ]
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    # Trailing-stop distance from high-water mark, as a %. Distinct from the
    # hard stop_loss_pct floor: lets winners run (e.g. trail 25%) while still
    # cutting losers at a tight fixed stop (e.g. 8%). Falls back to stop_loss_pct
    # when unset, preserving prior single-knob behavior.
    trailing_stop_pct: Optional[float] = None
    # Cap the capital the bot sizes positions off, ignoring balance beyond it.
    # Lets a huge (e.g. $1B paper) account be tested as if it held only $cap.
    # When set, sizing treats net-liq as min(real, cap) and available cash as
    # (cap − already-deployed). Unset = use the real account balance.
    trading_capital_cap: Optional[float] = None
    auto_execute_threshold: int = 60
    signal_min_confidence: int = 30
    auto_compliance_check: bool = True
    compliance_check_interval_hours: int = 12
    cash_sweep_enabled: bool = True
    cash_sweep_interval_min: int = 30
    use_atr_stops: bool = True
    # Base ATR multiplier for the volatility stop, widened by VIX regime when
    # atr_regime_scaling is on. Read by loops._regime_atr_multiplier; promoted to
    # first-class fields so core stops reading keys absent from its own model.
    atr_stop_multiplier: float = 2.5
    atr_regime_scaling: bool = True
    enable_discovery_auto: bool = True
    discovery_interval_hours: int = 6
    # Global trading: when True, main_loop pulls open-market halal symbols
    # from REGIONAL_HALAL into each cycle (in addition to watchlist).
    use_global_universe: bool = False
    enabled_regions: Optional[List[str]] = None  # None = all 33 regions
    global_universe_cap_per_cycle: int = 60
    max_slippage_pct: float = 0.5
    max_liquidity_pct: float = 1.0
    dry_run: bool = False
    max_drawdown_pct: float = 15.0
    max_daily_loss_pct: float = 5.0
    trading_start_offset_min: int = 30
    trading_end_offset_min: int = 30
    twap_threshold_pct: float = 0.5
    twap_slices: int = 5
    twap_interval_secs: int = 60
    require_pullback_entry: bool = True
    re_entry_cooldown_days: int = 14
    use_trailing_stop: bool = True
    # When True (default), BUYs are placed as native IBKR bracket orders with
    # broker-side stop/take-profit children. When False, BUYs are plain limit
    # entries and the main loop drives exits (trailing_stop_pct from HWM +
    # stop_loss_pct floor). Loop-managed exits are REQUIRED for the % trailing
    # stop to run: a resting bracket SELL child parks the symbol in pending_sell
    # and suppresses the loop's exit checks. Set False for the ride-winners
    # config (use_atr_stops=False + use_trailing_stop=True).
    bracket_exits: bool = True
    time_exit_days: int = 45
    time_exit_min_gain_pct: float = 5.0
    partial_profit_pct: float = 10.0
    partial_profit_fraction: float = 0.5
    use_kelly_sizing: bool = True
    use_limit_orders: bool = False
    limit_order_slippage_pct: float = 0.1
    # Some IBKR accounts cannot place fractional-sized orders via API (Error 10243).
    # Default True preserves fractional sizing; set False to floor BUYs to whole
    # shares (see Trader.execute_trade whole-share fallback).
    allow_fractional_shares: bool = True
    max_correlation: float = 0.85
    rl_weight: float = 0.2
    rerate_sell_threshold: int = 35
    max_vix_for_buys: float = 30.0
    position_size_pct: float = 5.0
    trading_paused: bool = False
    # Supervised alpha model (trained on realized SignalLog outcomes)
    supervised_weight: float = 0.3
    rl_enabled: bool = True
    # EV-optimal BUY cutoff derived from SignalLog history; None = region default
    buy_threshold: Optional[int] = None


def _settings_path(account_id: Optional[int]) -> str:
    if account_id is not None:
        return os.path.join(SETTINGS_DIR, f"settings_{account_id}.json")
    return os.path.join(SETTINGS_DIR, "settings.json")


def _validate_settings(merged: dict, account_id: Optional[int]) -> dict:
    """Coerce/validate a raw merged settings dict through the Settings model.

    Policy for the per-account config choke point:
      * Unknown keys (e.g. the private AI plugin's supervised_active / ev_auto_tune)
        are PRESERVED via extra='allow' and logged once at WARNING — never dropped,
        never fatal — so genuine typos surface without breaking the open-core plugin.
      * Known keys with a type-invalid value are logged at CRITICAL and reset to the
        field's default. This loader NEVER raises on a bad settings_{id}.json: an
        unmanaged open position is worse than one ignored setting, so we degrade
        gracefully and alert instead of halting the account loop.
    """
    known = set(Settings.model_fields)
    defaults = Settings().model_dump()

    for key in merged:
        if key not in known:
            cache_key = (account_id, key)
            if cache_key not in _warned_unknown_keys:
                _warned_unknown_keys.add(cache_key)
                logger.warning(
                    "settings_%s.json: unknown key %r (preserved, unvalidated)",
                    account_id, key,
                )

    attempt = dict(merged)
    # Reset offending known keys to their default until the model validates.
    for _ in range(len(known) + 1):
        try:
            return Settings(**attempt).model_dump()
        except ValidationError as exc:
            recovered = False
            for err in exc.errors():
                key = err["loc"][0] if err["loc"] else None
                if key in known and attempt.get(key) != defaults.get(key):
                    logger.critical(
                        "settings_%s.json: invalid value %r for %r (%s) — "
                        "falling back to default %r",
                        account_id, attempt.get(key), key, err.get("msg"), defaults.get(key),
                    )
                    attempt[key] = defaults[key]
                    recovered = True
            if not recovered:
                # Unrecoverable by resetting known keys (should not happen under
                # extra='allow'); drop the offending keys defensively rather than raise.
                for err in exc.errors():
                    loc = err["loc"][0] if err["loc"] else None
                    attempt.pop(loc, None)

    # Last resort: known-key defaults plus any preserved unknown keys.
    safe = dict(defaults)
    safe.update({k: v for k, v in merged.items() if k not in known})
    return safe


def load_settings(account_id: Optional[int] = None) -> dict:
    """
    Load settings with layered override:
      1. Model defaults
      2. Global settings.json
      3. Account-specific settings_{account_id}.json  (if account_id given)

    The merged result is schema-validated (see _validate_settings): known keys are
    type-checked and bad values fall back to defaults; unknown plugin keys survive.

    NOTE: trading code MUST pass account_id so the signal path and execution path
    read the SAME effective per-account config. A bare load_settings() in
    ibkr_core/features/trading/ is config drift and is banned by CI.

    When account_id is omitted it falls back to the task-bound active account (see
    set_active_account), so account-agnostic plugin call sites still get the right
    per-account overlay; with neither set it loads plain global settings.
    """
    if account_id is None:
        account_id = _active_account_id.get()

    base = Settings().model_dump()

    global_path = os.path.join(SETTINGS_DIR, "settings.json")
    if os.path.exists(global_path):
        with open(global_path) as f:
            base.update(json.load(f))

    if account_id is not None:
        account_path = _settings_path(account_id)
        if os.path.exists(account_path):
            with open(account_path) as f:
                base.update(json.load(f))

    return _validate_settings(base, account_id)


def save_settings(data: dict, account_id: Optional[int] = None) -> None:
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    path = _settings_path(account_id)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
