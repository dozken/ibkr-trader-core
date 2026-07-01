# How the Bot Works — Simple Guide

## What is this bot?

An automated trading bot connected to your Interactive Brokers (IBKR) paper/live account.
It only buys **Shariah-compliant** stocks — no interest, no debt-heavy companies, no prohibited industries.
It runs 24/7 and makes trades on your behalf.

---

## The Big Picture

```
Internet News + Yahoo Finance + Alpha Vantage
        ↓
   Bot scores stocks (0–100)
        ↓
   Compliance check (Shariah) + Entry filters
        ↓
   Score ≥ 65? → Place BUY order on IBKR
        ↓
   Monitor position every 60 seconds
        ↓
   Exit rules fire → SELL (full or partial)
```

---

## Step 1 — Scoring Stocks

Every cycle the bot scores each stock using three factors:

| Factor | What it checks | Components | Default weight |
|--------|---------------|------------|----------------|
| **Fundamental (F-score)** | Financial health | PEG ratio, profit margin, ROA, current ratio, cash flow, revenue growth, earnings growth, analyst target gap, insider buys, short interest | 25% (CALM) |
| **Technical (T-score)** | Price trend strength | Price vs SMA20, 5d change, RSI, volume surge, 12m momentum, weekly trend (50-day SMA), ADX trend strength | 45% (CALM) |
| **Sentiment (S-score)** | News tone | Yahoo Finance headlines + Alpha Vantage sentiment | 30% |

Weights shift by VIX regime:
- **CALM** (VIX < 20): F=25%, T=45%, S=30%
- **ELEVATED** (VIX 20–25): F=35%, T=35%, S=30%
- **CRISIS** (VIX > 25): F=45%, T=25%, S=30% — trust fundamentals over price noise

Weights also **learn from outcomes**: after 50+ resolved signals, the bot blends historical win-rate data (70%) with VIX-regime defaults (30%) to improve.

---

## Step 2 — Safety Vetoes (applied before any BUY)

| Veto | Trigger | Effect |
|------|---------|--------|
| Sentiment Sentry | News sentiment ≤ −0.4 | Forces score ≤ 40 (HOLD) |
| Gamble Guard | Earnings report within 72h | Forces score ≤ 40 |
| Pullback Filter | Price within 1% of 20-day high OR below SMA20 | Skips BUY this cycle |
| Correlation Filter | Candidate correlates >0.85 with existing position | Skips BUY |
| Re-entry Cooldown | Symbol was sold at take-profit < 14 days ago | Skips BUY |
| Sector Cap | Sector already >25% of portfolio | Skips BUY |
| Daily Loss Limit | Today's P&L < −5% of portfolio | Pauses all buying for 1h |
| Drawdown Circuit Breaker | Cumulative drawdown > 15% | Stops all trading |

---

## Step 3 — Shariah Compliance Screen

Before ANY buy, each stock is screened against our own **AAOIFI Shari'ah Standard No. 21** ratio screen (this is the canonical verdict; certifiers Zoya/Musaffa are advisory and may only *tighten* the result — block on doubt — never loosen it):

| Rule | Limit |
|------|-------|
| Total interest-based debt / market cap | < 30% |
| Cash & interest-bearing securities / market cap (single combined gate) | < 30% |
| Impure revenue (haram income) | < 5% |
| Excluded sectors | Gambling, Alcohol, Tobacco, Defense, Weapons, Adult Content, Pork, Conventional Finance, Insurance |

---

## Step 4 — Position Sizing

The bot calculates how many shares to buy using four layers:

1. **Base size**: min(available cash − reserve, max 15% of portfolio)
2. **Kelly fraction**: scales by signal confidence — high confidence = bigger position, low = smaller. Uses half-Kelly for safety.
3. **VIX scale**: CRISIS market → 0.5×, ELEVATED → 0.75×, CALM → 1.0×
4. **Slippage penalty**: symbols with historical fill slippage >1% get 0.5× size reduction

Sector diversification: underrepresented sectors are prioritized when multiple BUY signals compete.

---

## Step 5 — Order Execution (TWAP)

Large orders use **TWAP** (Time-Weighted Average Price):
- Split into 5 slices spread over 5 minutes
- Each slice goes as a market (or limit) order

Small orders go as single market orders.

Limit orders are available (toggle in Settings) — places order at mid-price ± 0.1% tolerance instead of paying full spread.

---

## Step 6 — Exit Rules (sell conditions)

The bot monitors every open position every 60 seconds. Multiple exit rules can fire:

| Rule | Trigger | Action |
|------|---------|--------|
| **Partial profit** | Unrealized gain ≥ 10% | Sells 50% of position — locks in gains |
| **Trailing stop** | Price drops >8% from high-water mark | Sells 100% — stop moves up as price rises |
| **Full take-profit** | Unrealized gain ≥ 15% (after fees) | Sells 100% |
| **Stop-loss** | Unrealized loss ≥ 8% (ATR-adjusted) | Sells 100% |
| **Time-based exit** | Held >45 days with gain <5% | Sells 100% — forces thesis review |
| **Re-rating exit** | AI score drops ≤ 35 during 4h re-scoring | Sells 100% — proactive, not reactive |

