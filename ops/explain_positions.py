#!/usr/bin/env python3
"""Explain why demo entries left 0 open positions."""
from agent import config, store


def main() -> None:
    c = store.connect(config.DB_PATH)
    print("=== positions (all statuses) ===")
    rows = c.execute(
        "SELECT symbol, status, qty, entry_price, entry_ts, "
        "exit_ts, exit_reason, exit_price FROM positions ORDER BY entry_ts"
    ).fetchall()
    if not rows:
        print("  (none — no row was ever opened in SQLite)")
    for r in rows:
        print(
            f"  {r['symbol']} status={r['status']} qty={r['qty']} "
            f"entry={r['entry_price']} @{r['entry_ts']} "
            f"exit={r['exit_ts']} reason={r['exit_reason']!r} px={r['exit_price']}"
        )
    print(f"open_now={len(store.open_positions(c))}")
    print()
    print("=== decisions ===")
    for r in c.execute(
        "SELECT ts_utc, symbol, action, detail, thesis FROM decisions ORDER BY ts_utc"
    ):
        print(f"  {r['ts_utc']} {r['symbol']} {r['action']}")
        print(f"    detail: {(r['detail'] or '')[:120]}")
        if r["thesis"]:
            print(f"    thesis: {r['thesis'][:120]}")


if __name__ == "__main__":
    main()
