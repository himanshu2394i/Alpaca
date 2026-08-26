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
    store.open_position(
        conn, symbol=SYM, underlying="SPY", right="call", qty=2,
        entry_price=2.0, entry_ts=NOW, entry_underlying=765.0,
        stop_underlying=760.0, target_underlying=775.0, expiry="2026-09-04",
    )
    sess = FakeSession([])

    notes = await reconcile.reconcile(conn, sess, NOW)

    assert store.open_positions(conn) == []
    assert any("ghost" in n for n in notes)


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
