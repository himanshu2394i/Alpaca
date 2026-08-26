"""Order construction, limit pricing, idempotency, and the dry-run guard."""
import pytest

from agent import execute, gates


def contract(bid=1.61, ask=1.63, symbol="SPY260904C00765000"):
    return gates.parse_chain({"snapshots": {symbol: {
        "greeks": {"delta": 0.45},
        "impliedVolatility": 0.10,
        "latestQuote": {"bp": bid, "ap": ask},
        "dailyBar": {"v": 1200}, "prevDailyBar": {"v": 5180},
    }}})[0]


TS = "2026-08-24T14:05:00Z"


# --- limit pricing ----------------------------------------------------------

def test_buy_limit_sits_above_mid_but_never_through_the_ask():
    c = contract(bid=1.00, ask=1.40)          # mid 1.20, half-spread 0.20
    px = execute.limit_price(c, "buy")
    assert px == pytest.approx(1.25)
    assert px <= c.ask


def test_sell_limit_sits_below_mid_but_never_through_the_bid():
    c = contract(bid=1.00, ask=1.40)
    px = execute.limit_price(c, "sell")
    assert px == pytest.approx(1.15)
    assert px >= c.bid


def test_limit_price_is_rounded_to_whole_cents():
    c = contract(bid=1.61, ask=1.63)          # mid 1.62, quarter half-spread 0.0025
    px = execute.limit_price(c, "buy")
    assert px == round(px, 2)
    assert c.bid <= px <= c.ask


def test_limit_price_is_clamped_inside_the_quote_after_rounding():
    # A one-cent market leaves no room; rounding must not push through either side.
    c = contract(bid=2.00, ask=2.01)
    assert c.bid <= execute.limit_price(c, "buy") <= c.ask
    assert c.bid <= execute.limit_price(c, "sell") <= c.ask


def test_retry_price_crosses_the_spread():
    c = contract(bid=1.00, ask=1.40)
    assert execute.limit_price(c, "buy", retry=True) == pytest.approx(1.40)
    assert execute.limit_price(c, "sell", retry=True) == pytest.approx(1.00)


def test_unknown_side_is_rejected():
    with pytest.raises(ValueError):
        execute.limit_price(contract(), "hold")


# --- idempotency ------------------------------------------------------------

def test_client_order_id_is_deterministic_for_the_same_trade():
    a = execute.client_order_id("SPY260904C00765000", "buy", TS)
    b = execute.client_order_id("SPY260904C00765000", "buy", TS)
    assert a == b


def test_client_order_id_differs_by_side_symbol_and_minute():
    base = execute.client_order_id("SPY260904C00765000", "buy", TS)
    assert base != execute.client_order_id("SPY260904C00765000", "sell", TS)
    assert base != execute.client_order_id("SPY260904C00770000", "buy", TS)
    assert base != execute.client_order_id("SPY260904C00765000", "buy",
                                           "2026-08-24T14:06:00Z")


def test_client_order_id_marks_retries():
    base = execute.client_order_id("SPY260904C00765000", "buy", TS)
    retry = execute.client_order_id("SPY260904C00765000", "buy", TS, retry=True)
    assert retry != base
    assert retry.endswith("-r")


def test_client_order_id_fits_alpaca_limits():
    cid = execute.client_order_id("GOOGL261218P00345000", "buy", TS)
    assert len(cid) <= 128 and cid.replace("-", "").isalnum()


# --- order construction -----------------------------------------------------

def test_build_order_serialises_every_numeric_field_as_a_string():
    # The MCP schema types qty and limit_price as strings; passing numbers is
    # how you get a silent validation failure at the worst possible moment.
    order = execute.build_order(contract(), qty=7, side="buy", ts_utc=TS)
    assert order["qty"] == "7"
    assert isinstance(order["limit_price"], str)
    assert float(order["limit_price"]) > 0


def test_build_order_sets_the_required_fields():
    order = execute.build_order(contract(), qty=7, side="buy", ts_utc=TS)
    assert order["symbol"] == "SPY260904C00765000"
    assert order["side"] == "buy"
    assert order["type"] == "limit"
    assert order["time_in_force"] == "day"
    assert order["client_order_id"] == execute.client_order_id(
        "SPY260904C00765000", "buy", TS)


