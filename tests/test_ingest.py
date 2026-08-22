from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from agent import ingest


def fake_bar(ts, **kw):
    return SimpleNamespace(
        symbol="SPY", timestamp=ts,
        open=kw.get("open", 1.0), high=kw.get("high", 2.0),
        low=kw.get("low", 0.5), close=kw.get("close", 1.5),
        volume=kw.get("volume", 100),
    )


def test_to_row_emits_the_store_tuple_order():
    ts = datetime(2026, 8, 24, 13, 30, tzinfo=timezone.utc)
    row = ingest._to_row("SPY", fake_bar(ts))
    assert row == ("SPY", "2026-08-24T13:30:00Z", 1.0, 2.0, 0.5, 1.5, 100)


def test_to_row_converts_non_utc_timestamps_to_utc():
    eastern = timezone(timedelta(hours=-4))  # 09:30 ET == 13:30 UTC
    ts = datetime(2026, 8, 24, 9, 30, tzinfo=eastern)
    row = ingest._to_row("SPY", fake_bar(ts))
    assert row[1] == "2026-08-24T13:30:00Z"


def test_to_row_coerces_types():
    # Alpaca returns Decimal for prices and may return float volume.
    from decimal import Decimal

    ts = datetime(2026, 8, 24, 13, 30, tzinfo=timezone.utc)
    bar = fake_bar(ts, open=Decimal("1.25"), volume=100.0)
    row = ingest._to_row("SPY", bar)
    assert isinstance(row[2], float) and row[2] == 1.25
    assert isinstance(row[6], int) and row[6] == 100


def test_to_row_output_round_trips_through_the_store(conn):
    from agent import store

    ts = datetime(2026, 8, 24, 13, 30, tzinfo=timezone.utc)
    store.upsert_bars(conn, [ingest._to_row("SPY", fake_bar(ts))])

    got = store.recent_bars(conn, "SPY")
    assert len(got) == 1
    assert got[0]["c"] == 1.5
    assert store.last_bar_ts(conn, "SPY") == "2026-08-24T13:30:00Z"
