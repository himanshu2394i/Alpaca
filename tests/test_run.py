"""The orchestration tick.

The property that matters most: exits must survive every condition that stops
entries. Being unable to open a position costs an opportunity; being unable to
close one costs money.
"""
import pytest

from agent import exits, run, screener, store

TODAY = "2026-08-26"
NOW = "2026-08-26T14:05:00Z"

BASE = dict(underlying="SPY", right="call", qty=7, entry_price=2.00,
            entry_underlying=765.0, stop_underlying=760.0,
            target_underlying=775.0, expiry="2026-09-11")


def seed_fresh_bars(conn, ts_utc=NOW):
    """Give the tick a live-looking tape so the RTH staleness gate does not trip."""
    store.upsert_bars(conn, [("SPY", ts_utc, 765.0, 766.0, 764.0, 765.0, 1000)])


class FakeBroker:
    """Stands in for the MCP session; records what the tick tried to do."""

    def __init__(self, chain=None):
        self.orders, self.chain = [], chain or {"snapshots": {}}

    async def fetch_chain(self, *a, **kw):
        return self.chain

    async def place(self, order, dry_run=True, contract=None, ts_utc=None, **kw):
        self.orders.append((order, dry_run))
        if dry_run:
            return {"dry_run": True, "status": "simulated", "order": order}
        return {"dry_run": False, "status": "filled",
                "fill_price": float(order["limit_price"])}


def open_a_losing_position(conn):
    store.open_position(conn, symbol="SPY260911C00765000",
                        entry_ts="2026-08-24T14:05:00Z", **BASE)


# Live quotes for the test position. Bid/ask must be real — exits must not
# fall back to entry_price ($2.00) when the option has already collapsed.
EXIT_QUOTES = {"SPY260911C00765000": (1.18, 1.22)}


async def test_exits_still_fire_when_the_halt_file_exists(conn, tmp_path):
    open_a_losing_position(conn)
    halt = tmp_path / "HALT"
    halt.write_text("stop")

    result = await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                            underlyings={"SPY": 750.0}, equity=100_000,
                            day_start=100_000, peak=100_000, halt_file=halt)

    assert result["halted"]
    assert len(result["exits"]) == 1
    assert result["entries"] == []


async def test_exits_still_fire_when_the_drawdown_halt_trips(conn, tmp_path):
    open_a_losing_position(conn)

    result = await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                            underlyings={"SPY": 750.0}, equity=88_000,
                            day_start=100_000, peak=100_000,
                            halt_file=tmp_path / "HALT")

    assert result["halted"] and "drawdown" in result["halt_reason"]
    assert len(result["exits"]) == 1


async def test_entries_are_blocked_while_halted(conn, tmp_path):
    result = await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                            underlyings={"SPY": 765.0}, equity=95_000,
                            day_start=100_000, peak=100_000,
                            halt_file=tmp_path / "HALT")

    assert result["halted"]
    assert result["entries"] == []


async def test_a_clean_tick_is_not_halted(conn, tmp_path):
    seed_fresh_bars(conn)
    result = await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                            underlyings={}, equity=100_000, day_start=100_000,
                            peak=100_000, halt_file=tmp_path / "HALT")
    assert not result["halted"]
    assert result["halt_reason"] is None


async def test_stale_bars_halt_entries_but_exits_still_fire(conn, tmp_path):
    open_a_losing_position(conn)
    # Stale RTH bar: 14:05 now, last bar at 13:55 → 10 minutes old.
    store.upsert_bars(conn, [("SPY", "2026-08-26T13:55:00Z",
                              750.0, 751.0, 749.0, 750.0, 1000)])

    result = await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                            underlyings={"SPY": 750.0}, equity=100_000,
                            day_start=100_000, peak=100_000,
                            halt_file=tmp_path / "HALT")

    assert result["halted"] and "stale" in result["halt_reason"]
    assert len(result["exits"]) == 1
    assert result["entries"] == []


async def test_exit_signals_are_submitted_as_sell_orders(conn, tmp_path):
    open_a_losing_position(conn)
    broker = FakeBroker()

    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   quotes=EXIT_QUOTES)

    assert len(broker.orders) == 1
    order, dry_run = broker.orders[0]
    assert order["side"] == "sell"
    assert order["qty"] == "7"
    assert dry_run is True
    # Stop-out sells at the live bid, not a limit near entry ($2.00).
    assert float(order["limit_price"]) == pytest.approx(1.18)


