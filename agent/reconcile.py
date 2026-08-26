"""Boot-time reconciliation between local SQLite and Alpaca."""
import logging
import re

from agent import exits, gates, indicators, store

log = logging.getLogger(__name__)
_OCC = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")


def _option_positions(payload: dict) -> dict[str, dict]:
    """Extract open option positions keyed by OCC symbol."""
    rows = payload.get("positions") or payload.get("snapshots") or payload
    if isinstance(rows, dict):
        items = rows.values()
    elif isinstance(rows, list):
        items = rows
    else:
        items = []

    out = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "")
        if _OCC.match(sym):
            out[sym] = row
    return out


def _import_position(conn, symbol: str, remote: dict, now_utc: str) -> None:
    underlying, expiry, right, _strike = gates.parse_occ(symbol)
    qty = int(float(remote.get("qty") or remote.get("quantity") or 0))
    if qty <= 0:
        return

    entry_price = float(remote.get("avg_entry_price") or remote.get("current_price") or 0)
    bars = [dict(b) for b in store.recent_bars(conn, underlying, limit=8000)]
    today = now_utc[:10]
    entry_underlying = float(bars[-1]["c"]) if bars else 0.0
    adr = indicators.avg_daily_range(bars, before_date=today) or max(entry_underlying * 0.02, 1.0)
    stop, target = exits.levels(entry_underlying, adr, right)

    store.open_position(
        conn, symbol=symbol, underlying=underlying, right=right, qty=qty,
        entry_price=entry_price, entry_ts=now_utc, entry_underlying=entry_underlying,
        stop_underlying=stop, target_underlying=target, expiry=expiry,
        thesis="imported from broker on boot",
    )
    store.record_decision(conn, now_utc, symbol, "reconcile",
                          f"imported {qty}x from broker")


async def reconcile(conn, sess, now_utc: str) -> list[str]:
    """Align local open positions with Alpaca before trading resumes."""
    from agent import mcp_bridge

    notes: list[str] = []
    payload = await mcp_bridge.call(sess, "get_all_positions", {})
    remote = _option_positions(payload)
    local = {p["symbol"]: dict(p) for p in store.open_positions(conn)}

    for sym, pos in local.items():
        if sym not in remote:
            store.close_position(
                conn, sym, exit_price=float(pos["entry_price"]),
                exit_ts=now_utc, exit_reason="reconcile: not at broker",
            )
            store.record_decision(conn, now_utc, sym, "reconcile",
                                  "closed ghost local position")
            notes.append(f"closed ghost local {sym}")

    for sym, row in remote.items():
        if sym in local:
            continue
        try:
            _import_position(conn, sym, row, now_utc)
            notes.append(f"imported broker position {sym}")
        except ValueError as exc:
            log.warning("could not import %s: %s", sym, exc)
            notes.append(f"failed import {sym}: {exc}")

    return notes
