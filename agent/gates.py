"""Deterministic risk gates. No LLM, no network, no I/O.

Every function here answers one question: may this trade proceed? They return a
prose reason on rejection and None on approval, so the reason lands in the
decision log and the demo can show exactly why the agent stood still.

Nothing the model outputs can bypass these. That is the entire point: the
screener nominates and the model decides, but the trade only reaches the market
if this module says so.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

RISK = {
    "max_position_pct":  0.02,    # $2,000 per trade on $100k
    "max_deployed_pct":  0.10,    # 10% in options at any time
    "max_concurrent":    5,
    "daily_loss_halt":  -0.03,    # -$3,000 -> stop trading today
    "drawdown_halt":    -0.08,    # -$8,000 from peak -> flatten and stop
    "no_entry_after":   "15:30",  # ET
    "dte_range":        (3, 45),
    "min_prev_volume":  500,      # prior-session contract volume
    "max_spread_pct":   0.10,     # bid-ask as a fraction of mid
    "delta_range":      (0.35, 0.55),
    "stale_bars_sec":   300,      # no bars for 5 min during RTH -> halt entries
    "max_per_underlying": 1,      # never hold two positions in the same underlying
}

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

CONTRACT_MULTIPLIER = 100

# SPY260831C00765000 -> underlying SPY, 2026-08-31, call, strike 765.0
_OCC = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")


def parse_occ(symbol: str) -> tuple[str, str, str, float]:
    """Split an OCC option symbol into (underlying, expiry ISO, right, strike)."""
    m = _OCC.match(symbol)
    if not m:
        raise ValueError(f"not an OCC option symbol: {symbol!r}")
    underlying, yymmdd, cp, strike = m.groups()
    expiry = f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:]}"
    return underlying, expiry, ("call" if cp == "C" else "put"), int(strike) / 1000


@dataclass(frozen=True)
class Contract:
    symbol: str
    underlying: str
    expiry: str
    right: str
    strike: float
    bid: float
    ask: float
    delta: float
    iv: float
    prev_volume: int
    day_volume: int

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> float:
        return (self.ask - self.bid) / self.mid if self.mid > 0 else 1.0

    def dte(self, today: str) -> int:
        return (date.fromisoformat(self.expiry) - date.fromisoformat(today)).days


def parse_chain(payload: dict) -> list[Contract]:
    """Build Contracts from an unwrapped get_option_chain payload.

    Snapshots lacking a quote or Greeks are dropped rather than defaulted: a
    contract we cannot price or measure is one we must not trade, and a zero
    default would silently look like a very cheap, very safe option.
    """
    out = []
    for symbol, snap in (payload.get("snapshots") or {}).items():
        quote, greeks = snap.get("latestQuote"), snap.get("greeks")
        if not quote or not greeks:
            continue
        try:
            underlying, expiry, right, strike = parse_occ(symbol)
        except ValueError:
            continue
        out.append(Contract(
            symbol=symbol, underlying=underlying, expiry=expiry, right=right,
            strike=strike,
            bid=float(quote.get("bp", 0.0)), ask=float(quote.get("ap", 0.0)),
            delta=float(greeks.get("delta", 0.0)),
            iv=float(snap.get("impliedVolatility", 0.0)),
            prev_volume=int((snap.get("prevDailyBar") or {}).get("v", 0)),
            day_volume=int((snap.get("dailyBar") or {}).get("v", 0)),
        ))
    return out


def viable(c: Contract, today: str, risk: dict = RISK) -> str | None:
    """Why this contract is untradeable, or None.

    Checked against live data: near-the-money SPY strikes quote 1.61/1.63 with
    5,180 prior-day volume, while deep-ITM strikes on the same chain last
    traded nine days ago on 4 contracts. Without these checks the agent would
    happily buy the latter.
    """
    if c.bid <= 0 or c.ask <= 0:
        return f"{c.symbol} has no two-sided market (bid {c.bid}, ask {c.ask})"

    dte = c.dte(today)
    lo, hi = risk["dte_range"]
    if not lo <= dte <= hi:
        return f"{c.symbol} dte {dte} outside {lo}-{hi}"

    if c.prev_volume < risk["min_prev_volume"]:
        return f"{c.symbol} prior-day volume {c.prev_volume} below {risk['min_prev_volume']}"

    if c.spread_pct > risk["max_spread_pct"]:
        return (f"{c.symbol} spread {c.spread_pct:.1%} above "
                f"{risk['max_spread_pct']:.0%} of mid")

    # Puts carry negative delta; the band applies to magnitude.
    dlo, dhi = risk["delta_range"]
    if not dlo <= abs(c.delta) <= dhi:
        return f"{c.symbol} delta {c.delta:.2f} outside {dlo}-{dhi}"

    return None


def size_contracts(equity: float, ask: float, risk: dict = RISK) -> int:
    """How many contracts fit inside the per-trade risk budget.

    Returns 0 when a single contract already exceeds the budget - the caller
    must treat that as "do not trade", never as "buy one anyway".
    """
    if ask <= 0:
        return 0
    budget = equity * risk["max_position_pct"]
    return max(0, int(budget // (ask * CONTRACT_MULTIPLIER)))


def entry_cutoff_reason(now_et: str, risk: dict = RISK) -> str | None:
    """Why no new entries may be attempted, based on the clock alone.

    Meant to be checked once per tick, before the screener or the LLM ever
    run. approve() already rejects a late entry with the same check, but only
    after a chain has been fetched and the model has been asked to decide -
    both real cost for an outcome the clock alone already determined. Live
    2026-09-04: from 15:30 ET to the close, every ~70s tick called Claude
    Opus for two candidates and rejected both here every time, for hours.
    """
    if now_et >= risk["no_entry_after"]:
        return f"{now_et} ET is past the {risk['no_entry_after']} entry cutoff"
    return None


def halt_reason(
    equity: float, day_start: float, peak: float, risk: dict = RISK
) -> str | None:
    """Why trading is halted account-wide, or None.

    Drawdown is checked before daily loss: it is the more severe condition and
    the one that stops the competition rather than the day.
    """
    if peak > 0:
        dd = (equity - peak) / peak
        if dd <= risk["drawdown_halt"]:
            return f"drawdown {dd:.1%} from peak {peak:,.0f} (limit {risk['drawdown_halt']:.0%})"

    if day_start > 0:
        day = (equity - day_start) / day_start
        if day <= risk["daily_loss_halt"]:
            return f"daily loss {day:.1%} (limit {risk['daily_loss_halt']:.0%})"

    return None


def data_stale_reason(
    newest_bar_ts: str | None,
    now_utc: str,
    risk: dict = RISK,
) -> str | None:
    """Why entries are halted for stale market data, or None.

    Only applies during RTH. Overnight and weekends the tape is quiet by
    definition; a missing bar then is not a feed failure. During the session,
    no bars (or bars older than stale_bars_sec) means the agent must not open
    new risk — exits still run separately.
    """
    from agent.indicators import _is_rth

    if not _is_rth(now_utc):
        return None

    max_age = int(risk["stale_bars_sec"])
    if newest_bar_ts is None:
        return f"no bars in store during RTH (staleness limit {max_age}s)"

    now = datetime.strptime(now_utc, _TS_FMT).replace(tzinfo=timezone.utc)
    newest = datetime.strptime(newest_bar_ts, _TS_FMT).replace(tzinfo=timezone.utc)
    age = (now - newest).total_seconds()
    if age > max_age:
        return f"bars stale by {int(age)}s (limit {max_age}s); newest {newest_bar_ts}"
    return None


def approve(
    contract: Contract,
    qty: int,
    equity: float,
    deployed: float,
    open_positions: int,
    now_et: str,
    today: str,
    open_underlyings: dict[str, int] | None = None,
    risk: dict = RISK,
) -> str | None:
    """Final check before an order is sent. Returns a rejection reason or None.

    Re-runs contract viability rather than trusting an earlier pass: the chain
    may have moved between nomination and execution, and this is the last point
    at which a bad fill can still be prevented.

    Live 2026-09-01: a second AAPL 330C entry was approved and filled while the
    first was still open, because nothing here checked for that. The broker
    happily filled it - Alpaca has no objection to buying more of a symbol you
    already hold - but store.open_position() then rejected the duplicate row,
    crashing that tick after the money had already been spent. The fill was
    real; the local tracking was not, so exits.scan() never saw it. Caught
    here, before the order is placed, not after.
    """
    if qty <= 0:
        return f"quantity {qty} is not tradeable"

    if now_et >= risk["no_entry_after"]:
        return f"{now_et} ET is past the {risk['no_entry_after']} entry cutoff"

    unviable = viable(contract, today, risk)
    if unviable:
        return unviable

    cost = qty * contract.ask * CONTRACT_MULTIPLIER
    if deployed + cost > equity * risk["max_deployed_pct"]:
        return (f"would put {(deployed + cost) / equity:.1%} of equity in options "
                f"(cap {risk['max_deployed_pct']:.0%})")

    if open_positions >= risk["max_concurrent"]:
        return f"{open_positions} open positions (cap {risk['max_concurrent']})"

    held = (open_underlyings or {}).get(contract.underlying, 0)
    if held >= risk["max_per_underlying"]:
        return (f"{contract.underlying} already has {held} open position(s) "
                f"(cap {risk['max_per_underlying']})")

    return None
