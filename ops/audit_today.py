#!/usr/bin/env python3
"""Audit today's entries, exits, decisions, and equity swings."""
from agent import config, store

c = store.connect(config.DB_PATH)
today = "2026-08-27"

print("=== DECISIONS TODAY ===")
for r in c.execute(
    "SELECT ts_utc, symbol, action, detail FROM decisions "
    "WHERE ts_utc >= ? ORDER BY ts_utc",
    (today,),
):
    print(f"{r['ts_utc']}  {r['action']:12s}  {r['symbol']}  {(r['detail'] or '')[:90]}")

print("\n=== POSITIONS (all) ===")
for r in c.execute(
    "SELECT symbol, status, qty, entry_price, exit_price, entry_ts, exit_ts, exit_reason "
    "FROM positions ORDER BY entry_ts, exit_ts"
):
    pnl = ""
    if r["exit_price"] is not None and r["entry_price"] is not None:
        pnl = f"  realized={((float(r['exit_price']) - float(r['entry_price'])) * r['qty'] * 100):+.0f}"
    print(
        f"{r['status']:6s} {r['symbol']} qty={r['qty']} "
        f"in={r['entry_price']}@{r['entry_ts']} "
        f"out={r['exit_price']}@{r['exit_ts']} {r['exit_reason'] or ''}{pnl}"
    )

print(f"\nopen_now={len(store.open_positions(c))}")

print("\n=== EQUITY TODAY (deltas) ===")
rows = c.execute(
    "SELECT ts_utc, value FROM equity WHERE ts_utc >= ? ORDER BY ts_utc",
    (today,),
).fetchall()
prev = None
for r in rows:
    v = float(r["value"])
    d = f"  ({v - prev:+.0f})" if prev is not None else ""
    print(f"{r['ts_utc']}  {v:,.2f}{d}")
    prev = v
if rows:
    vals = [float(r["value"]) for r in rows]
    print(f"\npoints={len(rows)}  min={min(vals):,.2f}  max={max(vals):,.2f}  swing={max(vals)-min(vals):,.0f}")

print("\n=== ACTION COUNTS TODAY ===")
for r in c.execute(
    "SELECT action, COUNT(*) AS n FROM decisions WHERE ts_utc >= ? GROUP BY action ORDER BY n DESC",
    (today,),
):
    print(f"  {r['action']}: {r['n']}")
