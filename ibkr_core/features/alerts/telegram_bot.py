import asyncio
import logging
import os
from typing import List

import httpx
from datetime import datetime

from ibkr_core.features.alerts.audit import log_telegram
from ibkr_core.core.health_utils import set_loop_error, clear_loop_error
from ibkr_core.features.trading.worker import IBKRWorker
from ibkr_core.features.settings.service import load_settings

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/"


async def _send_message(token: str, chat_id: str, text: str, reply_markup: dict = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(_API_URL.format(token=token) + "sendMessage", json=payload)
            log_telegram("out", chat_id, text, status="ok")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            log_telegram("out", chat_id, text, status="fail", error=str(e))


async def _answer_callback(token: str, callback_query_id: str):
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            await client.post(
                _API_URL.format(token=token) + "answerCallbackQuery",
                json={"callback_query_id": callback_query_id},
            )
        except Exception:
            pass


async def _handle_command(command: str, args: List[str], worker: IBKRWorker, token: str, chat_id: str):
    """Read-only commands + emergency liquidate only."""
    from ibkr_core.core.strategy import get_active_strategy
    from ibkr_core.features.trading.trader import Trader
    from ibkr_core.features.trading.schemas import TradeCreate

    kb = {
        "inline_keyboard": [
            [
                {"text": "📊 Status", "callback_data": "/status"},
                {"text": "🎯 Signals", "callback_data": "/signals"},
                {"text": "🆘 Liquidate", "callback_data": "/liquidate"},
            ]
        ]
    }

    if command in ("/start", "/help"):
        await _send_message(token, chat_id,
            "🏦 <b>IBKR Shariah Trader Bot</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "/status — Portfolio snapshot\n"
            "/signals — Actionable AI signals\n"
            "/liquidate [SYM] — Emergency exit\n\n"
            "<i>Approval buttons arrive for automated signals.</i>",
            reply_markup=kb
        )

    elif command == "/status":
        if not worker.ib.isConnected():
            await _send_message(token, chat_id, "⚠️ <b>IBKR disconnected</b>")
            return
        nlv = await asyncio.to_thread(worker.get_net_liquidation)
        cash = await asyncio.to_thread(worker.get_available_funds)
        pos = await asyncio.to_thread(worker.get_positions)
        await _send_message(token, chat_id,
            f"📊 <b>Portfolio Status</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Net Value: ${nlv:,.2f}\n"
            f"💵 Cash: ${cash:,.2f}\n"
            f"📈 Positions: {len(pos)}",
            reply_markup=kb
        )

    elif command == "/signals":
        await _send_message(token, chat_id, "🔍 <i>Scanning market...</i>")
        held = {p["symbol"] for p in await asyncio.to_thread(worker.get_positions)} if worker.ib.isConnected() else set()
        signals = await get_active_strategy().get_guarded_signals(held_symbols=held)
        
        actionable = [s for s in signals if s.action in ("BUY", "SELL")]
        if not actionable:
            await _send_message(token, chat_id, "⏸ No actionable Shariah-compliant signals at this time.")
            return

        lines = ["🎯 <b>Actionable Signals</b>", "━━━━━━━━━━━━━━━━━━"]
        for s in actionable[:8]:
            icon = "🟢" if s.action == "BUY" else "🔴"
            lines.append(f"{icon} <b>{s.action} {s.symbol}</b> (Conf: {s.confidence}%)\n<i>{s.reasoning}</i>\n")
        
        await _send_message(token, chat_id, "\n".join(lines))

    elif command == "/liquidate":
        if not args:
            await _send_message(token, chat_id, "⚠️ <b>Usage:</b> /liquidate [SYMBOL]")
            return
        
        symbol = args[0].upper()
        if not worker.ib.isConnected():
            await _send_message(token, chat_id, "⚠️ IBKR not connected.")
            return

        positions = await asyncio.to_thread(worker.get_positions)
        pos = next((p for p in positions if p["symbol"] == symbol), None)
        if not pos or pos["quantity"] == 0:
            await _send_message(token, chat_id, f"⚠️ You do not hold any shares of {symbol}.")
            return

        await _send_message(token, chat_id, f"🆘 <i>Liquidating {symbol} ({pos['quantity']} shares)...</i>")
        try:
            trader = Trader(worker)
            trade = await trader.execute_trade(
                TradeCreate(symbol=symbol, quantity=pos["quantity"], side="SELL")
            )
            await _send_message(token, chat_id, f"💀 <b>{symbol} LIQUIDATED</b>\nStatus: {trade.state}")
        except Exception as e:
            await _send_message(token, chat_id, f"❌ Liquidation failed for {symbol}: {e}")

    else:
        await _send_message(token, chat_id, "Commands: /status · /signals · /liquidate", reply_markup=kb)


async def _handle_signal_approval(symbol: str, worker: IBKRWorker, token: str, chat_id: str):
    """Approve a pending BUY signal via inline button callback."""
    from ibkr_core.features.compliance.screening import async_shariah_screen
    from ibkr_core.features.trading.trader import Trader
    from ibkr_core.features.trading.schemas import TradeCreate

    await _send_message(token, chat_id, f"⏳ <i>Executing BUY {symbol}...</i>")
    try:
        compliance = await async_shariah_screen(symbol)
        if not compliance.is_compliant:
            await _send_message(token, chat_id, f"🚫 <b>{symbol}</b> failed compliance re-check.\n<i>{compliance.reason}</i>")
            return
        trader = Trader(worker)
        trade = await trader.execute_trade(
            TradeCreate(symbol=symbol, quantity=0, side="BUY"),
            pre_screened=compliance,
        )
        state = trade.state.value if hasattr(trade.state, "value") else str(trade.state)
        oid = trade.ibkr_order_id or "—"
        await _send_message(token, chat_id, f"✅ <b>BUY {symbol}</b>\nStatus: {state} · Order #{oid}")
    except Exception as e:
        await _send_message(token, chat_id, f"❌ Execution failed for {symbol}:\n{e}")


async def telegram_bot_loop(worker, health: dict) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    health["telegram_bot_loop"] = {"last_run": None, "status": "starting"}

    if not token or not allowed_chat_id:
        logger.warning("Telegram bot disabled: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set.")
        health["telegram_bot_loop"]["status"] = "disabled"
        return

    health["telegram_bot_loop"]["status"] = "running"
    offset = 0

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=45, write=10, pool=10)) as client:
        while True:
            try:
                resp = await client.get(
                    _API_URL.format(token=token) + "getUpdates",
                    params={"offset": offset, "timeout": 30,
                            "allowed_updates": ["message", "callback_query"]},
                )
                resp.raise_for_status()
                data = resp.json()

                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    # Inline button press
                    cq = update.get("callback_query", {})
                    if cq:
                        cb_id = cq.get("id")
                        if cb_id:
                            asyncio.create_task(_answer_callback(token, cb_id))
                        chat_id = str(cq.get("message", {}).get("chat", {}).get("id", ""))
                        cb_data = cq.get("data", "")
                        username = cq.get("from", {}).get("username")
                        if chat_id != allowed_chat_id:
                            log_telegram("in", chat_id, cb_data, kind="callback",
                                         username=username, status="unauthorized")
                            continue
                        log_telegram("in", chat_id, cb_data, kind="callback",
                                     username=username, status="ok")
                        if cb_data.startswith("approve:"):
                            symbol = cb_data.split(":", 1)[1].upper()
                            asyncio.create_task(_handle_signal_approval(symbol, worker, token, chat_id))
                        elif cb_data.startswith("/"):
                            parts = cb_data.split()
                            command = parts[0].lower()
                            args = parts[1:]
                            asyncio.create_task(_handle_command(command, args, worker, token, chat_id))
                        continue

                    # Text command
                    msg = update.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "").strip()
                    username = msg.get("from", {}).get("username")
                    if chat_id != allowed_chat_id:
                        logger.warning(f"Unauthorized Telegram access from chat {chat_id}")
                        log_telegram("in", chat_id, text, kind="message",
                                     username=username, status="unauthorized")
                        continue
                    log_telegram("in", chat_id, text, kind="message",
                                 username=username, status="ok")
                    if text.startswith("/"):
                        parts = text.split()
                        command = parts[0].lower()
                        args = parts[1:]
                        asyncio.create_task(_handle_command(command, args, worker, token, chat_id))

                health["telegram_bot_loop"]["last_run"] = datetime.now().isoformat()
                clear_loop_error(health["telegram_bot_loop"])
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException):
                health["telegram_bot_loop"]["last_run"] = datetime.now().isoformat()
                continue
            except Exception as e:
                logger.error(f"telegram_bot_loop error: {e}")
                set_loop_error(health["telegram_bot_loop"], 10, e)
                await asyncio.sleep(10)
