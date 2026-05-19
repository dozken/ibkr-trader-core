"""Tests for _dispatch_signal cooldown logic — prevents retry storms after IBKR errors."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core.state import TradeState
from backend.features.compliance.schemas import ComplianceStatus
from backend.features.trading.schemas import TradeSignal


_SETTINGS = {
    "signal_min_confidence": 30,
    "auto_execute_threshold": 50,  # trigger auto-execute branch
    "alert_channels": [],
}

_COMPLIANCE = ComplianceStatus(
    symbol="INTC", sector="Technology", is_compliant=True,
    debt_to_mkt_cap=0.1, cash_to_mkt_cap=0.05, impure_revenue_pct=0.0,
)


def _signal(symbol="INTC", action="SELL", confidence=80):
    return TradeSignal(
        symbol=symbol, action=action, confidence=confidence,
        sentiment_score=0.5, reasoning="test", timestamp=datetime.utcnow(),
    )


class TestDispatchCooldown(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.trader = MagicMock()
        self.trader.execute_trade = AsyncMock()
        self.manager = MagicMock()
        self.manager.broadcast = AsyncMock()

    async def test_skip_when_recent_ibkr_error_within_15min(self):
        """Recent IBKR_ERROR on (symbol, side) blocks auto-execute for 15min."""
        from backend.features.trading import loops

        recent_err = MagicMock()
        recent_err.created_at = datetime.utcnow() - timedelta(minutes=5)

        # Mock SessionLocal context manager
        mock_db = MagicMock()
        # First filter() call = IBKR_ERROR query, returns the row
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.side_effect = [recent_err, None]  # err yes, reject no
        mock_db.query.return_value = mock_query
        mock_session_local = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        with patch.object(loops, "SessionLocal", mock_session_local):
            await loops._dispatch_signal(
                _signal(action="SELL"), _COMPLIANCE, "NMS",
                self.trader, self.manager, _SETTINGS,
            )

        self.trader.execute_trade.assert_not_called()

    async def test_skip_when_recent_rejected_funds_buy_within_24h(self):
        """Recent REJECTED_FUNDS BUY blocks auto-execute for 24h."""
        from backend.features.trading import loops

        recent_reject = MagicMock()
        recent_reject.created_at = datetime.utcnow() - timedelta(hours=2)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.side_effect = [None, recent_reject]  # err no, reject yes
        mock_db.query.return_value = mock_query
        mock_session_local = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        with patch.object(loops, "SessionLocal", mock_session_local):
            await loops._dispatch_signal(
                _signal(symbol="NVDA", action="BUY"), _COMPLIANCE, "NMS",
                self.trader, self.manager, _SETTINGS,
            )

        self.trader.execute_trade.assert_not_called()

    async def test_skip_sell_with_zero_quantity(self):
        """SELL with quantity=0 must be skipped (IBKR rejects with Error 321)."""
        from backend.features.trading import loops
        from backend.features.trading.schemas import TradeCreate

        await loops._dispatch_signal(
            _signal(action="SELL"), _COMPLIANCE, "NMS",
            self.trader, self.manager, _SETTINGS,
            trade=TradeCreate(symbol="INTC", quantity=0, side="SELL"),
        )
        self.trader.execute_trade.assert_not_called()

    async def test_proceed_when_no_recent_failures(self):
        """Clean history → auto-execute proceeds normally."""
        from backend.features.trading import loops

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # both queries return None
        mock_db.query.return_value = mock_query
        mock_session_local = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # Stub trader to return a trade-like mock with state
        fake_trade = MagicMock()
        fake_trade.state = TradeState.SUBMITTED
        self.trader.execute_trade.return_value = fake_trade

        with patch.object(loops, "SessionLocal", mock_session_local):
            await loops._dispatch_signal(
                _signal(action="BUY"), _COMPLIANCE, "NMS",
                self.trader, self.manager, _SETTINGS,
            )

        self.trader.execute_trade.assert_called_once()


if __name__ == "__main__":
    unittest.main()
