"""
Tests for discovery_loop (auto-execute Discovery signals).

All IBKR, AI, compliance, and alert dependencies are mocked.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ibkr_core.features.compliance.schemas import ComplianceStatus
from ibkr_core.features.trading.schemas import TradeSignal


def _make_signal(symbol="NVDA", confidence=82, action="BUY"):
    return TradeSignal(
        symbol=symbol,
        sentiment_score=confidence / 100.0,
        confidence=confidence,
        action=action,
        reasoning="Halal Discovery: strong fundamentals",
    )


def _make_compliance(symbol="NVDA", compliant=True, exchange="NMS"):
    return ComplianceStatus(
        symbol=symbol,
        sector="Technology",
        is_compliant=compliant,
        debt_to_mkt_cap=0.10,
        cash_to_mkt_cap=0.05,
        impure_revenue_pct=0.01,
        reason=None if compliant else "Debt too high",
        exchange=exchange,
    )


def _make_worker(positions=None):
    w = MagicMock()
    w.ib = MagicMock()
    w.ib.isConnected.return_value = True
    w.get_positions.return_value = positions or []
    return w


_SETTINGS_ENABLED = {
    "enable_discovery_auto": True,
    "discovery_interval_hours": 6,
    "auto_execute_threshold": 75,
    "signal_min_confidence": 30,
    "alert_channels": [],
    "watchlist": [],
}

_SETTINGS_DISABLED = {**_SETTINGS_ENABLED, "enable_discovery_auto": False}


class TestDiscoveryLoopDisabled(unittest.IsolatedAsyncioTestCase):
    async def test_loop_skips_when_disabled(self):
        """Loop does nothing and sleeps when enable_discovery_auto=False."""
        worker = _make_worker()
        health = {"discovery_loop": {"status": "starting", "last_run": None}}

        call_count = 0

        async def _fake_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with patch("ibkr_core.features.trading.loops.load_settings", return_value=_SETTINGS_DISABLED), \
             patch("asyncio.sleep", side_effect=_fake_sleep), \
             patch("ibkr_core.features.trading.loops.discover_halal_buys", new_callable=AsyncMock) as mock_discover:
            from ibkr_core.features.trading.loops import discovery_loop
            manager = MagicMock()
            try:
                await discovery_loop(worker, manager, health)
            except asyncio.CancelledError:
                pass

        mock_discover.assert_not_called()


class TestDiscoveryLoopEnabled(unittest.IsolatedAsyncioTestCase):
    async def test_loop_dispatches_compliant_signal_above_threshold(self):
        """Loop auto-executes signal when enabled, market open, and confidence >= threshold."""
        worker = _make_worker()
        health = {"discovery_loop": {"status": "starting", "last_run": None}}
        signal = _make_signal(confidence=82)
        compliance = _make_compliance()

        call_count = 0

        async def _fake_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise asyncio.CancelledError

        mock_trader = MagicMock()
        mock_result = MagicMock()
        mock_result.state = MagicMock()
        mock_result.state.value = "SUBMITTED"
        mock_trader.execute_trade = AsyncMock(return_value=mock_result)

        with patch("ibkr_core.features.trading.loops.load_settings", return_value=_SETTINGS_ENABLED), \
             patch("ibkr_core.features.trading.loops.discover_halal_buys", new_callable=AsyncMock, return_value=[signal]), \
             patch("ibkr_core.features.trading.loops.screen_many", new_callable=AsyncMock, return_value=[compliance]), \
             patch("ibkr_core.features.trading.loops.market_status", return_value={"is_open": True}), \
             patch("ibkr_core.features.trading.loops.Trader", return_value=mock_trader), \
             patch("ibkr_core.features.trading.loops.send_alert", new_callable=AsyncMock), \
             patch("ibkr_core.features.trading.loops._exceeds_daily_loss_limit", return_value=False), \
             patch("ibkr_core.core.market_hours.any_market_open", return_value=True), \
             patch("ibkr_core.features.compliance.vix.get_current_vix", return_value=15.0), \
             patch("asyncio.sleep", side_effect=_fake_sleep):
            from ibkr_core.features.trading.loops import discovery_loop
            manager = MagicMock()
            manager.broadcast = AsyncMock()
            try:
                await discovery_loop(worker, manager, health)
            except asyncio.CancelledError:
                pass

        mock_trader.execute_trade.assert_called()

    async def test_loop_skips_already_held_symbol(self):
        """Discovery opens NEW positions only — a compliant, above-threshold,
        market-open signal for a symbol already held is NOT re-bought (avoids
        Qabd re-lock + piling into a name the exit loop may be selling)."""
        worker = _make_worker(positions=[{"symbol": "NVDA", "quantity": 10.0}])
        health = {"discovery_loop": {"status": "starting", "last_run": None}}
        signal = _make_signal(symbol="NVDA", confidence=82)   # already held
        compliance = _make_compliance(symbol="NVDA")

        call_count = 0

        async def _fake_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise asyncio.CancelledError

        mock_trader = MagicMock()
        mock_trader.execute_trade = AsyncMock()

        with patch("ibkr_core.features.trading.loops.load_settings", return_value=_SETTINGS_ENABLED), \
             patch("ibkr_core.features.trading.loops.discover_halal_buys", new_callable=AsyncMock, return_value=[signal]), \
             patch("ibkr_core.features.trading.loops.screen_many", new_callable=AsyncMock, return_value=[compliance]), \
             patch("ibkr_core.features.trading.loops.market_status", return_value={"is_open": True}), \
             patch("ibkr_core.features.trading.loops.Trader", return_value=mock_trader), \
             patch("ibkr_core.features.trading.loops.send_alert", new_callable=AsyncMock), \
             patch("ibkr_core.features.trading.loops._exceeds_daily_loss_limit", return_value=False), \
             patch("ibkr_core.core.market_hours.any_market_open", return_value=True), \
             patch("ibkr_core.features.compliance.vix.get_current_vix", return_value=15.0), \
             patch("asyncio.sleep", side_effect=_fake_sleep):
            from ibkr_core.features.trading.loops import discovery_loop
            manager = MagicMock()
            manager.broadcast = AsyncMock()
            try:
                await discovery_loop(worker, manager, health)
            except asyncio.CancelledError:
                pass

        mock_trader.execute_trade.assert_not_called()

    async def test_loop_skips_when_market_closed(self):
        """Loop does not dispatch when market is closed."""
        worker = _make_worker()
        health = {"discovery_loop": {"status": "starting", "last_run": None}}
        signal = _make_signal(confidence=85)
        compliance = _make_compliance()

        call_count = 0

        async def _fake_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        mock_trader = MagicMock()
        mock_trader.execute_trade = AsyncMock()

        with patch("ibkr_core.features.trading.loops.load_settings", return_value=_SETTINGS_ENABLED), \
             patch("ibkr_core.features.trading.loops.discover_halal_buys", new_callable=AsyncMock, return_value=[signal]), \
             patch("ibkr_core.features.trading.loops.screen_many", new_callable=AsyncMock, return_value=[compliance]), \
             patch("ibkr_core.features.trading.loops.market_status", return_value={"is_open": False}), \
             patch("ibkr_core.features.trading.loops.Trader", return_value=mock_trader), \
             patch("asyncio.sleep", side_effect=_fake_sleep):
            from ibkr_core.features.trading.loops import discovery_loop
            manager = MagicMock()
            manager.broadcast = AsyncMock()
            try:
                await discovery_loop(worker, manager, health)
            except asyncio.CancelledError:
                pass

        mock_trader.execute_trade.assert_not_called()

    async def test_loop_skips_non_compliant_signal(self):
        """Loop does not dispatch non-compliant discovery signals."""
        worker = _make_worker()
        health = {"discovery_loop": {"status": "starting", "last_run": None}}
        signal = _make_signal(symbol="BAD", confidence=88)
        bad_compliance = _make_compliance(symbol="BAD", compliant=False)

        call_count = 0

        async def _fake_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        mock_trader = MagicMock()
        mock_trader.execute_trade = AsyncMock()

        with patch("ibkr_core.features.trading.loops.load_settings", return_value=_SETTINGS_ENABLED), \
             patch("ibkr_core.features.trading.loops.discover_halal_buys", new_callable=AsyncMock, return_value=[signal]), \
             patch("ibkr_core.features.trading.loops.screen_many", new_callable=AsyncMock, return_value=[bad_compliance]), \
             patch("ibkr_core.features.trading.loops.market_status", return_value={"is_open": True}), \
             patch("ibkr_core.features.trading.loops.Trader", return_value=mock_trader), \
             patch("asyncio.sleep", side_effect=_fake_sleep):
            from ibkr_core.features.trading.loops import discovery_loop
            manager = MagicMock()
            manager.broadcast = AsyncMock()
            try:
                await discovery_loop(worker, manager, health)
            except asyncio.CancelledError:
                pass

        mock_trader.execute_trade.assert_not_called()

    async def test_loop_skips_scan_when_position_cap_reached(self):
        """No free slots (positions >= max_positions) → discovery scan is skipped
        entirely; main_loop's trim must never race freshly-overshot fills."""
        worker = _make_worker(positions=[{"symbol": "AAPL"}, {"symbol": "MSFT"}])
        health = {"discovery_loop": {"status": "starting", "last_run": None}}
        settings = {**_SETTINGS_ENABLED, "max_positions": 2}

        call_count = 0

        async def _fake_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with patch("ibkr_core.features.trading.loops.load_settings", return_value=settings), \
             patch("ibkr_core.features.trading.loops.discover_halal_buys", new_callable=AsyncMock) as mock_discover, \
             patch("ibkr_core.features.trading.loops._exceeds_daily_loss_limit", return_value=False), \
             patch("ibkr_core.core.market_hours.any_market_open", return_value=True), \
             patch("ibkr_core.features.compliance.vix.get_current_vix", return_value=15.0), \
             patch("asyncio.sleep", side_effect=_fake_sleep):
            from ibkr_core.features.trading.loops import discovery_loop
            manager = MagicMock()
            manager.broadcast = AsyncMock()
            try:
                await discovery_loop(worker, manager, health)
            except asyncio.CancelledError:
                pass

        mock_discover.assert_not_called()

    async def test_loop_dispatches_at_most_free_slots(self):
        """3 signals but only 1 free slot (max_positions=2, 1 held) → exactly
        one BUY dispatched in the cycle, the rest dropped. (Cancel after the
        FIRST end-of-cycle sleep: the mocked positions never grow, so every
        extra cycle would legitimately dispatch one more.)"""
        worker = _make_worker(positions=[{"symbol": "AAPL"}])
        health = {"discovery_loop": {"status": "starting", "last_run": None}}
        settings = {**_SETTINGS_ENABLED, "max_positions": 2}
        signals = [_make_signal(symbol=s, confidence=82) for s in ("NVDA", "AMD", "QCOM")]
        compliances = [_make_compliance(symbol=s) for s in ("NVDA", "AMD", "QCOM")]

        async def _fake_sleep(n):
            raise asyncio.CancelledError

        mock_trader = MagicMock()
        mock_result = MagicMock()
        mock_result.state = MagicMock()
        mock_result.state.value = "SUBMITTED"
        mock_trader.execute_trade = AsyncMock(return_value=mock_result)

        with patch("ibkr_core.features.trading.loops.load_settings", return_value=settings), \
             patch("ibkr_core.features.trading.loops.discover_halal_buys", new_callable=AsyncMock, return_value=signals), \
             patch("ibkr_core.features.trading.loops.screen_many", new_callable=AsyncMock, return_value=compliances), \
             patch("ibkr_core.features.trading.loops.market_status", return_value={"is_open": True}), \
             patch("ibkr_core.features.trading.loops.Trader", return_value=mock_trader), \
             patch("ibkr_core.features.trading.loops.send_alert", new_callable=AsyncMock), \
             patch("ibkr_core.features.trading.loops._exceeds_daily_loss_limit", return_value=False), \
             patch("ibkr_core.core.market_hours.any_market_open", return_value=True), \
             patch("ibkr_core.features.compliance.vix.get_current_vix", return_value=15.0), \
             patch("asyncio.sleep", side_effect=_fake_sleep):
            from ibkr_core.features.trading.loops import discovery_loop
            manager = MagicMock()
            manager.broadcast = AsyncMock()
            try:
                await discovery_loop(worker, manager, health)
            except asyncio.CancelledError:
                pass

        assert mock_trader.execute_trade.call_count == 1

    async def test_health_updated_after_scan(self):
        """health dict is updated with last_run timestamp after each scan."""
        worker = _make_worker()
        health = {"discovery_loop": {"status": "starting", "last_run": None}}

        call_count = 0

        async def _fake_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with patch("ibkr_core.features.trading.loops.load_settings", return_value=_SETTINGS_ENABLED), \
             patch("ibkr_core.features.trading.loops.discover_halal_buys", new_callable=AsyncMock, return_value=[]), \
             patch("ibkr_core.features.trading.loops.screen_many", new_callable=AsyncMock, return_value=[]), \
             patch("ibkr_core.features.trading.loops.market_status", return_value={"is_open": True}), \
             patch("ibkr_core.features.trading.loops.Trader"), \
             patch("ibkr_core.features.trading.loops._exceeds_daily_loss_limit", return_value=False), \
             patch("ibkr_core.core.market_hours.any_market_open", return_value=True), \
             patch("ibkr_core.features.compliance.vix.get_current_vix", return_value=15.0), \
             patch("asyncio.sleep", side_effect=_fake_sleep):
            from ibkr_core.features.trading.loops import discovery_loop
            manager = MagicMock()
            manager.broadcast = AsyncMock()
            try:
                await discovery_loop(worker, manager, health)
            except asyncio.CancelledError:
                pass

        assert health["discovery_loop"]["last_run"] is not None


if __name__ == "__main__":
    unittest.main()
