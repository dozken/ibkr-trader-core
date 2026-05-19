"""
Tests for telegram_bot — push notification bot (read + emergency kill only).
No live network calls — httpx mocked throughout.
"""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_worker(connected=True, nlv=100_000.0, cash=20_000.0, positions=None):
    worker = MagicMock()
    worker.ib.isConnected.return_value = connected
    worker.get_net_liquidation.return_value = nlv
    worker.get_available_funds.return_value = cash
    worker.get_positions.return_value = positions or []
    return worker


def _trade_result(state_val="SUBMITTED"):
    t = MagicMock()
    t.state.value = state_val
    return t


TOKEN = "test-token"
CHAT_ID = "999"


# ── _send_message ─────────────────────────────────────────────────────────────

class TestSendMessage(unittest.IsolatedAsyncioTestCase):
    async def test_posts_to_telegram(self):
        from backend.features.alerts.telegram_bot import _send_message
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock()
        with patch("backend.features.alerts.telegram_bot.httpx.AsyncClient", return_value=mock_client):
            await _send_message(TOKEN, CHAT_ID, "hello")
        payload = mock_client.post.call_args.kwargs["json"]
        self.assertEqual(payload["chat_id"], CHAT_ID)
        self.assertEqual(payload["text"], "hello")

    async def test_includes_reply_markup_when_provided(self):
        from backend.features.alerts.telegram_bot import _send_message
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock()
        kb = {"inline_keyboard": [[{"text": "btn", "callback_data": "/x"}]]}
        with patch("backend.features.alerts.telegram_bot.httpx.AsyncClient", return_value=mock_client):
            await _send_message(TOKEN, CHAT_ID, "msg", reply_markup=kb)
        payload = mock_client.post.call_args.kwargs["json"]
        self.assertEqual(payload["reply_markup"], kb)

    async def test_swallows_exception_silently(self):
        from backend.features.alerts.telegram_bot import _send_message
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))
        with patch("backend.features.alerts.telegram_bot.httpx.AsyncClient", return_value=mock_client):
            await _send_message(TOKEN, CHAT_ID, "hi")  # must not raise


# ── _answer_callback ──────────────────────────────────────────────────────────

class TestAnswerCallback(unittest.IsolatedAsyncioTestCase):
    async def test_posts_answer_callback(self):
        from backend.features.alerts.telegram_bot import _answer_callback
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock()
        with patch("backend.features.alerts.telegram_bot.httpx.AsyncClient", return_value=mock_client):
            await _answer_callback(TOKEN, "cb123")
        payload = mock_client.post.call_args.kwargs["json"]
        self.assertEqual(payload["callback_query_id"], "cb123")

    async def test_swallows_exception_silently(self):
        from backend.features.alerts.telegram_bot import _answer_callback
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("net"))
        with patch("backend.features.alerts.telegram_bot.httpx.AsyncClient", return_value=mock_client):
            await _answer_callback(TOKEN, "cb123")  # must not raise


# ── _handle_command ───────────────────────────────────────────────────────────

