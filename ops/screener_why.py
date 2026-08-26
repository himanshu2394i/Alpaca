#!/usr/bin/env python3
"""Explain why the screener is (or isn't) nominating candidates right now."""
from collections import Counter
from datetime import datetime, timezone

from agent import config, indicators, screener, store

TRIGGER = screener.TRIGGER


def fail_reason(bars, session_date: str) -> str:
    adr = indicators.avg_daily_range(
        bars, before_date=session_date, lookback_days=TRIGGER["adr_lookback_days"]
    )
    if adr <= 0:
        return "no_adr_history"

    open_px = indicators.session_open(bars, session_date)
    if open_px is None:
        return "no_session_open"

    today = [b for b in indicators.rth_bars(bars) if b["ts_utc"][:10] == session_date]
    if len(today) < TRIGGER["min_session_bars"]:
        return f"too_few_bars({len(today)}<{TRIGGER['min_session_bars']})"

    last = today[-1]
    price = float(last["c"])
    move_adr = (price - open_px) / adr
    if abs(move_adr) < TRIGGER["move_adr_mult"]:
        return f"move_too_small({move_adr:+.2f}<±{TRIGGER['move_adr_mult']})"

    rvol = indicators.rvol(
        bars, session_date=session_date, lookback_days=TRIGGER["rvol_lookback_days"]
    )
    if rvol < TRIGGER["min_rvol"]:
        return f"rvol_low({rvol:.2f}<{TRIGGER['min_rvol']})"

    if len(bars) < TRIGGER["ema_period"]:
        return "too_few_for_ema"

    ema = indicators.ema(bars, TRIGGER["ema_period"])
    going_up = move_adr > 0
    if going_up and price <= ema:
        return f"above_move_but_below_ema(px={price:.2f},ema={ema:.2f})"
    if not going_up and price >= ema:
        return f"below_move_but_above_ema(px={price:.2f},ema={ema:.2f})"

    direction = "call" if going_up else "put"
    if TRIGGER.get("mtf_enabled", True):
        ok, ctx = indicators.mtf_confirm(bars, price, direction)
        if ok is False:
            return f"mtf_reject({ctx.get('note', 'fail')})"
        if ok is None:
            mtf = "mtf_warmup_pass"
        else:
            mtf = f"mtf_ok({ctx.get('note', '')})"
    else:
        mtf = "mtf_off"

    return (
        f"PASS direction={direction} move={move_adr:+.2f} rvol={rvol:.2f} "
        f"px={price:.2f} open={open_px:.2f} adr={adr:.2f} {mtf}"
    )


def main() -> None:
    now = datetime.now(timezone.utc)
    session_date = now.strftime("%Y-%m-%d")
    conn = store.connect(config.DB_PATH)
    print(f"now_utc={now.strftime('%Y-%m-%dT%H:%M:%SZ')} session_date={session_date}")
    print(
        f"thresholds: move>={TRIGGER['move_adr_mult']} ADR, "
        f"rvol>={TRIGGER['min_rvol']}, min_bars={TRIGGER['min_session_bars']}, "
        f"mtf={TRIGGER['mtf_enabled']}"
    )
    print()

    reasons = []
    near = []
    for symbol in config.UNIVERSE:
        bars = [dict(b) for b in store.recent_bars(conn, symbol, limit=8000)]
        if not bars:
            reason = "no_bars"
        else:
            reason = fail_reason(bars, session_date)
        reasons.append(reason.split("(")[0].split(" ")[0])
        # Always print a compact line
        print(f"{symbol:6} {reason}")

        # Track near-misses for move
        if bars and reason.startswith("move_too_small"):
            adr = indicators.avg_daily_range(
                bars, before_date=session_date, lookback_days=TRIGGER["adr_lookback_days"]
            )
            open_px = indicators.session_open(bars, session_date)
            today = [b for b in indicators.rth_bars(bars) if b["ts_utc"][:10] == session_date]
            if open_px and adr > 0 and today:
                move = (float(today[-1]["c"]) - open_px) / adr
                rvol = indicators.rvol(bars, session_date=session_date)
                near.append((abs(move), symbol, move, rvol, float(today[-1]["c"]), open_px))

    print()
    print("reason_counts:")
    for k, v in Counter(reasons).most_common():
        print(f"  {v:2d}  {k}")

    if near:
        print()
        print("closest_moves (need ±0.50 ADR):")
        for _, sym, move, rvol, px, opn in sorted(near, reverse=True)[:8]:
            print(f"  {sym:6} move={move:+.3f} ADR  rvol={rvol:.2f}  px={px:.2f} open={opn:.2f}")

    state = screener.ThrottleState()
    cands = screener.scan(conn, config.UNIVERSE, session_date, state)
    print()
    print(f"scan_candidates={len(cands)}")
    for c in cands:
        print(f"  {c.symbol} {c.direction} move={c.move_adr:+.2f} rvol={c.rvol:.2f} {c.mtf_note}")


if __name__ == "__main__":
    main()
