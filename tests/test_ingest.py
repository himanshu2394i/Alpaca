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


def test_fill_gap_pulls_bars_from_newest_stored_ts(conn, monkeypatch):
    from agent import store

    store.upsert_bars(conn, [
        ("SPY", "2026-08-26T14:00:00Z", 100.0, 101.0, 99.0, 100.5, 1000),
    ])

    captured = {}

    class FakeClient:
        def get_stock_bars(self, request):
            captured["start"] = request.start
            captured["end"] = request.end
            ts = datetime(2026, 8, 26, 14, 1, tzinfo=timezone.utc)
            return SimpleNamespace(data={"SPY": [fake_bar(ts, close=101.0)]})

    now = datetime(2026, 8, 26, 14, 5, tzinfo=timezone.utc)
    written = ingest.fill_gap(conn, ["SPY"], client=FakeClient(), now=now)

    assert written == 1
    # alpaca-py may normalize request.start to naive UTC
    assert captured["start"].replace(tzinfo=timezone.utc) == datetime(
        2026, 8, 26, 13, 59, tzinfo=timezone.utc)
    assert store.last_bar_ts(conn, "SPY") == "2026-08-26T14:01:00Z"


def test_fill_gap_uses_lookback_when_store_is_empty(conn):
    captured = {}

    class FakeClient:
        def get_stock_bars(self, request):
            captured["start"] = request.start
            return SimpleNamespace(data={})

    now = datetime(2026, 8, 26, 14, 5, tzinfo=timezone.utc)
    assert ingest.fill_gap(conn, ["SPY"], client=FakeClient(), now=now,
                           lookback_minutes=10) == 0
    assert captured["start"].replace(tzinfo=timezone.utc) == now - timedelta(minutes=10)


def test_universe_fits_the_free_tier_websocket_cap():
    # Alpaca's Basic plan caps unique streamed symbols. Exceeding it does not
    # degrade gracefully - the subscription is rejected and ingest goes dark.
    from agent import config

    assert len(config.UNIVERSE) <= config.MAX_WS_SYMBOLS
    assert len(set(config.UNIVERSE)) == len(config.UNIVERSE), "duplicate symbols"


def test_warm_start_backfills_enough_history_to_arm_the_mtf_filter():
    # mtf_confirm() fails OPEN when it lacks history, so too short a backfill
    # silently drops the 4H/15m confirmation instead of blocking the trade.
    from agent.indicators import MTF

    sessions = ingest.WARM_START_DAYS * 5 / 7          # calendar days -> sessions
    bars_15m = sessions * 26                            # 6.5h RTH / 15min
    bars_4h = sessions * 2

    assert bars_15m >= MTF["min_15m_bars"] * 1.5, (
        f"{ingest.WARM_START_DAYS}d yields ~{bars_15m:.0f} 15m bars, "
        f"need {MTF['min_15m_bars']} with margin"
    )
    assert bars_4h >= MTF["min_4h_bars"] * 1.5
