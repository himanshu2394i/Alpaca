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

from agent import config, decide, exits, execute, gates, reconcile, screener, store
from agent.indicators import _is_rth

log = logging.getLogger(__name__)

DELTA_TARGET = 0.45          # middle of the gates' 0.35-0.55 band
CHAIN_STRIKE_WINDOW = 0.10   # fetch strikes within +/-10% of spot


def _log_attempts(conn, now_utc: str, symbol: str, result: dict) -> None:
    """Record every non-final order attempt in the decision log.

    Live: the AAPL order the night of 2026-08-26 canceled once and retried
    once, and none of that was visible on the dashboard afterward - only the
    original entry intent line, with the actual outcome only recoverable by
    cross-referencing the broker's own order history directly. A "filled"
    attempt is not logged here since the caller already logs "entry"/the exit
    close for that case; this only fills in the intermediate steps.

    Offsets each row's timestamp by one second per attempt: `decisions`'
    primary key is (ts_utc, symbol, action), and two failed attempts for the
    same symbol in the same tick both being "canceled" would otherwise share
    a key and silently overwrite each other via INSERT OR REPLACE - exactly
    the kind of quiet data loss this whole task exists to eliminate.
    """
    from datetime import datetime, timedelta, timezone

    base = datetime.strptime(now_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    logged = 0
    for attempt in result.get("attempts", []):
        status = attempt.get("status")
        if status == "unfilled":
            action, verb = "canceled", "unfilled, canceled"
        elif status == "rejected":
            action, verb = "broker_rejected", "rejected by broker"
        else:
            continue
        ts = (base + timedelta(seconds=logged)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.record_decision(
            conn, ts, symbol, action,
            f"{attempt['client_order_id']} @ {attempt['limit_price']} {verb}")
        logged += 1


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
    quotes: dict[str, tuple[float, float]] | None = None,
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
    premiums = dict(premiums or {})
    quotes = dict(quotes or {})
    for occ, (bid, ask) in quotes.items():
        premiums[occ] = (bid + ask) / 2.0
    symbols = symbols or config.UNIVERSE

    halt_reason = None
    if Path(halt_file).exists():
        halt_reason = f"{halt_file} present"
    else:
        halt_reason = gates.halt_reason(equity, day_start, peak)
        if halt_reason is None:
            halt_reason = gates.data_stale_reason(store.newest_bar_ts(conn), now_utc)

    # --- exits first, and regardless of any halt --------------------------
    exit_signals = exits.scan(conn, underlyings, premiums, today)
    for signal in exit_signals:
        position = next(p for p in store.open_positions(conn)
                        if p["symbol"] == signal.symbol)
        log.info("EXIT %s: %s", signal.symbol, signal.reason)
        store.record_decision(conn, now_utc, signal.symbol, "exit", signal.reason)

        if not _is_rth(now_utc):
            store.record_decision(conn, now_utc, signal.symbol, "exit_failed",
                                  "session closed; options not trading")
            log.warning("exit skipped (session closed) for %s", signal.symbol)
            continue

        quote = quotes.get(signal.symbol)
        if quote is None and not signal.forced:
            store.record_decision(conn, now_utc, signal.symbol, "exit_failed",
                                  "no_quote; will not sell at entry price")
            log.warning("exit skipped (no_quote) for %s", signal.symbol)
            continue
        if quote is None:
            # Forced (DTE cliff / competition end): skipping forever means the
            # position rides to expiry untouched. A resting sell at a one-cent
            # floor never invents a value - it only fills against a real buyer -
            # but unlike skipping, it gives a stuck illiquid contract a chance
            # to actually close instead of waiting on auto-exercise/expiration.
            quote = (0.01, 0.01)
            log.warning("forced exit with no quote for %s, trying $0.01 floor",
                        signal.symbol)

        bid, ask = quote
        contract = _contract_for_exit(position, bid, ask)
        # Sell at the live bid so a stop-out can actually fill (NVDA 2026-08-28).
        order = execute.build_order(contract, signal.qty, "sell", now_utc,
                                    retry=True)
        result = await broker.place(order, dry_run=dry_run, contract=contract,
                                  ts_utc=now_utc, aggressive=True)
        if not dry_run:
            _log_attempts(conn, now_utc, signal.symbol, result)
        if not dry_run and result.get("status") == "filled":
            px = result.get("fill_price", contract.mid)
            store.close_position(conn, signal.symbol,
                                 exit_price=px, exit_ts=now_utc,
                                 exit_reason=signal.reason)
        elif not dry_run and result.get("status") != "filled":
            # Failing to close a position costs money, unlike failing to open
            # one - this must land in the decision log, not only a python
            # warning nobody reading the dashboard will ever see.
            store.record_decision(conn, now_utc, signal.symbol, "exit_failed",
                                  f"status={result.get('status')}", signal.reason)
            log.warning("exit not filled for %s: %s", signal.symbol,
                        result.get("status"))

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
        result = await broker.place(order, dry_run=dry_run, contract=contract,
                                    ts_utc=now_utc)
        if not dry_run:
            # Unconditional: a fill-on-retry still has a canceled first
            # attempt worth recording, not only the eventual "entry" row.
            _log_attempts(conn, now_utc, contract.symbol, result)
        status = result.get("status")
        detail = (f"{qty}x @ {contract.ask:.2f}, delta {contract.delta:.2f}")

        if dry_run or status == "filled":
            store.record_decision(conn, now_utc, contract.symbol, "entry",
                                  detail, thesis)
            entries.append((candidate, contract, qty))
            if not dry_run and status == "filled":
                fill_px = result.get("fill_price", contract.ask)
                stop, target = _entry_levels(candidate)
                store.open_position(
                    conn, symbol=contract.symbol, underlying=candidate.symbol,
                    right=candidate.direction, qty=qty, entry_price=fill_px,
                    entry_ts=now_utc, entry_underlying=candidate.price,
                    stop_underlying=stop, target_underlying=target,
                    expiry=contract.expiry,
                    thesis=thesis,
                )
        else:
            action = status if status in ("abandoned", "unfilled", "rejected") \
                else "unfilled"
            store.record_decision(conn, now_utc, contract.symbol, action,
                                  detail, thesis)
            log.warning("entry not filled for %s: %s", contract.symbol, status)

    return {"halted": False, "halt_reason": None,
            "exits": exit_signals, "entries": entries}


def _entry_levels(candidate) -> tuple[float, float]:
    """Stop/target for a new position.

    When the hybrid MTF filter supplied a 4H alert range, use alert low/high
    for a 1:2 reward-to-risk (cousin's rule). Otherwise fall back to ADR levels.
    """
    if candidate.direction == "call" and candidate.alert_low is not None:
        stop = candidate.alert_low
        risk = candidate.price - stop
        if risk > 0:
            return stop, candidate.price + 2 * risk
    if candidate.direction == "put" and candidate.alert_high is not None:
        stop = candidate.alert_high
        risk = stop - candidate.price
        if risk > 0:
            return stop, candidate.price - 2 * risk
    return exits.levels(candidate.price, candidate.adr, candidate.direction)


def _contract_for_exit(position, bid: float, ask: float) -> gates.Contract:
    """Contract for pricing an exit from a live two-sided quote.

    Never invents a market from entry_price. A collapsed option sold at
    yesterday's entry is unfillable; missing quotes are handled by the
    caller before this runs.
    """
    if bid <= 0 or ask <= 0:
        raise ValueError(f"exit quote must be two-sided, got bid={bid} ask={ask}")
    underlying, expiry, right, strike = gates.parse_occ(position["symbol"])
    return gates.Contract(
        symbol=position["symbol"], underlying=underlying, expiry=expiry,
        right=right, strike=strike,
        bid=float(bid), ask=float(ask),
        delta=0.0, iv=0.0, prev_volume=0, day_volume=0,
    )


def _et_hhmm(ts_utc: str) -> str:
    from datetime import datetime, timezone

    from agent.indicators import ET

    t = datetime.strptime(ts_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return t.astimezone(ET).strftime("%H:%M")


def _session_bounds(conn, current_equity: float, today: str) -> tuple[float, float]:
    """Day-start and all-time-peak equity, recovered from persisted history.

    loop() used to set both to current_equity fresh on every process boot.
    That silently resets the daily-loss and drawdown gates whenever the
    process restarts mid-session - a crash, a redeploy, or deliberately
    switching decide_client on or off, which is exactly what happens when
    flipping from a deterministic launch to the LLM partway through a day.
    """
    rows = store.equity_series(conn)
    if not rows:
        return current_equity, current_equity

    todays = [r for r in rows if r["ts_utc"][:10] == today]
    day_start = float(todays[0]["value"]) if todays else current_equity
    peak = max(max(float(r["value"]) for r in rows), current_equity)
    return day_start, peak


class MCPBroker:
    """Adapts the MCP session to the two calls tick() needs."""

    def __init__(self, sess):
        self.sess = sess

    async def fetch_chain(self, underlying, right, dte_lo, dte_hi, strike_lo, strike_hi):
        from agent import mcp_bridge
        return await mcp_bridge.fetch_chain(self.sess, underlying, right,
                                            dte_lo, dte_hi, strike_lo, strike_hi)

    async def place(self, order, dry_run=True, contract=None, ts_utc=None,
                    aggressive=False):
        return await execute.submit(self.sess, order, dry_run=dry_run,
                                    contract=contract, ts_utc=ts_utc,
                                    aggressive=aggressive)


async def _option_quotes(sess, symbols: list[str]) -> dict[str, tuple[float, float]]:
    """Live bid/ask for each OCC symbol, in one batched call.

    The tool's only accepted parameter is `symbols` (plural, comma-separated,
    up to 100) - verified against the live tool schema on 2026-08-31. Earlier
    per-symbol calls sent {"symbol": sym} / {"option_symbol": sym}, both of
    which the server rejects with a 400, so this had never actually returned a
    quote in production. The response nests results as {"quotes": {sym: {...}}},
    not at the top level, which is why each symbol's inner dict - not the
    envelope - gets handed to option_quote_bid_ask. Missing quotes are
    omitted, never faked.
    """
    from agent import mcp_bridge

    if not symbols:
        return {}

    try:
        raw = await mcp_bridge.call(sess, "get_option_latest_quote",
                                    {"symbols": ",".join(symbols)})
    except Exception:
        log.warning("option quote batch failed for %s", symbols, exc_info=True)
        return {}

    quotes = raw.get("quotes") if isinstance(raw, dict) else None
    if not isinstance(quotes, dict):
        log.warning("no quotes in option quote response for %s", symbols)
        return {}

    out: dict[str, tuple[float, float]] = {}
    for sym in symbols:
        parsed = mcp_bridge.option_quote_bid_ask(quotes.get(sym, {}))
        if parsed:
            out[sym] = parsed
        else:
            log.warning("no two-sided quote for %s", sym)
    return out


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
        boot_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        boot_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        day_start, peak = _session_bounds(conn, equity, boot_today)

        for note in await reconcile.reconcile(conn, sess, boot_now):
            log.warning("reconcile: %s", note)

        log.info("agent starting: equity %.2f, dry_run=%s, llm=%s, "
                 "day_start=%.2f, peak=%.2f",
                 equity, dry_run, decide_client is not None, day_start, peak)

        while True:
            now = datetime.now(timezone.utc)
            now_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            today = now_utc[:10]
            if today != boot_today:
                # Crossed a UTC date boundary since boot (overnight, between
                # sessions) - today's baseline resets, the all-time peak does not.
                day_start, boot_today = equity, today
            try:
                underlyings, equity = await _market_state(conn, sess, config.UNIVERSE)
                peak = max(peak, equity)
                store.record_equity(conn, now_utc, equity)

                occ = [p["symbol"] for p in store.open_positions(conn)]
                quotes = await _option_quotes(sess, occ) if occ else {}

                result = await tick(conn, broker, now_utc, today, underlyings,
                                    equity, day_start, peak, halt_file,
                                    quotes=quotes,
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
