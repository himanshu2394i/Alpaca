"""Exit triggers.

Deliberately asymmetric with entries. An entry that fails to fire costs an
opportunity; an exit that fails to fire costs money. So exits run on every
position on every tick, need no LLM approval, and a missing quote produces a
signal rather than silence.

Forced exits (expiry proximity, competition end) outrank discretionary ones and
are reported first, because they must happen regardless of how the trade looks.
"""
from dataclasses import dataclass
from datetime import date

EXIT = {
    "premium_stop_pct":   -0.40,   # give back 40% of premium -> out
    "premium_target_pct":  0.80,   # +80% -> take it
    "min_dte":             2,      # never hold into the gamma cliff
    "competition_end":    "2026-09-04",
}


@dataclass(frozen=True)
class ExitSignal:
    symbol: str
    qty: int
    reason: str
    forced: bool


def levels(entry_underlying: float, adr: float, right: str,
           stop_mult: float = 1.0, target_mult: float = 2.0) -> tuple[float, float]:
    """Stop and target underlying prices for a new position.

    Sized in average daily ranges, the same yardstick the screener uses to
    decide the move was significant, so entry and exit speak one language.
    Reward-to-risk is 2:1 by construction.
    """
    if adr <= 0:
        raise ValueError("adr must be positive; a zero range exits on the next tick")

    if right == "call":
        return entry_underlying - stop_mult * adr, entry_underlying + target_mult * adr
    return entry_underlying + stop_mult * adr, entry_underlying - target_mult * adr


def _dte(expiry: str, today: str) -> int:
    return (date.fromisoformat(expiry) - date.fromisoformat(today)).days


def check(position, underlying: float | None, premium: float | None,
          today: str, rules: dict = EXIT) -> ExitSignal | None:
    """Why this position should be closed now, or None.

    `position` is a mapping shaped like a row of the positions table.
    """
    symbol, qty = position["symbol"], position["qty"]

    def signal(reason, forced=False):
        return ExitSignal(symbol=symbol, qty=qty, reason=reason, forced=forced)

    # --- forced, checked first ---------------------------------------------
    if today >= rules["competition_end"]:
        return signal(f"competition ends {rules['competition_end']}", forced=True)

    dte = _dte(position["expiry"], today)
    if dte <= rules["min_dte"]:
        return signal(f"dte {dte} at or below {rules['min_dte']}", forced=True)

    # --- discretionary ------------------------------------------------------
    if premium is not None and position["entry_price"] > 0:
        change = (premium - position["entry_price"]) / position["entry_price"]
        if change <= rules["premium_stop_pct"]:
            return signal(f"premium {change:+.0%} at or below "
                          f"{rules['premium_stop_pct']:.0%}")
        if change >= rules["premium_target_pct"]:
            return signal(f"premium {change:+.0%} at or above "
                          f"{rules['premium_target_pct']:.0%}")

    if underlying is not None:
        stop, target = position["stop_underlying"], position["target_underlying"]
        if position["right"] == "call":
            if underlying <= stop:
                return signal(f"underlying {underlying:.2f} broke stop {stop:.2f}")
            if underlying >= target:
                return signal(f"underlying {underlying:.2f} reached target {target:.2f}")
        else:
            # A put's adverse direction is up: stop sits above entry, target below.
            if underlying >= stop:
                return signal(f"underlying {underlying:.2f} broke stop {stop:.2f}")
            if underlying <= target:
                return signal(f"underlying {underlying:.2f} reached target {target:.2f}")

    return None


def scan(conn, underlyings: dict[str, float], premiums: dict[str, float],
         today: str, rules: dict = EXIT) -> list[ExitSignal]:
    """Check every open position. Returns one signal per position to close.

    A position with no premium quote is still evaluated on its underlying
    rather than skipped: an unquoted option is a reason for concern, not a
    reason to stop watching the position.
    """
    from agent import store

    out = []
    for position in store.open_positions(conn):
        signal = check(
            position,
            underlying=underlyings.get(position["underlying"]),
            premium=premiums.get(position["symbol"]),
            today=today,
            rules=rules,
        )
        if signal:
            out.append(signal)
    return out
