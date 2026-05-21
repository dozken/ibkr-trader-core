import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import pandas as pd
from ibkr_core.features.portfolio.router import get_portfolio_history
from ibkr_core.core.models import PortfolioSnapshot, TradeHistory, PositionCompliance
from ibkr_core.core.state import TradeState

def _make_snapshot(timestamp, total_value, cash_balance):
    snap = PortfolioSnapshot(
        timestamp=timestamp,
        total_value=total_value,
        cash_balance=cash_balance,
        unrealized_pnl=0.0
    )
    return snap

def _make_trade(symbol, side, quantity, fill_price, timestamp):
    trade = TradeHistory(
        symbol=symbol,
        side=side,
        quantity=quantity,
        fill_price=fill_price,
        state=TradeState.FILLED,
        updated_at=timestamp
    )
    return trade

def _make_compliance(symbol, impure_pct):
    row = PositionCompliance(
        symbol=symbol,
        shariah_status="COMPLIANT",
        metrics={"impure_revenue_pct": impure_pct},
        timestamp=datetime.now()
    )
    return row

class TestPortfolioHistoryPurification(unittest.IsolatedAsyncioTestCase):
    
    @patch("yfinance.download")
    async def test_history_includes_net_purified_value(self, mock_download):
        # Mock benchmark data
        mock_bench = pd.DataFrame({"Close": [100.0, 101.0]}, 
                                  index=[pd.Timestamp("2023-01-01"), pd.Timestamp("2023-01-02")])
        mock_download.return_value = mock_bench
        
        # Snapshots
        snaps = [
            _make_snapshot(datetime(2023, 1, 1, 23, 59), 10000.0, 2000.0),
            _make_snapshot(datetime(2023, 1, 2, 23, 59), 11000.0, 2000.0)
        ]
        
        # Trades: BUY 10 AAPL @ 100 on Jan 1, SELL 10 AAPL @ 120 on Jan 2
        # Realized gain = 200
        trades = [
            _make_trade("AAPL", "BUY", 10, 100.0, datetime(2023, 1, 1, 10, 0)),
            _make_trade("AAPL", "SELL", 10, 120.0, datetime(2023, 1, 2, 10, 0))
        ]
        
        # Compliance: AAPL has 5% impure revenue
        compliance = [_make_compliance("AAPL", 0.05)]
        
        db = MagicMock()
        def _query(model):
            q = MagicMock()
            if model == PortfolioSnapshot:
                q.order_by.return_value.all.return_value = snaps
            elif model == TradeHistory:
                q.filter.return_value.order_by.return_value.all.return_value = trades
            elif model == PositionCompliance:
                q.order_by.return_value.all.return_value = compliance
            return q
        db.query.side_effect = _query
        
        results = await get_portfolio_history(db=db)
        
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIn("net_purified_value", r)
            self.assertLessEqual(r["net_purified_value"], r["total_value"])
            
        # Snapshot 2:
        # Total Value = 11000 (normalized to 110)
        # Zakat: Realized 200 * 0.025 = 5.0
        # Purification: (11000 - 2000) * 0.05 = 450.0
        # Net Value = 11000 - 5.0 - 450.0 = 10545.0
        # Normalized Net = 10545 / 10000 * 100 = 105.45
        
        self.assertAlmostEqual(results[1]["total_value"], 110.0)
        self.assertAlmostEqual(results[1]["net_purified_value"], 105.45)

if __name__ == "__main__":
    unittest.main()
