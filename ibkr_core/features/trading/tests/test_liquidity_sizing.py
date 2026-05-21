import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from ibkr_core.features.trading.trader import Trader, _MIN_FRACTIONAL_QTY
from ibkr_core.core.state import TradeState
from ibkr_core.features.trading.schemas import TradeCreate
from ibkr_core.features.compliance.schemas import ComplianceStatus

_COMPLIANT = ComplianceStatus(
    symbol="AAPL", sector="Technology", is_compliant=True,
    debt_to_mkt_cap=0.1, cash_to_mkt_cap=0.1, impure_revenue_pct=0.01
)
_SETTINGS = {
    "min_trade_size": 10.0,
    "cash_reserve_pct": 5.0,
    "max_position_size_pct": 10.0,
    "max_slippage_pct": 0.5,
    "max_liquidity_pct": 1.0,
    "twap_threshold_pct": 100.0,  # disable TWAP — these tests focus on liquidity downsizing
}

class TestLiquiditySizing(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_worker = MagicMock()
        self.mock_worker.get_market_data = AsyncMock(
            return_value={"bid": 149.9, "ask": 150.1, "last": 150.0, "volume": 1_000_000}
        )
        self.mock_worker.get_avg_volume_20d = AsyncMock(return_value=1000) # Very low volume to trigger limit
        self.mock_worker.get_last_price = AsyncMock(return_value=150.0)
        self.mock_worker.get_available_funds.return_value = 10000.0
        self.mock_worker.get_net_liquidation.return_value = 10000.0
        self.mock_worker.get_positions.return_value = []
        self.mock_worker.place_bracket_order = AsyncMock(return_value=42)
        self.mock_worker.place_order = AsyncMock(return_value=42)

        self.trader = Trader(self.mock_worker)
        self.patcher_db = patch('ibkr_core.features.trading.trader.SessionLocal')
        self.mock_session_local = self.patcher_db.start()
        self.mock_db = MagicMock()
        self.mock_session_local.return_value = self.mock_db
        self.patcher_settings = patch('ibkr_core.features.trading.trader._load_settings',
                                      return_value=_SETTINGS)
        self.patcher_settings.start()

    def tearDown(self):
        self.patcher_db.stop()
        self.patcher_settings.stop()

    async def test_downsizes_on_liquidity_risk(self):
        # quantity = 5. avg_vol = 100. 5/100 = 5% > 1%.
        # limit is 1% of 100 = 1.0.
        # It should downsize to 1.0.
        self.mock_worker.get_avg_volume_20d = AsyncMock(return_value=100)
        trade_req = TradeCreate(symbol="AAPL", quantity=5, side="BUY")
        trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)
        
        self.assertEqual(trade.quantity, 1.0)
        self.assertEqual(trade.state, TradeState.SUBMITTED)
        self.mock_worker.place_bracket_order.assert_called()
        
        # Verify it passed 1.0 to place_bracket_order
        args, _ = self.mock_worker.place_bracket_order.call_args
        self.assertEqual(args[0].quantity, 1.0)

    async def test_rejects_if_downsized_below_minimum(self):
        # limit is 1% of 0.05 = 0.0005 < 0.001
        self.mock_worker.get_avg_volume_20d = AsyncMock(return_value=0.05)
        trade_req = TradeCreate(symbol="AAPL", quantity=1, side="BUY")
        trade = await self.trader.execute_trade(trade_req, pre_screened=_COMPLIANT)
        
        self.assertEqual(trade.state, TradeState.REJECTED_FUNDS)
        self.mock_worker.place_bracket_order.assert_not_called()
