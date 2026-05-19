"""
Unit tests for alert dispatcher and Telegram sender.
No live network calls — httpx mocked throughout.
"""
import os
import unittest
from unittest.mock import AsyncMock, patch, MagicMock


class TestSendTelegram(unittest.IsolatedAsyncioTestCase):
    async def test_returns_false_when_token_missing(self):
        from backend.features.alerts.telegram import send_telegram
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "123"}):
            result = await send_telegram("hello")
        self.assertFalse(result)

    async def test_returns_false_when_chat_id_missing(self):
        from backend.features.alerts.telegram import send_telegram
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": ""}):
            result = await send_telegram("hello")
        self.assertFalse(result)

    async def test_sends_post_and_returns_true(self):
        from backend.features.alerts.telegram import send_telegram

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok123", "TELEGRAM_CHAT_ID": "456"}), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await send_telegram("test message")

        self.assertTrue(result)
        mock_client.post.assert_called_once()
        _, kwargs = mock_client.post.call_args
        self.assertEqual(kwargs["json"]["chat_id"], "456")
        self.assertIn("test message", kwargs["json"]["text"])

    async def test_returns_false_on_http_error(self):
        from backend.features.alerts.telegram import send_telegram

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("network error"))

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"}), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await send_telegram("fail")

        self.assertFalse(result)


class TestDispatcher(unittest.IsolatedAsyncioTestCase):
    async def test_no_channels_no_call(self):
        from backend.features.alerts.dispatcher import alert
        with patch("backend.features.alerts.dispatcher.send_telegram") as mock_tg:
            await alert("title", "body", channels=[])
        mock_tg.assert_not_called()

    async def test_telegram_channel_calls_send_telegram(self):
        from backend.features.alerts.dispatcher import alert
        with patch("backend.features.alerts.dispatcher.send_telegram", new_callable=AsyncMock) as mock_tg:
            await alert("Title", "Body", channels=["telegram"])
        mock_tg.assert_called_once()
        call_text = mock_tg.call_args[0][0]
        self.assertIn("Title", call_text)
        self.assertIn("Body", call_text)

    async def test_unknown_channel_logged_not_raised(self):
        from backend.features.alerts.dispatcher import alert
        # Should not raise
        await alert("t", "b", channels=["smoke_signal"])

    async def test_html_formatting(self):
        from backend.features.alerts.dispatcher import alert
        with patch("backend.features.alerts.dispatcher.send_telegram", new_callable=AsyncMock) as mock_tg:
            await alert("My Title", "Some body", channels=["telegram"])
        text = mock_tg.call_args[0][0]
        self.assertIn("<b>My Title</b>", text)


if __name__ == "__main__":
    unittest.main()
