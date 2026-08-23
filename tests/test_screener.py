"""Entry-trigger and throttle behaviour.

Bar fixtures are built so the indicator inputs are exact: prior sessions are
flat with a known high-low range (so ADR is exact), and today's volume is a
clean multiple of prior volume (so RVOL is exact).
"""
import pytest

from agent import screener


def _ts(date, i):
    """i-th regular-hours minute of `date`. 09:30 ET == 13:30Z during EDT."""
    m = 13 * 60 + 30 + i
    return f"{date}T{m // 60:02d}:{m % 60:02d}:00Z"


def flat_session(date, base=100.0, rng=10.0, n=40, vol=1000, symbol="SPY"):
    """A session whose RTH range is exactly `rng` and whose closes never move."""
    bars = []
    for i in range(n):
        hi = base + rng / 2 if i == 0 else base
        lo = base - rng / 2 if i == 0 else base
        bars.append({"symbol": symbol, "ts_utc": _ts(date, i), "o": base,
                     "h": hi, "l": lo, "c": base, "v": vol})
    return bars


def moving_session(date, closes, vol=1000, symbol="SPY"):
    """A session that walks through `closes`, opening at closes[0]."""
    return [
        {"symbol": symbol, "ts_utc": _ts(date, i), "o": c,
         "h": c + 0.01, "l": c - 0.01, "c": c, "v": vol}
        for i, c in enumerate(closes)
    ]


PRIOR = ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]
TODAY = "2026-08-24"


def history(vol=1000, rng=10.0, base=100.0):
    out = []
    for d in PRIOR:
        out.extend(flat_session(d, base=base, rng=rng, vol=vol))
    return out


def ramp(start, end, n=40):
    step = (end - start) / (n - 1)
    return [start + i * step for i in range(n)]


# --- evaluate ---------------------------------------------------------------

def test_fires_long_on_a_strong_up_move_with_volume():
    # ADR = 10. Move 100 -> 108 is 0.8 ADR, over the 0.75 threshold.
    # Today's volume is 2x prior, so RVOL = 2.0, over the 1.5 minimum.
    bars = history() + moving_session(TODAY, ramp(100.0, 108.0), vol=2000)
    c = screener.evaluate(bars, TODAY)

    assert c is not None
    assert c.symbol == "SPY"
    assert c.direction == "call"
    assert c.move_adr == pytest.approx(0.8, abs=0.01)
    assert c.rvol == pytest.approx(2.0, abs=0.01)
    assert c.ts_utc == _ts(TODAY, 39)


def test_fires_short_on_a_strong_down_move():
    bars = history() + moving_session(TODAY, ramp(100.0, 92.0), vol=2000)
    c = screener.evaluate(bars, TODAY)

    assert c is not None
    assert c.direction == "put"
    assert c.move_adr == pytest.approx(-0.8, abs=0.01)


def test_no_candidate_when_move_is_below_threshold():
    # ADR = 10, so 100 -> 103 is 0.3 ADR: clearly under any tuned threshold.
    bars = history() + moving_session(TODAY, ramp(100.0, 103.0), vol=2000)
    assert screener.evaluate(bars, TODAY) is None


def test_tuned_defaults_are_what_the_replay_measured():
    # Pins the values tools/replay.py justified, so changing them is deliberate
    # rather than accidental. Re-run the replay if this fails.
    assert screener.TRIGGER["move_adr_mult"] == 0.50
    assert screener.TRIGGER["min_rvol"] == 1.5
    assert screener.LIMITS["max_entries_per_day"] == 3
    assert screener.LIMITS["max_concurrent"] == 5


def test_no_candidate_when_volume_is_ordinary():
    # Move qualifies but RVOL is 1.0.
    bars = history() + moving_session(TODAY, ramp(100.0, 108.0), vol=1000)
    assert screener.evaluate(bars, TODAY) is None