All exit thresholds are configurable in Settings. Stop distance uses ATR (Average True Range) by default — wider stops in volatile conditions.

After a take-profit exit: **14-day re-entry cooldown** prevents immediately buying back the same stock.

---

## Step 7 — Continuous Monitoring Loops

The bot runs many parallel background tasks:

| Loop | Frequency | Purpose |
|------|-----------|---------|
| Main trading loop | Every 60s | Scan signals, check exits, execute BUYs |
| Position re-rating | Every 4h | Re-score held positions, sell if degraded |
| Cash sweep | Every 30min | Deploy idle cash when signals are strong |
| Discovery scan | Every 6h | Scan full halal universe for new opportunities |
| Compliance audit | Daily | Re-screen all holdings for Shariah compliance |
| Signal outcome tracker | Hourly | Fill in 7d/30d outcome for past signals |
| ML retraining | Weekly | Update learned weights from signal outcomes |
| Halal DRIP | Every 6h | Reinvest dividends (after purification) |
| Daily digest | Market close | Telegram: P&L, cash, positions, benchmarks |
| Position aging alert | In main loop | Telegram alert if held >60d with <5% gain |
| Purification reminder | Monthly | Telegram prompt to calculate Zakat/purification |

---

## Supported Exchanges

The bot can screen and trade stocks on 40+ exchanges worldwide:

| Region | Exchanges |
|--------|-----------|
| US | NASDAQ, NYSE (default) |
| Asia | Tokyo (.T), Hong Kong (.HK), China Shanghai (.SS), Shenzhen (.SZ), Korea (.KS), Taiwan (.TW), Singapore (.SI), India NSE (.NS), India BSE (.BO), Indonesia (.JK), Malaysia (.KL), Thailand (.BK), Philippines (.PS) |
| Oceania | Australia (.AX), New Zealand (.NZ) |
| Americas | Canada (.TO), Brazil (.SA), Mexico (.MX), Argentina (.BA), Chile (.SN) |
| Europe | London (.L), Frankfurt (.F), Paris (.PA), Stockholm (.ST), Helsinki (.HE), Oslo (.OL), Copenhagen (.CO), Amsterdam (.AS), Milan (.MI), Madrid (.MC), Zurich (.SW), Vienna (.VI), Warsaw (.WA), Athens (.AT), Istanbul (.IS) |
| MENA | Saudi Arabia (.SR), UAE Abu Dhabi (.AD), UAE Dubai (.DU), Qatar (.QA), Kuwait (.KW), Egypt (.CA) |
| Central Asia | Kazakhstan (.KZ) |

Use format `EXCHANGE:TICKER` (e.g. `HEL:NOKIA`, `SSE:600519`, `ASX:BHP`) or standard Yahoo Finance suffix (e.g. `NOKIA.HE`).

---

## Current Key Settings

| Setting | Default | Meaning |
|---------|---------|---------|
| Min trade size | $100 | Don't buy if position < this |
| Max position size | 15% of portfolio | One stock can't dominate |
| Max sector exposure | 25% | Sector concentration limit |
| Stop loss | 8% (ATR-adjusted) | Exit if position falls this much from peak |
| Take profit | 15% | Exit full position at this gain |
| Partial profit | 10% | Sell half at this gain |
| Auto-execute threshold | 60% confidence | Auto-buy above this; queue for approval below |
| Signal minimum | 30% confidence | Ignore signals below this |
| VIX scaling | On | Smaller positions in volatile markets |
| Kelly sizing | On | Position size scales with signal quality |
| ATR stops | On | Dynamic stop distance based on volatility |
| Trailing stop | On | Stop moves up as price rises |
| Pullback filter | On | Only buy 1–5% below recent high |
| Re-entry cooldown | 14 days | Wait 2 weeks after take-profit before re-buying |
| Earnings blackout | 72h | No new buys within 3 days of earnings |
| Correlation filter | 0.85 | Skip buy if >85% correlated with held position |
| Re-rating threshold | Score ≤ 35 | Sell held position if AI score degrades to this |

---

## What the Bot Does NOT Do

- **No margin trading** — buys only with settled cash
- **No short selling** — only long positions
- **No options/derivatives** — stocks only
- **No leverage** — fully Shariah-compliant, zero-interest
- **No overnight futures** — equity market hours only
- **No automatic limit increases** — you set the budget, it respects it

---

## UI Pages

| Page | What you see |
|------|-------------|
| Dashboard | Portfolio value chart, positions, P&L |
| Compliance Screen | Screen any stock for Shariah compliance |
| Signals | Pending trade approvals requiring your click |
| Portfolio | Holdings, sector breakdown, compliance status |
| Settings | All trading parameters, watchlist, risk controls |
| Signal Log | History of all signals fired + 7d/30d outcomes |
| Signal Quality | Win rates, weight evolution, learned factors |
| System Health | Loop status, last-run times, error indicators |
