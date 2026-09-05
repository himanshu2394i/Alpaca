"""Risk gates. Pure logic - every limit has a case that must be rejected."""
import pytest

from agent import gates


def snap(bid=1.61, ask=1.63, delta=0.45, iv=0.10, prev_vol=5180, day_vol=1200):
    return {
        "greeks": {"delta": delta, "gamma": 0.026, "theta": -0.245, "vega": 0.349},
        "impliedVolatility": iv,
        "latestQuote": {"bp": bid, "ap": ask, "bs": 67, "as": 92},
        "dailyBar": {"v": day_vol, "c": (bid + ask) / 2},
        "prevDailyBar": {"v": prev_vol},
    }


# --- OCC symbol parsing -----------------------------------------------------

def test_parse_occ_splits_symbol_into_its_parts():
    got = gates.parse_occ("SPY260831C00765000")
    assert got == ("SPY", "2026-08-31", "call", 765.0)


def test_parse_occ_handles_puts_and_fractional_strikes():
    assert gates.parse_occ("QQQ260918P00612500")[2:] == ("put", 612.5)


def test_parse_occ_handles_short_and_long_underlyings():
    assert gates.parse_occ("F261218C00012000")[0] == "F"
    assert gates.parse_occ("GOOGL260904C00345000")[0] == "GOOGL"


def test_parse_occ_rejects_malformed_symbols():
    with pytest.raises(ValueError):
        gates.parse_occ("NOTASYMBOL")


# --- chain parsing ----------------------------------------------------------

def test_parse_chain_builds_contracts_from_the_mcp_payload():
    payload = {"snapshots": {"SPY260831C00765000": snap()}}
    got = gates.parse_chain(payload)
    assert len(got) == 1
    c = got[0]
    assert c.symbol == "SPY260831C00765000"
    assert c.right == "call" and c.strike == 765.0 and c.expiry == "2026-08-31"
    assert c.bid == 1.61 and c.ask == 1.63 and c.delta == 0.45
    assert c.prev_volume == 5180


def test_parse_chain_skips_contracts_missing_quotes_or_greeks():
    payload = {"snapshots": {
        "SPY260831C00765000": snap(),
        "SPY260831C00900000": {"latestQuote": {"bp": 0.01, "ap": 0.05}},   # no greeks
        "SPY260831C00100000": {"greeks": {"delta": 0.99}},                  # no quote
    }}
    assert [c.strike for c in gates.parse_chain(payload)] == [765.0]


def test_parse_chain_tolerates_an_empty_payload():
    assert gates.parse_chain({}) == []


def test_mid_and_spread_pct():
    c = gates.parse_chain({"snapshots": {"SPY260831C00765000": snap(bid=1.00, ask=1.10)}})[0]
    assert c.mid == pytest.approx(1.05)
    assert c.spread_pct == pytest.approx(0.10 / 1.05, abs=1e-6)


# --- contract viability -----------------------------------------------------

TODAY = "2026-08-24"


def one(**kw):
    return gates.parse_chain({"snapshots": {"SPY260904C00765000": snap(**kw)}})[0]


def test_viable_accepts_a_liquid_near_the_money_contract():
    assert gates.viable(one(), TODAY) is None


def test_rejects_a_spread_wider_than_the_limit():
    reason = gates.viable(one(bid=1.00, ask=1.40), TODAY)   # 33% of mid
    assert reason is not None and "spread" in reason


def test_rejects_an_illiquid_contract():
    reason = gates.viable(one(prev_vol=12), TODAY)
    assert reason is not None and "volume" in reason


def test_rejects_delta_outside_the_band():
    assert "delta" in gates.viable(one(delta=0.05), TODAY)
    assert "delta" in gates.viable(one(delta=0.95), TODAY)


def test_delta_band_is_applied_to_put_magnitude_not_sign():
    # Puts carry negative delta; a -0.45 put is as valid as a +0.45 call.
    c = gates.parse_chain({"snapshots": {"SPY260904P00765000": snap(delta=-0.45)}})[0]
    assert gates.viable(c, TODAY) is None


def test_rejects_an_expiry_that_is_too_near():
    c = gates.parse_chain({"snapshots": {"SPY260825C00765000": snap()}})[0]  # 1 DTE
    assert "dte" in gates.viable(c, TODAY)


def test_rejects_an_expiry_that_is_too_far():
    c = gates.parse_chain({"snapshots": {"SPY261218C00765000": snap()}})[0]  # ~116 DTE
    assert "dte" in gates.viable(c, TODAY)


def test_rejects_a_zero_bid_contract():
    assert gates.viable(one(bid=0.0, ask=0.05), TODAY) is not None


# --- position sizing --------------------------------------------------------

def test_size_caps_at_the_position_limit():
    # 2% of 100k = $2,000. At $1.63 ask, a contract costs $163.
    assert gates.size_contracts(equity=100_000, ask=1.63) == 12


def test_size_returns_zero_when_one_contract_exceeds_the_cap():
    assert gates.size_contracts(equity=100_000, ask=25.00) == 0


def test_size_is_never_negative_or_fractional():
    n = gates.size_contracts(equity=100_000, ask=0.07)
    assert isinstance(n, int) and n >= 0