def test_build_order_never_emits_a_market_order():
    order = execute.build_order(contract(), qty=7, side="buy", ts_utc=TS)
    assert order["type"] != "market"


def test_build_order_rejects_a_non_positive_quantity():
    with pytest.raises(ValueError):
        execute.build_order(contract(), qty=0, side="buy", ts_utc=TS)


# --- dry run ----------------------------------------------------------------

class RecordingSession:
    def __init__(self): self.calls = []
    async def call_tool(self, name, args):
        self.calls.append((name, args))
        raise AssertionError("dry run must not reach the network")


async def test_dry_run_never_calls_the_broker():
    sess = RecordingSession()
    result = await execute.submit(sess, execute.build_order(contract(), 7, "buy", TS),
                                  dry_run=True)
    assert sess.calls == []
    assert result["dry_run"] is True
    assert result["status"] == "simulated"


async def test_dry_run_is_the_default():
    sess = RecordingSession()
    await execute.submit(sess, execute.build_order(contract(), 7, "buy", TS))
    assert sess.calls == []


# --- fill polling -----------------------------------------------------------

class FakeMCP:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = []

    async def call_tool(self, name, args):
        import json
        self.calls.append((name, args))
        if name == "place_option_order":
            data = {"id": "ord-1", "status": "new",
                    "client_order_id": args["client_order_id"]}
        elif name == "get_order_by_client_id":
            status = self.statuses.pop(0) if self.statuses else "filled"
            data = {"id": "ord-1", "status": status, "filled_avg_price": "1.62",
                    "filled_qty": "7" if status in ("filled", "partially_filled")
                    else "0"}
        elif name == "cancel_order_by_id":
            data = {"id": args["order_id"], "status": "canceled"}
        else:
            raise AssertionError(f"unexpected tool {name}")
        return type("R", (), {"content": [type("C", (), {"text": json.dumps(data)})()]})()


async def test_submit_returns_filled_when_the_broker_fills():
    order = execute.build_order(contract(), 7, "buy", TS)
    sess = FakeMCP(["filled"])
    result = await execute.submit(sess, order, dry_run=False, contract=contract(),
                                  ts_utc=TS, poll_seconds=0.1, poll_interval=0.01)
    assert result["status"] == "filled"
    assert result["fill_price"] == pytest.approx(1.62)


async def test_submit_retries_once_at_the_ask_after_a_timeout():
    order = execute.build_order(contract(), 7, "buy", TS)
    # first order: never fills; retry order: fills immediately
    sess = FakeMCP(["new"] * 5 + ["filled"])
    result = await execute.submit(sess, order, dry_run=False, contract=contract(),
                                  ts_utc=TS, poll_seconds=0.05, poll_interval=0.01)
    assert result["status"] == "filled"
    placed = [c for c in sess.calls if c[0] == "place_option_order"]
    assert len(placed) == 2
    assert float(placed[1][1]["limit_price"]) == pytest.approx(1.63)
    assert "cancel_order_by_id" in [c[0] for c in sess.calls]


async def test_submit_abandons_when_both_attempts_fail():
    order = execute.build_order(contract(), 7, "buy", TS)
    sess = FakeMCP(["new"] * 20)
    result = await execute.submit(sess, order, dry_run=False, contract=contract(),
                                  ts_utc=TS, poll_seconds=0.05, poll_interval=0.01)
    assert result["status"] == "abandoned"


async def test_filled_status_with_zero_filled_qty_is_not_a_fill():
    # A "filled" row with no size must not open a local position - that is how
    # ghost positions appear after the next reconcile.
    assert execute.is_filled({"status": "filled", "filled_qty": "0",
                              "filled_avg_price": "1.62"}) is False
    assert execute.is_filled({"status": "filled", "filled_qty": "2",
                              "filled_avg_price": "1.62"}) is True
    assert execute.is_filled({"status": "partially_filled", "filled_qty": "1",
                              "filled_avg_price": "1.62"}) is True
