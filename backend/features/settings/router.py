from typing import Any, Dict, Optional, List, Literal

from fastapi import APIRouter

from backend.features.settings.service import Settings, load_settings, save_settings
from pydantic import BaseModel

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PartialSettings(BaseModel):
    """All-optional mirror of Settings used for PATCH (partial update) requests."""

    min_trade_size: Optional[float] = None
    max_commission_pct: Optional[float] = None
    cash_reserve_pct: Optional[float] = None
    max_position_size_pct: Optional[float] = None
    max_sector_exposure_pct: Optional[float] = None
    max_positions: Optional[int] = None
    target_weights: Optional[Dict[str, float]] = None
    trading_mode: Optional[Literal["MANUAL", "AUTO"]] = None
    settlement_strictness: Optional[Literal["CONSTRUCTIVE", "PHYSICAL_T2"]] = None
    purification_automation: Optional[Literal["MANUAL", "AUTO_CALC"]] = None
    ratio_buffer: Optional[float] = None
    risk_profile: Optional[Literal["CONSERVATIVE", "BALANCED", "AGGRESSIVE"]] = None
    sector_exclusion: Optional[List[str]] = None
    rebalance_frequency: Optional[Literal["DAILY", "WEEKLY"]] = None
    critical_auto_sell: Optional[bool] = None
    alert_channels: Optional[List[str]] = None
    watchlist: Optional[List[str]] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    auto_execute_threshold: Optional[int] = None
    signal_min_confidence: Optional[int] = None
    auto_compliance_check: Optional[bool] = None
    compliance_check_interval_hours: Optional[int] = None
    cash_sweep_enabled: Optional[bool] = None
    cash_sweep_interval_min: Optional[int] = None
    use_atr_stops: Optional[bool] = None
    enable_halal_drip: Optional[bool] = None
    enable_discovery_auto: Optional[bool] = None
    discovery_interval_hours: Optional[int] = None
    dry_run: Optional[bool] = None
    position_size_pct: Optional[float] = None
    trading_paused: Optional[bool] = None


@router.get("", response_model=Settings)
def get_settings(account_id: Optional[int] = None) -> Settings:
    return Settings(**load_settings(account_id=account_id))


@router.post("", response_model=Settings)
def update_settings(settings: Settings, account_id: Optional[int] = None) -> Settings:
    save_settings(settings.model_dump(), account_id=account_id)
    return settings


@router.patch("", response_model=Settings)
def patch_settings(partial: PartialSettings, account_id: Optional[int] = None) -> Settings:
    """Merge only the provided fields into the current settings and save."""
    current = load_settings(account_id=account_id)
    updates: Dict[str, Any] = partial.model_dump(exclude_none=True)
    current.update(updates)
    validated = Settings(**current)
    save_settings(validated.model_dump(), account_id=account_id)
    return validated


@router.post("/pause", response_model=Settings)
def pause_trading(account_id: Optional[int] = None) -> Settings:
    current = load_settings(account_id=account_id)
    current["trading_paused"] = True
    validated = Settings(**current)
    save_settings(validated.model_dump(), account_id=account_id)
    return validated


@router.post("/resume", response_model=Settings)
def resume_trading(account_id: Optional[int] = None) -> Settings:
    current = load_settings(account_id=account_id)
    current["trading_paused"] = False
    validated = Settings(**current)
    save_settings(validated.model_dump(), account_id=account_id)
    return validated
