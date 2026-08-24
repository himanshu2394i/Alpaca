"""The agent loop: one tick wires screener, exits, gates and execution together.

Runs as its own process, separate from ingest. ingest.py owns the websocket and
writes `bars`; this process reads them and writes `positions`. Two processes
rather than the one the design assumed, because StockDataStream.run() owns its
own event loop - composing them would mean depending on a private API for no
gain, and independent restart is worth more than a shared process.

Ordering inside a tick is a safety property, not a style choice: exits are
processed before entries, and they run even when every entry path is halted.
"""
import logging
from pathlib import Path

from agent import config, decide, exits, execute, gates, screener, store

log = logging.getLogger(__name__)

DELTA_TARGET = 0.45          # middle of the gates' 0.35-0.55 band
CHAIN_STRIKE_WINDOW = 0.10   # fetch strikes within +/-10% of spot


def pick_contract(contracts, today: str, risk: dict = gates.RISK):
    """Choose the most standard viable contract: closest to mid-band delta.

    This is the deterministic fallback for decide(). It makes a defensible
    choice with no model in the loop, so the agent still functions when the
    LLM is unavailable - and so every other component can be tested without it.
    """
    viable = [c for c in contracts if gates.viable(c, today, risk) is None]
    if not viable:
        return None
    return min(viable, key=lambda c: abs(abs(c.delta) - DELTA_TARGET))


async def tick(
    conn,
    broker,
    now_utc: str,
    today: str,
    underlyings: dict[str, float],
    equity: float,
    day_start: float,
    peak: float,
    halt_file: Path,
    premiums: dict[str, float] | None = None,
    symbols=None,
    dry_run: bool = True,
    decide_client=None,
) -> dict:
    """One decision cycle. Returns what it did, for the decision log.

    `broker` needs `fetch_chain(...)` and `place(order, dry_run=...)`, which
    keeps this function testable without a live MCP session.

    `decide_client` is an anthropic client, or None. None means the LLM is out
    of the loop entirely and pick_contract() chooses deterministically - the
    agent stays fully functional, and every other component stays testable,
    with no model in the picture at all.
    """
    premiums = premiums or {}
    symbols = symbols or config.UNIVERSE

    halt_reason = None
    if Path(halt_file).exists():
        halt_reason = f"{halt_file} present"
    else:
        halt_reason = gates.halt_reason(equity, day_start, peak)

    # --- exits first, and regardless of any halt --------------------------
    exit_signals = exits.scan(conn, underlyings, premiums, today)
    for signal in exit_signals:
        position = next(p for p in store.open_positions(conn)
                        if p["symbol"] == signal.symbol)
        contract = _contract_for_exit(position, premiums.get(signal.symbol))
        order = execute.build_order(contract, signal.qty, "sell", now_utc)
        log.info("EXIT %s: %s", signal.symbol, signal.reason)
        store.record_decision(conn, now_utc, signal.symbol, "exit", signal.reason)
        await broker.place(order, dry_run=dry_run)
        if not dry_run:
            store.close_position(conn, signal.symbol,
                                 exit_price=contract.mid, exit_ts=now_utc,
                                 exit_reason=signal.reason)

    if halt_reason:
        log.warning("halted: %s (exits still active)", halt_reason)
        return {"halted": True, "halt_reason": halt_reason,
                "exits": exit_signals, "entries": []}

    # --- entries ----------------------------------------------------------
    open_now = store.open_positions(conn)
    state = screener.ThrottleState(
        last_entry={p["underlying"]: p["entry_ts"] for p in open_now},
        entries_today=sum(1 for p in open_now if p["entry_ts"][:10] == today),
        open_positions=len(open_now),
    )

    entries = []
    for candidate in screener.scan(conn, symbols, today, state):
        chain = await broker.fetch_chain(
            candidate.symbol, candidate.direction, *gates.RISK["dte_range"],
            candidate.price * (1 - CHAIN_STRIKE_WINDOW),
            candidate.price * (1 + CHAIN_STRIKE_WINDOW),
        )
        parsed = gates.parse_chain(chain)
        open_now2 = store.open_positions(conn)
        deployed = sum(p["entry_price"] * p["qty"] * gates.CONTRACT_MULTIPLIER
                       for p in open_now2)

        if decide_client is not None:
            viable = [c for c in parsed if gates.viable(c, today) is None]
            portfolio = {"equity": equity, "open_positions": len(open_now2),
                        "deployed": deployed}
            decision = decide.decide(decide_client, candidate, viable, portfolio, today)
            if decision.action != "enter" or decision.contract is None:
                log.info("model skipped %s: %s", candidate.symbol, decision.thesis)
                store.record_decision(conn, now_utc, candidate.symbol, "skip",
                                      f"confidence {decision.confidence:.2f}",
                                      decision.thesis)
                continue
            contract, thesis = decision.contract, decision.thesis
        else:
            contract = pick_contract(parsed, today)
            if contract is None:
                log.info("no viable contract for %s", candidate.symbol)
                store.record_decision(conn, now_utc, candidate.symbol, "no_contract",
                                      "no contract passed the gates")
                continue
            thesis = f"move {candidate.move_adr:+.2f} ADR, rvol {candidate.rvol:.2f}"

        qty = gates.size_contracts(equity, contract.ask)
        blocked = gates.approve(contract, qty, equity, deployed,
                                len(open_now2),
                                now_et=_et_hhmm(now_utc), today=today)
        if blocked:
            log.info("gate rejected %s: %s", contract.symbol, blocked)
            store.record_decision(conn, now_utc, contract.symbol, "rejected", blocked)
            continue

        order = execute.build_order(contract, qty, "buy", now_utc)
        store.record_decision(conn, now_utc, contract.symbol, "entry",
                              f"{qty}x @ {contract.ask:.2f}, delta {contract.delta:.2f}",
                              thesis)
        await broker.place(order, dry_run=dry_run)
        entries.append((candidate, contract, qty))

        if not dry_run:
            stop, target = exits.levels(candidate.price, candidate.adr,
                                        candidate.direction)
            store.open_position(
                conn, symbol=contract.symbol, underlying=candidate.symbol,
                right=candidate.direction, qty=qty, entry_price=contract.ask,
                entry_ts=now_utc, entry_underlying=candidate.price,
                stop_underlying=stop, target_underlying=target,
                expiry=contract.expiry,
                thesis=thesis,
            )

    return {"halted": False, "halt_reason": None,
            "exits": exit_signals, "entries": entries}


