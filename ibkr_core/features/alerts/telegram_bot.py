import asyncio
import logging
import os
from typing import Dict, List, Optional

import httpx
from datetime import datetime

from ibkr_core.features.alerts.audit import log_telegram
from ibkr_core.core.health_utils import set_loop_error, clear_loop_error
from ibkr_core.features.trading.worker import IBKRWorker
from ibkr_core.features.settings.service import load_settings

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/"

# chat_id → selected account DB id
_selected_account: Dict[str, int] = {}


def _get_account_labels() -> Dict[int, str]:
    from ibkr_core.core.database import SessionLocal
    from ibkr_core.core.models import Account
    db = SessionLocal()
    try:
        rows = db.query(Account).filter(Account.is_active == True).order_by(Account.id).all()
        return {a.id: a.label for a in rows}
    finally:
        db.close()


def _resolve_worker(account_manager, chat_id: str, fallback_worker: IBKRWorker) -> (IBKRWorker, int, str):
    """Returns (worker, account_id, label) for the chat's selected account."""
    labels = _get_account_labels()
    aid = _selected_account.get(chat_id)
    if aid and account_manager:
        w = account_manager.get_worker_by_id(aid)
        if w:
            return w, aid, labels.get(aid, f"Account {aid}")
    if account_manager:
        first_id = account_manager.list_account_ids()[0] if account_manager.list_account_ids() else None
        if first_id:
            w = account_manager.get_worker_by_id(first_id)
            if w:
                return w, first_id, labels.get(first_id, f"Account {first_id}")
    return fallback_worker, 0, "Default"


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


async def _handle_command(command: str, args: List[str],
                          worker: IBKRWorker, account_manager,
                          token: str, chat_id: str):
    """Read-only commands + emergency liquidate only."""
    from ibkr_core.core.strategy import get_active_strategy
    from ibkr_core.features.trading.trader import Trader
    from ibkr_core.features.trading.schemas import TradeCreate

    w, aid, label = _resolve_worker(account_manager, chat_id, worker)

    kb = {
        "inline_keyboard": [
            [
                {"text": "📊 Status", "callback_data": "/status"},
                {"text": "🎯 Signals", "callback_data": "/signals"},
                {"text": "🔀 Accounts", "callback_data": "/accounts"},
            ]
        ]
    }

    if command in ("/start", "/help"):
        await _send_message(token, chat_id,
            "🏦 <b>IBKR Shariah Trader Bot</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "/accounts — Switch account\n"
            "/status — Portfolio snapshot\n"
            "/signals — Actionable AI signals\n"
            "/liquidate [SYM] — Emergency exit\n\n"
            f"<i>Active: {label}</i>",
            reply_markup=kb
        )

    elif command == "/accounts":
        labels = _get_account_labels()
        if not labels:
            await _send_message(token, chat_id, "⚠️ No accounts configured.")
            return
        buttons = []
        for acc_id, acc_label in labels.items():
            connected = False
            if account_manager:
                aw = account_manager.get_worker_by_id(acc_id)
                connected = aw and aw.ib.isConnected()
            icon = "✅" if acc_id == aid else "⬜"
            status = "🟢" if connected else "🔴"
            buttons.append([{
                "text": f"{icon} {status} {acc_label}",
                "callback_data": f"account:{acc_id}",
            }])
        await _send_message(token, chat_id,
            f"🔀 <b>Select Account</b>\n<i>Current: {label}</i>",
            reply_markup={"inline_keyboard": buttons}
        )

    elif command == "/status":
        if not w.ib.isConnected():
            await _send_message(token, chat_id,
                f"⚠️ <b>{label}</b> — IBKR disconnected", reply_markup=kb)
            return
        nlv = await asyncio.to_thread(w.get_net_liquidation)
        cash = await asyncio.to_thread(w.get_available_funds)
        pos = await asyncio.to_thread(w.get_positions)
        total_pnl = sum(float(p.get("unrealized_pnl", 0)) for p in pos)
        total_cost = sum(float(p.get("avg_cost", 0)) * float(p.get("quantity", 0)) for p in pos)
        ret_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0
        pnl_icon = "📈" if total_pnl >= 0 else "📉"
        settings = load_settings(aid if aid else None)
        mode = settings.get("trading_mode", "?")
        await _send_message(token, chat_id,
            f"📊 <b>{label}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Net Value: ${nlv:,.2f}\n"
            f"💵 Cash: ${cash:,.2f}\n"
            f"📈 Positions: {len(pos)}\n"
            f"{pnl_icon} P&L: ${total_pnl:,.2f} ({ret_pct:+.1f}%)\n"
            f"⚙️ Mode: {mode}",
            reply_markup=kb
        )

    elif command == "/signals":
        await _send_message(token, chat_id, f"🔍 <i>Scanning for {label}...</i>")
        held = {p["symbol"] for p in await asyncio.to_thread(w.get_positions)} if w.ib.isConnected() else set()
        signals = await get_active_strategy().get_guarded_signals(held_symbols=held)

        actionable = [s for s in signals if s.action in ("BUY", "SELL")]
        if not actionable:
            await _send_message(token, chat_id,
                f"⏸ No actionable signals for <b>{label}</b>.")
            return

        lines = [f"🎯 <b>Signals — {label}</b>", "━━━━━━━━━━━━━━━━━━"]
        for s in actionable[:8]:
            icon = "🟢" if s.action == "BUY" else "🔴"
            lines.append(f"{icon} <b>{s.action} {s.symbol}</b> (Conf: {s.confidence}%)\n<i>{s.reasoning}</i>\n")

        await _send_message(token, chat_id, "\n".join(lines))

    elif command == "/liquidate":
        if not args:
            await _send_message(token, chat_id, "⚠️ <b>Usage:</b> /liquidate [SYMBOL]")
            return

        if w.readonly:
            await _send_message(token, chat_id,
                f"🚫 <b>{label}</b> is read-only. Cannot execute trades.")
            return

        symbol = args[0].upper()
        if not w.ib.isConnected():
            await _send_message(token, chat_id, f"⚠️ {label} — IBKR not connected.")
            return

        positions = await asyncio.to_thread(w.get_positions)
        pos = next((p for p in positions if p["symbol"] == symbol), None)
        if not pos or pos["quantity"] == 0:
            await _send_message(token, chat_id, f"⚠️ {label} does not hold {symbol}.")
            return

        await _send_message(token, chat_id,
            f"🆘 <i>Liquidating {symbol} ({pos['quantity']} shares) on {label}...</i>")
        try:
            trader = Trader(w)
            trade = await trader.execute_trade(
                TradeCreate(symbol=symbol, quantity=pos["quantity"], side="SELL")
            )
            await _send_message(token, chat_id,
                f"💀 <b>{symbol} LIQUIDATED</b> on {label}\nStatus: {trade.state}")
        except Exception as e:
            await _send_message(token, chat_id, f"❌ Liquidation failed for {symbol}: {e}")

    else:
        await _send_message(token, chat_id,
            f"Commands: /accounts · /status · /signals · /liquidate\n"
            f"<i>Active: {label}</i>", reply_markup=kb)


