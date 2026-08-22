"""Pure indicator functions. No I/O, no database, no network.

Each takes a sequence of bar mappings (as returned by store.recent_bars,
oldest first) and returns a single float.
"""
from typing import Sequence

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
