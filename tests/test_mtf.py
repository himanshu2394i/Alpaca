"""Multi-timeframe indicators: RSI, Supertrend, hybrid confirmation."""
import pytest

from agent import indicators


def rows_from_closes(closes, start_ts="2026-08-01T13:30:00Z", step_min=15):
    """Build 15-min style bars from a close series."""
    from datetime import datetime, timedelta, timezone

    t0 = datetime.strptime(start_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    out = []
    for i, c in enumerate(closes):
        ts = (t0 + timedelta(minutes=i * step_min)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"symbol": "SPY", "ts_utc": ts, "o": c, "h": c + 1, "l": c - 1,
                    "c": c, "v": 1000})
    return out


def test_rsi_is_high_on_a_sustained_uptrend():
    closes = [100 + i * 0.5 for i in range(30)]
    assert indicators.rsi(rows_from_closes(closes), period=14) > 60


def test_rsi_is_low_on_a_sustained_downtrend():
    closes = [100 - i * 0.5 for i in range(30)]
    assert indicators.rsi(rows_from_closes(closes), period=14) < 40


def test_rsi_detects_a_fresh_cross_above_fifty():
    closes = [100 - i * 0.5 for i in range(15)] + [100 - 15 * 0.5 + 7]
    assert indicators.rsi_cross_above(rows_from_closes(closes, step_min=1),
                                      level=50, period=14) is True


def test_supertrend_is_bullish_on_a_strong_uptrend():
    closes = [100 + i * 2 for i in range(40)]
    st = indicators.supertrend(rows_from_closes(closes), period=10, multiplier=3)
    assert st["direction"] == 1
    assert closes[-1] > st["value"]


def test_mtf_rejects_a_call_when_price_is_below_the_200_ema_on_15m():
    """Enough RTH history for EMA200, but entry price sits below the slow EMA."""
    bars = _many_rth_sessions(n_sessions=25, base=100.0, step=0.05)
    ok, ctx = indicators.mtf_confirm(bars, price=100.0, direction="call")
    assert ok is False
    assert "below 15m EMA200" in ctx["reason"]


def test_mtf_passes_when_insufficient_history():
    bars = rows_from_closes([100.0] * 5, step_min=1)
    ok, ctx = indicators.mtf_confirm(bars, price=100.0, direction="call")
    assert ok is None
    assert ctx["reason"] == "insufficient history"


def _many_rth_sessions(n_sessions, base=100.0, step=0.05, n_per_session=390):
    """Build `n_sessions` of synthetic RTH 1-min uptrend bars."""
    from datetime import date, datetime, timedelta, timezone

    out = []
    price = base
    day = date(2026, 7, 1)
    sessions = 0
    while sessions < n_sessions:
        if day.weekday() < 5:
            t0 = datetime(day.year, day.month, day.day, 13, 30, tzinfo=timezone.utc)
            for i in range(n_per_session):
                ts = (t0 + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
                out.append({"symbol": "SPY", "ts_utc": ts, "o": price, "h": price + 0.5,
                            "l": price - 0.5, "c": price, "v": 1000})
                price += step
            sessions += 1
        day += timedelta(days=1)
    return out
