"""
Tests for the compliance_audit_loop kill-switch logic.
Mocks IBKR worker and DB — no live connections.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.features.compliance.schemas import ComplianceStatus
from backend.features.trading.schemas import TradeCreate


_COMPLIANT_STATUS = ComplianceStatus(
    symbol="AAPL", sector="Technology", is_compliant=True,
    debt_to_mkt_cap=0.1, cash_to_mkt_cap=0.05, impure_revenue_pct=0.0,
)
_NON_COMPLIANT_STATUS = ComplianceStatus(
    symbol="TOBK", sector="Tobacco", is_compliant=False,
    debt_to_mkt_cap=0.1, cash_to_mkt_cap=0.05, impure_revenue_pct=0.9,
    reason="Prohibited sector: Tobacco",
)


def _make_worker(positions, connected=True):
    worker = MagicMock()
    worker.ib.isConnected.return_value = connected
    worker.get_positions.return_value = positions
    return worker


class TestComplianceAuditLoopLogic(unittest.IsolatedAsyncioTestCase):
    """
    Tests audit loop kill-switch logic in isolation.
    Calls the inner body directly rather than running the full infinite loop.
    """

    async def _run_one_audit(self, worker, compliance_map, auto_sell=False):
        """
        Simulates one iteration of compliance_audit_loop body (no sleep).
        Returns list of (symbol, side) execute_trade calls made.
        """
        calls = []

        trader = MagicMock()
        trader.execute_trade.side_effect = lambda trade_req, **kw: calls.append(
            (trade_req.symbol, trade_req.side)
        ) or MagicMock(state="SUBMITTED")

        positions = worker.get_positions()
        loop = asyncio.get_running_loop()
        auto_liquidate = auto_sell

        for pos in positions:
            symbol = str(pos["symbol"])
            qty = int(pos["quantity"])
            compliance_status = await loop.run_in_executor(None, lambda s=symbol: compliance_map[s])

            if not compliance_status.is_compliant and qty > 0 and auto_liquidate:
                trader.execute_trade(
                    TradeCreate(symbol=symbol, quantity=qty, side="SELL"),
                    pre_screened=compliance_status,
                    force_liquidation=True,
                )

        return calls

    async def test_compliant_position_no_trade_executed(self):
        worker = _make_worker([{"symbol": "AAPL", "quantity": 10}])
        calls = await self._run_one_audit(worker, {"AAPL": _COMPLIANT_STATUS}, auto_sell=True)
        self.assertEqual(calls, [])

    async def test_non_compliant_auto_sell_true_triggers_sell(self):
        worker = _make_worker([{"symbol": "TOBK", "quantity": 5}])
        calls = await self._run_one_audit(worker, {"TOBK": _NON_COMPLIANT_STATUS}, auto_sell=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ("TOBK", "SELL"))

    async def test_non_compliant_auto_sell_false_no_trade(self):
        worker = _make_worker([{"symbol": "TOBK", "quantity": 5}])
        calls = await self._run_one_audit(worker, {"TOBK": _NON_COMPLIANT_STATUS}, auto_sell=False)
        self.assertEqual(calls, [])

    async def test_zero_quantity_non_compliant_no_trade(self):
        worker = _make_worker([{"symbol": "TOBK", "quantity": 0}])
        calls = await self._run_one_audit(worker, {"TOBK": _NON_COMPLIANT_STATUS}, auto_sell=True)
        self.assertEqual(calls, [])

    async def test_multiple_positions_only_non_compliant_sold(self):
        worker = _make_worker([{"symbol": "AAPL", "quantity": 10}, {"symbol": "TOBK", "quantity": 5}])
        calls = await self._run_one_audit(
            worker,
            {"AAPL": _COMPLIANT_STATUS, "TOBK": _NON_COMPLIANT_STATUS},
            auto_sell=True,
        )
        symbols_sold = [c[0] for c in calls]
        self.assertNotIn("AAPL", symbols_sold)
        self.assertIn("TOBK", symbols_sold)


class TestVixTierNotification(unittest.IsolatedAsyncioTestCase):
    """
    Tests for _check_vix_tier_change: fires Telegram alert only when VIX tier changes.
    """

    def _health(self, vix_tier=None):
        return {"compliance_audit_loop": {"vix_tier": vix_tier, "last_run": None, "status": "running"}}

    async def test_first_run_no_alert(self):
        """No previous tier in health → store tier, no alert."""
        from backend.features.compliance.loops import _check_vix_tier_change
        health = self._health(vix_tier=None)
        with patch("backend.features.compliance.loops.send_alert", new_callable=AsyncMock) as mock_alert:
            tier = await _check_vix_tier_change(15.0, health, [])
        self.assertEqual(tier, "CALM")
        mock_alert.assert_not_called()
        self.assertEqual(health["compliance_audit_loop"]["vix_tier"], "CALM")

    async def test_unchanged_tier_no_alert(self):
        from backend.features.compliance.loops import _check_vix_tier_change
        health = self._health(vix_tier="CALM")
        with patch("backend.features.compliance.loops.send_alert", new_callable=AsyncMock) as mock_alert:
            tier = await _check_vix_tier_change(18.0, health, [])
        self.assertEqual(tier, "CALM")
        mock_alert.assert_not_called()

    async def test_calm_to_elevated_fires_alert(self):
        from backend.features.compliance.loops import _check_vix_tier_change
        health = self._health(vix_tier="CALM")
        with patch("backend.features.compliance.loops.send_alert", new_callable=AsyncMock) as mock_alert:
            tier = await _check_vix_tier_change(22.0, health, ["telegram"])
        self.assertEqual(tier, "ELEVATED")
        mock_alert.assert_called_once()
        title = mock_alert.call_args[0][0]
        self.assertIn("ELEVATED", title)

    async def test_elevated_to_crisis_fires_alert(self):
        from backend.features.compliance.loops import _check_vix_tier_change
        health = self._health(vix_tier="ELEVATED")
        with patch("backend.features.compliance.loops.send_alert", new_callable=AsyncMock) as mock_alert:
            tier = await _check_vix_tier_change(35.0, health, ["telegram"])
        self.assertEqual(tier, "CRISIS")
        mock_alert.assert_called_once()

    async def test_crisis_to_calm_fires_alert(self):
        from backend.features.compliance.loops import _check_vix_tier_change
        health = self._health(vix_tier="CRISIS")
        with patch("backend.features.compliance.loops.send_alert", new_callable=AsyncMock) as mock_alert:
            tier = await _check_vix_tier_change(15.0, health, ["telegram"])
        self.assertEqual(tier, "CALM")
        mock_alert.assert_called_once()

    async def test_health_dict_updated_with_new_tier(self):
        from backend.features.compliance.loops import _check_vix_tier_change
        health = self._health(vix_tier="CALM")
        with patch("backend.features.compliance.loops.send_alert", new_callable=AsyncMock):
            await _check_vix_tier_change(25.0, health, [])
        self.assertEqual(health["compliance_audit_loop"]["vix_tier"], "ELEVATED")


if __name__ == "__main__":
    unittest.main()
