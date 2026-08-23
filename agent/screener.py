"""Deterministic entry screening.

This module nominates candidates. It never decides and never orders — the LLM
decides, the gates approve, execute places. Keeping nomination deterministic is
what stops the agent from inventing a symbol out of nothing.

Thresholds below were measured against 9 sessions of real IEX bars via
tools/replay.py, not chosen by taste:

    mult   candidates   per day   sessions with no candidate
    0.50       13         2.17              1 of 6
    0.60        9         1.50              2 of 6
    0.75        8         1.33              2 of 6
    1.00        6         1.00              3 of 6

0.50 is chosen because it reaches the ~11 trades the design targets over a
5-session competition and leaves only one idle session. The error here is
asymmetric: a screener that nominates too little starves the agent outright,
while one that nominates too much only gives the decision agent and the risk
gates more to reject. Re-run tools/replay.py before changing this.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent import indicators, store

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

TRIGGER = {
    "move_adr_mult": 0.50,      # move from session open, in average daily ranges
    "min_rvol": 1.5,
    "ema_period": 20,
    "rvol_lookback_days": 5,
    "adr_lookback_days": 10,
    "min_session_bars": 20,     # do not judge a session on its first few minutes
}

LIMITS = {
    "cooldown_min": 60,
    "max_entries_per_day": 3,
    "max_concurrent": 5,
}


@dataclass(frozen=True)
class Candidate:
    """One nominated trade. Immutable: the LLM may reject it, never edit it."""
    symbol: str
    direction: str          # "call" | "put"
    ts_utc: str
    price: float
    session_open: float
    adr: float
    move_adr: float         # signed, in average daily ranges
    rvol: float
    ema: float


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, TS_FMT).replace(tzinfo=timezone.utc)


def evaluate(bars, session_date: str, trigger: dict = TRIGGER) -> Candidate | None:
    """Nominate `bars`' symbol for entry, or return None.

    `bars` must be oldest-first and end at the moment being evaluated.
    Every failure path returns None rather than raising: a screener that
    crashes on thin data would take the whole ingest process down with it.
    """
    adr = indicators.avg_daily_range(
        bars, before_date=session_date, lookback_days=trigger["adr_lookback_days"]
    )
    if adr <= 0:
        return None  # no history to size the move against

    open_px = indicators.session_open(bars, session_date)
    if open_px is None:
        return None  # session has no regular-hours bars yet

    today = [b for b in indicators.rth_bars(bars) if b["ts_utc"][:10] == session_date]
    if len(today) < trigger["min_session_bars"]:
        return None

    last = today[-1]
    price = float(last["c"])
    move_adr = (price - open_px) / adr
    if abs(move_adr) < trigger["move_adr_mult"]:
        return None

    rvol = indicators.rvol(
        bars, session_date=session_date, lookback_days=trigger["rvol_lookback_days"]
    )
    if rvol < trigger["min_rvol"]:
        return None

    if len(bars) < trigger["ema_period"]:
        return None
    ema = indicators.ema(bars, trigger["ema_period"])

    # A move that has round-tripped back through its own EMA is reverting, not
    # trending. This rejects roughly one candidate in fourteen — cheap, and it
    # is not a substitute for a real trend filter.
    going_up = move_adr > 0
    if going_up and price <= ema:
        return None
    if not going_up and price >= ema:
        return None

    return Candidate(
        symbol=str(last["symbol"]),
        direction="call" if going_up else "put",
        ts_utc=str(last["ts_utc"]),
        price=price,
        session_open=open_px,
        adr=adr,
        move_adr=move_adr,
        rvol=rvol,
        ema=ema,
    )


@dataclass
class ThrottleState:
    """What the screener needs to know about what has already been traded."""
    last_entry: dict[str, str] = field(default_factory=dict)  # symbol -> ts_utc
    entries_today: int = 0
    open_positions: int = 0


def throttle_reason(
    state: ThrottleState, symbol: str, now_ts: str, limits: dict = LIMITS
) -> str | None:
    """Why `symbol` may not be entered right now, or None if it may.

    Returns prose rather than a bool so the reason lands in the decision log
    and the demo can show why the agent stood still.
    """
    if state.entries_today >= limits["max_entries_per_day"]:
        return f"{state.entries_today} entries today (cap {limits['max_entries_per_day']})"

    if state.open_positions >= limits["max_concurrent"]:
        return f"{state.open_positions} open positions (cap {limits['max_concurrent']})"

    last = state.last_entry.get(symbol)
    if last:
        elapsed_min = (_parse(now_ts) - _parse(last)).total_seconds() / 60
        if elapsed_min < limits["cooldown_min"]:
            left = limits["cooldown_min"] - elapsed_min
            return f"{symbol} in cooldown, {left:.0f} min left"

    return None


def scan(
    conn,
    symbols,
    session_date: str,
    state: ThrottleState,
    trigger: dict = TRIGGER,
    limits: dict = LIMITS,
) -> list[Candidate]:
    """Evaluate every symbol and return those that qualify and are not throttled."""
    out = []
    for symbol in symbols:
        bars = [dict(b) for b in store.recent_bars(conn, symbol, limit=8000)]
        if not bars:
            continue
        candidate = evaluate(bars, session_date, trigger)
        if candidate is None:
            continue
        if throttle_reason(state, symbol, candidate.ts_utc, limits):
            continue
        out.append(candidate)
    return out
