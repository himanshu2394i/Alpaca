#!/usr/bin/env python3
"""Prove the store is receiving live IEX bars (not stuck warm-start history)."""
import time
from collections import defaultdict
from datetime import datetime, timezone

from agent import config, store


def snapshot(conn):
    now = datetime.now(timezone.utc)
    out = {}
    for sym in config.UNIVERSE:
        ts = store.last_bar_ts(conn, sym)
        bars = store.recent_bars(conn, sym, limit=1)
        px = float(bars[0]["c"]) if bars else None
        age = None
        if ts:
            age = (
                now
                - datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
            ).total_seconds()
        out[sym] = {"ts": ts, "c": px, "age_sec": age}
    newest = store.newest_bar_ts(conn)
    return now, newest, out


def main() -> None:
    conn = store.connect(config.DB_PATH)
    t0, newest0, snap0 = snapshot(conn)
    print(f"sample_at={t0.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"newest_bar={newest0}")
    print()
    print("symbol  last_ts              age_s   last_close")
    fresh = 0
    for sym, d in snap0.items():
        age = d["age_sec"]
        flag = ""
        if age is not None and age <= 180:
            fresh += 1
            flag = "LIVE"
        elif age is not None and age <= 600:
            flag = "warm"
        else:
            flag = "STALE?"
        print(f"{sym:6}  {d['ts']}  {age:6.0f}  {d['c']:10.2f}  {flag}")
    print()
    print(f"symbols_with_bar_age_<=180s: {fresh}/{len(config.UNIVERSE)}")

    print()
    print("waiting 75s for next 1-min bar cycle...")
    time.sleep(75)

    conn2 = store.connect(config.DB_PATH)
    t1, newest1, snap1 = snapshot(conn2)
    print(f"sample_at={t1.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"newest_bar={newest1}")

    advanced = []
    unchanged = []
    for sym in config.UNIVERSE:
        a, b = snap0[sym]["ts"], snap1[sym]["ts"]
        if b and a and b > a:
            advanced.append((sym, a, b, snap1[sym]["c"]))
        else:
            unchanged.append(sym)

    print()
    print(f"symbols_that_advanced_in_75s: {len(advanced)}/{len(config.UNIVERSE)}")
    for sym, a, b, c in advanced[:12]:
        print(f"  {sym:6} {a} -> {b}  c={c:.2f}")
    if len(advanced) > 12:
        print(f"  ... +{len(advanced) - 12} more")
    if unchanged:
        print(f"unchanged: {', '.join(unchanged)}")

    # Count bars stamped in the last 5 wall-clock minutes
    cutoff = (datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # last 5 minutes of clock
    from datetime import timedelta

    since = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    n = conn2.execute(
        "SELECT COUNT(*) AS n FROM bars WHERE ts_utc >= ?", (since,)
    ).fetchone()["n"]
    by_min = conn2.execute(
        "SELECT substr(ts_utc,1,16) AS m, COUNT(*) AS n "
        "FROM bars WHERE ts_utc >= ? GROUP BY m ORDER BY m",
        (since,),
    ).fetchall()
    print()
    print(f"bars_written_last_5_min_wallclock: {n}")
    print("bars_per_minute:")
    for row in by_min:
        print(f"  {row['m']}  {row['n']}")

    ok = len(advanced) >= 10 and fresh >= 10 and n >= 40
    print()
    print(f"VERDICT={'GENUINE_LIVE_DATA' if ok else 'PROBLEM'}")


if __name__ == "__main__":
    main()
