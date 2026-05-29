from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone
from ibkr_core.core.state import TradeState

Base = declarative_base()

def get_utc_now():
    return datetime.now(timezone.utc)


class Account(Base):
    """
    IBKR sub-account configuration. One row per trading account.
    """
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)
    ibkr_account_id = Column(String, index=True)  # e.g. "DU1234567"
    host = Column(String, default="127.0.0.1", nullable=False)
    port = Column(Integer, default=7497, nullable=False)
    client_id = Column(Integer, default=1, nullable=False)
    is_paper = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    read_only = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)

    def __repr__(self):
        return f"<Account(id={self.id}, label='{self.label}', port={self.port})>"

class AuditLog(Base):
    """
    Immutable compliance snapshots for every trade.
    Ref: AUDIT_LOG.md Section 1 & 2.
    Cite: AGENT.md - Transparency: Every trade must have a corresponding "Compliance Snapshot".
    """
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=get_utc_now, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    action = Column(String, nullable=False)  # BUY, SELL, etc.
    shariah_status = Column(String, nullable=False)  # COMPLIANT, NON_COMPLIANT
    data_source = Column(String)
    metrics = Column(JSON, nullable=False)  # Snapshot of AAOIFI ratios
    business_activity = Column(String)
    ibkr_order_id = Column(Integer, index=True)
    
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)

    # Cryptographic Audit Integrity
    hash = Column(String, index=True)
    previous_hash = Column(String)

    def __repr__(self):
        return f"<AuditLog(symbol='{self.symbol}', action='{self.action}', hash='{self.hash[:8] if self.hash else 'None'}')>"

class PurificationHistory(Base):
    """
    Log of dividend purification and donation proofs.
    Ref: AUDIT_LOG.md Section 3.
    """
    __tablename__ = "purification_history"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    dividend_amount = Column(Float, nullable=False)
    purification_amount = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=get_utc_now, nullable=False)
    donation_receipt_link = Column(String, nullable=True)
    
    def __repr__(self):
        return f"<PurificationHistory(symbol='{self.symbol}', amount={self.purification_amount})>"

class TradeHistory(Base):
    """
    Record of all trade executions and their states.
    Track C requirement per PARALLEL_WORKFLOW.md.
    """
    __tablename__ = "trade_history"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    quantity = Column(Float, nullable=False)
    side = Column(String, nullable=False)  # BUY or SELL
    order_type = Column(String, default="MKT")
    state = Column(SQLEnum(TradeState), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    ibkr_order_id = Column(Integer, index=True)
    fill_price = Column(Float)
    commission = Column(Float)
    signal_price = Column(Float)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    @property
    def slippage_delta(self):
        if self.fill_price is not None and self.signal_price is not None and self.signal_price != 0:
            return round(self.fill_price - self.signal_price, 4)
        return None

    def __repr__(self):
        return f"<TradeHistory(symbol='{self.symbol}', side='{self.side}', state='{self.state}')>"

class PositionCompliance(Base):
    """
    Historical compliance status of current holdings, refreshed daily.
    Ref: ROADMAP.md Phase 4.
    """
    __tablename__ = "position_compliance"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    timestamp = Column(DateTime, default=get_utc_now, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    shariah_status = Column(String, nullable=False)
    metrics = Column(JSON, nullable=False)
    is_active_holding = Column(Boolean, default=True)

    def __repr__(self):
        return f"<PositionCompliance(symbol='{self.symbol}', status='{self.shariah_status}', date='{self.timestamp}')>"

class PortfolioSnapshot(Base):
    """
    Time-series snapshots of the total portfolio value.
    Used for historical equity curves.
    """
    __tablename__ = "portfolio_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    timestamp = Column(DateTime, default=get_utc_now, index=True, nullable=False)
    total_value = Column(Float, nullable=False)      # Net Liquidation Value
    cash_balance = Column(Float, nullable=False)    # Available Funds
    unrealized_pnl = Column(Float, nullable=False)
    
    def __repr__(self):
        return f"<PortfolioSnapshot(date='{self.timestamp}', value=${self.total_value})>"

class FeatureSnapshot(Base):
    """
    Point-in-time alpha features for ML training.
    Ref: Intelligence Depth (Path 2)
    """
    __tablename__ = "feature_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=get_utc_now, index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    features = Column(JSON, nullable=False)  # Momentum, Quality, Sentiment, etc.
    price = Column(Float, nullable=False)    # Current price at snapshot
    
    def __repr__(self):
        return f"<FeatureSnapshot(symbol='{self.symbol}', date='{self.timestamp}')>"

class TwapExecution(Base):
    """
    Tracks TWAP slice progress so remaining slices survive app restarts.
    status: RUNNING | COMPLETED | FAILED
    """
    __tablename__ = "twap_executions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    slice_qty = Column(Float, nullable=False)
    n_slices = Column(Integer, nullable=False)
    slices_submitted = Column(Integer, default=0, nullable=False)
    interval_secs = Column(Integer, nullable=False)
    stop_price = Column(Float, nullable=True)
    tp_price = Column(Float, nullable=True)
    trailing_amount = Column(Float, nullable=True)
    exchange = Column(String, nullable=False)
    status = Column(String, default="RUNNING", nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)

    def __repr__(self):
        return f"<TwapExecution(symbol='{self.symbol}', {self.slices_submitted}/{self.n_slices}, status='{self.status}')>"


class PendingSignal(Base):
    """
    Signals awaiting human approval. Persisted so they survive app restarts.
    Resolved=True means approved or rejected (or expired).
    """
    __tablename__ = "pending_signals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    action = Column(String, nullable=False)  # BUY or SELL
    confidence = Column(Float, nullable=False)
    sentiment_score = Column(Float, nullable=True)
    reasoning = Column(String, nullable=True)
    exchange = Column(String, nullable=True)
    source = Column(String, nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<PendingSignal(symbol='{self.symbol}', action='{self.action}', resolved={self.resolved})>"


class SignalLog(Base):
    """Records every generated signal for outcome tracking."""
    __tablename__ = "signal_logs"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    action = Column(String, nullable=False)       # BUY | SELL | HOLD
    confidence = Column(Float, nullable=False)
    f_score = Column(Float, nullable=True)
    t_score = Column(Float, nullable=True)
    s_score = Column(Float, nullable=True)
    features = Column(JSON, nullable=True)        # full feature vector at signal time (for supervised training)
    signal_price = Column(Float, nullable=True)   # price at signal time (filled async)
    outcome_7d_pct = Column(Float, nullable=True) # % return 7 days later
    outcome_30d_pct = Column(Float, nullable=True)
    outcome_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)


# Note: All tables above are intended to be APPEND-ONLY to maintain audit integrity.
# Ref: AUDIT_LOG.md Section 2 - "The audit_logs table must be append-only."
