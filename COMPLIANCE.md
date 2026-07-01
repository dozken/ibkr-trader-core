# COMPLIANCE.md — Shariah Screening Specification

**Canonical standard: AAOIFI Shari'ah Standard No. 21** (*Financial Paper — Shares and Bonds*),
with Standard No. 57 (*Gold and its Trading Controls*) for physical-gold instruments.

This document is the single source of truth for what the bot considers halal. The screening
engine (`ibkr_core/features/compliance/screening.py`) MUST match this spec exactly. If code and
this document disagree, this document wins and the code is the bug.

Rule #1 (project-wide): **no interest (Riba), no margin, no shorting.** Screening is fail-closed —
if compliance cannot be determined, the symbol is **blocked**, never traded on doubt.

---

## 1. Financial ratio screens (AAOIFI Standard 21)

All ratios use **market capitalisation** as the denominator (spot market cap; a trailing average
MAY be substituted later — see §6). A symbol is **NON_COMPLIANT** if *any* screen fails.

| # | Screen | Rule (pass) | Fail condition |
|---|--------|-------------|----------------|
| A | Interest-based debt | `debt / mkt_cap < 30%` | `>= 30%` |
| B | Interest-bearing liquidity | `(cash + interest_bearing_securities) / mkt_cap < 30%` | `>= 30%` |
| C | Impure income | `prohibited_income / total_revenue < 5%` | `>= 5%` |

All three comparisons are inclusive-fail (`>=` the buffered threshold) — a ratio exactly at the
limit is blocked. This is one notch stricter than a literal "not exceeding" reading of AAOIFI, chosen
deliberately (a false NON_COMPLIANT is lost opportunity; a false COMPLIANT trades a haram name).
Also fail-closed: a non-positive market cap (`mkt_cap <= 0`) is undeterminable → blocked.

Notes:
- Screen **B is COMBINED** — cash and interest-bearing securities are summed into a single
  liquidity figure and screened against one 30% limit. (They are NOT two separate 30% gates.)
- `prohibited_income` = interest income where available, else non-operating income (conservative).
- Thresholds are **30% / 30% / 5%** — AAOIFI. (33% is Dow Jones Islamic / S&P; not used here.)

### Dynamic VIX buffer
A market-volatility buffer (`ratio_buffer`, percentage points from `compliance/vix.py`,
values 0 / 2 / 5 at VIX < 20 / 20–30 / ≥ 30) **tightens** every threshold:
`effective_threshold = base_threshold - ratio_buffer/100`. The buffer only makes screening
*stricter*, never looser. A per-account `settings.ratio_buffer` acts as a floor.

---

## 2. Business-activity screen

A symbol whose sector matches any prohibited category is NON_COMPLIANT regardless of ratios:

`Conventional Finance, Conventional Insurance, Alcohol, Tobacco, Gambling, Adult Content,
Pork, Defense, Weapons, Entertainment, Interest-bearing` (+ per-account `sector_exclusion`).

---

## 3. Source-of-truth hierarchy (our screen is canonical)

Evaluated top-down; first decisive layer wins:

1. **Static allowlists** — physical-gold ETCs (AAOIFI Std 57) and Shariah-certified ETFs.
   Explicit, human-vetted → COMPLIANT short-circuit.
2. **Manual verification** — user-confirmed halal with a TTL (default 90d). Short-circuit while valid.
3. **Our AAOIFI ratio screen** — **THE canonical verdict** whenever financial data is available.
   This is deterministic, auditable, and independent of any third-party API key.
4. **Certifier fallback** — Zoya / Musaffa verdict is used **only when our own financial data is
   unavailable** (e.g. Gulf/ADX/DFM tickers yfinance can't cover). Flagged as certifier-sourced.
5. **Fail-closed** — no allowlist, no manual, no financials, no certifier → **BLOCKED** (UNKNOWN).

**Certifiers are advisory, not authoritative — and may only TIGHTEN, never loosen.** Our AAOIFI
screen is the canonical verdict. When our screen has data:
- Certifier **agrees** → recorded as corroboration.
- Certifier says **non-compliant / doubtful** while our ratios pass → **blocked, fail-closed**
  (a professional Shariah board flagging a name is credible doubt; AGENT.md: compliance doubt → block),
  and a `DISAGREEMENT`/`WARNING` is logged for review.
- Certifier says **compliant** while our ratios **fail** → still **blocked** (our screen is necessary);
  disagreement logged.

So a name is halal **iff it passes our AAOIFI screen AND no consulted certifier flags it**. A
certifier can never make a name that fails our ratios halal. This removes the previous behaviour
where a live Zoya key silently overrode our ratios (two methodologies → non-deterministic), while
keeping the system fail-closed on any credible non-compliance signal.

---

## 4. Purification (dividend cleansing)

For dividends received from a compliant-but-imperfect holding (impure income 0 < x ≤ 5%):

```
purification_amount = total_dividend * non_compliant_revenue_pct
```

(`ibkr_core/features/zakat/purification.py`.) This amount is donated, not retained. Tracked per
holding and surfaced in the portfolio purification total.

---

## 5. Data quality & caching

- **Staleness**: financials older than `COMPLIANCE_STALENESS_DAYS` (default 90) are flagged `STALE`
  in `sources_detail`; the ratios are still applied but the note travels with the verdict.
- **Cache**: 24h TTL per symbol. A `ratio_buffer_override` bypasses the cache (used for VIX re-screens).
- **Every trade** carries a Compliance Snapshot (AGENT.md §Transparency).

---

## 6. Deliberately deferred (documented, not yet implemented)

- **Trailing-average market cap** denominator (AAOIFI permits; DJIM mandates 24-mo). Current impl
  uses spot market cap — simpler, slightly more conservative on price spikes for the debt ratio.
- **Accounts-receivable / liquidity screen** (DJIM/MSCI have it; AAOIFI Std 21 does not require a
  separate receivables ratio). Not screened. The data feed also lacks `accounts_receivable`.

Any change to §1 thresholds, §3 hierarchy, or the standard itself MUST update this document and the
pinned tests in `ibkr_core/features/compliance/tests/` in the same commit.
