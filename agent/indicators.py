"""Pure indicator functions. No I/O, no database, no network.

Each takes a sequence of bar mappings (as returned by store.recent_bars,
oldest first) and returns a single float.
"""
from datetime import datetime, time, timezone
from functools import lru_cache
from typing import Sequence
from zoneinfo import ZoneInfo

import pandas as pd


def _frame(bars: Sequence[dict]) -> pd.DataFrame:
    return pd.DataFrame([dict(b) for b in bars])


def ema(bars: Sequence[dict], period: int) -> float:
    """Exponential moving average of closes; returns the final value."""
    if len(bars) < period:
        raise ValueError(f"need at least {period} bars, got {len(bars)}")
    closes = _frame(bars)["c"]
    return float(closes.ewm(span=period, adjust=False).mean().iloc[-1])


def atr(bars: Sequence[dict], period: int = 14) -> float:
    """Wilder's Average True Range; returns the final value."""
    if len(bars) < period:
        raise ValueError(f"need at least {period} bars, got {len(bars)}")
    df = _frame(bars)
    prev_close = df["c"].shift(1)
    true_range = pd.concat(
        [
            df["h"] - df["l"],
            (df["h"] - prev_close).abs(),
            (df["l"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder smoothing is an EMA with alpha = 1/period.
    return float(true_range.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def rvol(bars: Sequence[dict], session_date: str, lookback_days: int = 5) -> float:
    """Relative volume: today's volume so far divided by the mean volume over
    the same number of elapsed bars on the previous `lookback_days` sessions.

    Returns 0.0 when there is no prior history to compare against, so a caller
    thresholding on `rvol > 1.5` fails closed rather than firing.
    """
    df = _frame(bars)
    df["date"] = df["ts_utc"].str[:10]

    today = df[df["date"] == session_date]
    if today.empty:
        return 0.0
    elapsed = len(today)

    prior_dates = sorted(d for d in df["date"].unique() if d < session_date)
    prior_dates = prior_dates[-lookback_days:]
    if not prior_dates:
        return 0.0

    baselines = [df[df["date"] == d].head(elapsed)["v"].sum() for d in prior_dates]
    mean_baseline = sum(baselines) / len(baselines)
    if mean_baseline == 0:
        return 0.0

    return float(today["v"].sum() / mean_baseline)


# --- session-aware helpers --------------------------------------------------
#
# Bars from Alpaca include pre- and post-market prints. Those have thin volume
# and wild spreads, so anything measuring "where did this session start" or
# "how wide is a normal day" must exclude them first.

ET = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


@lru_cache(maxsize=200_000)
def _is_rth(ts_utc: str) -> bool:
    """True if the timestamp falls inside 09:30-16:00 America/New_York.

    Converts through zoneinfo rather than assuming a fixed UTC offset: 09:30 ET
    is 13:30Z in summer and 14:30Z in winter, and the competition straddles no
    DST boundary but the code should not quietly break in November.

    Cached because the screener re-filters the same bars every time it runs:
    strptime plus a timezone conversion per bar per call is the difference
    between a scan taking milliseconds and taking minutes. Timestamps repeat
    exactly, so the hit rate is near 100%.
    """
    t = datetime.strptime(ts_utc, TS_FMT).replace(tzinfo=timezone.utc).astimezone(ET)
    return RTH_OPEN <= t.time() < RTH_CLOSE


def rth_bars(bars: Sequence[dict]) -> list[dict]:
    """Only the bars inside regular trading hours, order preserved."""
    return [dict(b) for b in bars if _is_rth(b["ts_utc"])]


def session_open(bars: Sequence[dict], session_date: str) -> float | None:
    """Opening price of `session_date`'s first regular-hours bar.

    Returns None when that session has no RTH bars, so a caller cannot
    accidentally measure a move against a pre-market print.
    """
    todays = [b for b in rth_bars(bars) if b["ts_utc"][:10] == session_date]
    return float(todays[0]["o"]) if todays else None


def avg_daily_range(
    bars: Sequence[dict], before_date: str, lookback_days: int = 10
) -> float:
    """Mean regular-hours high-low range over the sessions before `before_date`.

    This is the volatility yardstick for "has price travelled unusually far
    from today's open". Deliberately a range and not a true ATR: ATR folds in
    the overnight gap, which is irrelevant when the move being measured starts
    at the opening bell.

    Returns 0.0 when there is no prior history, so a caller dividing by it must
    check first and a caller thresholding on it fails closed.
    """
    by_date: dict[str, list[dict]] = {}
    for b in rth_bars(bars):
        d = b["ts_utc"][:10]
        if d < before_date:
            by_date.setdefault(d, []).append(b)

    if not by_date:
        return 0.0

    recent = sorted(by_date)[-lookback_days:]
    ranges = [
        max(x["h"] for x in by_date[d]) - min(x["l"] for x in by_date[d])
        for d in recent
    ]
    return float(sum(ranges) / len(ranges))