async def _handle_signal_approval(symbol: str, worker: IBKRWorker,
                                   account_manager, token: str, chat_id: str):
    """Approve a pending BUY signal via inline button callback."""
    from ibkr_core.features.compliance.screening import async_shariah_screen
    from ibkr_core.features.trading.trader import Trader
    from ibkr_core.features.trading.schemas import TradeCreate

    w, aid, label = _resolve_worker(account_manager, chat_id, worker)

    if w.readonly:
        await _send_message(token, chat_id,
            f"🚫 <b>{label}</b> is read-only. Cannot execute trades.\n"
            f"Switch to a trading account with /accounts first.")
        return

    await _send_message(token, chat_id, f"⏳ <i>Executing BUY {symbol} on {label}...</i>")
    try:
        compliance = await async_shariah_screen(symbol)
        if not compliance.is_compliant:
            await _send_message(token, chat_id, f"🚫 <b>{symbol}</b> failed compliance re-check.\n<i>{compliance.reason}</i>")
            return
        trader = Trader(w)
        trade = await trader.execute_trade(
            TradeCreate(symbol=symbol, quantity=0, side="BUY"),
            pre_screened=compliance,
        )
        state = trade.state.value if hasattr(trade.state, "value") else str(trade.state)
        oid = trade.ibkr_order_id or "—"
        await _send_message(token, chat_id, f"✅ <b>BUY {symbol}</b> on {label}\nStatus: {state} · Order #{oid}")
    except Exception as e:
        await _send_message(token, chat_id, f"❌ Execution failed for {symbol}:\n{e}")


async def telegram_bot_loop(worker, health: dict, account_manager=None) -> None:
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
                        if cb_data.startswith("account:"):
                            acc_id = int(cb_data.split(":", 1)[1])
                            _selected_account[chat_id] = acc_id
                            labels = _get_account_labels()
                            lbl = labels.get(acc_id, f"Account {acc_id}")
                            await _send_message(token, chat_id,
                                f"✅ Switched to <b>{lbl}</b>")
                            asyncio.create_task(
                                _handle_command("/status", [], worker, account_manager, token, chat_id))
                        elif cb_data.startswith("approve:"):
                            parts = cb_data.split(":")
                            symbol = parts[1].upper()
                            if len(parts) >= 3 and parts[2].isdigit():
                                _selected_account[chat_id] = int(parts[2])
                            asyncio.create_task(
                                _handle_signal_approval(symbol, worker, account_manager, token, chat_id))
                        elif cb_data.startswith("/"):
                            parts = cb_data.split()
                            command = parts[0].lower()
                            args = parts[1:]
                            asyncio.create_task(
                                _handle_command(command, args, worker, account_manager, token, chat_id))
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
                        asyncio.create_task(
                            _handle_command(command, args, worker, account_manager, token, chat_id))

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