async def test_dry_run_is_the_default_for_the_tick(conn, tmp_path):
    open_a_losing_position(conn)
    broker = FakeBroker()
    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   quotes=EXIT_QUOTES)
    assert broker.orders[0][1] is True


async def test_closing_a_position_marks_it_closed_in_the_store(conn, tmp_path):
    open_a_losing_position(conn)
    await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   dry_run=False, quotes=EXIT_QUOTES)
    assert store.open_positions(conn) == []


async def test_dry_run_does_not_mutate_position_state(conn, tmp_path):
    # A simulated exit must not look like a real one in the database.
    open_a_losing_position(conn)
    await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   dry_run=True, quotes=EXIT_QUOTES)
    assert len(store.open_positions(conn)) == 1


async def test_exit_without_a_live_quote_does_not_sell_at_entry_price(conn, tmp_path):
    """NVDA live: missing premiums priced the sell at $7.50 (entry) after the
    option had already collapsed. That order cannot fill. No quote → no order.
    """
    open_a_losing_position(conn)
    broker = FakeBroker()
    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   dry_run=False)
    assert broker.orders == []
    assert len(store.open_positions(conn)) == 1
    logged = store.recent_decisions(conn)
    assert any(d["action"] == "exit_failed" and "no_quote" in d["detail"] for d in logged)


async def test_forced_exit_with_no_quote_tries_a_penny_floor_instead_of_giving_up(
    conn, tmp_path
):
    """A discretionary exit with no quote should skip (existing behavior,
    covered above). A forced one - DTE cliff or competition end - cannot: the
    position rides all the way to expiry/auto-exercise if it just keeps
    skipping forever. Resting a sell at a one-cent floor still never invents
    a value, but gives a stuck illiquid contract a chance to actually close.
    """
    store.open_position(conn, symbol="SPY260827C00765000",
                        entry_ts="2026-08-24T14:05:00Z",
                        **{**BASE, "expiry": "2026-08-27"})  # dte 1, forced
    broker = FakeBroker()
    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   dry_run=False)

    assert len(broker.orders) == 1
    order, dry_run = broker.orders[0]
    assert order["side"] == "sell"
    assert float(order["limit_price"]) == pytest.approx(0.01)
    assert store.open_positions(conn) == []  # FakeBroker fills it


async def test_premium_target_exits_when_underlying_has_not_hit_target(conn, tmp_path):
    """+80% premium take-profit must work once live quotes are wired — this is
    how equity can be locked without waiting for the underlying target.
    """
    store.open_position(conn, symbol="SPY260911C00765000",
                        entry_ts="2026-08-24T14:05:00Z", **BASE)
    broker = FakeBroker()
    quotes = {"SPY260911C00765000": (3.70, 3.80)}  # mid 3.75 = +87.5% vs $2 entry
    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 767.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   quotes=quotes, dry_run=False)
    assert store.open_positions(conn) == []
    assert broker.orders[0][0]["side"] == "sell"
    assert float(broker.orders[0][0]["limit_price"]) == pytest.approx(3.70)


async def test_no_exit_order_after_the_options_close(conn, tmp_path):
    open_a_losing_position(conn)
    broker = FakeBroker()
    # 20:30 UTC = 16:30 ET in August — options session is closed.
    await run.tick(conn, broker, now_utc="2026-08-26T20:30:00Z", today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   quotes=EXIT_QUOTES, dry_run=False)
    assert broker.orders == []
    assert len(store.open_positions(conn)) == 1
    logged = store.recent_decisions(conn)
    assert any(d["action"] == "exit_failed" and "session" in d["detail"] for d in logged)


async def test_option_quotes_sends_the_plural_symbols_param_in_one_call(monkeypatch):
    """The live MCP server rejects {"symbol": ...} and {"option_symbol": ...}
    with a 400 - only {"symbols": "a,b,..."} is accepted (verified against the
    real tool schema 2026-08-31). One call for every open position, not one
    call per position.
    """
    seen_calls = []

    async def fake_call(sess, name, args):
        seen_calls.append((name, args))
        return {"quotes": {
            "SPY260911C00765000": {"bp": 1.18, "ap": 1.22},
            "AAPL260911P00200000": {"bp": 0.0, "ap": 0.0},  # dead book
        }}

    import agent.mcp_bridge as mcp_bridge_module
    monkeypatch.setattr(mcp_bridge_module, "call", fake_call)

    result = await run._option_quotes(
        object(), ["SPY260911C00765000", "AAPL260911P00200000", "MSFT260911C00500000"]
    )

    assert len(seen_calls) == 1
    name, args = seen_calls[0]
    assert name == "get_option_latest_quote"
    assert args == {"symbols": "SPY260911C00765000,AAPL260911P00200000,MSFT260911C00500000"}
    assert result == {"SPY260911C00765000": (1.18, 1.22)}  # dead book and missing symbol omitted


