# Shariah Compliance Framework

> **This document is a stub.** The single canonical screening spec now lives at the
> repo root. **Canonical spec: [ibkr-trader-core/COMPLIANCE.md](../COMPLIANCE.md).**

Screening follows **AAOIFI Shari'ah Standard No. 21**. A symbol is NON_COMPLIANT if any
screen fails (inclusive-fail `>=`, fail-closed — missing or non-positive market cap is blocked):

- Interest-based debt / market cap **< 30%**
- (cash + interest-bearing securities) / market cap **< 30%** — a single COMBINED liquidity gate (not two separate ratios)
- Prohibited (impure) income / total revenue **< 5%**

Plus a business-activity blocklist (conventional finance/insurance, alcohol, tobacco,
gambling, adult content, pork, defense/weapons). The dynamic VIX buffer only *tightens* these
thresholds, never loosens them. Our AAOIFI screen is canonical — certifiers (Zoya/Musaffa) are
advisory and may only TIGHTEN (block on non-compliant/doubtful), never loosen. Rule #1: no
interest (Riba), no margin, no shorting. Purification = dividend × non-compliant revenue %.

Canonical spec: ibkr-trader-core/COMPLIANCE.md
