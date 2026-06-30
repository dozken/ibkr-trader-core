"""
OrderPolicy — the single, broker-free home for the market-vs-limit decision.

Order-type selection used to be duplicated across IBKRWorker.place_order (single
orders) and IBKRWorker.place_bracket_order (bracket entry), and the delayed-data
detection lived implicitly in the connection port. This module centralises that
rule so it is pure, side-effect free, and unit-testable without ib_insync or a
database:

  * On delayed market data (reqMarketDataType(3)) a bare MARKET order is
    cancelled by IBKR (error 10349), so we must route to a *marketable* LIMIT.
  * The operator can also force limit orders via the use_limit_orders setting.
  * A 0/None price can never build a usable limit (it would rest forever or fill
    absurdly), so we fail closed with a ValueError before anything reaches the
    broker — preserving the guard previously inlined in place_order.

The single-order slippage (limit_order_slippage_pct) and the bracket entry
premium (BRACKET_ENTRY_PREMIUM_PCT) are kept as *distinct* inputs and are
deliberately not merged.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Ports on which IBKR serves real-time market data; everything else is treated
# as delayed (reqMarketDataType(3)), where bare MARKET orders get cancelled.
# Canonical home for the literal set duplicated in worker.connect / router /
# main port_type checks.
LIVE_PORTS = frozenset({7496, 4001, 4003})

# Bracket entry premium (percent): the parent BUY limit is placed this far above
# the signal price so it fills immediately like a market order. Distinct from the
# single-order limit_order_slippage_pct — do not merge the two knobs.
BRACKET_ENTRY_PREMIUM_PCT = 0.5


class DataState(Enum):
    REALTIME = "realtime"  # real-time market data — MARKET orders fill normally
    DELAYED = "delayed"    # reqMarketDataType(3) — bare MARKET orders are cancelled (IBKR 10349)


def subscription_for_port(port: int) -> DataState:
    """Classify a connection port into its market-data subscription state."""
    return DataState.REALTIME if port in LIVE_PORTS else DataState.DELAYED


def marketable_limit(price: float, side: str, slippage_pct: float) -> float:
    """Limit price skewed across the spread so it fills like a market order.

    BUY pays up (price * (1 + slip)); SELL gives up (price * (1 - slip)).
    slippage_pct is a percentage value (0.1 == 0.1%). Rounded to 2dp (USD tick).
    """
    slip = slippage_pct / 100.0
    return round(price * (1 + slip) if side == "BUY" else price * (1 - slip), 2)


@dataclass(frozen=True)
class OrderDecision:
    order_type: str               # "MKT" | "LMT"
    limit_price: Optional[float]  # None for a MARKET order
    reason: str


class OrderPolicy:
    """Pure market-vs-limit decision. No broker, no DB, no I/O."""

    @staticmethod
    def decide(
        data_state: DataState,
        order_type: str,
        side: str,
        price: float,
        slippage_pct: float,
        symbol: str = "",
    ) -> OrderDecision:
        """Resolve the order type and, when a limit, its marketable limit price.

        ``order_type`` is the operator's base intent ("MKT" by default, "LMT"
        when use_limit_orders is set). The decision UPGRADES "MKT" to a
        marketable "LMT" on delayed data, because a bare MARKET order would be
        cancelled by IBKR (error 10349).

        Raises ValueError when a limit is required but no usable price is
        available (fail-closed: a $0 limit rests forever / fills absurdly).
        """
        want_limit = order_type == "LMT" or data_state is DataState.DELAYED
        if not want_limit:
            return OrderDecision("MKT", None, "realtime data — market order")
        if not price or price <= 0:
            sym = f" {symbol}" if symbol else ""
            raise ValueError(
                f"Refusing limit {side}{sym}: no usable price "
                f"({price}) — likely missing/blocked market data."
            )
        if order_type == "LMT":
            reason = "use_limit_orders — marketable limit"
        else:
            reason = "delayed data — marketable limit (avoids IBKR 10349)"
        return OrderDecision("LMT", marketable_limit(price, side, slippage_pct), reason)