def test_pick_contract_targets_the_middle_of_the_delta_band():
    from agent import gates

    def snap(delta, bid=1.60, ask=1.63):
        return {"greeks": {"delta": delta}, "impliedVolatility": 0.1,
                "latestQuote": {"bp": bid, "ap": ask},
                "dailyBar": {"v": 900}, "prevDailyBar": {"v": 5180}}

    chain = gates.parse_chain({"snapshots": {
        "SPY260904C00760000": snap(0.54),
        "SPY260904C00765000": snap(0.45),
        "SPY260904C00770000": snap(0.36),
    }})
    assert run.pick_contract(chain, TODAY).strike == 765.0


def test_pick_contract_returns_none_when_nothing_is_viable():
    from agent import gates

    chain = gates.parse_chain({"snapshots": {"SPY260904C00765000": {
        "greeks": {"delta": 0.45}, "impliedVolatility": 0.1,
        "latestQuote": {"bp": 1.60, "ap": 1.63},
        "dailyBar": {"v": 1}, "prevDailyBar": {"v": 2},   # illiquid
    }}})
    assert run.pick_contract(chain, TODAY) is None


# --- the decide() integration -----------------------------------------------
#
# The entry path (screener -> chain -> contract selection -> gates -> order)
# had no coverage through tick() even before decide() was wired in - only
# pick_contract() itself was unit-tested in isolation. screener.scan is
# monkeypatched so these tests don't need realistic multi-session bar data to
# trigger a real screener signal; everything downstream of the candidate is
# exercised for real.

OPTION_SYMBOL = "SPY260911C00765000"


def option_snap(delta=0.45, bid=1.60, ask=1.63, prev_vol=5000):
    return {"greeks": {"delta": delta}, "impliedVolatility": 0.12,
           "latestQuote": {"bp": bid, "ap": ask},
           "dailyBar": {"v": 900}, "prevDailyBar": {"v": prev_vol}}


def a_candidate():
    return screener.Candidate(symbol="SPY", direction="call", ts_utc=NOW,
                              price=765.0, session_open=760.0, adr=5.0,
                              move_adr=1.0, rvol=2.0, ema=762.0)


class FakeDecideClient:
    """Stands in for the anthropic client decide.decide() calls."""

    def __init__(self, action, symbol=None, confidence=0.7, thesis="because"):
        self.action, self.symbol = action, symbol
        self.confidence, self.thesis = confidence, thesis
        self.calls = []

        class Messages:
            def create(_self, **kwargs):
                self.calls.append(kwargs)
                block = type("Block", (), {"type": "tool_use", "input": {
                    "action": self.action, "symbol": self.symbol or "none",
                    "confidence": self.confidence, "thesis": self.thesis}})()
                return type("Resp", (), {"stop_reason": "tool_use",
                                         "content": [block]})()

        self.messages = Messages()


async def test_tick_enters_via_decide_when_a_client_is_given(conn, tmp_path, monkeypatch):
    seed_fresh_bars(conn)
    monkeypatch.setattr(screener, "scan", lambda *a, **kw: [a_candidate()])
    broker = FakeBroker(chain={"snapshots": {OPTION_SYMBOL: option_snap()}})
    client = FakeDecideClient(action="enter", symbol=OPTION_SYMBOL, thesis="strong setup")

    result = await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                            underlyings={}, equity=100_000, day_start=100_000,
                            peak=100_000, halt_file=tmp_path / "HALT",
                            decide_client=client)

    assert len(result["entries"]) == 1
    assert client.calls, "decide.decide() must actually call the client"
    order, dry_run = broker.orders[0]
    assert order["side"] == "buy" and order["symbol"] == OPTION_SYMBOL
    logged = store.recent_decisions(conn)
    assert any(d["action"] == "entry" and d["thesis"] == "strong setup" for d in logged)


