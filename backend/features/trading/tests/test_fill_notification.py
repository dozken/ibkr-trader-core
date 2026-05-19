"""
Tests that a Telegram push alert is fired when an IBKR fill arrives.
No live connection required — ib_insync objects are fully mocked.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSendFillAlert(unittest.IsolatedAsyncioTestCase):
    """Unit tests for IBKRWorker._send_fill_alert."""

    def _make_fill_objects(self, symbol="AAPL", side="BUY", qty=10.0, price=175.50, order_id=12345):
        trade = MagicMock()
        trade.contract.symbol = symbol
        trade.order.action = side
        trade.order.orderId = order_id

        fill = MagicMock()
        fill.execution.cumQty = qty
        fill.execution.price = price
        return trade, fill

    @patch("backend.features.settings.service.load_settings", return_value={"alert_channels": ["telegram"]})
    @patch("backend.features.alerts.dispatcher.alert", new_callable=AsyncMock)
    async def test_alert_called_with_correct_title_and_body(self, mock_alert, _mock_settings):
        from backend.features.trading.worker import IBKRWorker

        trade, fill = self._make_fill_objects(
            symbol="AAPL", side="BUY", qty=10.0, price=175.50, order_id=12345
        )
        await IBKRWorker._send_fill_alert(trade, fill)

        mock_alert.assert_awaited_once()
        title, body, channels = mock_alert.call_args.args
        self.assertEqual(title, "Trade Filled")
        self.assertEqual(body, "AAPL BUY 10.0 @ $175.50 · Order #12345")
        self.assertEqual(channels, ["telegram"])

    @patch("backend.features.settings.service.load_settings", return_value={"alert_channels": ["telegram"]})
    @patch("backend.features.alerts.dispatcher.alert", new_callable=AsyncMock)
    async def test_alert_sell_order(self, mock_alert, _mock_settings):
        from backend.features.trading.worker import IBKRWorker

        trade, fill = self._make_fill_objects(
            symbol="MSFT", side="SELL", qty=5.0, price=320.00, order_id=99
        )
        await IBKRWorker._send_fill_alert(trade, fill)

        mock_alert.assert_awaited_once()
        title, body, channels = mock_alert.call_args.args
        self.assertEqual(title, "Trade Filled")
        self.assertEqual(body, "MSFT SELL 5.0 @ $320.00 · Order #99")

    @patch("backend.features.settings.service.load_settings", return_value={"alert_channels": []})
    @patch("backend.features.alerts.dispatcher.alert", new_callable=AsyncMock)
    async def test_no_alert_when_channels_empty(self, mock_alert, _mock_settings):
        """alert() is still called but with empty channels — dispatcher silently drops it."""
        from backend.features.trading.worker import IBKRWorker

        trade, fill = self._make_fill_objects()
        await IBKRWorker._send_fill_alert(trade, fill)

        mock_alert.assert_awaited_once()
        _, _, channels = mock_alert.call_args.args
        self.assertEqual(channels, [])

    @patch("backend.features.settings.service.load_settings", side_effect=Exception("settings error"))
    @patch("backend.features.alerts.dispatcher.alert", new_callable=AsyncMock)
    async def test_exception_does_not_propagate(self, mock_alert, _mock_settings):
        """A failure inside _send_fill_alert must be swallowed — never crash the fill handler."""
        from backend.features.trading.worker import IBKRWorker

        trade, fill = self._make_fill_objects()
        # Should not raise
        await IBKRWorker._send_fill_alert(trade, fill)
        mock_alert.assert_not_awaited()

    @patch("backend.features.settings.service.load_settings", return_value={"alert_channels": ["telegram"]})
    @patch("backend.features.alerts.dispatcher.alert", new_callable=AsyncMock)
    async def test_price_formatted_to_two_decimal_places(self, mock_alert, _mock_settings):
        from backend.features.trading.worker import IBKRWorker

        trade, fill = self._make_fill_objects(price=99.9)
        await IBKRWorker._send_fill_alert(trade, fill)

        _, body, _ = mock_alert.call_args.args
        self.assertIn("$99.90", body)


class TestOnExecDetailsDispatchesAlert(unittest.IsolatedAsyncioTestCase):
    """Integration-level: _on_exec_details schedules _send_fill_alert on the running loop."""

    def _make_worker(self):
        from backend.features.trading.worker import IBKRWorker
        w = IBKRWorker.__new__(IBKRWorker)
        w.ib = MagicMock()
        w.host = "127.0.0.1"
        w.port = 7497
        w.client_id = 1
        w._ticker_callbacks = {}
        w._reconnecting = False
        import asyncio
        w._limiter = asyncio.Semaphore(5)
        w._last_request_time = 0.0
        return w

    async def test_fill_alert_task_is_created(self):
        """_on_exec_details must schedule _send_fill_alert as an asyncio task."""
        import asyncio
        w = self._make_worker()

        trade = MagicMock()
        trade.order.orderId = 42
        fill = MagicMock()
        fill.execution.price = 150.0
        fill.commissionReport = None

        tasks_created = []
        original_create_task = asyncio.get_event_loop().create_task

        with patch(
            "backend.features.trading.worker.IBKRWorker._db_update_fill_details"
        ), patch.object(
            asyncio.get_event_loop(),
            "create_task",
            side_effect=lambda coro: tasks_created.append(coro) or MagicMock(),
        ):
            w._on_exec_details(trade, fill)

        # Two tasks: one for DB update (via to_thread), one for the alert
        self.assertEqual(len(tasks_created), 2)


if __name__ == "__main__":
    unittest.main()
