import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_connect_success():
    mock_ib = MagicMock()
    mock_ib.connectAsync = AsyncMock()

    with patch("ib_insync.IB", return_value=mock_ib):
        from backend.features.trading.worker import IBKRWorker
        worker = IBKRWorker(port=7497)
        worker.ib = mock_ib

        result = await worker.connect()

        assert result is True
        mock_ib.connectAsync.assert_called_once_with("127.0.0.1", 7497, clientId=1)


@pytest.mark.asyncio
async def test_connect_failure():
    mock_ib = MagicMock()
    mock_ib.connectAsync = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("ib_insync.IB", return_value=mock_ib):
        from backend.features.trading.worker import IBKRWorker
        worker = IBKRWorker(port=7497)
        worker.ib = mock_ib

        result = await worker.connect()

        assert result is False


def test_disconnect():
    mock_ib = MagicMock()

    with patch("ib_insync.IB", return_value=mock_ib):
        from backend.features.trading.worker import IBKRWorker
        worker = IBKRWorker()
        worker.ib = mock_ib

        worker.disconnect()

        mock_ib.disconnect.assert_called_once()
