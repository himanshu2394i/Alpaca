"""Exit triggers.

Exits must be strictly harder to suppress than entries: failing to open a
position costs an opportunity, failing to close one costs money.
"""
import pytest

from agent import exits

TODAY = "2026-08-26"


def pos(right="call", entry_price=2.00, entry_underlying=765.0,
        stop=760.0, target=775.0, expiry="2026-09-11", qty=7):
    return {
        "symbol": "SPY260911C00765000", "underlying": "SPY", "right": right,
        "qty": qty, "entry_price": entry_price, "entry_ts": "2026-08-24T14:05:00Z",
        "entry_underlying": entry_underlying, "stop_underlying": stop,
        "target_underlying": target, "expiry": expiry, "status": "open",
    }


# --- no exit ----------------------------------------------------------------

def test_no_exit_while_the_thesis_is_intact():
    assert exits.check(pos(), underlying=767.0, premium=2.10, today=TODAY) is None


# --- premium triggers -------------------------------------------------------

def test_premium_stop_fires_at_minus_forty_percent():
    sig = exits.check(pos(entry_price=2.00), underlying=764.0, premium=1.19, today=TODAY)
    assert sig is not None and "premium" in sig.reason and "-40" in sig.reason


def test_premium_stop_does_not_fire_just_above_the_threshold():
    assert exits.check(pos(entry_price=2.00), underlying=764.0, premium=1.21,
                       today=TODAY) is None


def test_premium_target_fires_at_plus_eighty_percent():
    sig = exits.check(pos(entry_price=2.00), underlying=770.0, premium=3.61, today=TODAY)
    assert sig is not None and "premium" in sig.reason


# --- underlying triggers ----------------------------------------------------

def test_call_stops_out_when_the_underlying_breaks_below_stop():
    sig = exits.check(pos(right="call", stop=760.0), underlying=759.5,
                      premium=1.90, today=TODAY)
    assert sig is not None and "stop" in sig.reason


def test_call_takes_profit_when_the_underlying_reaches_target():
    sig = exits.check(pos(right="call", target=775.0), underlying=775.5,
                      premium=2.50, today=TODAY)
    assert sig is not None and "target" in sig.reason


def test_put_stops_out_when_the_underlying_rises_through_stop():
    # A put's adverse direction is up: stop sits above entry, target below.
    sig = exits.check(pos(right="put", stop=770.0, target=755.0), underlying=770.5,
                      premium=1.90, today=TODAY)
    assert sig is not None and "stop" in sig.reason


def test_put_takes_profit_when_the_underlying_falls_to_target():
    sig = exits.check(pos(right="put", stop=770.0, target=755.0), underlying=754.0,
                      premium=2.50, today=TODAY)
    assert sig is not None and "target" in sig.reason


def test_put_is_not_stopped_out_by_a_falling_underlying():
    assert exits.check(pos(right="put", stop=770.0, target=755.0), underlying=760.0,
                       premium=2.10, today=TODAY) is None


# --- forced exits -----------------------------------------------------------

def test_expiry_forces_an_exit_inside_two_days():
    sig = exits.check(pos(expiry="2026-08-27"), underlying=767.0, premium=2.10,
                      today=TODAY)
    assert sig is not None and sig.forced and "dte" in sig.reason


def test_competition_end_forces_an_exit():
    sig = exits.check(pos(expiry="2026-10-16"), underlying=767.0, premium=2.10,
                      today="2026-09-04")
    assert sig is not None and sig.forced and "competition" in sig.reason


def test_forced_exit_outranks_a_healthy_position():
    # Position is in profit and nowhere near a level, but must still be closed.
    sig = exits.check(pos(expiry="2026-08-27"), underlying=767.0, premium=9.00,
                      today=TODAY)
    assert sig is not None and sig.forced


def test_forced_exit_is_reported_ahead_of_a_discretionary_one():
    sig = exits.check(pos(expiry="2026-08-27", entry_price=2.00), underlying=759.0,
                      premium=1.00, today=TODAY)
    assert sig.forced and "dte" in sig.reason


# --- scan -------------------------------------------------------------------

def test_scan_returns_one_signal_per_triggered_position(conn):
    from agent import store
    base = dict(underlying="SPY", right="call", qty=7, entry_price=2.00,
                entry_underlying=765.0, stop_underlying=760.0,
                target_underlying=775.0, expiry="2026-09-11")
    store.open_position(conn, symbol="SPY260911C00765000",
                        entry_ts="2026-08-24T14:05:00Z", **base)
    store.open_position(conn, symbol="SPY260911C00770000",
                        entry_ts="2026-08-24T14:06:00Z", **base)

    got = exits.scan(conn,
                     underlyings={"SPY": 759.0},                       # below stop
                     premiums={"SPY260911C00765000": 1.90,
                               "SPY260911C00770000": 1.90},
                     today=TODAY)
    assert len(got) == 2
    assert all("stop" in s.reason for s in got)


def test_scan_skips_positions_with_no_quote(conn):
    from agent import store
    store.open_position(conn, symbol="SPY260911C00765000", underlying="SPY",
                        right="call", qty=7, entry_price=2.00,
                        entry_ts="2026-08-24T14:05:00Z", entry_underlying=765.0,
                        stop_underlying=760.0, target_underlying=775.0,
                        expiry="2026-09-11")
    # Missing premium must not crash and must not silently look healthy.
    got = exits.scan(conn, underlyings={"SPY": 759.0}, premiums={}, today=TODAY)
    assert len(got) == 1 and "stop" in got[0].reason


def test_scan_returns_nothing_when_no_positions_are_open(conn):
    assert exits.scan(conn, underlyings={}, premiums={}, today=TODAY) == []


# --- level construction -----------------------------------------------------

def test_call_levels_put_stop_below_and_target_above():
    stop, target = exits.levels(entry_underlying=765.0, adr=5.0, right="call")
    assert stop == pytest.approx(760.0)
    assert target == pytest.approx(775.0)


def test_put_levels_are_mirrored():
    stop, target = exits.levels(entry_underlying=765.0, adr=5.0, right="put")
    assert stop == pytest.approx(770.0)
    assert target == pytest.approx(755.0)


def test_levels_use_a_two_to_one_reward_to_risk():
    stop, target = exits.levels(765.0, 5.0, "call")
    assert abs(target - 765.0) == pytest.approx(2 * abs(765.0 - stop))


def test_levels_reject_a_non_positive_range():
    # ADR of zero would put stop and target on top of the entry price and exit
    # the position on the very next tick.
    with pytest.raises(ValueError):
        exits.levels(765.0, 0.0, "call")


def test_levels_feed_straight_into_check():
    stop, target = exits.levels(765.0, 5.0, "call")
    p = pos(right="call", entry_underlying=765.0, stop=stop, target=target)
    assert exits.check(p, underlying=766.0, premium=2.10, today=TODAY) is None
    assert exits.check(p, underlying=759.9, premium=2.10, today=TODAY) is not None
