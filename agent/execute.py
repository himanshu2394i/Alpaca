"""Order construction and submission.

Dry run is the default. Every path that can spend money must be asked for
explicitly, because the failure mode of the opposite default is unrecoverable.

Limit orders only. With indicative pricing and options spreads that reach
double digits on illiquid strikes, a market order is a donation.
"""
import asyncio
import logging
import time
from typing import Any

from agent.gates import Contract

log = logging.getLogger(__name__)

AGGRESSION = 0.25
POLL_SECONDS = 60
POLL_INTERVAL = 2
FILLED = frozenset({"filled", "partially_filled"})
DEAD = frozenset({"canceled", "cancelled", "expired", "rejected", "replaced"})


def limit_price(c: Contract, side: str, retry: bool = False) -> float:
    """Limit price for one side of a trade, clamped inside the quote."""
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")

    if retry:
        return round(c.ask if side == "buy" else c.bid, 2)

    half_spread = (c.ask - c.bid) / 2
    raw = c.mid + AGGRESSION * half_spread * (1 if side == "buy" else -1)
    return round(min(max(round(raw, 2), c.bid), c.ask), 2)


def client_order_id(symbol: str, side: str, ts_utc: str, retry: bool = False) -> str:
    minute = ts_utc[:16].replace("-", "").replace(":", "").replace("T", "")
    base = f"aoa-{symbol}-{side}-{minute}"
    return f"{base}-r" if retry else base


def build_order(c: Contract, qty: int, side: str, ts_utc: str,
                retry: bool = False) -> dict[str, Any]:
    if qty <= 0:
        raise ValueError(f"quantity must be positive, got {qty}")

    return {
        "symbol": c.symbol,
        "qty": str(qty),
        "side": side,
        "type": "limit",
        "time_in_force": "day",
        "limit_price": f"{limit_price(c, side, retry):.2f}",
        "client_order_id": client_order_id(c.symbol, side, ts_utc, retry=retry),
    }


def _order_payload(raw: dict) -> dict:
    if not raw:
        return {}
    if isinstance(raw.get("order"), dict):
        return raw["order"]
    return raw


def order_status(raw: dict) -> str:
    return str(_order_payload(raw).get("status", "")).lower()


def filled_qty(raw: dict) -> float:
    qty = _order_payload(raw).get("filled_qty")
    try:
        return float(qty) if qty not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def is_filled(raw: dict) -> bool:
    """True only when status is filled/partial and size actually moved."""
    return order_status(raw) in FILLED and filled_qty(raw) > 0


def order_id(raw: dict) -> str | None:
    oid = _order_payload(raw).get("id")
    return str(oid) if oid else None


def fill_price(raw: dict, fallback: float) -> float:
    px = _order_payload(raw).get("filled_avg_price")
    try:
        return float(px) if px not in (None, "", "0") else fallback
    except (TypeError, ValueError):
        return fallback


async def _poll_fill(sess, client_order_id: str, poll_seconds: float,
                     poll_interval: float) -> dict | None:
    from agent import mcp_bridge

    deadline = time.monotonic() + poll_seconds
    last: dict = {}
    while time.monotonic() < deadline:
        last = await mcp_bridge.call(sess, "get_order_by_client_id",
                                     {"client_order_id": client_order_id})
        if is_filled(last) or order_status(last) in DEAD:
            return last
        await asyncio.sleep(poll_interval)
    return last or None


async def _cancel(sess, raw: dict) -> None:
    from agent import mcp_bridge

    oid = order_id(raw)
    if oid:
        await mcp_bridge.call(sess, "cancel_order_by_id", {"order_id": oid})


async def _attempt(sess, order: dict, contract: Contract, poll_seconds: float,
                   poll_interval: float) -> dict:
    from agent import mcp_bridge

    log.warning("PLACING LIVE ORDER: %s", order)
    placed = await mcp_bridge.call(sess, "place_option_order", order)
    if placed.get("error"):
        return {"dry_run": False, "status": "rejected", "order": order,
                "reason": str(placed.get("error"))}

    polled = await _poll_fill(sess, order["client_order_id"], poll_seconds,
                            poll_interval)
    if polled and is_filled(polled):
        fallback = float(order["limit_price"])
        return {"dry_run": False, "status": "filled", "order": order,
                "fill_price": fill_price(polled, fallback), "result": polled}

    await _cancel(sess, polled or placed)
    return {"dry_run": False, "status": "unfilled", "order": order}


def _attempt_summary(order: dict, outcome: dict) -> dict:
    """One entry of the `attempts` trail: what was tried and how it ended.

    Live: the AAPL retry the night of 2026-08-26 canceled once and retried
    once, and the decision log showed only the original entry intent - none
    of the cancel/retry lifecycle was recorded anywhere the dashboard could
    show it. This is what lets the caller log each attempt, not just the
    final outcome.
    """
    return {"client_order_id": order["client_order_id"],
           "limit_price": order["limit_price"], "status": outcome["status"]}


async def submit(sess, order: dict, dry_run: bool = True,
                 contract: Contract | None = None, ts_utc: str | None = None,
                 poll_seconds: float = POLL_SECONDS,
                 poll_interval: float = POLL_INTERVAL) -> dict:
    """Place an order, poll for a fill, cancel and retry once if needed.

    The returned dict always carries `attempts`: one entry per order actually
    placed, in order, so a caller can log the full lifecycle (canceled,
    retried, filled, rejected) rather than only the terminal status.
    """
    if dry_run:
        log.info("DRY RUN would place: %s", order)
        return {"dry_run": True, "status": "simulated", "order": order,
                "attempts": [{"client_order_id": order["client_order_id"],
                             "limit_price": order["limit_price"],
                             "status": "simulated"}]}

    if contract is None or ts_utc is None:
        raise ValueError("contract and ts_utc are required for live submission")

    first = await _attempt(sess, order, contract, poll_seconds, poll_interval)
    attempts = [_attempt_summary(order, first)]
    if first["status"] in ("filled", "rejected"):
        return {**first, "attempts": attempts}

    retry_order = build_order(contract, int(order["qty"]), order["side"],
                              ts_utc, retry=True)
    second = await _attempt(sess, retry_order, contract, poll_seconds,
                            poll_interval)
    attempts.append(_attempt_summary(retry_order, second))
    if second["status"] == "filled":
        return {**second, "attempts": attempts}

    log.warning("order abandoned: %s", order["symbol"])
    return {"dry_run": False, "status": "abandoned", "order": order,
           "attempts": attempts}
