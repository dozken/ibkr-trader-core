# Telegram Notifications

Telegram is the sole notification channel. Configure with two env vars:

```
TELEGRAM_BOT_TOKEN=<bot token from @BotFather>
TELEGRAM_CHAT_ID=<your personal chat ID>
```

Alerts fire when `alert_channels` includes `"telegram"` in settings (default: enabled).

---

## Push Alerts (System → You)

These fire automatically from background loops.

### Trade Events

| Trigger | When |
|---|---|
| **Signal: BUY/SELL `SYMBOL`** | AI found actionable signal, awaiting your approval in dashboard |
| **Cash Sweep Complete** | Idle cash deployed into N halal opportunities |
| *(future)* **Trade Filled** | IBKR fill confirmation with price and qty |

### Compliance Events

| Trigger | When |
|---|---|
| **ACTION REQUIRED: `SYMBOL` Non-Compliant** | Position failed re-screen; `critical_auto_sell=False` — sell manually |
| **LIQUIDATED: `SYMBOL`** | Kill-switch fired; auto-sold N shares; reason included |
| **WATCH: `SYMBOL` — MERGER/SPINOFF** | yfinance news keyword hit — ratios may change, manual review |

### Daily Digest (4PM market close)

Fires once per day after US market close if IBKR connected:

```
📊 Market Close Report
━━━━━━━━━━━━━━━━━━
💰 Total Value: $124,500.00
💵 Cash: $12,300.00
📈 Total Positions: 8
🛡️ Shariah Safe: 8/8
━━━━━━━━━━━━━━━━━━
Log in to the dashboard for details.
```

### System Health

| Trigger | When |
|---|---|
| **IBKR Connection Failed** | TWS/Gateway unreachable at startup |
| **Main Loop Crashed** | Unhandled exception — restart required |

---

## Remote Commands (You → Bot)

Security: only your `TELEGRAM_CHAT_ID` is accepted. All other senders are silently ignored and logged.

Bot is read-only + emergency exit. Trading and rebalancing happen in the dashboard.

| Command | Action |
|---|---|
| `/start` or `/help` | Show command list |
| `/status` | Net value, cash, open position count |
| `/signals` | AI actionable signals (BUY/SELL/HOLD) |
| `/liquidate SYMBOL` | Kill switch — sell 100% of position immediately |

> `/liquidate` bypasses compliance screening intentionally — it's an emergency exit.

---

## Planned Additions

- **VIX buffer notification** — alert when dynamic ratio buffer changes tier (calm → elevated → crisis), so you know thresholds tightened
- **Trade filled confirmation** — push confirmation with fill price + qty when IBKR executes an order
- **Purification reminder** — monthly reminder to calculate and donate impure income
- **`/zakat`** — on-demand Zakat calculation in chat

---

## Not Supported

Discord, Slack, Email, and SMS (Twilio) are intentionally excluded. Single user, single channel.