async def test_tick_records_a_skip_from_decide_and_places_no_order(conn, tmp_path, monkeypatch):
    seed_fresh_bars(conn)
    monkeypatch.setattr(screener, "scan", lambda *a, **kw: [a_candidate()])
    broker = FakeBroker(chain={"snapshots": {OPTION_SYMBOL: option_snap()}})
    client = FakeDecideClient(action="skip", thesis="not convinced")

    result = await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                            underlyings={}, equity=100_000, day_start=100_000,
                            peak=100_000, halt_file=tmp_path / "HALT",
                            decide_client=client)

    assert result["entries"] == []
    assert broker.orders == []
    logged = store.recent_decisions(conn)
    assert any(d["action"] == "skip" and d["thesis"] == "not convinced" for d in logged)


async def test_tick_falls_back_to_pick_contract_without_a_decide_client(conn, tmp_path, monkeypatch):
    seed_fresh_bars(conn)
    monkeypatch.setattr(screener, "scan", lambda *a, **kw: [a_candidate()])
    broker = FakeBroker(chain={"snapshots": {OPTION_SYMBOL: option_snap()}})

    result = await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                            underlyings={}, equity=100_000, day_start=100_000,
                            peak=100_000, halt_file=tmp_path / "HALT")

    assert len(result["entries"]) == 1
    order, _ = broker.orders[0]
    assert order["symbol"] == OPTION_SYMBOL


async def test_tick_still_respects_gates_when_decide_says_enter(conn, tmp_path, monkeypatch):
    # decide() only ever offers contracts that already passed gates.viable(),
    # so it cannot choose an illiquid one - approve() re-checks viability too,
    # covering that case. What it can still catch is a contract sizing to zero
    # (too expensive for the position budget), which viable() does not check.
    seed_fresh_bars(conn)
    monkeypatch.setattr(screener, "scan", lambda *a, **kw: [a_candidate()])
    expensive = {OPTION_SYMBOL: option_snap(bid=24.50, ask=25.00)}
    broker = FakeBroker(chain={"snapshots": expensive})
    client = FakeDecideClient(action="enter", symbol=OPTION_SYMBOL)

    result = await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                            underlyings={}, equity=100_000, day_start=100_000,
                            peak=100_000, halt_file=tmp_path / "HALT",
                            decide_client=client)

    assert result["entries"] == []
    assert broker.orders == []
    logged = store.recent_decisions(conn)
    assert any(d["action"] == "rejected" and "quantity" in d["detail"] for d in logged)


class UnfilledBroker(FakeBroker):
    async def place(self, order, dry_run=True, contract=None, ts_utc=None, **kw):
        self.orders.append((order, dry_run))
        if dry_run:
            return {"dry_run": True, "status": "simulated", "order": order}
        return {"dry_run": False, "status": "abandoned", "order": order}


async def test_live_entry_is_logged_only_after_a_fill(conn, tmp_path, monkeypatch):
    seed_fresh_bars(conn)
    monkeypatch.setattr(screener, "scan", lambda *a, **kw: [a_candidate()])
    broker = FakeBroker(chain={"snapshots": {OPTION_SYMBOL: option_snap()}})

    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={}, equity=100_000, day_start=100_000,
                   peak=100_000, halt_file=tmp_path / "HALT", dry_run=False)

    logged = store.recent_decisions(conn)
    assert any(d["action"] == "entry" for d in logged)
    assert len(store.open_positions(conn)) == 1


async def test_live_unfilled_order_does_not_log_entry_or_open_a_position(
        conn, tmp_path, monkeypatch):
    # Live today: AAPL was logged as "entry" even though the limit never filled.
    # The decision log must only say entry when money actually moved.
    seed_fresh_bars(conn)
    monkeypatch.setattr(screener, "scan", lambda *a, **kw: [a_candidate()])
    broker = UnfilledBroker(chain={"snapshots": {OPTION_SYMBOL: option_snap()}})

    result = await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                            underlyings={}, equity=100_000, day_start=100_000,
                            peak=100_000, halt_file=tmp_path / "HALT",
                            dry_run=False)

    assert result["entries"] == []
    assert store.open_positions(conn) == []
    logged = store.recent_decisions(conn)
    assert not any(d["action"] == "entry" for d in logged)
    assert any(d["action"] == "abandoned" for d in logged)


