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
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Ports on which IBKR serves real-time market data; everything else is treated
# as delayed (reqMarketDataType(3)), where bare MARKET orders get cancelled.
# Canonical home for the literal set duplicated in worker.connect / router /
# main port_type checks.
LIVE_PORTS = frozenset({7496, 4001, 4003})

# Ports that PROVE a paper account (TWS 7497 / IBGW raw 4002 / gnzsnz paper 4004).
# Deliberately an explicit allowlist rather than "everything not in LIVE_PORTS":
# code that arms trading must require proof of paper, never infer it from the
# absence of evidence, so an unrecognised port is treated as real money.
PAPER_PORTS = frozenset({7497, 4002, 4004})

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


def cold_boot_arming(port: int) -> tuple[bool, bool]:
    """(is_active, read_only) for an account auto-seeded into an empty DB.

    A first boot has had no human confirm anything, so it may only arm trading
    against a port that PROVES paper. Everything else — a live port, or one we
    do not recognise — is seeded inactive and read-only and waits to be armed
    deliberately. This is not hypothetical: compose defaults IBKR_PORT to 4003,
    the real-money gateway, so seeding active-and-writable meant a cold boot on
    an empty database came up able to place real orders.
    """
    provably_paper = port in PAPER_PORTS
    return provably_paper, not provably_paper


def marketable_limit(price: float, side: str, slippage_pct: float) -> float:
    """Limit price skewed across the spread so it fills like a market order.

    BUY pays up (price * (1 + slip)); SELL gives up (price * (1 - slip)).
    slippage_pct is a percentage value (0.1 == 0.1%). Rounded to 2dp (USD tick).

    NOTE: 2dp is a valid tick only on US SMART (and other 0.01-tick venues). For
    SIX/Euronext/XETRA large-tick names the caller MUST additionally snap the
    result to the contract's real market-rule increment (see
    ``select_tick_increment`` / ``quantize_to_increment`` and
    IBKRWorker._quantize_to_tick) or IBKR rejects the order with error 110.
    """
    slip = slippage_pct / 100.0
    return round(price * (1 + slip) if side == "BUY" else price * (1 - slip), 2)


# Float slack when converting a price to an integer count of ticks: guards
# against binary-representation noise (e.g. 100.1/0.05 == 2001.9999999999998)
# rounding a price already ON a tick to the wrong neighbour.
_TICK_EPS = 1e-9

# Coarse fallback increment for NON-USD venues when the market rule cannot be
# resolved. A coarser-than-actual tick is still a VALID multiple of the real
# per-band tick (IBKR error 110 fires only on a FINER-than-tick price), whereas
# the naive 2dp is FINER than the large-tick EU bands that caused the bug — so
# snapping to this coarse tick fails SAFE (a valid, if slightly less precise,
# price) rather than submitting a possibly-invalid one. US SMART keeps 2dp.
COARSE_NONUS_TICK = 0.05


def select_tick_increment(price: float, increments) -> Optional[float]:
    """Return the tick increment for the price BAND containing ``price``.

    ``increments`` is an iterable of (low_edge, increment) pairs (from an IBKR
    market rule's PriceIncrements). MiFID II ticks are per price-band: the
    applicable band is the one with the greatest low_edge <= price (each band
    extends upward until the next edge). Returns None when no band applies
    (empty list, or every edge is above price).
    """
    tick = None
    for low_edge, increment in sorted(increments):
        if price >= low_edge:
            tick = increment
        else:
            break
    return tick


def quantize_to_increment(price: float, side: str, tick: Optional[float]) -> float:
    """Round ``price`` to a multiple of ``tick`` in the MARKETABLE direction.

    BUY rounds UP (pay up to cross the spread); SELL rounds DOWN (give up to
    cross). Both keep the order marketable AND land on a valid exchange tick, so
    IBKR does not reject it with error 110. A non-positive/None tick returns the
    price unchanged (caller decides the fallback).
    """
    if not tick or tick <= 0:
        return price
    ratio = price / tick
    if side == "BUY":
        n = math.ceil(ratio - _TICK_EPS)
    else:
        n = math.floor(ratio + _TICK_EPS)
    return round(n * tick, 10)


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