# --- entry cutoff, checked once per tick, not once per candidate -----------
#
# approve() already rejects a late entry, but only after the screener has
# fetched a chain and the LLM has been asked to decide - both real cost for
# an outcome the clock alone already determined. Live 2026-09-04: from 15:30
# ET to the close, the agent called Claude Opus for two candidates roughly
# every 70 seconds, for hours, and rejected both every single time on this
# exact check. entry_cutoff_reason() lets the caller skip the screener and
# the LLM entirely once it's true, instead of discovering it after paying for both.

def test_entry_cutoff_reason_is_none_before_the_cutoff():
    assert gates.entry_cutoff_reason("15:29") is None


def test_entry_cutoff_reason_fires_at_and_after_the_cutoff():
    assert gates.entry_cutoff_reason("15:30") is not None
    assert gates.entry_cutoff_reason("19:59") is not None
    assert "15:30" in gates.entry_cutoff_reason("16:00")


# --- account-level halts ----------------------------------------------------

def test_no_halt_on_a_normal_day():
    assert gates.halt_reason(equity=100_000, day_start=100_000, peak=100_000) is None


def test_daily_loss_halt():
    r = gates.halt_reason(equity=96_500, day_start=100_000, peak=100_000)
    assert r is not None and "daily loss" in r


def test_drawdown_halt_from_peak():
    r = gates.halt_reason(equity=91_000, day_start=92_000, peak=100_000)
    assert r is not None and "drawdown" in r


def test_drawdown_halt_outranks_daily_loss():
    r = gates.halt_reason(equity=88_000, day_start=100_000, peak=100_000)
    assert "drawdown" in r


# --- data staleness (RTH only) ----------------------------------------------

def test_data_stale_ignored_outside_rth():
    # 20:30 UTC = 16:30 ET in August — after the close.
    assert gates.data_stale_reason(None, "2026-08-26T20:30:00Z") is None
    assert gates.data_stale_reason("2026-08-26T13:00:00Z", "2026-08-26T20:30:00Z") is None


def test_data_stale_halts_when_no_bars_during_rth():
    # 14:05 UTC = 10:05 ET — mid-session.
    r = gates.data_stale_reason(None, "2026-08-26T14:05:00Z")
    assert r is not None and "no bars" in r


def test_data_stale_halts_when_newest_bar_is_older_than_five_minutes():
    r = gates.data_stale_reason("2026-08-26T13:55:00Z", "2026-08-26T14:05:00Z")
    assert r is not None and "stale" in r


def test_data_stale_passes_when_bars_are_fresh():
    assert gates.data_stale_reason("2026-08-26T14:03:00Z", "2026-08-26T14:05:00Z") is None


# --- final approval ---------------------------------------------------------

def test_approve_passes_a_clean_trade():
    assert gates.approve(one(), qty=10, equity=100_000, deployed=0,
                         open_positions=0, now_et="11:00", today=TODAY) is None


def test_approve_blocks_entries_after_the_cutoff():
    r = gates.approve(one(), qty=10, equity=100_000, deployed=0,
                      open_positions=0, now_et="15:45", today=TODAY)
    assert r is not None and "cutoff" in r


def test_approve_blocks_when_deployed_capital_would_exceed_the_cap():
    # 10 contracts at $1.63 = $1,630. Already 9.9% deployed -> over the 10% cap.
    r = gates.approve(one(), qty=10, equity=100_000, deployed=9_900,
                      open_positions=1, now_et="11:00", today=TODAY)
    assert r is not None and "cap 10%" in r

    # And the same trade is fine when there is room for it.
    assert gates.approve(one(), qty=10, equity=100_000, deployed=0,
                         open_positions=1, now_et="11:00", today=TODAY) is None


def test_approve_blocks_at_the_concurrent_position_cap():
    r = gates.approve(one(), qty=10, equity=100_000, deployed=0,
                      open_positions=5, now_et="11:00", today=TODAY)
    assert r is not None and "open positions" in r


def test_approve_blocks_a_zero_quantity():
    r = gates.approve(one(), qty=0, equity=100_000, deployed=0,
                      open_positions=0, now_et="11:00", today=TODAY)
    assert r is not None and "quantity" in r


def test_approve_blocks_a_second_entry_in_an_already_open_underlying():
    """Live 2026-09-01: AAPL had one open position; the screener re-nominated
    AAPL, decide() picked a viable contract (nothing here stopped it), and the
    order filled for real - store.open_position() then rejected the duplicate
    row and crashed the tick, leaving 3 broker-side contracts with zero local
    tracking or exit protection. gates.approve() must catch this before the
    order is ever placed, not after the fill.
    """
    r = gates.approve(one(), qty=10, equity=100_000, deployed=0,
                      open_positions=1, now_et="11:00", today=TODAY,
                      open_underlyings={"SPY": 1})
    assert r is not None and "SPY" in r and "already has" in r


def test_approve_allows_a_different_underlying_while_one_is_open():
    r = gates.approve(one(), qty=10, equity=100_000, deployed=0,
                      open_positions=1, now_et="11:00", today=TODAY,
                      open_underlyings={"MSFT": 1})
    assert r is None


def test_approve_rechecks_contract_viability():
    # An unviable contract must not slip through just because sizing is fine.
    r = gates.approve(one(prev_vol=3), qty=10, equity=100_000, deployed=0,
                      open_positions=0, now_et="11:00", today=TODAY)
    assert r is not None and "volume" in r