class AbandonedWithAttemptsBroker(FakeBroker):
    """Both order attempts time out and get canceled - matches what
    execute.submit() actually returns when neither fill."""

    async def place(self, order, dry_run=True, contract=None, ts_utc=None, **kw):
        self.orders.append((order, dry_run))
        if dry_run:
            return {"dry_run": True, "status": "simulated", "order": order}
        return {"dry_run": False, "status": "abandoned", "order": order,
               "attempts": [
                   {"client_order_id": order["client_order_id"],
                    "limit_price": order["limit_price"], "status": "unfilled"},
                   {"client_order_id": order["client_order_id"] + "-r",
                    "limit_price": str(float(order["limit_price"]) + 0.01),
                    "status": "unfilled"},
               ]}


class FilledOnRetryBroker(FakeBroker):
    """One call to place() - the retry happens inside execute.submit() itself,
    invisible to run.py - returning the shape submit() actually returns when
    the first attempt times out and the retry fills."""

    async def place(self, order, dry_run=True, contract=None, ts_utc=None, **kw):
        self.orders.append((order, dry_run))
        if dry_run:
            return {"dry_run": True, "status": "simulated", "order": order}
        return {"dry_run": False, "status": "filled",
               "fill_price": float(order["limit_price"]),
               "attempts": [
                   {"client_order_id": order["client_order_id"],
                    "limit_price": order["limit_price"], "status": "unfilled"},
                   {"client_order_id": order["client_order_id"] + "-r",
                    "limit_price": str(float(order["limit_price"]) + 0.01),
                    "status": "filled"},
               ]}


async def test_live_abandoned_entry_logs_every_canceled_attempt(
        conn, tmp_path, monkeypatch):
    # Live: the AAPL retry the night of 2026-08-26 canceled once and retried
    # once, and none of that lifecycle showed up anywhere the dashboard could
    # show it - only the original entry intent. Both attempts must be visible,
    # and distinctly (not one silently overwriting the other - see the
    # (ts_utc, symbol, action) primary key collision this guards against).
    seed_fresh_bars(conn)
    monkeypatch.setattr(screener, "scan", lambda *a, **kw: [a_candidate()])
    broker = AbandonedWithAttemptsBroker(
        chain={"snapshots": {OPTION_SYMBOL: option_snap()}})

    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={}, equity=100_000, day_start=100_000,
                   peak=100_000, halt_file=tmp_path / "HALT", dry_run=False)

    logged = store.recent_decisions(conn)
    canceled = [d for d in logged if d["action"] == "canceled"]
    assert len(canceled) == 2, "both failed attempts must be logged, not just one"
    assert canceled[0]["detail"] != canceled[1]["detail"]
    assert any(d["action"] == "abandoned" for d in logged)


async def test_live_fill_on_retry_still_logs_the_canceled_first_attempt(
        conn, tmp_path, monkeypatch):
    # A successful retry must not hide that the first attempt failed - a
    # trade that took two tries to place is worth knowing about even when it
    # eventually worked.
    seed_fresh_bars(conn)
    monkeypatch.setattr(screener, "scan", lambda *a, **kw: [a_candidate()])
    broker = FilledOnRetryBroker(
        chain={"snapshots": {OPTION_SYMBOL: option_snap()}})

    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={}, equity=100_000, day_start=100_000,
                   peak=100_000, halt_file=tmp_path / "HALT", dry_run=False)

    logged = store.recent_decisions(conn)
    assert any(d["action"] == "canceled" for d in logged)
    assert any(d["action"] == "entry" for d in logged)
    assert len(store.open_positions(conn)) == 1


# --- partial fill whose remainder gets canceled ------------------------------
#
# execute.submit() can report status "filled" with a filled_qty smaller than
# the order actually requested - a broker that fills 4 of 7 and cancels the
# rest. The requested qty and the actual qty must never be conflated: opening
# a position sized at the request, when only part of it filled, records
# contracts the account does not hold.

class PartialFillEntryBroker(FakeBroker):
    """Fills fewer contracts than requested; remainder was canceled upstream."""

    def __init__(self, filled_qty, chain=None):
        super().__init__(chain)
        self.filled_qty = filled_qty

    async def place(self, order, dry_run=True, contract=None, ts_utc=None, **kw):
        self.orders.append((order, dry_run))
        if dry_run:
            return {"dry_run": True, "status": "simulated", "order": order}
        return {"dry_run": False, "status": "filled",
               "fill_price": float(order["limit_price"]),
               "filled_qty": self.filled_qty}


