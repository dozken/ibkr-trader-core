"""
Tests for cash_sweep_loop (FR9 – Autonomous Cash Sweeping).

All IBKR, AI, compliance, and alert dependencies are mocked.
No live connections or network calls are made.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.features.compliance.schemas import ComplianceStatus
from backend.features.trading.schemas import TradeSignal, TradeCreate


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_signal(symbol="AAPL", confidence=80, action="BUY"):
    return TradeSignal(
        symbol=symbol,
        sentiment_score=confidence / 100.0,
        confidence=confidence,
        action=action,
        reasoning=f"Test signal for {symbol}",
    )


def _make_compliance(symbol="AAPL", compliant=True, exchange="NMS"):
    return ComplianceStatus(
        symbol=symbol,
        sector="Technology",
        is_compliant=compliant,
        debt_to_mkt_cap=0.10,
        cash_to_mkt_cap=0.05,
        impure_revenue_pct=0.0,
        reason=None if compliant else "Prohibited sector",
        exchange=exchange,
    )


def _make_trade(symbol="AAPL", quantity=5.0):
    return TradeCreate(symbol=symbol, quantity=quantity, side="BUY", order_type="MKT")


def _make_worker(connected=True, available_funds=5000.0):
    worker = MagicMock()
    worker.ib.isConnected.return_value = connected
    worker.get_available_funds.return_value = available_funds
    worker.get_positions.return_value = []
    return worker


def _market_open(exchange="NMS"):
    return {"is_open": True, "exchange": exchange}


def _market_closed(exchange="NMS"):
    return {"is_open": False, "exchange": exchange}


# ── Helpers ───────────────────────────────────────────────────────────────────

_LOOP_MODULE = "backend.features.trading.loops"


async def _run_one_sweep(
    *,
    settings: dict,
    worker,
    signals=None,
    compliance_map=None,
    market_open=True,
    allocator_trades=None,
    execute_result_state="SUBMITTED",
):
    """
    Drives one iteration of cash_sweep_loop without the infinite loop or sleep
    by patching all external dependencies.

    Returns a dict with:
      execute_calls   – symbol strings passed to trader.execute_trade
      broadcast_calls – messages passed to manager.broadcast
      alert_calls     – (subject, body) tuples passed to send_alert
    """
    from backend.features.trading.loops import cash_sweep_loop

    execute_calls: list[str] = []
    broadcast_calls: list = []
    alert_calls: list[tuple] = []

    signals = signals or []
    compliance_map = compliance_map or {}
    allocator_trades = allocator_trades or []

    async def _execute(trade_req, **kwargs):
        execute_calls.append(trade_req.symbol)
        result = MagicMock()
        result.state = execute_result_state
        return result

    trader_mock = MagicMock()
    trader_mock.execute_trade = AsyncMock(side_effect=_execute)

    mock_manager = MagicMock()
    mock_manager.broadcast = AsyncMock(side_effect=lambda msg: broadcast_calls.append(msg))

    async def _alert(subject, body, channels=None):
        alert_calls.append((subject, body))

    allocator_mock = MagicMock()
    allocator_mock.allocate.return_value = allocator_trades

    sleep_count = [0]

    async def _fake_sleep(seconds):
        sleep_count[0] += 1
        if sleep_count[0] >= 1:
            raise asyncio.CancelledError()

    market_fn = _market_open if market_open else _market_closed
    health = {"cash_sweep_loop": {"last_run": None, "status": "starting"}}

    with (
        patch(f"{_LOOP_MODULE}.load_settings", return_value=settings),
        patch(f"{_LOOP_MODULE}.generate_signals", new=AsyncMock(return_value=signals)),
        patch(f"{_LOOP_MODULE}.async_shariah_screen",
              new=AsyncMock(side_effect=lambda sym: compliance_map.get(sym, _make_compliance(sym)))),
        patch(f"{_LOOP_MODULE}.market_status", side_effect=lambda ex: market_fn(ex)),
        patch(f"{_LOOP_MODULE}.PortfolioAllocator", return_value=allocator_mock),
        patch(f"{_LOOP_MODULE}.Trader", return_value=trader_mock),
        patch(f"{_LOOP_MODULE}.send_alert", new=AsyncMock(side_effect=_alert)),
        patch("asyncio.sleep", side_effect=_fake_sleep),
    ):
        try:
            await cash_sweep_loop(worker, mock_manager, health)
        except asyncio.CancelledError:
            pass

    return {
        "execute_calls": execute_calls,
        "broadcast_calls": broadcast_calls,
        "alert_calls": alert_calls,
    }


# ── Test Cases ────────────────────────────────────────────────────────────────

class TestCashSweepLoop(unittest.IsolatedAsyncioTestCase):

    async def test_sweep_skips_when_disabled(self):
        """cash_sweep_enabled=False → no signals fetched, no trades."""
        worker = _make_worker(available_funds=5000.0)
        settings = {
            "cash_sweep_enabled": False,
            "cash_sweep_interval_min": 30,
            "min_trade_size": 100,
            "auto_execute_threshold": 80,
            "signal_min_confidence": 30,
            "alert_channels": [],
        }

        generate_mock = AsyncMock(return_value=[_make_signal()])

        with patch(f"{_LOOP_MODULE}.generate_signals", new=generate_mock):
            result = await _run_one_sweep(settings=settings, worker=worker, signals=[_make_signal()])

        generate_mock.assert_not_called()
        self.assertEqual(result["execute_calls"], [])
        self.assertEqual(result["broadcast_calls"], [])

    async def test_sweep_skips_when_cash_below_minimum(self):
        """available_cash < min_trade_size → sleep, no trades."""
        worker = _make_worker(available_funds=50.0)
        settings = {
            "cash_sweep_enabled": True,
            "cash_sweep_interval_min": 30,
            "min_trade_size": 100,
            "auto_execute_threshold": 80,
            "signal_min_confidence": 30,
            "alert_channels": [],
        }

        generate_mock = AsyncMock(return_value=[_make_signal()])

        with patch(f"{_LOOP_MODULE}.generate_signals", new=generate_mock):
            result = await _run_one_sweep(settings=settings, worker=worker)

        generate_mock.assert_not_called()
        self.assertEqual(result["execute_calls"], [])

    async def test_sweep_skips_when_no_buy_signals(self):
        """Only SELL/HOLD signals → no trades, no broadcasts."""
        worker = _make_worker(available_funds=5000.0)
        settings = {
            "cash_sweep_enabled": True,
            "cash_sweep_interval_min": 30,
            "min_trade_size": 100,
            "auto_execute_threshold": 80,
            "signal_min_confidence": 30,
            "alert_channels": [],
        }
        result = await _run_one_sweep(
            settings=settings,
            worker=worker,
            signals=[_make_signal(symbol="MSFT", action="HOLD"), _make_signal(symbol="AMZN", action="SELL")],
        )
        self.assertEqual(result["execute_calls"], [])
        self.assertEqual(result["broadcast_calls"], [])

    async def test_sweep_executes_trade_when_compliant_and_threshold_met(self):
        """BUY signal, Shariah-compliant, market open, confidence >= auto_threshold → execute_trade called."""
        worker = _make_worker(available_funds=5000.0)
        settings = {
            "cash_sweep_enabled": True,
            "cash_sweep_interval_min": 30,
            "min_trade_size": 100,
            "auto_execute_threshold": 70,
            "signal_min_confidence": 30,
            "alert_channels": [],
        }
        result = await _run_one_sweep(
            settings=settings,
            worker=worker,
            signals=[_make_signal("AAPL", confidence=85)],
            compliance_map={"AAPL": _make_compliance("AAPL", compliant=True)},
            market_open=True,
            allocator_trades=[_make_trade("AAPL", quantity=5.0)],
        )
        self.assertIn("AAPL", result["execute_calls"])
        pending = [m for m in result["broadcast_calls"] if m.type == "pending_signal"]
        self.assertEqual(pending, [])

    async def test_sweep_broadcasts_pending_when_below_threshold(self):
        """confidence < auto_threshold → pending_signal broadcast + alert, no execute_trade."""
        worker = _make_worker(available_funds=5000.0)
        settings = {
            "cash_sweep_enabled": True,
            "cash_sweep_interval_min": 30,
            "min_trade_size": 100,
            "auto_execute_threshold": 90,
            "signal_min_confidence": 30,
            "alert_channels": [],
        }
        result = await _run_one_sweep(
            settings=settings,
            worker=worker,
            signals=[_make_signal("MSFT", confidence=60)],
            compliance_map={"MSFT": _make_compliance("MSFT", compliant=True)},
            market_open=True,
            allocator_trades=[_make_trade("MSFT", quantity=3.0)],
        )
        self.assertEqual(result["execute_calls"], [])
        pending = [m for m in result["broadcast_calls"] if m.type == "pending_signal"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].payload.symbol, "MSFT")
        self.assertEqual(pending[0].payload.action, "BUY")

    async def test_sweep_skips_non_compliant_symbol(self):
        """Non-compliant → skip trade, no broadcast, no execute."""
        worker = _make_worker(available_funds=5000.0)
        settings = {
            "cash_sweep_enabled": True,
            "cash_sweep_interval_min": 30,
            "min_trade_size": 100,
            "auto_execute_threshold": 70,
            "signal_min_confidence": 30,
            "alert_channels": [],
        }
        result = await _run_one_sweep(
            settings=settings,
            worker=worker,
            signals=[_make_signal("TOBK", confidence=85)],
            compliance_map={"TOBK": _make_compliance("TOBK", compliant=False)},
            market_open=True,
            allocator_trades=[_make_trade("TOBK", quantity=5.0)],
        )
        self.assertEqual(result["execute_calls"], [])
        self.assertEqual([m for m in result["broadcast_calls"] if m.type == "pending_signal"], [])

    async def test_sweep_skips_when_market_closed(self):
        """Compliant symbol but market closed → no execute, no broadcast."""
        worker = _make_worker(available_funds=5000.0)
        settings = {
            "cash_sweep_enabled": True,
            "cash_sweep_interval_min": 30,
            "min_trade_size": 100,
            "auto_execute_threshold": 70,
            "signal_min_confidence": 30,
            "alert_channels": [],
        }
        result = await _run_one_sweep(
            settings=settings,
            worker=worker,
            signals=[_make_signal("AAPL", confidence=85)],
            compliance_map={"AAPL": _make_compliance("AAPL", compliant=True)},
            market_open=False,
            allocator_trades=[_make_trade("AAPL", quantity=5.0)],
        )
        self.assertEqual(result["execute_calls"], [])
        self.assertEqual([m for m in result["broadcast_calls"] if m.type == "pending_signal"], [])

    async def test_sweep_sends_summary_alert_when_opportunities_found(self):
        """At least one opportunity → summary alert fired."""
        worker = _make_worker(available_funds=5000.0)
        settings = {
            "cash_sweep_enabled": True,
            "cash_sweep_interval_min": 30,
            "min_trade_size": 100,
            "auto_execute_threshold": 70,
            "signal_min_confidence": 30,
            "alert_channels": ["telegram"],
        }
        result = await _run_one_sweep(
            settings=settings,
            worker=worker,
            signals=[_make_signal("AAPL", confidence=85)],
            compliance_map={"AAPL": _make_compliance("AAPL", compliant=True)},
            market_open=True,
            allocator_trades=[_make_trade("AAPL", quantity=5.0)],
        )
        summary_alerts = [a for a in result["alert_calls"] if "Cash Sweep" in a[0]]
        self.assertGreater(len(summary_alerts), 0)

    async def test_sweep_filters_non_compliant_from_batch(self):
        """AAPL (compliant) + TOBK (non-compliant) → only AAPL executed."""
        worker = _make_worker(available_funds=10000.0)
        settings = {
            "cash_sweep_enabled": True,
            "cash_sweep_interval_min": 30,
            "min_trade_size": 100,
            "auto_execute_threshold": 50,
            "signal_min_confidence": 30,
            "alert_channels": [],
        }
        result = await _run_one_sweep(
            settings=settings,
            worker=worker,
            signals=[_make_signal("AAPL", confidence=80), _make_signal("TOBK", confidence=80)],
            compliance_map={
                "AAPL": _make_compliance("AAPL", compliant=True),
                "TOBK": _make_compliance("TOBK", compliant=False),
            },
            market_open=True,
            allocator_trades=[_make_trade("AAPL", quantity=5.0), _make_trade("TOBK", quantity=5.0)],
        )
        self.assertIn("AAPL", result["execute_calls"])
        self.assertNotIn("TOBK", result["execute_calls"])


if __name__ == "__main__":
    unittest.main()
