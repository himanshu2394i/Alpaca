import pytest

from agent import indicators
from tests.helpers import make_bars


def rows(bars):
    """helpers tuples -> mappings shaped like sqlite3.Row."""
    keys = ("symbol", "ts_utc", "o", "h", "l", "c", "v")
    return [dict(zip(keys, b)) for b in bars]


def test_ema_of_flat_series_equals_the_price():
    bars = rows(make_bars(n=30, start_price=50.0, step=0.0))
    assert indicators.ema(bars, period=10) == pytest.approx(50.0)


def test_ema_trails_a_rising_series():
    bars = rows(make_bars(n=30, start_price=100.0, step=1.0))
    last_close = bars[-1]["c"]
    value = indicators.ema(bars, period=10)
    assert value < last_close
    assert value > bars[-10]["c"]


def test_ema_raises_when_not_enough_bars():
    with pytest.raises(ValueError):
        indicators.ema(rows(make_bars(n=3)), period=10)


def test_atr_converges_to_the_constant_true_range():
    # make_bars gives every bar a high/low spread of 1.0 and a close-to-close
    # step of 1.0, so true range is 1.0 on the first bar and 1.5 thereafter
    # (high - previous close). Wilder smoothing converges toward 1.5; with 200
    # bars the residual from the initial 1.0 is far below the tolerance.
    bars = rows(make_bars(n=200, start_price=100.0, step=1.0))
    assert indicators.atr(bars, period=14) == pytest.approx(1.5, abs=0.01)


def test_atr_has_not_converged_after_few_bars():
    # Guards the smoothing direction: a young ATR must sit below the limit,
    # not above it or already equal to it.
    bars = rows(make_bars(n=30, start_price=100.0, step=1.0))
    value = indicators.atr(bars, period=14)
    assert 1.4 < value < 1.5


def test_atr_is_zero_for_a_frozen_market():
    bars = rows(make_bars(n=30, start_price=100.0, step=0.0))
    flat = [{**b, "h": 100.0, "l": 100.0, "c": 100.0, "o": 100.0} for b in bars]
    assert indicators.atr(flat, period=14) == pytest.approx(0.0)


def test_rvol_is_one_when_today_matches_the_average():
    bars = []
    for day in range(24, 29):  # 24..28 Aug, five sessions
        for b in make_bars(n=10):
            ts = b[1].replace("2026-08-24", f"2026-08-{day}")
            bars.append((b[0], ts, b[2], b[3], b[4], b[5], 1000))
    value = indicators.rvol(rows(bars), session_date="2026-08-28", lookback_days=4)
    assert value == pytest.approx(1.0)


def test_rvol_detects_a_volume_spike():
    bars = []
    for day in range(24, 28):
        for b in make_bars(n=10):
            ts = b[1].replace("2026-08-24", f"2026-08-{day}")
            bars.append((b[0], ts, b[2], b[3], b[4], b[5], 1000))
    for b in make_bars(n=10):  # today, triple volume
        ts = b[1].replace("2026-08-24", "2026-08-28")
        bars.append((b[0], ts, b[2], b[3], b[4], b[5], 3000))
    value = indicators.rvol(rows(bars), session_date="2026-08-28", lookback_days=4)
    assert value == pytest.approx(3.0)


def test_rvol_returns_zero_without_prior_history():
    bars = rows(make_bars(n=10))
    assert indicators.rvol(bars, session_date="2026-08-24") == 0.0