def _contract_for_exit(position, premium: float | None) -> gates.Contract:
    """Minimal Contract for pricing an exit.

    When the option has no quote, fall back to the entry price. The order is a
    limit either way - a stale limit that does not fill is recoverable, a
    market order into a wide spread is not.
    """
    px = premium if premium and premium > 0 else position["entry_price"]
    underlying, expiry, right, strike = gates.parse_occ(position["symbol"])
    return gates.Contract(
        symbol=position["symbol"], underlying=underlying, expiry=expiry,
        right=right, strike=strike,
        bid=round(px * 0.99, 2), ask=round(px * 1.01, 2),
        delta=0.0, iv=0.0, prev_volume=0, day_volume=0,
    )


def _et_hhmm(ts_utc: str) -> str:
    from datetime import datetime, timezone

    from agent.indicators import ET

    t = datetime.strptime(ts_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return t.astimezone(ET).strftime("%H:%M")


class MCPBroker:
    """Adapts the MCP session to the two calls tick() needs."""

    def __init__(self, sess):
        self.sess = sess

    async def fetch_chain(self, underlying, right, dte_lo, dte_hi, strike_lo, strike_hi):
        from agent import mcp_bridge
        return await mcp_bridge.fetch_chain(self.sess, underlying, right,
                                            dte_lo, dte_hi, strike_lo, strike_hi)

    async def place(self, order, dry_run=True):
        return await execute.submit(self.sess, order, dry_run=dry_run)


async def _market_state(conn, sess, symbols):
    """Latest underlying prices from the local bars, equity from the broker."""
    from agent import mcp_bridge

    underlyings = {}
    for symbol in symbols:
        rows = store.recent_bars(conn, symbol, limit=1)
        if rows:
            underlyings[symbol] = float(rows[0]["c"])

    account = await mcp_bridge.call(sess, "get_account_info", {})
    equity = float(account.get("equity", 0) or 0)
    return underlyings, equity


async def loop(dry_run: bool = True, interval: int = 60, decide_client=None) -> None:
    """Run ticks until interrupted.

    Dry run by default. Going live is an explicit act, never a default.

    `decide_client` is threaded straight through to tick() on every iteration -
    None disables the LLM, in which case pick_contract() decides deterministically.
    """
    import asyncio
    from datetime import datetime, timezone

    from agent import mcp_bridge

    conn = store.connect(config.DB_PATH)
    halt_file = config.ROOT / "HALT"

    async with mcp_bridge.session() as sess:
        broker = MCPBroker(sess)
        underlyings, equity = await _market_state(conn, sess, config.UNIVERSE)
        day_start = peak = equity
        log.info("agent starting: equity %.2f, dry_run=%s, llm=%s",
                 equity, dry_run, decide_client is not None)

        while True:
            now = datetime.now(timezone.utc)
            now_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            today = now_utc[:10]
            try:
                underlyings, equity = await _market_state(conn, sess, config.UNIVERSE)
                peak = max(peak, equity)
                store.record_equity(conn, now_utc, equity)

                result = await tick(conn, broker, now_utc, today, underlyings,
                                    equity, day_start, peak, halt_file,
                                    dry_run=dry_run, decide_client=decide_client)
                if result["exits"] or result["entries"]:
                    log.info("tick: %d exits, %d entries",
                             len(result["exits"]), len(result["entries"]))
            except Exception:
                # A bad tick must not kill the loop; the next one may succeed,
                # and a dead agent cannot close its open positions.
                log.exception("tick failed")

            await asyncio.sleep(interval)


def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Run the trading agent loop.")
    parser.add_argument("--live", action="store_true",
                        help="place real paper orders (default is dry run)")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--deterministic", action="store_true",
                        help="skip the LLM decision layer; use the mid-delta "
                             "fallback (no ANTHROPIC_API_KEY required)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    decide_client = None if args.deterministic else decide.make_client()
    asyncio.run(loop(dry_run=not args.live, interval=args.interval,
                     decide_client=decide_client))


if __name__ == "__main__":
    main()