class TestHandleCommand(unittest.IsolatedAsyncioTestCase):

    async def _run(self, command, args=None, worker=None):
        from backend.features.alerts.telegram_bot import _handle_command
        if worker is None:
            worker = _make_worker()
        send_mock = AsyncMock()
        with patch("backend.features.alerts.telegram_bot._send_message", send_mock):
            await _handle_command(command, args or [], worker, TOKEN, CHAT_ID)
        return send_mock

    def _last_text(self, mock):
        return mock.call_args[0][2]

    async def test_disconnected_sends_error(self):
        mock = await self._run("/status", worker=_make_worker(connected=False))
        self.assertIn("disconnected", self._last_text(mock).lower())

    async def test_start_sends_welcome_with_keyboard(self):
        mock = await self._run("/start")
        text = self._last_text(mock)
        self.assertIn("Shariah Trader", text)
        self.assertIn("/liquidate", text)
        kb = mock.call_args.kwargs.get("reply_markup")
        self.assertIsNotNone(kb)

    async def test_help_same_as_start(self):
        mock_start = await self._run("/start")
        mock_help = await self._run("/help")
        self.assertEqual(self._last_text(mock_start), self._last_text(mock_help))

    async def test_status_shows_portfolio_figures(self):
        worker = _make_worker(nlv=123_456.78, cash=9_000.0,
                              positions=[{"symbol": "AAPL", "quantity": 5}])
        mock = await self._run("/status", worker=worker)
        text = self._last_text(mock)
        self.assertIn("123,456.78", text)
        self.assertIn("9,000.00", text)
        self.assertIn("1", text)

    async def test_signals_no_actionable(self):
        from backend.features.trading.schemas import TradeSignal
        signals = [TradeSignal(symbol="AAPL", action="HOLD", confidence=40,
                               reasoning="flat", sentiment_score=0.0)]
        fake_strategy = MagicMock()
        fake_strategy.get_guarded_signals = AsyncMock(return_value=signals)
        with patch("backend.core.strategy.registry.get_active_strategy", return_value=fake_strategy), \
             patch("backend.core.strategy.get_active_strategy", return_value=fake_strategy):
            mock = await self._run("/signals")
        self.assertIn("No actionable", self._last_text(mock))

    async def test_signals_actionable_shown(self):
        from backend.features.trading.schemas import TradeSignal
        signals = [TradeSignal(symbol="AAPL", action="BUY", confidence=80,
                               reasoning="strong uptrend", sentiment_score=0.8)]
        fake_strategy = MagicMock()
        fake_strategy.get_guarded_signals = AsyncMock(return_value=signals)
        with patch("backend.core.strategy.registry.get_active_strategy", return_value=fake_strategy), \
             patch("backend.core.strategy.get_active_strategy", return_value=fake_strategy):
            with patch("backend.features.compliance.screening.async_shariah_screen", AsyncMock()) as mock_screen:
                mock_comp = MagicMock()
                mock_comp.is_compliant = True
                mock_screen.return_value = mock_comp
                mock = await self._run("/signals")
        text = self._last_text(mock)
        self.assertIn("BUY", text)

    async def test_liquidate_no_args_sends_usage(self):
        mock = await self._run("/liquidate")
        self.assertIn("Usage", self._last_text(mock))

    async def test_liquidate_no_position_sends_warning(self):
        mock = await self._run("/liquidate", ["AAPL"], worker=_make_worker(positions=[]))
        self.assertIn("hold any shares", self._last_text(mock))

    async def test_liquidate_zero_qty_sends_warning(self):
        worker = _make_worker(positions=[{"symbol": "AAPL", "quantity": 0}])
        mock = await self._run("/liquidate", ["AAPL"], worker=worker)
        self.assertIn("hold any shares", self._last_text(mock))

    async def test_liquidate_success(self):
        worker = _make_worker(positions=[{"symbol": "AAPL", "quantity": 10}])
        with patch("backend.features.trading.trader.Trader") as MockTrader:
            MockTrader.return_value.execute_trade = AsyncMock(return_value=_trade_result())
            mock = await self._run("/liquidate", ["AAPL"], worker=worker)
        self.assertIn("LIQUIDATED", self._last_text(mock))

    async def test_liquidate_exception_sends_error(self):
        worker = _make_worker(positions=[{"symbol": "AAPL", "quantity": 10}])
        with patch("backend.features.trading.trader.Trader") as MockTrader:
            MockTrader.return_value.execute_trade = AsyncMock(side_effect=Exception("timeout"))
            mock = await self._run("/liquidate", ["AAPL"], worker=worker)
        self.assertIn("failed", self._last_text(mock).lower())

    async def test_unknown_command_sends_help(self):
        mock = await self._run("/unknown")
        text = self._last_text(mock)
        self.assertIn("/status", text)
        self.assertIn("/liquidate", text)


# ── telegram_bot_loop ─────────────────────────────────────────────────────────

