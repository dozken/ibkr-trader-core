import json
import os
from typing import List, Literal, Optional

from pydantic import BaseModel

SETTINGS_DIR = os.environ.get("SETTINGS_DIR", os.path.join(os.path.dirname(__file__), "../../../data"))
# Legacy single-file path — kept for callers that haven't migrated
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

RISK_STOP_TAKE: dict = {
    "CONSERVATIVE": (3.0, 6.0),
    "BALANCED":     (5.0, 10.0),
    "AGGRESSIVE":   (8.0, 16.0),
}


class Settings(BaseModel):
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
    auto_execute_threshold: int = 60
    signal_min_confidence: int = 30
    auto_compliance_check: bool = True
    compliance_check_interval_hours: int = 12
    cash_sweep_enabled: bool = True
    cash_sweep_interval_min: int = 30
    use_atr_stops: bool = True
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
    time_exit_days: int = 45
    time_exit_min_gain_pct: float = 5.0
    partial_profit_pct: float = 10.0
    partial_profit_fraction: float = 0.5
    use_kelly_sizing: bool = True
    use_limit_orders: bool = False
    limit_order_slippage_pct: float = 0.1
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


def load_settings(account_id: Optional[int] = None) -> dict:
    """
    Load settings with layered override:
      1. Model defaults
      2. Global settings.json
      3. Account-specific settings_{account_id}.json  (if account_id given)
    """
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

    return base


def save_settings(data: dict, account_id: Optional[int] = None) -> None:
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    path = _settings_path(account_id)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
