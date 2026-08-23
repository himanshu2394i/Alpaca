"""Session-aware indicator helpers: RTH filtering, session open, daily range."""
import pytest

from agent import indicators
from tests.helpers import make_bars


def rows(bars):
    keys = ("symbol", "ts_utc", "o", "h", "l", "c", "v")
    return [dict(zip(keys, b)) for b in bars]


def bar(ts, o=100.0, h=101.0, l=99.0, c=100.0, v=1000):
    return {"symbol": "SPY", "ts_utc": ts, "o": o, "h": h, "l": l, "c": c, "v": v}


# --- rth_bars ---------------------------------------------------------------

def test_rth_bars_drops_premarket_and_afterhours():
    bars = [
        bar("2026-08-24T12:00:00Z"),  # 08:00 ET, pre-market
        bar("2026-08-24T13:29:00Z"),  # 09:29 ET, pre-market
        bar("2026-08-24T13:30:00Z"),  # 09:30 ET, open
        bar("2026-08-24T19:59:00Z"),  # 15:59 ET, last RTH minute
        bar("2026-08-24T20:00:00Z"),  # 16:00 ET, closed
        bar("2026-08-24T22:00:00Z"),  # 18:00 ET, after hours
    ]
    got = indicators.rth_bars(bars)
    assert [b["ts_utc"] for b in got] == [
        "2026-08-24T13:30:00Z",
        "2026-08-24T19:59:00Z",
    ]


def test_rth_bars_handles_standard_time_not_just_dst():
    # In January, 09:30 ET is 14:30 UTC, not 13:30 UTC.
    bars = [
        bar("2027-01-12T13:30:00Z"),  # 08:30 ET, pre-market in winter
        bar("2027-01-12T14:30:00Z"),  # 09:30 ET, the open
    ]
    got = indicators.rth_bars(bars)
    assert [b["ts_utc"] for b in got] == ["2027-01-12T14:30:00Z"]


# --- session_open -----------------------------------------------------------

def test_session_open_is_the_first_rth_bar_open():
    bars = [
        bar("2026-08-24T12:00:00Z", o=95.0),   # pre-market, must be ignored
        bar("2026-08-24T13:30:00Z", o=100.0),  # the real open
        bar("2026-08-24T13:31:00Z", o=101.0),
    ]
    assert indicators.session_open(bars, "2026-08-24") == 100.0


def test_session_open_returns_none_when_session_has_no_rth_bars():
    bars = [bar("2026-08-24T12:00:00Z", o=95.0)]
    assert indicators.session_open(bars, "2026-08-24") is None


def test_session_open_isolates_the_requested_date():
    bars = [
        bar("2026-08-24T13:30:00Z", o=100.0),
        bar("2026-08-25T13:30:00Z", o=200.0),
    ]
    assert indicators.session_open(bars, "2026-08-25") == 200.0


# --- avg_daily_range --------------------------------------------------------

def test_avg_daily_range_averages_prior_sessions():
    bars = []
    for day, (lo, hi) in zip(range(24, 27), [(90.0, 100.0), (95.0, 105.0), (80.0, 100.0)]):
        bars.append(bar(f"2026-08-{day}T13:30:00Z", h=hi, l=lo))
    # ranges are 10, 10, 20 -> mean 13.333
    got = indicators.avg_daily_range(bars, before_date="2026-08-27", lookback_days=5)
    assert got == pytest.approx(13.3333, abs=0.001)


def test_avg_daily_range_excludes_the_current_session():
    bars = [
        bar("2026-08-24T13:30:00Z", h=100.0, l=90.0),   # range 10
        bar("2026-08-25T13:30:00Z", h=500.0, l=100.0),  # range 400, today
    ]
    got = indicators.avg_daily_range(bars, before_date="2026-08-25", lookback_days=5)
    assert got == pytest.approx(10.0)


def test_avg_daily_range_respects_lookback_window():
    bars = [bar(f"2026-08-{d}T13:30:00Z", h=100.0, l=90.0) for d in range(11, 21)]
    bars.append(bar("2026-08-21T13:30:00Z", h=1000.0, l=0.0))  # huge, but it is "today"
    got = indicators.avg_daily_range(bars, before_date="2026-08-21", lookback_days=2)
    assert got == pytest.approx(10.0)


def test_avg_daily_range_returns_zero_without_history():
    bars = [bar("2026-08-24T13:30:00Z", h=100.0, l=90.0)]
    assert indicators.avg_daily_range(bars, before_date="2026-08-24") == 0.0


def test_avg_daily_range_ignores_extended_hours_spikes():
    bars = [
        bar("2026-08-24T10:00:00Z", h=999.0, l=1.0),   # pre-market fat print
        bar("2026-08-24T13:30:00Z", h=100.0, l=90.0),  # real RTH range 10
    ]
    got = indicators.avg_daily_range(bars, before_date="2026-08-25", lookback_days=5)
    assert got == pytest.approx(10.0)
