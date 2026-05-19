# Deployment & Operations Guide

> Shariah-compliant auto-trader — from zero to live in 6 steps.  
> Start on **paper trading**. Run 60 days. Then go live.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [IBKR Account & IB Gateway](#2-ibkr-account--ib-gateway)
3. [Telegram Bot](#3-telegram-bot)
4. [API Keys](#4-api-keys)
5. [Environment Configuration](#5-environment-configuration)
6. [Run — Local](#6-run--local)
7. [Run — Docker (recommended for 24/7)](#7-run--docker-recommended-for-247)
8. [Verify Everything Works](#8-verify-everything-works)
9. [Settings Reference](#9-settings-reference)
10. [Paper → Live Checklist](#10-paper--live-checklist)
11. [Day-to-Day Operations](#11-day-to-day-operations)
12. [Emergency Procedures](#12-emergency-procedures)
13. [Monitoring & Alerts](#13-monitoring--alerts)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.14 recommended |
| Node.js | 18+ | For dashboard frontend |
| Docker + Compose | any recent | Only needed for option B |
| IB Gateway | latest | Free download from IBKR |
| IBKR account | — | Paper account is free |

---

## 2. IBKR Account & IB Gateway

### 2a. Open a paper trading account

1. Go to **ibkr.com** → Create Account  
   If you already have a live account: log in → User Menu → Paper Trading Account (free, instant)
2. Paper account starts with **$1,000,000 virtual USD**

### 2b. Download IB Gateway

IB Gateway is lighter than TWS and runs headless — use it for the bot.

- Download: https://www.interactivebrokers.com/en/trading/ibgateway.html
- Choose **"Standalone IB Gateway"**, not the full TWS

### 2c. Configure IB Gateway

1. Launch IB Gateway, log in with **paper account** credentials
2. Click **Configure → API → Settings**:

```
[✓] Enable ActiveX and Socket Clients
Socket port:  4002          ← paper (4001 = live)
[✓] Allow connections from: 127.0.0.1
[ ] Read-Only API           ← must be UNCHECKED (we need to place orders)
```

3. Click **OK** — keep IB Gateway running **at all times** when the bot is active
4. IB Gateway must be **re-logged in daily** (IBKR session expires ~24h). Set your OS to auto-login on boot and use the "Save password" option in IB Gateway.

> **Tip for Mac:** Add IB Gateway to Login Items (System Settings → General → Login Items) so it starts automatically on reboot.

---

## 3. Telegram Bot

All trade signals, fills, compliance violations, and daily reports are sent via Telegram.

### 3a. Create the bot

1. Open Telegram → search `@BotFather` → start chat
2. Send `/newbot` → choose a name (e.g. "MyHalalTrader") and username (e.g. `my_halal_trader_bot`)
3. Copy the **Bot Token**: looks like `123456789:ABCdef-ghijklmnopq`

### 3b. Get your Chat ID

1. Start a chat with your new bot (send it any message)
2. Open in browser (replace `YOUR_TOKEN`):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
3. Find `"chat":{"id":` in the response — that number is your **Chat ID**

Or run the helper script in the project:
```sh
bash get_telegram_chat_id.sh
```

---

## 4. API Keys

| Service | Used for | Free tier | Get key |
|---|---|---|---|
| **Alpha Vantage** | News sentiment signals | 25 calls/day | alphavantage.co/support/#api-key |
| **Zoya** | Authoritative Shariah verdicts | Free tier (~100/day) | app.zoya.finance → Settings → API |
| **FMP** | Balance sheet fallback for non-US stocks | 250 calls/day | financialmodelingprep.com/developer |

All three are optional but improve signal quality. The system falls back to yfinance if keys are missing.

---

## 5. Environment Configuration

```sh
cd /path/to/ibkr-trader
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```ini
# ── IBKR ─────────────────────────────────────────────────────────────────────
IBKR_HOST=127.0.0.1
IBKR_PORT=4002                   # 4002=paper IB Gateway | 4001=live IB Gateway
                                 # 7497=paper TWS | 7496=live TWS

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=sqlite:///./backend/data/trading_paper.db
LOG_LEVEL=INFO

# ── API Keys ──────────────────────────────────────────────────────────────────
ALPHA_VANTAGE_API_KEY=YOUR_KEY
ZOYA_API_KEY=YOUR_KEY
FMP_API_KEY=YOUR_KEY             # optional

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=987654321

# ── Security ──────────────────────────────────────────────────────────────────
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
IBKR_API_KEY=your_strong_secret_here
DEV_MODE=false
```

> **Never commit `.env` to git.** It is in `.gitignore` already.

---

## 6. Run — Local

Best for development and initial paper testing.

```sh
# Step 1: Install Python deps
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Step 2: Initialize database
python3 -c "from backend.core.database import init_db; init_db()"

# Step 3: Start backend (keep terminal open)
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Step 4: Install frontend deps (separate terminal)
cd frontend
npm install
npm run dev
```

URLs:
- Dashboard: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/system/health

---

## 7. Run — Docker (recommended for 24/7)

IB Gateway runs on the **host machine**. The bot runs in Docker. Docker Compose wires them together.

```sh
# Build and start all services
docker-compose up -d

# View logs
docker logs ibkr-backend -f

# Restart just the backend (e.g. after a code change)
docker-compose restart backend

# Stop everything
docker-compose down
```

Services started by Docker Compose:

| Container | URL | Purpose |
|---|---|---|
| `ibkr-backend` | :8000 | FastAPI + all trading loops |
| `ibkr-frontend` | :80 | React dashboard |
| `prometheus` | :9090 | Metrics collection |
| `grafana` | :3001 | Metrics visualization (login: admin/admin) |

> **Important:** IB Gateway must run on the host, not in Docker. The compose file sets `IBKR_HOST=host.docker.internal` so the container can reach it.

### Keep IB Gateway alive with a cron job (Mac)

```sh
# Check every 5 minutes; relaunch if not running
crontab -e
```
Add:
```
*/5 * * * * pgrep -x "IBGateway" || open -a "IB Gateway"
```

---

## 8. Verify Everything Works

After starting the backend, run these checks:

```sh
BASE=http://localhost:8000
KEY=your_IBKR_API_KEY_here

# 1. Backend alive
curl $BASE/health

# 2. All loops running
curl $BASE/api/system/health | python3 -m json.tool

# 3. IBKR connected
curl $BASE/api/trades/ibkr/health | python3 -m json.tool

# 4. Open orders (should be empty initially)
curl -H "x-api-key: $KEY" $BASE/api/trades/open-orders

# 5. Trigger a compliance check (manual)
curl $BASE/api/compliance/screen/AAPL | python3 -m json.tool

# 6. Trigger a signal scan
curl $BASE/api/ai/signals | python3 -m json.tool
```

Expected system health output:
```json
{
  "main_loop":               {"status": "running", "last_run": "2024-..."},
  "compliance_audit_loop":   {"status": "running", "last_run": "..."},
  "portfolio_snapshot_loop": {"status": "running", "last_run": "..."},
  ...
}
```

If any loop shows `"status": "error"`, check logs:
```sh
docker logs ibkr-backend --tail 100 | grep ERROR
```

---

## 9. Settings Reference

Settings live in `data/settings.json` and can be changed via the dashboard (Settings page) without restarting the server.

### Key settings for paper trading

```json
{
  "trading_mode": "AUTO",
  "auto_execute_threshold": 70,
  "signal_min_confidence": 50,
  "max_position_size_pct": 8.0,
  "max_sector_exposure_pct": 20.0,
  "cash_reserve_pct": 30.0,
  "max_drawdown_pct": 10.0,
  "max_daily_loss_pct": 3.0,
  "trading_start_offset_min": 30,
  "trading_end_offset_min": 30,
  "use_atr_stops": true,
  "dry_run": false
}
```

### Critical settings explained

| Setting | Default | Meaning |
|---|---|---|
| `auto_execute_threshold` | 70 | Auto-buy when signal confidence ≥ 70%. Below this → Telegram approval required |
| `signal_min_confidence` | 50 | Ignore signals below 50% confidence entirely |
| `max_drawdown_pct` | 10% | **Circuit breaker**: halt all trading if portfolio drops 10% from peak |
| `max_daily_loss_pct` | 3% | Pause trading if daily P&L < −3% of opening NLV |
| `trading_start_offset_min` | 30 | Skip first 30 min of market open (high volatility) |
| `trading_end_offset_min` | 30 | Skip last 30 min before market close |
| `cash_reserve_pct` | 30% | Always keep 30% as uninvested cash buffer |
| `critical_auto_sell` | true | Auto-liquidate positions that fail compliance re-check |
| `dry_run` | false | If true: logs trades but never submits to IBKR |

### Start conservative — tighten over time

```
Week 1-2:   auto_execute_threshold=85, signal_min_confidence=60  (almost nothing executes)
Week 3-4:   auto_execute_threshold=75, signal_min_confidence=55
Month 2+:   auto_execute_threshold=70, signal_min_confidence=50
```

---

## 10. Paper → Live Checklist

Run 60 days on paper before touching real money. Check all of these:

### Performance gates
- [ ] Annualized Sharpe ratio > 0.5 (check daily P&L in Telegram reports)
- [ ] Maximum drawdown never exceeded 10% (circuit breaker never fired)
- [ ] Win rate > 40% on closed trades
- [ ] Average winner > average loser (trailing stops working)

### Operational gates
- [ ] Daily Telegram reports arriving every market close
- [ ] No unexpected `IBKR_ERROR` clusters in trade history
- [ ] Compliance audit running every 24h (check system health)
- [ ] Bot survived at least 2 IB Gateway restarts/re-logins without issue
- [ ] Reconciliation ran correctly after each restart (check logs for "Reconciliation complete")

### Database sanity check
```sh
sqlite3 data/trading_paper.db "
  SELECT state, COUNT(*) as n
  FROM trade_history
  GROUP BY state
  ORDER BY n DESC;
"
```
Expected: mostly SUBMITTED/FILLED. Flag if IBKR_ERROR > 10% of total.

### Switch to live

1. Edit `backend/.env`:
   ```ini
   IBKR_PORT=4001                              # live IB Gateway
   DATABASE_URL=sqlite:///./backend/data/trading.db
   ```
2. Log IB Gateway out of paper → log in with **live** account
3. Start with reduced position size:
   ```json
   { "max_position_size_pct": 3.0, "cash_reserve_pct": 60.0 }
   ```
4. Increase gradually over 4 weeks as confidence builds

---

## 11. Day-to-Day Operations

### Morning (before market open)
- Verify IB Gateway is logged in and connected
- Check `http://localhost:8000/api/system/health` — all loops green
- Review overnight Telegram messages for any compliance violations

### During market hours
- Dashboard shows live positions with real-time price updates
- Signals appear on the Signals page and in Telegram
- Confidence ≥ `auto_execute_threshold`: trades automatically
- Confidence < threshold: Telegram approval button appears — tap ✅ to approve

### Evening (after market close)
- Daily Telegram digest arrives automatically with:
  - Total portfolio value
  - Day's return vs HLAL/SPY benchmark
  - Compliance status of all positions
  - Cash balance

### Weekly
- Check purification ledger (Zakat/purification page in dashboard)
- Review active strategy status at `/api/ai/ml-status` (private AI module only — public build returns 404)
- Check `discovery_loop` found new halal candidates

### Monthly (1st of month)
- Purification reminder arrives via Telegram automatically
- Donate impure income (if any) as calculated in the purification page

---

## 12. Emergency Procedures

### Cancel all open orders immediately
```sh
curl -X POST \
  -H "x-api-key: $KEY" \
  http://localhost:8000/api/trades/cancel-all-orders
```
Or: in IB Gateway → click **"Cancel All Orders"** button directly.

### Cancel a specific order
```sh
curl -X POST \
  -H "x-api-key: $KEY" \
  http://localhost:8000/api/trades/cancel-order/ORDER_ID
```

### Drawdown circuit breaker fired
The bot halts automatically and sends Telegram alert. To investigate:
1. Check `http://localhost:8000/api/system/health` → `current_drawdown_pct`
2. Review positions in dashboard
3. Circuit breaker auto-recovers when drawdown falls below `max_drawdown_pct / 2`
4. To manually reset: restart the backend (peak NLV re-seeds from DB)

### Bot is stuck / not trading
1. Check IBKR connection: `curl $BASE/api/trades/ibkr/health`
2. Check loop health: `curl $BASE/api/system/health`
3. Check drawdown flag: look for `"drawdown_triggered": true` in health response
4. Check logs: `docker logs ibkr-backend --tail 200`
5. Restart backend: `docker-compose restart backend`

### Nuclear option — liquidate everything
1. Go to IB Gateway → Account → Positions
2. Right-click each position → Close Position
3. Or call `cancel_all_orders` then manually submit market SELLs via IB Gateway

---

## 13. Monitoring & Alerts

### Prometheus + Grafana (Docker only)

Grafana: http://localhost:3001 (admin / admin on first login)

Key metrics:
- `ibkr_connected` — IBKR connection status (alert if 0)
- `total_nlv` — Portfolio net liquidation value
- `trades_executed_total` — Cumulative trades by side
- `cash_available` — Uninvested cash
- `active_positions` — Number of open positions
- `portfolio_compliance_pct` — % of positions passing Shariah screen

### Telegram alert types

| Alert | Trigger |
|---|---|
| `Trade Filled` | Any bracket order fills |
| `BUY/SELL Signal` | New signal generated, awaiting approval |
| `LIQUIDATED: SYMBOL` | Non-compliant position auto-sold |
| `ACTION REQUIRED` | Non-compliant position, auto-sell disabled |
| `🛑 DRAWDOWN CIRCUIT BREAKER` | Portfolio dropped > `max_drawdown_pct` from peak |
| `Daily Performance Digest` | Every market close |
| `🌙 Purification Reminder` | 1st of each month |
| `🚨 EMERGENCY: AUDIT LOG TAMPER` | Cryptographic hash chain broken |
| `VIX Tier Change` | Market volatility regime shift (CALM/ELEVATED/CRISIS) |

---

## 14. Troubleshooting

### "Failed to connect to IBKR"
- IB Gateway not running → launch it
- Wrong port in `.env` → 4002 for paper IB Gateway
- IB Gateway session expired → log back in
- Firewall blocking 127.0.0.1:4002 → check OS firewall / antivirus

### "No signals generated"
- Alpha Vantage key is `demo` → get a real key (free)
- Market is closed → signals only generate during trading hours
- Watchlist too small → add more tickers in Settings
- All watchlist stocks already held → no BUY signals needed

### "Compliance screen returns UNKNOWN"
- Zoya API key missing → get free key, add to `.env`
- Falls back to yfinance data, which may lack financial ratios for some stocks
- Add the symbol to watchlist and re-screen after a few hours

### "Trade state stuck at SUBMITTED"
- IBKR fill event may have been missed during reconnect
- Reconciliation runs on restart and should heal it
- Check manually: `sqlite3 trading_paper.db "SELECT * FROM trade_history WHERE state='SUBMITTED' ORDER BY created_at DESC LIMIT 10"`
- If position exists in IBKR but DB says SUBMITTED → restart backend (reconciliation will fix it)

### "Drawdown circuit breaker triggered but portfolio looks fine"
- Peak NLV was seeded from a snapshot taken when portfolio was higher
- If expected, restart backend to re-seed peak from current DB max
- Then re-evaluate whether the drawdown is real

### "Telegram alerts not arriving"
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
- Send any message to the bot first (Telegram requires user-initiated contact)
- Test: `curl "https://api.telegram.org/bot$TOKEN/getMe"`
- Check backend logs for "Telegram alert failed"

---

## Architecture Summary

```
IB Gateway (port 4002/4001)
        │
        │ ib_insync (TCP)
        ▼
┌─────────────────────────────────────────┐
│  FastAPI Backend (port 8000)            │
│                                         │
│  Loops (asyncio, all concurrent):       │
│  ├── main_loop          60s cadence     │
│  ├── compliance_audit   24h cadence     │
│  ├── cash_sweep_loop    60min cadence   │
│  ├── discovery_loop     8h cadence      │
│  ├── portfolio_snapshot 1h cadence      │
│  ├── price_push_loop    30s cadence     │
│  ├── ml_retraining      Sunday 2am      │
│  ├── daily_report_loop  market close    │
│  └── audit_integrity    1h cadence      │
│                                         │
│  Guards (checked before every trade):   │
│  ├── Shariah compliance (Zoya/yfinance) │
│  ├── Drawdown circuit breaker           │
│  ├── Daily loss limit                   │
│  ├── Time-of-day filter                 │
│  ├── VIX-adjusted position sizing       │
│  ├── Sector concentration (25% max)     │
│  ├── Slippage + liquidity check         │
│  └── T+2 possession guard (Qabd)        │
└─────────────────────────────────────────┘
        │                    │
        │ WebSocket           │ REST API
        ▼                    ▼
┌──────────────┐    ┌──────────────────┐
│  React       │    │  Telegram Bot    │
│  Dashboard   │    │  (alerts +       │
│  (port 5173) │    │   approvals)     │
└──────────────┘    └──────────────────┘
        │
        ▼
┌──────────────┐    ┌──────────────┐
│  Prometheus  │───▶│  Grafana     │
│  (port 9090) │    │  (port 3001) │
└──────────────┘    └──────────────┘
```

---

*Last updated: 2026-05-03*
