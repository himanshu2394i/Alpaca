"""The orchestration tick.

The property that matters most: exits must survive every condition that stops
entries. Being unable to open a position costs an opportunity; being unable to
close one costs money.
"""
import pytest

from agent import exits, run, store

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

    async def place(self, order, dry_run=True):
        self.orders.append((order, dry_run))
        return {"status": "simulated", "dry_run": dry_run, "order": order}


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
