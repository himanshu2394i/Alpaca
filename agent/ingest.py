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


def run(conn) -> None:
    """Subscribe to 1-minute bars for the universe and write each to SQLite.

    Blocks until interrupted. alpaca-py's own run() owns the event loop and
    already reconnects with backoff, so we do not write a retry loop here.

    # ponytail: an in-process reconnect leaves a gap in `bars`; only a process
    # restart backfills it via warm_start. Add a periodic gap-filler if the
    # screener starts tripping over holes.
    """
    key, secret = config.api_keys()
    stream = StockDataStream(key, secret, feed=DataFeed.IEX)

    async def on_bar(bar):
        store.upsert_bars(conn, [_to_row(bar.symbol, bar)])
        log.debug("bar %s %s c=%s", bar.symbol, bar.timestamp, bar.close)

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
