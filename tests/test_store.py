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
