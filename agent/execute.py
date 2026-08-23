"""Order construction and submission.

Dry run is the default. Every path that can spend money must be asked for
explicitly, because the failure mode of the opposite default is unrecoverable.

Limit orders only. With indicative pricing and options spreads that reach
double digits on illiquid strikes, a market order is a donation.
"""
import logging
from typing import Any

from agent.gates import Contract

log = logging.getLogger(__name__)

# Fraction of the half-spread to give up in order to get filled. 0.25 pays a
# quarter of the way toward the far side: better fill odds than resting at mid,
# without crossing.
AGGRESSION = 0.25


def limit_price(c: Contract, side: str, retry: bool = False) -> float:
    """Limit price for one side of a trade, clamped inside the quote.

    Entry rests above mid, exit below it, and neither crosses. `retry=True`
    takes the far side outright - used once, after a resting order times out,
    when getting done matters more than the last cent.
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")

    if retry:
        return round(c.ask if side == "buy" else c.bid, 2)

    half_spread = (c.ask - c.bid) / 2
    raw = c.mid + AGGRESSION * half_spread * (1 if side == "buy" else -1)

    # Round first, then clamp: on a one-cent market rounding alone can push the
    # price through the quote.
    return round(min(max(round(raw, 2), c.bid), c.ask), 2)


def client_order_id(symbol: str, side: str, ts_utc: str) -> str:
    """Deterministic order id, unique per (contract, side, minute).

    Idempotency key. If the process restarts mid-submit, or a retry fires after
    the broker already accepted the order, replaying the same id is rejected as
    a duplicate instead of opening a second position.
    """
    minute = ts_utc[:16].replace("-", "").replace(":", "").replace("T", "")
    return f"aoa-{symbol}-{side}-{minute}"


def build_order(c: Contract, qty: int, side: str, ts_utc: str,
                retry: bool = False) -> dict[str, Any]:
    """Build the place_option_order arguments for one single-leg trade.

    qty and limit_price are strings because that is what the MCP tool schema
    declares. Passing numbers is how you get a validation failure at the exact
    moment you least want one.
    """
    if qty <= 0:
        raise ValueError(f"quantity must be positive, got {qty}")

    return {
        "symbol": c.symbol,
        "qty": str(qty),
        "side": side,
        "type": "limit",
        "time_in_force": "day",
        "limit_price": f"{limit_price(c, side, retry):.2f}",
        "client_order_id": client_order_id(c.symbol, side, ts_utc),
    }


async def submit(sess, order: dict, dry_run: bool = True) -> dict:
    """Place an order, or simulate it.

    Dry run defaults to True and short-circuits before any network call, so a
    caller that forgets the flag logs an intention rather than buying options.
    """
    if dry_run:
        log.info("DRY RUN would place: %s", order)
        return {"dry_run": True, "status": "simulated", "order": order}

    from agent import mcp_bridge

    log.warning("PLACING LIVE ORDER: %s", order)
    result = await mcp_bridge.call(sess, "place_option_order", order)
    return {"dry_run": False, "status": "submitted", "order": order, "result": result}
