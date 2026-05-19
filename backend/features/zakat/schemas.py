from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import Optional

class ZakatCalculation(BaseModel):
    zakatable_assets_value: float
    zakat_rate: float
    zakat_due: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: Optional[str] = None