def test_no_candidate_when_price_round_tripped_through_the_ema():
    # Spikes to 115 then falls back to 108: still +0.8 ADR from the open, but
    # price is now below its own EMA20, so the move is reverting, not trending.
    closes = ramp(100.0, 115.0, 20) + ramp(115.0, 108.0, 20)
    bars = history() + moving_session(TODAY, closes, vol=2000)
    c = screener.evaluate(bars, TODAY)
    assert c is None


def test_no_candidate_without_prior_history_to_size_the_move():
    # No prior sessions -> ADR is 0.0 -> must fail closed, not divide by zero.
    bars = moving_session(TODAY, ramp(100.0, 108.0), vol=2000)
    assert screener.evaluate(bars, TODAY) is None


def test_no_candidate_before_enough_bars_have_accumulated():
    bars = history() + moving_session(TODAY, ramp(100.0, 108.0, 10), vol=2000)
    assert screener.evaluate(bars, TODAY) is None


def test_no_candidate_when_session_has_no_regular_hours_bars():
    premarket = [{"symbol": "SPY", "ts_utc": f"{TODAY}T11:00:00Z", "o": 100.0,
                  "h": 108.0, "l": 100.0, "c": 108.0, "v": 5000}]
    assert screener.evaluate(history() + premarket, TODAY) is None


# --- throttles --------------------------------------------------------------

def test_throttle_allows_a_clean_symbol():
    state = screener.ThrottleState()
    assert screener.throttle_reason(state, "SPY", _ts(TODAY, 40)) is None


def test_throttle_blocks_inside_the_cooldown_window():
    state = screener.ThrottleState(last_entry={"SPY": _ts(TODAY, 0)})
    reason = screener.throttle_reason(state, "SPY", _ts(TODAY, 30))
    assert reason is not None and "cooldown" in reason


def test_throttle_releases_after_the_cooldown_window():
    state = screener.ThrottleState(last_entry={"SPY": _ts(TODAY, 0)})
    assert screener.throttle_reason(state, "SPY", _ts(TODAY, 61)) is None


def test_cooldown_is_per_symbol():
    state = screener.ThrottleState(last_entry={"SPY": _ts(TODAY, 0)})
    assert screener.throttle_reason(state, "NVDA", _ts(TODAY, 30)) is None


def test_throttle_blocks_at_the_daily_entry_cap():
    state = screener.ThrottleState(entries_today=3)
    reason = screener.throttle_reason(state, "SPY", _ts(TODAY, 40))
    assert reason is not None and "entries today" in reason


def test_throttle_blocks_at_the_concurrent_position_cap():
    state = screener.ThrottleState(open_positions=5)
    reason = screener.throttle_reason(state, "SPY", _ts(TODAY, 40))
    assert reason is not None and "open positions" in reason


def test_throttle_reports_the_first_binding_limit_only():
    state = screener.ThrottleState(entries_today=3, open_positions=5)
    reason = screener.throttle_reason(state, "SPY", _ts(TODAY, 40))
    assert reason.count(";") == 0


# --- scan -------------------------------------------------------------------

def test_scan_returns_candidates_for_qualifying_symbols(conn):
    from agent import store

    for sym, end in [("SPY", 108.0), ("QQQ", 100.0)]:
        rows = history() + moving_session(TODAY, ramp(100.0, end), vol=2000)
        store.upsert_bars(conn, [(sym, r["ts_utc"], r["o"], r["h"], r["l"],
                                  r["c"], r["v"]) for r in rows])

    got = screener.scan(conn, ["SPY", "QQQ"], TODAY, screener.ThrottleState())
    assert [c.symbol for c in got] == ["SPY"]


def test_scan_drops_throttled_symbols(conn):
    from agent import store

    rows = history() + moving_session(TODAY, ramp(100.0, 108.0), vol=2000)
    store.upsert_bars(conn, [("SPY", r["ts_utc"], r["o"], r["h"], r["l"],
                              r["c"], r["v"]) for r in rows])

    state = screener.ThrottleState(last_entry={"SPY": _ts(TODAY, 39)})
    assert screener.scan(conn, ["SPY"], TODAY, state) == []