class TestTelegramBotLoop(unittest.IsolatedAsyncioTestCase):

    async def test_disabled_when_token_missing(self):
        from backend.features.alerts.telegram_bot import telegram_bot_loop
        health = {"telegram_bot_loop": {"last_run": None, "status": "starting"}}
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "123"}):
            await telegram_bot_loop(_make_worker(), health)
        self.assertEqual(health["telegram_bot_loop"]["status"], "disabled")

    async def test_disabled_when_chat_id_missing(self):
        from backend.features.alerts.telegram_bot import telegram_bot_loop
        health = {"telegram_bot_loop": {"last_run": None, "status": "starting"}}
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": ""}):
            await telegram_bot_loop(_make_worker(), health)
        self.assertEqual(health["telegram_bot_loop"]["status"], "disabled")

    async def _run_one_poll(self, updates, env=None):
        from backend.features.alerts.telegram_bot import telegram_bot_loop
        health = {}
        if env is None:
            env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": CHAT_ID}
        poll_calls = []

        async def fake_get(*args, **kwargs):
            if poll_calls:
                raise asyncio.CancelledError
            poll_calls.append(1)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"ok": True, "result": updates}
            return resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = fake_get

        with patch.dict(os.environ, env):
            with patch("backend.features.alerts.telegram_bot.httpx.AsyncClient", return_value=mock_client):
                with patch("backend.features.alerts.telegram_bot._handle_command", AsyncMock()) as mock_cmd:
                    with patch("backend.features.alerts.telegram_bot.asyncio.sleep", AsyncMock()):
                        try:
                            await telegram_bot_loop(_make_worker(), health)
                        except asyncio.CancelledError:
                            pass
        return mock_cmd

    async def test_text_command_dispatched(self):
        updates = [{"update_id": 1,
                    "message": {"chat": {"id": int(CHAT_ID)}, "text": "/status"}}]
        mock_cmd = await self._run_one_poll(updates)
        await asyncio.sleep(0)
        mock_cmd.assert_called_once()
        self.assertEqual(mock_cmd.call_args[0][0], "/status")

    async def test_callback_query_dispatched(self):
        updates = [{"update_id": 2, "callback_query": {
            "id": "cb1", "data": "/signals",
            "message": {"chat": {"id": int(CHAT_ID)}},
        }}]
        mock_cmd = await self._run_one_poll(updates)
        await asyncio.sleep(0)
        mock_cmd.assert_called_once()
        self.assertEqual(mock_cmd.call_args[0][0], "/signals")

    async def test_unauthorized_chat_ignored(self):
        updates = [{"update_id": 3,
                    "message": {"chat": {"id": 666}, "text": "/liquidate ALL"}}]
        mock_cmd = await self._run_one_poll(updates)
        await asyncio.sleep(0)
        mock_cmd.assert_not_called()

    async def test_non_command_text_ignored(self):
        updates = [{"update_id": 4,
                    "message": {"chat": {"id": int(CHAT_ID)}, "text": "hello there"}}]
        mock_cmd = await self._run_one_poll(updates)
        await asyncio.sleep(0)
        mock_cmd.assert_not_called()

    async def test_offset_advances(self):
        from backend.features.alerts.telegram_bot import telegram_bot_loop
        health = {}
        env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": CHAT_ID}
        offsets_seen = []
        call_count = 0

        async def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            offsets_seen.append(kwargs.get("params", {}).get("offset", 0))
            if call_count >= 2:
                raise asyncio.CancelledError
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "ok": True,
                "result": [{"update_id": 42, "message": {"chat": {"id": 0}, "text": "hi"}}],
            }
            return resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = fake_get

        with patch.dict(os.environ, env):
            with patch("backend.features.alerts.telegram_bot.httpx.AsyncClient", return_value=mock_client):
                with patch("backend.features.alerts.telegram_bot.asyncio.sleep", AsyncMock()):
                    try:
                        await telegram_bot_loop(_make_worker(), health)
                    except asyncio.CancelledError:
                        pass

        self.assertEqual(offsets_seen[0], 0)
        self.assertEqual(offsets_seen[1], 43)

    async def test_read_timeout_continues(self):
        from backend.features.alerts.telegram_bot import telegram_bot_loop
        import httpx as _httpx
        health = {}
        env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": CHAT_ID}
        call_count = 0

        async def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _httpx.ReadTimeout("timeout", request=MagicMock())
            raise asyncio.CancelledError

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = fake_get

        with patch.dict(os.environ, env):
            with patch("backend.features.alerts.telegram_bot.httpx.AsyncClient", return_value=mock_client):
                with patch("backend.features.alerts.telegram_bot.asyncio.sleep", AsyncMock()):
                    try:
                        await telegram_bot_loop(_make_worker(), health)
                    except asyncio.CancelledError:
                        pass

        self.assertEqual(call_count, 2)

    async def test_general_exception_sets_error_status(self):
        from backend.features.alerts.telegram_bot import telegram_bot_loop
        health = {}
        env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": CHAT_ID}
        call_count = 0

        async def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("unexpected")
            raise asyncio.CancelledError

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = fake_get

        with patch.dict(os.environ, env):
            with patch("backend.features.alerts.telegram_bot.httpx.AsyncClient", return_value=mock_client):
                with patch("backend.features.alerts.telegram_bot.asyncio.sleep", AsyncMock()):
                    try:
                        await telegram_bot_loop(_make_worker(), health)
                    except asyncio.CancelledError:
                        pass

        self.assertIn("error", health["telegram_bot_loop"]["status"])
        self.assertIn("next_retry", health["telegram_bot_loop"])


if __name__ == "__main__":
    unittest.main()
