import sqlite3

import pytest

from agent import store
from tests.helpers import make_bars


def test_upsert_and_read_back(conn):
    rows = make_bars(n=3)
    assert store.upsert_bars(conn, rows) == 3

    got = store.recent_bars(conn, "SPY")
    assert len(got) == 3
    assert [r["c"] for r in got] == [100.0, 101.0, 102.0]


def test_upsert_is_idempotent_on_replay(conn):
    rows = make_bars(n=3)
    store.upsert_bars(conn, rows)
    store.upsert_bars(conn, rows)

    assert len(store.recent_bars(conn, "SPY")) == 3


def test_upsert_overwrites_same_timestamp(conn):
    rows = make_bars(n=1)
    store.upsert_bars(conn, rows)

    symbol, ts, o, h, l, _c, v = rows[0]
    store.upsert_bars(conn, [(symbol, ts, o, h, l, 999.0, v)])

    got = store.recent_bars(conn, "SPY")
    assert len(got) == 1
    assert got[0]["c"] == 999.0


def test_recent_bars_returns_ascending_and_respects_limit(conn):
    store.upsert_bars(conn, make_bars(n=10))

    got = store.recent_bars(conn, "SPY", limit=3)
    assert len(got) == 3
    assert [r["c"] for r in got] == [107.0, 108.0, 109.0]


def test_recent_bars_isolates_symbols(conn):
    store.upsert_bars(conn, make_bars(symbol="SPY", n=3))
    store.upsert_bars(conn, make_bars(symbol="QQQ", n=5))

    assert len(store.recent_bars(conn, "SPY")) == 3
    assert len(store.recent_bars(conn, "QQQ")) == 5


def test_last_bar_ts(conn):
    assert store.last_bar_ts(conn, "SPY") is None

    store.upsert_bars(conn, make_bars(n=3))
    assert store.last_bar_ts(conn, "SPY") == "2026-08-24T13:32:00Z"


def test_newest_bar_ts_across_symbols(conn):
    assert store.newest_bar_ts(conn) is None
    store.upsert_bars(conn, make_bars("SPY", n=2))
    store.upsert_bars(conn, [
        ("QQQ", "2026-08-24T14:00:00Z", 400.0, 401.0, 399.0, 400.5, 2000),
    ])
    assert store.newest_bar_ts(conn) == "2026-08-24T14:00:00Z"


# --- positions --------------------------------------------------------------

POS = dict(
    symbol="SPY260904C00765000", underlying="SPY", right="call", qty=7,
    entry_price=1.62, entry_ts="2026-08-24T14:05:00Z", entry_underlying=765.55,
    stop_underlying=761.28, target_underlying=774.10, expiry="2026-09-04",
    thesis="momentum break with 2.2x volume",
)


def test_open_position_round_trips(conn):
    store.open_position(conn, **POS)
    got = store.open_positions(conn)
    assert len(got) == 1
    assert got[0]["symbol"] == "SPY260904C00765000"
    assert got[0]["qty"] == 7
    assert got[0]["entry_price"] == 1.62
    assert got[0]["thesis"] == "momentum break with 2.2x volume"


def test_open_positions_excludes_closed_ones(conn):
    store.open_position(conn, **POS)
    store.close_position(conn, POS["symbol"], exit_price=2.10,
                         exit_ts="2026-08-25T15:00:00Z", exit_reason="target hit")
    assert store.open_positions(conn) == []


def test_close_position_records_the_exit(conn):
    store.open_position(conn, **POS)
    store.close_position(conn, POS["symbol"], exit_price=2.10,
                         exit_ts="2026-08-25T15:00:00Z", exit_reason="target hit")
    row = conn.execute("SELECT * FROM positions WHERE symbol = ?",
                       (POS["symbol"],)).fetchone()
    assert row["status"] == "closed"
    assert row["exit_price"] == 2.10
    assert row["exit_reason"] == "target hit"


def test_reopening_the_same_contract_after_closing_is_allowed(conn):
    store.open_position(conn, **POS)
    store.close_position(conn, POS["symbol"], 2.10, "2026-08-25T15:00:00Z", "target")
    store.open_position(conn, **{**POS, "entry_ts": "2026-08-26T14:00:00Z"})
    assert len(store.open_positions(conn)) == 1


def test_cannot_open_the_same_contract_twice_while_it_is_open(conn):
    store.open_position(conn, **POS)
    with pytest.raises(ValueError):
        store.open_position(conn, **POS)


def test_open_positions_is_empty_on_a_fresh_database(conn):
    assert store.open_positions(conn) == []


def test_open_position_rejects_a_right_that_contradicts_the_symbol(conn):
    # A call stored as a put gets put-style inverted stop/target levels, so
    # every exit then fires on exactly the wrong move.
    with pytest.raises(ValueError, match="right"):
        store.open_position(conn, **{**POS, "symbol": "SPY260904C00765000",
                                     "right": "put"})


def test_open_position_rejects_a_symbol_it_cannot_parse(conn):
    with pytest.raises(ValueError):
        store.open_position(conn, **{**POS, "symbol": "NOTACONTRACT"})


def test_open_position_accepts_a_matching_put(conn):
    store.open_position(conn, **{**POS, "symbol": "SPY260904P00765000",
                                 "right": "put"})
    assert store.open_positions(conn)[0]["right"] == "put"


def test_upsert_bars_is_atomic_on_failure(conn):
    # A NULL ts_utc violates the PRIMARY KEY's NOT NULL constraint. If the
    # batch is written row-by-row under autocommit rather than as one
    # transaction, the two good rows land before the bad one fails, and the
    # caller is left with a partial write it never asked for.
    good = make_bars(n=2)
    bad = [("SPY", None, 1.0, 1.0, 1.0, 1.0, 100)]

    with pytest.raises(sqlite3.Error):
        store.upsert_bars(conn, good + bad)

    assert store.recent_bars(conn, "SPY") == []
