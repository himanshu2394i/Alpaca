"""Replay the screener over stored bars to measure how often it fires.

Used to tune TRIGGER thresholds against real data instead of taste.

    python -m tools.replay              # current threshold
    python -m tools.replay 0.5 0.6 0.75 # compare several
"""
import sys

from agent import config, indicators, screener, store

CHECKS = [60, 120, 180, 240, 300, 360]  # minutes after the open


def replay(cache, sessions, mult):
    trigger = {**screener.TRIGGER, "move_adr_mult": mult}
    found = []
    for sess in sessions:
        for sym, bars in cache.items():
            rth = [b for b in indicators.rth_bars(bars) if b["ts_utc"][:10] == sess]
            if len(rth) < 40:
                continue
            for k in CHECKS:
                if k >= len(rth):
                    break
                sliced = [b for b in bars if b["ts_utc"] <= rth[k]["ts_utc"]]
                cand = screener.evaluate(sliced, sess, trigger)
                if cand:
                    found.append((sess, cand, k))
                    break  # one nomination per symbol per session
    return found


def main(mults):
    conn = store.connect(config.DB_PATH)
    sessions = sorted(
        {r[0] for r in conn.execute("SELECT DISTINCT substr(ts_utc,1,10) FROM bars")}
    )[3:]  # leave the earliest sessions as ADR history
    cache = {
        s: [dict(b) for b in store.recent_bars(conn, s, limit=8000)]
        for s in config.UNIVERSE
    }

    print(f"{'mult':>6} {'cands':>6} {'per day':>8} {'idle sessions':>14}  detail")
    for mult in mults:
        found = replay(cache, sessions, mult)
        active = {sess for sess, _, _ in found}
        idle = [s for s in sessions if s not in active]
        detail = ", ".join(f"{c.symbol}/{c.direction}" for _, c, _ in found[:8])
        print(
            f"{mult:>6.2f} {len(found):>6} {len(found)/len(sessions):>8.2f} "
            f"{len(idle):>7}/{len(sessions):<6}  {detail}"
        )


if __name__ == "__main__":
    main([float(a) for a in sys.argv[1:]] or [screener.TRIGGER["move_adr_mult"]])
