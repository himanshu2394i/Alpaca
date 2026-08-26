#!/usr/bin/env python3
"""Live RTH health snapshot for the trading agent."""
from datetime import datetime, timezone

from agent import config, gates, store


def main() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = store.connect(config.DB_PATH)
    newest = store.newest_bar_ts(conn)
    spy = store.last_bar_ts(conn, "SPY")
    stale = gates.data_stale_reason(newest, now)
    positions = store.open_positions(conn)
    decisions = store.recent_decisions(conn)[:10]
    equity_rows = conn.execute(
        "SELECT ts_utc, value FROM equity ORDER BY ts_utc DESC LIMIT 5"
    ).fetchall()
    decision_count = conn.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()["n"]

    age = None
    if newest:
        age = (
            datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ")
            - datetime.strptime(newest, "%Y-%m-%dT%H:%M:%SZ")
        ).total_seconds()

    status = "OK"
    if stale:
        status = "STALE_HALT"
    elif age is not None and age > 180:
        status = "BARS_LAGGING"

    print(f"STATUS={status}")
    print(f"now_utc={now}")
    print(f"newest_bar={newest} age_sec={age}")
    print(f"SPY_last={spy}")
    print(f"stale_reason={stale!r}")
    print(f"open_positions={len(positions)}")
    for p in positions:
        print(
            f"  pos {p['symbol']} qty={p['qty']} entry={p['entry_price']} "
            f"u={p['entry_underlying']} stop={p['stop_underlying']} "
            f"tgt={p['target_underlying']}"
        )
    print(f"decision_count={decision_count}")
    print("recent_equity:")
    for row in equity_rows:
        print(f"  {row['ts_utc']} {row['value']}")
    if not equity_rows:
        print("  (none)")
    print("recent_decisions:")
    for d in decisions:
        detail = (d["detail"] or "")[:100].replace("\n", " ")
        print(f"  {d['ts_utc']} {d['symbol']} {d['action']} {detail}")
    if not decisions:
        print("  (none)")


if __name__ == "__main__":
    main()
