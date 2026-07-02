from typing import Any, Dict, Optional

from fastapi import APIRouter

from ibkr_core.features.settings.service import Settings, load_settings, save_settings
from pydantic import create_model

router = APIRouter(prefix="/api/settings", tags=["settings"])

# All-optional mirror of Settings used for PATCH (partial update) requests.
# Generated from Settings so new fields are PATCHable automatically — a
# hand-maintained copy silently dropped 33 of 72 fields (PATCH returned 200
# and did nothing for e.g. buy_threshold, enabled_regions, supervised_weight).
# Note: exclude_none in the handler means a field cannot be PATCHed *to* null.
PartialSettings = create_model(
    "PartialSettings",
    **{
        name: (Optional[field.annotation], None)
        for name, field in Settings.model_fields.items()
    },
)


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
