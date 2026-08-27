"""Boot reconciliation between SQLite and Alpaca."""
import pytest

from agent import reconcile, store


NOW = "2026-08-26T14:00:00Z"
SYM = "SPY260904C00765000"


class FakeSession:
    def __init__(self, positions):
        self.positions = positions
        self.calls = []

    async def call_tool(self, name, args):
        import json
        self.calls.append((name, args))
        if name == "get_all_positions":
            data = {"positions": self.positions}
        else:
            raise AssertionError(name)
        return type("R", (), {"content": [type("C", (), {"text": json.dumps(data)})()]})()


@pytest.mark.asyncio
async def test_reconcile_closes_a_local_position_missing_at_the_broker(conn):
    # entry_ts is well outside GHOST_CLOSE_GRACE_MINUTES so this exercises the
    # true-orphan path, not the grace window (see test_reconcile_grants_a_
    # grace_window_for_a_very_recent_entry for that case).
    store.open_position(
        conn, symbol=SYM, underlying="SPY", right="call", qty=2,
        entry_price=2.0, entry_ts="2026-08-26T13:00:00Z", entry_underlying=765.0,
        stop_underlying=760.0, target_underlying=775.0, expiry="2026-09-04",
    )
    sess = FakeSession([])

    notes = await reconcile.reconcile(conn, sess, NOW)

    assert store.open_positions(conn) == []
    assert any("ghost" in n for n in notes)


@pytest.mark.asyncio
async def test_reconcile_grants_a_grace_window_for_a_very_recent_entry(conn):
    # Live: MSFT filled at 18:26:46 and reconcile ran 44s later and still
    # ghost-closed it - the broker's position snapshot can lag a genuine fill.
    now = "2026-08-26T14:00:30Z"
    entry_ts = "2026-08-26T14:00:00Z"   # 30 seconds before `now`
    store.open_position(
        conn, symbol=SYM, underlying="SPY", right="call", qty=2,
        entry_price=2.0, entry_ts=entry_ts, entry_underlying=765.0,
        stop_underlying=760.0, target_underlying=775.0, expiry="2026-09-04",
    )

    notes = await reconcile.reconcile(conn, FakeSession([]), now)

    assert len(store.open_positions(conn)) == 1
    assert any("deferred" in n.lower() for n in notes)


async def test_reconcile_grace_window_expires(conn):
    # Same fixture shape as the grace-window test above, but `now` is past
    # GHOST_CLOSE_GRACE_MINUTES - proves the window is temporary protection,
    # not a permanent exemption for any position that happens to be recent.
    entry_ts = "2026-08-26T14:00:00Z"
    now = "2026-08-26T14:04:00Z"   # 4 minutes later, past the 3-minute grace
    assert 4 > reconcile.GHOST_CLOSE_GRACE_MINUTES
    store.open_position(
        conn, symbol=SYM, underlying="SPY", right="call", qty=2,
        entry_price=2.0, entry_ts=entry_ts, entry_underlying=765.0,
        stop_underlying=760.0, target_underlying=775.0, expiry="2026-09-04",
    )

    notes = await reconcile.reconcile(conn, FakeSession([]), now)

    assert store.open_positions(conn) == []
    assert any("ghost" in n for n in notes)


@pytest.mark.asyncio
async def test_reconcile_does_not_close_a_position_present_in_the_result_shape(conn):
    # Regression, at the reconcile() level rather than just the parser unit:
    # a position genuinely present in the live "result" shape must never be
    # closed as a ghost, independent of the grace window (entry is 4h old).
    store.open_position(
        conn, symbol="MSFT260918C00500000", underlying="MSFT", right="call",
        qty=1, entry_price=10.20, entry_ts="2026-08-26T10:00:00Z",
        entry_underlying=500.0, stop_underlying=490.0, target_underlying=520.0,
        expiry="2026-09-18",
    )

    class ResultSession(FakeSession):
        async def call_tool(self, name, args):
            import json
            self.calls.append((name, args))
            data = {"result": [{"symbol": "MSFT260918C00500000", "qty": "1",
                                "avg_entry_price": "10.2"}]}
            return type("R", (), {"content": [type("C", (), {
                "text": json.dumps(data)})()]})()

    notes = await reconcile.reconcile(conn, ResultSession([]), "2026-08-26T14:00:00Z")

    open_now = store.open_positions(conn)
    assert len(open_now) == 1 and open_now[0]["symbol"] == "MSFT260918C00500000"
    assert not any("ghost" in n for n in notes)


@pytest.mark.asyncio
async def test_reconcile_imports_a_broker_position_missing_locally(conn):
    sess = FakeSession([{
        "symbol": SYM, "qty": "3", "avg_entry_price": "2.10",
    }])
    store.upsert_bars(conn, [
        ("SPY", "2026-08-26T13:30:00Z", 765, 766, 764, 765.5, 1000),
        ("SPY", "2026-08-26T13:31:00Z", 765.5, 766, 765, 765.5, 1000),
    ])

    notes = await reconcile.reconcile(conn, sess, NOW)

    open_now = store.open_positions(conn)
    assert len(open_now) == 1
    assert open_now[0]["symbol"] == SYM
    assert open_now[0]["qty"] == 3
    assert any("imported" in n for n in notes)


def test_option_positions_reads_the_shape_the_mcp_server_actually_returns():
    # Captured verbatim from alpaca-mcp-server 3.4.7 get_all_positions.
    # The payload is keyed "result", not "positions" - the mock shape used by
    # the other tests in this file never occurs in production, so this parser
    # returned {} for every live call and reconcile() closed every real
    # position as a ghost.
    payload = {"result": [{
        "asset_id": "b1a79dd4-b409-4622-ae18-d3a96cb4b6cc",
        "symbol": "MSFT260918C00500000",
        "asset_class": "us_option",
        "qty": "1", "qty_available": "1",
        "avg_entry_price": "10.2", "side": "long",
        "market_value": "1090", "cost_basis": "1020",
        "unrealized_pl": "70", "current_price": "10.9",
    }]}

    found = reconcile._option_positions(payload)
    assert "MSFT260918C00500000" in found, "live broker position not seen"
    assert found["MSFT260918C00500000"]["qty"] == "1"


@pytest.mark.asyncio
async def test_reconcile_skips_ghost_closes_when_broker_payload_is_unusable(conn):
    # An error / malformed payload must not look like "broker has zero
    # positions" - that would wipe every real local row as a ghost.
    store.open_position(
        conn, symbol=SYM, underlying="SPY", right="call", qty=2,
        entry_price=2.0, entry_ts=NOW, entry_underlying=765.0,
        stop_underlying=760.0, target_underlying=775.0, expiry="2026-09-04",
    )

    class ErrSession(FakeSession):
        async def call_tool(self, name, args):
            import json
            self.calls.append((name, args))
            data = {"error": "upstream timeout"}
            return type("R", (), {"content": [type("C", (), {
                "text": json.dumps(data)})()]})()

    notes = await reconcile.reconcile(conn, ErrSession([]), NOW)

    assert len(store.open_positions(conn)) == 1
    assert any("skipped" in n.lower() or "unavailable" in n.lower() for n in notes)