async def test_live_partial_fill_entry_records_the_actual_filled_qty(
        conn, tmp_path, monkeypatch):
    seed_fresh_bars(conn)
    monkeypatch.setattr(screener, "scan", lambda *a, **kw: [a_candidate()])
    broker = PartialFillEntryBroker(
        filled_qty=4, chain={"snapshots": {OPTION_SYMBOL: option_snap()}})

    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={}, equity=100_000, day_start=100_000,
                   peak=100_000, halt_file=tmp_path / "HALT", dry_run=False)

    positions = store.open_positions(conn)
    assert len(positions) == 1
    requested_qty = int(broker.orders[0][0]["qty"])
    assert requested_qty > 4, "test is only meaningful if the fill was partial"
    assert positions[0]["qty"] == 4


class PartialFillExitBroker(FakeBroker):
    """Sells fewer contracts than the position holds; remainder was canceled."""

    def __init__(self, filled_qty, chain=None):
        super().__init__(chain)
        self.filled_qty = filled_qty

    async def place(self, order, dry_run=True, contract=None, ts_utc=None, **kw):
        self.orders.append((order, dry_run))
        if dry_run:
            return {"dry_run": True, "status": "simulated", "order": order}
        return {"dry_run": False, "status": "filled",
               "fill_price": float(order["limit_price"]),
               "filled_qty": self.filled_qty}


async def test_live_partial_fill_exit_is_not_silently_marked_a_clean_close(
        conn, tmp_path):
    # BASE opens 7 contracts; only part of the stop-out actually sells before
    # the remainder is canceled. The row still closes locally (closing beats
    # leaving exits.scan() re-selling the ORIGINAL qty next tick, which the
    # broker no longer fully holds - reconcile() picks up any true remainder
    # at next boot), but the record must say it was partial, not clean.
    open_a_losing_position(conn)
    broker = PartialFillExitBroker(filled_qty=3)

    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   dry_run=False, quotes=EXIT_QUOTES)

    assert store.open_positions(conn) == []
    closed = store.closed_positions(conn)
    assert len(closed) == 1
    assert "3" in closed[0]["exit_reason"] and "7" in closed[0]["exit_reason"]


# --- session bounds persist across a restart --------------------------------
#
# loop() used to set day_start = peak = equity fresh on every process boot.
# That quietly resets both the daily-loss and drawdown baselines whenever the
# process restarts mid-session - a crash, a deploy, or deliberately switching
# decide_client on or off, as tonight's launch plan does.

def test_entry_levels_use_4h_alert_range_when_available():
    c = screener.Candidate(
        symbol="SPY", direction="call", ts_utc="2026-08-24T18:00:00Z",
        price=105.0, session_open=100.0, adr=10.0, move_adr=0.8, rvol=2.0,
        ema=104.0, alert_high=108.0, alert_low=100.0,
    )
    stop, target = run._entry_levels(c)
    assert stop == 100.0
    assert target == pytest.approx(115.0)


def test_session_bounds_use_current_equity_with_no_history(conn):
    day_start, peak = run._session_bounds(conn, current_equity=100_000, today=TODAY)
    assert day_start == 100_000 and peak == 100_000


def test_session_bounds_recover_todays_opening_equity_after_a_restart(conn):
    store.record_equity(conn, f"{TODAY}T13:30:00Z", 100_000)
    store.record_equity(conn, f"{TODAY}T15:00:00Z", 101_800)
    store.record_equity(conn, f"{TODAY}T16:45:00Z", 99_200)   # equity at "restart"

    day_start, peak = run._session_bounds(conn, current_equity=99_200, today=TODAY)
    assert day_start == 100_000          # today's first snapshot, not the restart value
    assert peak == 101_800               # the running high, not the restart value


def test_session_bounds_ignore_a_prior_days_equity(conn):
    store.record_equity(conn, "2026-08-25T13:30:00Z", 100_000)
    store.record_equity(conn, "2026-08-25T20:00:00Z", 97_000)

    day_start, peak = run._session_bounds(conn, current_equity=97_500, today=TODAY)
    assert day_start == 97_500           # no snapshot for TODAY yet -> use current
    assert peak == 100_000               # all-time peak still carries forward


def test_session_bounds_peak_never_falls_below_current_equity(conn):
    # A fresh all-time high must count even if no history row reflects it yet.
    store.record_equity(conn, f"{TODAY}T13:30:00Z", 100_000)
    day_start, peak = run._session_bounds(conn, current_equity=103_000, today=TODAY)
    assert peak == 103_000
