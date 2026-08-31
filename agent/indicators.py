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
    """True if the timestamp falls inside 09:30-16:00 America/New_York on a weekday.

    Converts through zoneinfo rather than assuming a fixed UTC offset: 09:30 ET
    is 13:30Z in summer and 14:30Z in winter, and the competition straddles no
    DST boundary but the code should not quietly break in November.

    Weekday-only, not holiday-aware: the loop runs 24/7 and this clock check
    alone would say "open" at 11am ET on a Saturday. A market holiday would
    still slip through - not fetched here since none falls inside the 31 Aug -
    4 Sep competition week (ponytail: wire agent.mcp_bridge's get_calendar if
    this needs to hold outside that window).

    Cached because the screener re-filters the same bars every time it runs:
    strptime plus a timezone conversion per bar per call is the difference
    between a scan taking milliseconds and taking minutes. Timestamps repeat
    exactly, so the hit rate is near 100%.
    """
    t = datetime.strptime(ts_utc, TS_FMT).replace(tzinfo=timezone.utc).astimezone(ET)
    return t.weekday() < 5 and RTH_OPEN <= t.time() < RTH_CLOSE


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


# --- multi-timeframe (hybrid screener filters) ------------------------------
#
# Cousin's Supertrend/RSI/EMA rules, applied as confirmation on top of the
# intraday momentum screener. When history is too thin to compute a filter,
# we fail open (return None) so warmup does not starve the agent.

MTF = {
    "enabled": True,
    "supertrend_period": 10,
    "supertrend_mult": 3.0,
    "rsi_period": 14,
    "ema_slow_15m": 200,
    "min_4h_bars": 11,
    "min_15m_bars": 200,
    "require_rsi_cross": False,
}


def resample_bars(bars: Sequence[dict], rule: str) -> list[dict]:
    """Aggregate 1-min (or finer) bars into `rule` OHLCV bars, oldest first."""
    if not bars:
        return []
    df = _frame(bars)
    df["ts"] = pd.to_datetime(df["ts_utc"], utc=True)
    df = df.set_index("ts").sort_index()
    ohlcv = df.resample(rule, label="right", closed="right").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}
    ).dropna(subset=["c"])
    symbol = str(bars[0].get("symbol", ""))
    out = []
    for ts, row in ohlcv.iterrows():
        out.append(
            {
                "symbol": symbol,
                "ts_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "o": float(row["o"]),
                "h": float(row["h"]),
                "l": float(row["l"]),
                "c": float(row["c"]),
                "v": int(row["v"]),
            }
        )
    return out


def rsi(bars: Sequence[dict], period: int = 14) -> float:
    """Wilder RSI on closes; returns the final value."""
    if len(bars) < period + 1:
        raise ValueError(f"need at least {period + 1} bars, got {len(bars)}")
    closes = _frame(bars)["c"]
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi_series = 100 - (100 / (1 + rs))
    rsi_series = rsi_series.fillna(100.0)
    return float(rsi_series.iloc[-1])


def rsi_cross_above(bars: Sequence[dict], level: float = 50.0,
                    period: int = 14) -> bool:
    """True when RSI crossed from below `level` to at/above it on the last bar."""
    if len(bars) < period + 2:
        return False
    closes = _frame(bars)["c"]
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi_series = (100 - (100 / (1 + rs))).fillna(100.0)
    prev, curr = float(rsi_series.iloc[-2]), float(rsi_series.iloc[-1])
    return prev < level <= curr


def supertrend(bars: Sequence[dict], period: int = 10,
               multiplier: float = 3.0) -> dict:
    """Latest Supertrend value and direction (+1 bullish, -1 bearish)."""
    if len(bars) < period + 1:
        raise ValueError(f"need at least {period + 1} bars, got {len(bars)}")
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
    atr_series = true_range.ewm(alpha=1 / period, adjust=False).mean()
    hl2 = (df["h"] + df["l"]) / 2
    basic_upper = hl2 + multiplier * atr_series
    basic_lower = hl2 - multiplier * atr_series

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    direction = pd.Series(index=df.index, dtype=int)

    for i in range(1, len(df)):
        if basic_upper.iloc[i] < final_upper.iloc[i - 1] or df["c"].iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        if basic_lower.iloc[i] > final_lower.iloc[i - 1] or df["c"].iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        if df["c"].iloc[i] > final_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["c"].iloc[i] < final_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

    if pd.isna(direction.iloc[0]):
        direction.iloc[0] = 1

    last_dir = int(direction.iloc[-1])
    st_val = float(final_lower.iloc[-1] if last_dir == 1 else final_upper.iloc[-1])
    return {"value": st_val, "direction": last_dir}


def mtf_confirm(bars: Sequence[dict], price: float, direction: str,
                config: dict | None = None) -> tuple[bool | None, dict]:
    """Hybrid MTF filter from the Supertrend/RSI/EMA setup.

    Returns (True, ctx) when filters confirm, (False, ctx) when they reject,
    and (None, ctx) when there is not enough history to compute them (caller
    should skip the filter rather than block the trade).
    """
    cfg = config or MTF
    ctx: dict = {"alert_high": None, "alert_low": None, "reason": "", "note": ""}

    rth = rth_bars(bars)
    bars_4h = resample_bars(rth, "4h")
    bars_15m = resample_bars(rth, "15min")

    if len(bars_4h) < cfg["min_4h_bars"] or len(bars_15m) < cfg["min_15m_bars"]:
        ctx["reason"] = "insufficient history"
        return None, ctx

    try:
        st = supertrend(bars_4h, period=cfg["supertrend_period"],
                        multiplier=cfg["supertrend_mult"])
        rsi_val = rsi(bars_4h, period=cfg["rsi_period"])
        ema200 = ema(bars_15m, period=cfg["ema_slow_15m"])
    except ValueError:
        ctx["reason"] = "insufficient history"
        return None, ctx

    last_4h = bars_4h[-1]
    ctx["alert_high"] = float(last_4h["h"])
    ctx["alert_low"] = float(last_4h["l"])

    if direction == "call":
        if st["direction"] != 1 or last_4h["c"] <= st["value"]:
            ctx["reason"] = "4H not above Supertrend"
            return False, ctx
        if rsi_val < 50:
            ctx["reason"] = f"4H RSI {rsi_val:.1f} below 50"
            return False, ctx
        if cfg["require_rsi_cross"] and not rsi_cross_above(
            bars_4h, level=50, period=cfg["rsi_period"]
        ):
            ctx["reason"] = "4H RSI has not freshly crossed above 50"
            return False, ctx
        if price <= ema200:
            ctx["reason"] = f"entry {price:.2f} below 15m EMA200 {ema200:.2f}"
            return False, ctx
        cross = rsi_cross_above(bars_4h, level=50, period=cfg["rsi_period"])
        ctx["note"] = f"MTF ok: 4H ST bullish, RSI {rsi_val:.0f}" + (
            ", fresh RSI cross" if cross else ""
        )
        return True, ctx

    if direction == "put":
        if st["direction"] != -1 or last_4h["c"] >= st["value"]:
            ctx["reason"] = "4H not below Supertrend"
            return False, ctx
        if rsi_val > 50:
            ctx["reason"] = f"4H RSI {rsi_val:.1f} above 50"
            return False, ctx
        if price >= ema200:
            ctx["reason"] = f"entry {price:.2f} above 15m EMA200 {ema200:.2f}"
            return False, ctx
        ctx["note"] = f"MTF ok: 4H ST bearish, RSI {rsi_val:.0f}"
        return True, ctx

    ctx["reason"] = f"unknown direction {direction!r}"
    return False, ctx
