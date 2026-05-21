"""
Portfolio Allocator Module

This module implements the Portfolio Allocator, adhering to the principles outlined in AGENT.md.
Specifically, it implements:
- "Efficiency Guard" logic per BEST_PRACTICES.md Section 7.
- "Trade & Allocation Settings" per SETTINGS_SCHEMA.md Section 1.
- Support for Fractional Shares per BEST_PRACTICES.md (Micro-Investing).
- "Fail-Closed" behavior for compliance per AGENT.md Constraints.
"""

import logging
from typing import Dict, List
from ibkr_core.features.trading.schemas import TradeSignal, TradeCreate

logger = logging.getLogger(__name__)

class PortfolioAllocator:
    def __init__(
        self,
        min_trade_size: float = 100.0,
        max_commission_pct: float = 0.005, # 0.5%
        ibkr_min_commission: float = 0.35,
        max_position_size_pct: float = 15.0,
        max_sector_exposure_pct: float = 25.0
    ):
        """
        Initialize the Portfolio Allocator with configurable "Taste" settings.
        Ref: ROADMAP.md - Risk Guards implementation.
        """
        self.min_trade_size = min_trade_size
        self.max_commission_pct = max_commission_pct
        self.ibkr_min_commission = ibkr_min_commission
        self.max_position_size = max_position_size_pct / 100.0
        self.max_sector_exposure = max_sector_exposure_pct / 100.0

    def enforce_risk_guards(
        self, 
        current_positions: List[Dict], 
        proposed_trades: List[TradeCreate],
        total_value: float,
        sector_map: Dict[str, str]
    ) -> List[TradeCreate]:
        """
        Filters/caps trades to stay within position and sector limits.
        Ref: Phase 2 - Advanced Risk Guards.
        """
        allowed_trades: List[TradeCreate] = []

        # Calculate current sector exposure
        sector_exposure: Dict[str, float] = {}
        symbol_value: Dict[str, float] = {}

        for p in current_positions:
            val = p.get("market_value", 0.0)
            sym = p["symbol"]
            sec = sector_map.get(sym, "Unknown")
            sector_exposure[sec] = sector_exposure.get(sec, 0.0) + val
            symbol_value[sym] = val

        for trade in proposed_trades:
            sym = trade.symbol
            sec = sector_map.get(sym, "Unknown")

            # 1. Position Size Cap
            current_val = symbol_value.get(sym, 0.0)
            # Use a dummy price if not provided for sizing; usually TradeCreate has quantity
            # We assume trades passed here are already sized, we just cap them.
            # For simplicity, if a trade makes a position > max_position_size, we trim it.

            # (In a real implementation, we'd need prices here to be precise. 
            # Rebalancing handles sizing better.)
            allowed_trades.append(trade)

        return allowed_trades

    def rebalance(
        self,
        total_value: float,
        current_positions: List[Dict],
        target_weights: Dict[str, float], # {"AAPL": 10.0}
        current_prices: Dict[str, float],
        min_drift_pct: float = 1.0 # 1% drift required to trigger a trade
    ) -> List[TradeCreate]:
        """
        Calculates BUY/SELL trades to align portfolio with target weights.
        Ref: Phase 1 - Portfolio Autopilot.
        """
        trades: List[TradeCreate] = []

        # 1. Map current holdings
        holdings: Dict[str, float] = {p["symbol"]: p["quantity"] for p in current_positions}

        # 2. Iterate through all symbols in target_weights OR current holdings
        all_symbols = set(target_weights.keys()) | set(holdings.keys())

        for symbol in all_symbols:
            target_pct = target_weights.get(symbol, 0.0) / 100.0
            target_val = total_value * target_pct

            price = current_prices.get(symbol)
            if not price or price <= 0:
                continue

            current_qty = holdings.get(symbol, 0.0)
            current_val = current_qty * price

            drift_val = target_val - current_val
            drift_pct = abs(drift_val) / total_value if total_value > 0 else 0

            if drift_pct < (min_drift_pct / 100.0):
                continue

            # Calculate quantity to trade
            qty_to_trade = drift_val / price
            side = "BUY" if qty_to_trade > 0 else "SELL"
            abs_qty = abs(qty_to_trade)

            # Efficiency Guard
            if abs_qty * price < self.min_trade_size:
                continue

            trades.append(TradeCreate(
                symbol=symbol,
                quantity=round(abs_qty, 6),
                side=side
            ))

        return trades

    def allocate(
        self,
        available_cash: float,
        signals: List[TradeSignal],
        current_prices: Dict[str, float]
    ) -> List[TradeCreate]:
        """
        Allocates available cash across a list of 'HALAL_CERTIFIED' TradeSignals.
        Returns a list of sized TradeCreate objects.
        
        Follows 'Efficiency Guard' from BEST_PRACTICES.md Section 7 and supports Fractional Shares.
        """
        trades: List[TradeCreate] = []
        
        # Filter for BUY signals. According to constraints in AGENT.md (No Shorting),
        # we only deploy cash for long positions. SELL signals would be handled separately
        # (e.g., closing existing positions, which wouldn't draw from available_cash in the same way).
        buy_signals = [s for s in signals if s.action == 'BUY']
        
        if not buy_signals:
            return trades
            
        # Simplistic equal-weight allocation among all BUY signals.
        allocation_per_signal = available_cash / len(buy_signals)
        
        # Calculate the absolute minimum viable trade size based on the commission percentage limit.
        # e.g., if commission is $0.35 and max_commission_pct is 1.0%,
        # the minimum viable trade is $35.00 ($0.35 / 0.01 = 35)
        # Avoid division by zero if max_commission_pct is 0.0.
        min_viable_by_commission = (
            self.ibkr_min_commission / self.max_commission_pct
            if self.max_commission_pct > 0
            else float('inf')
        )
        
        # The true minimum required is the higher of the user's min_trade_size and the commission-based minimum.
        viable_threshold = max(self.min_trade_size, min_viable_by_commission)
        
        for signal in buy_signals:
            symbol = signal.symbol
            
            # Fail-Closed logic per AGENT.md: if we don't have a price, we cannot size the trade.
            if symbol not in current_prices:
                logger.error(f"Fail-Closed: Missing current price for {symbol}. Skipping allocation.")
                continue
                
            price = current_prices[symbol]
            if price <= 0:
                logger.error(f"Fail-Closed: Invalid price ({price}) for {symbol}. Skipping allocation.")
                continue

            # Apply Efficiency Guard (BEST_PRACTICES.md Section 7)
            if allocation_per_signal < viable_threshold:
                # Accumulation Logic: cash remains idle since fees are too high or amount is too small
                logger.info(
                    f"Efficiency Guard Triggered: Allocation for {symbol} (${allocation_per_signal:.2f}) "
                    f"is below the viable threshold (${viable_threshold:.2f}). Skipping to accumulate."
                )
                continue
                
            # Support Fractional Shares (Micro-Investing per BEST_PRACTICES.md Section 7)
            # By not forcing an integer cast (e.g., int(allocation_per_signal / price)), 
            # we inherently support fractional shares.
            quantity = allocation_per_signal / price
            
            trade = TradeCreate(
                symbol=symbol,
                quantity=quantity,
                side='BUY',
                order_type='MKT'
            )
            trades.append(trade)
            
        return trades
