#!/usr/bin/env python3
"""Summarize today's equity path and whether P&L is real."""
from agent import config, store


def main() -> None:
    c = store.connect(config.DB_PATH)
    rows = c.execute(
        "SELECT ts_utc, value FROM equity "
        "WHERE ts_utc LIKE '2026-08-26%' ORDER BY ts_utc"
    ).fetchall()
    print("=== equity 2026-08-26 ===")
    if not rows:
        print("no equity rows")
        return
    vals = [float(r["value"]) for r in rows]
    start, end = vals[0], vals[-1]
    print(f"points={len(rows)}")
    print(f"first={rows[0]['ts_utc']} {start}")
    print(f"last ={rows[-1]['ts_utc']} {end}")
    print(f"min={min(vals)} max={max(vals)}")
    print(f"vs_100k={end - 100000:+.2f}")
    print(f"session_change={end - start:+.2f}")
    print()
    print("non-flat snapshots:")
    for r in rows:
        v = float(r["value"])
        if abs(v - 100000) > 0.01:
            print(f"  {r['ts_utc']} {v}")
    print()
    print("=== positions ===")
    pos = c.execute(
        "SELECT symbol, status, qty, entry_price, exit_price, entry_ts, exit_ts, exit_reason "
        "FROM positions ORDER BY entry_ts"
    ).fetchall()
    if not pos:
        print("  none")
    for r in pos:
        pnl = None
        if r["exit_price"] is not None and r["entry_price"] is not None:
            pnl = (r["exit_price"] - r["entry_price"]) * r["qty"] * 100
        print(
            f"  {r['symbol']} {r['status']} qty={r['qty']} "
            f"entry={r['entry_price']} exit={r['exit_price']} "
            f"local_pnl={pnl} reason={r['exit_reason']!r}"
        )
    print()
    print("=== decisions ===")
    for r in c.execute(
        "SELECT ts_utc, symbol, action, detail FROM decisions ORDER BY ts_utc"
    ):
        print(f"  {r['ts_utc']} {r['symbol']} {r['action']} {(r['detail'] or '')[:90]}")


if __name__ == "__main__":
    main()
