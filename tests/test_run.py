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


class FakeBroker:
    """Stands in for the MCP session; records what the tick tried to do."""

    def __init__(self, chain=None):
        self.orders, self.chain = [], chain or {"snapshots": {}}

    async def fetch_chain(self, *a, **kw):
        return self.chain

    async def place(self, order, dry_run=True, contract=None, ts_utc=None):
        self.orders.append((order, dry_run))
        if dry_run:
            return {"dry_run": True, "status": "simulated", "order": order}
        return {"dry_run": False, "status": "filled",
                "fill_price": float(order["limit_price"])}


def open_a_losing_position(conn):
    store.open_position(conn, symbol="SPY260911C00765000",
                        entry_ts="2026-08-24T14:05:00Z", **BASE)


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
    result = await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                            underlyings={}, equity=100_000, day_start=100_000,
                            peak=100_000, halt_file=tmp_path / "HALT")
    assert not result["halted"]
    assert result["halt_reason"] is None


async def test_exit_signals_are_submitted_as_sell_orders(conn, tmp_path):
    open_a_losing_position(conn)
    broker = FakeBroker()

    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT")

    assert len(broker.orders) == 1
    order, dry_run = broker.orders[0]
    assert order["side"] == "sell"
    assert order["qty"] == "7"
    assert dry_run is True


async def test_dry_run_is_the_default_for_the_tick(conn, tmp_path):
    open_a_losing_position(conn)
    broker = FakeBroker()
    await run.tick(conn, broker, now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT")
    assert broker.orders[0][1] is True


async def test_closing_a_position_marks_it_closed_in_the_store(conn, tmp_path):
    open_a_losing_position(conn)
    await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   dry_run=False)
    assert store.open_positions(conn) == []


async def test_dry_run_does_not_mutate_position_state(conn, tmp_path):
    # A simulated exit must not look like a real one in the database.
    open_a_losing_position(conn)
    await run.tick(conn, FakeBroker(), now_utc=NOW, today=TODAY,
                   underlyings={"SPY": 750.0}, equity=100_000,
                   day_start=100_000, peak=100_000, halt_file=tmp_path / "HALT",
                   dry_run=True)
    assert len(store.open_positions(conn)) == 1


# --- the fallback decision function ----------------------------------------

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
