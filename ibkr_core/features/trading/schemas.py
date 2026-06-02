from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from ibkr_core.core.state import TradeState
from ibkr_core.core.websocket import WSBaseMessage
from ibkr_core.features.compliance.schemas import ComplianceStatus


class TradeSignal(BaseModel):
    symbol: str
    sentiment_score: float  # -1.0 to 1.0
    confidence: int         # 0-100
    action: Literal['BUY', 'SELL', 'HOLD']
    reasoning: str
    f_score: Optional[int] = None   # Fundamental score
    t_score: Optional[int] = None   # Technical score
    s_score: Optional[int] = None   # Sentiment score
    vix_tier: str = "CALM"          # "CALM" | "ELEVATED" | "CRISIS"
    timestamp: datetime = datetime.now()


class AnalystConsensus(BaseModel):
    symbol: str
    recommendation: str      # "strong_buy", "buy", "hold", "sell", "strong_sell", "none"
    mean_score: float        # 1=Strong Buy … 5=Strong Sell (yfinance scale)
    num_analysts: int
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    target_mean: Optional[float] = None
    buy_count: int = 0
    hold_count: int = 0
    sell_count: int = 0


class TradeBase(BaseModel):
    symbol: str
    quantity: float = 0.0  # 0 = auto-size via position sizing logic
    side: str  # 'BUY' or 'SELL'
    order_type: str = 'MKT'


class TradeCreate(TradeBase):
    confidence: int = 50  # signal confidence 0-100, used for Kelly sizing


class Trade(TradeBase):
    id: Optional[int] = None
    state: TradeState
    compliance_snapshot: Optional[ComplianceStatus] = None
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    ibkr_order_id: Optional[int] = None
    fill_price: Optional[float] = None
    commission: Optional[float] = None
    signal_price: Optional[float] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)


class PendingSignalPayload(BaseModel):
    symbol: str
    action: str
    confidence: int
    sentiment_score: float
    reasoning: str
    exchange: str
    source: Optional[str] = None
    account_id: Optional[int] = None


class PendingSignalMessage(WSBaseMessage):
    type: Literal["pending_signal"] = "pending_signal"
    payload: PendingSignalPayload
