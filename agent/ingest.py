"""Market data ingestion: REST backfill on boot, then the live websocket.

This module deliberately contains no trading logic. It writes rows.
"""
import logging
from datetime import datetime, timedelta, timezone

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live.stock import StockDataStream
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from agent import config, store

log = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _to_row(symbol: str, bar) -> tuple:
    """Alpaca Bar -> the (symbol, ts_utc, o, h, l, c, v) tuple store expects."""
    return (
        symbol,
        bar.timestamp.astimezone(timezone.utc).strftime(TS_FMT),
        float(bar.open),
        float(bar.high),
        float(bar.low),
        float(bar.close),
        int(bar.volume),
    )


def warm_start(conn, symbols: list[str], days: int = 12) -> int:
    """Backfill recent 1-minute bars so indicators are live immediately.

    One multi-symbol request, not one per symbol: the free tier allows 200 REST
    calls per minute and there is no reason to spend 20 of them. The 15-minute
    REST delay does not matter here because this is history, not a live price.

    `days` is CALENDAR days, not sessions. 12 calendar days guarantees at least
    6 trading sessions across a weekend and a public holiday, which is what
    indicators.rvol(lookback_days=5) needs: five prior sessions plus today.
    Asking for 5 here yields 3-4 sessions and rvol silently degrades.
    """
    key, secret = config.api_keys()
    client = StockHistoricalDataClient(key, secret)

    request = StockBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=TimeFrame.Minute,
        start=datetime.now(timezone.utc) - timedelta(days=days),
        feed=DataFeed.IEX,
    )
    barset = client.get_stock_bars(request)

    rows = [_to_row(sym, bar) for sym, series in barset.data.items() for bar in series]
    written = store.upsert_bars(conn, rows)
    log.info("warm start: %d bars across %d symbols", written, len(symbols))
    return written


def fill_gap(
    conn,
    symbols: list[str],
    *,
    client=None,
    now: datetime | None = None,
    lookback_minutes: int = 30,
) -> int:
    """REST-backfill recent bars to close holes left by a websocket reconnect.

    Starts from the newest stored bar (minus one minute of overlap) or from
    `lookback_minutes` ago when the store is empty. Safe to call repeatedly:
    upserts are idempotent.
    """
    now = now or datetime.now(timezone.utc)
    newest = store.newest_bar_ts(conn)
    if newest:
        start = datetime.strptime(newest, TS_FMT).replace(tzinfo=timezone.utc)
        start = start - timedelta(minutes=1)
    else:
        start = now - timedelta(minutes=lookback_minutes)

    if start >= now:
        return 0

    if client is None:
        key, secret = config.api_keys()
        client = StockHistoricalDataClient(key, secret)

    request = StockBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=TimeFrame.Minute,
        start=start,
        end=now,
        feed=DataFeed.IEX,
    )
    barset = client.get_stock_bars(request)
    rows = [_to_row(sym, bar) for sym, series in barset.data.items() for bar in series]
    written = store.upsert_bars(conn, rows)
    if written:
        log.info("gap fill: %d bars since %s", written, start.strftime(TS_FMT))
    return written


RECONNECT_BASE_DELAY = 5.0
RECONNECT_MAX_DELAY = 120.0
# A stream must survive at least this long to count as "it actually
# connected" rather than "failed immediately" - see _backoff_delay.
RECONNECT_RESET_AFTER = 60.0


def _backoff_delay(attempt: int) -> float:
    """Seconds to wait before reconnect attempt `attempt` (1-indexed).

    Live: a flat 5s retry against Alpaca's "connection limit exceeded"
    hammered the API every ~20-30s for over an hour straight without ever
    recovering, because the server needs longer than 5s to release a stale
    connection slot for the same API key - every retry landed while the
    prior one was still being counted, a self-sustaining lockout rather
    than a transient failure. Exponential backoff, capped, gives the server
    room to actually clear the slot.
    """
    return min(RECONNECT_MAX_DELAY, RECONNECT_BASE_DELAY * (2 ** attempt))


def run(conn) -> None:
    """Subscribe to 1-minute bars for the universe and write each to SQLite.

    Blocks until interrupted. On stream exit (timeout / disconnect that
    escapes alpaca-py's internal reconnect), REST-fill any gap and restart.
    """
    import time

    attempt = 0
    while True:
        started = time.monotonic()
        try:
            _stream_once(conn)
        except KeyboardInterrupt:
            raise
        except Exception:
            log.exception("stream stopped; filling gap before reconnect")

        try:
            fill_gap(conn, config.UNIVERSE)
        except Exception:
            log.exception("gap fill failed")

        # A stream that ran a while before failing was a real, working
        # connection - a later, unrelated failure should not inherit a
        # backoff built up from an earlier connection-limit lockout.
        if time.monotonic() - started > RECONNECT_RESET_AFTER:
            attempt = 0
        attempt += 1

        delay = _backoff_delay(attempt)
        log.warning("reconnecting in %.0fs (attempt %d)", delay, attempt)
        time.sleep(delay)


def _stream_once(conn) -> None:
    key, secret = config.api_keys()
    # data_timeout is None by default, which disables alpaca-py's only defence
    # against a "connected but mute" socket - a connection that stays
    # TCP-ESTABLISHED while the remote side has gone silent, which the
    # transport-level ping/pong keepalive does not catch. Without it, a dead
    # socket can sit doing nothing indefinitely; the reconnect backoff (max
    # 30s) never engages because no exception is ever raised to trigger it.
    # Live: this is exactly what happened - three failures, then silence for
    # ~19 hours spanning an entire trading session with zero bars received.
    # 120s is generous for 1-min bars across 20 liquid symbols during RTH,
    # and a spurious reconnect while idle outside market hours is harmless.
    stream = StockDataStream(key, secret, feed=DataFeed.IEX, data_timeout=120.0)

    # DEBUG-only per-bar logging is silent for hours outside market hours, so
    # a process watching this log for "is the stream actually alive" cannot
    # tell idle-and-fine apart from broken. This INFO heartbeat, roughly once
    # a minute once the full 20-symbol universe is streaming, is that signal.
    counter = {"n": 0}
    HEARTBEAT_EVERY = 20

    async def on_bar(bar):
        store.upsert_bars(conn, [_to_row(bar.symbol, bar)])
        log.debug("bar %s %s c=%s", bar.symbol, bar.timestamp, bar.close)
        counter["n"] += 1
        if counter["n"] % HEARTBEAT_EVERY == 0:
            log.info("streaming: %d bars received, latest %s %s",
                     counter["n"], bar.symbol, bar.timestamp)

    stream.subscribe_bars(on_bar, *config.UNIVERSE)
    log.info("streaming %d symbols from IEX", len(config.UNIVERSE))
    stream.run()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    conn = store.connect(config.DB_PATH)
    warm_start(conn, config.UNIVERSE)
    run(conn)


if __name__ == "__main__":
    main()
