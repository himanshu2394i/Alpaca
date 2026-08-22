# Data Pipeline Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream real-time 1-minute bars for ~20 liquid underlyings from Alpaca's free IEX websocket into a local SQLite database, backfilled on boot, with indicators computed on read.

**Architecture:** One asyncio process. `ingest.py` subscribes to the websocket and writes rows through `store.py`; it holds no logic. `indicators.py` provides pure functions that read bars out of SQLite and return EMA/ATR/RVOL. Everything downstream (screener, agent, gates) reads from the same database, so it can be tested against a seeded fixture DB with no network.

**Tech Stack:** Python 3.11, `alpaca-py`, `pandas`, `pytest`, `python-dotenv`, `sqlite3` (stdlib).

## Global Constraints

- Python 3.11 (Alpaca MCP server requires 3.10+; pin 3.11 for the project).
- Market data feed is **IEX** everywhere — `DataFeed.IEX` for both historical and stream. The free tier has no SIP access.
- **Maximum 30 websocket symbol subscriptions.** The universe is 20 underlyings; the remaining 10 slots are reserved for held option contracts in a later phase.
- REST limit is **200 calls/minute**. Warm start must batch symbols into single multi-symbol requests, not one call per symbol.
- REST stock data is **delayed 15 minutes**. Never use REST for a current price; it is for history only.
- All timestamps stored as **ISO-8601 UTC text** with a trailing `Z`, e.g. `2026-08-24T13:31:00Z`. Conversion to ET happens only at display.
- SQLite has exactly **one writer** (the ingest process). Readers open separate read-only connections.
- No new dependencies beyond those listed in Tech Stack without justification.
- Secrets come from environment variables only. Never commit `.env`.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Dependencies, pytest config |
| `.env.example` | Documents required env vars; committed |
| `agent/__init__.py` | Empty package marker |
| `agent/config.py` | Universe list, DB path, env loading. No logic. |
| `agent/store.py` | SQLite schema and all read/write access. The only module that touches SQL. |
| `agent/indicators.py` | Pure functions: EMA, ATR, RVOL. No I/O. |
| `agent/ingest.py` | Warm start + websocket subscription. Writes via `store`. No logic. |
| `tests/test_store.py` | Schema, upsert idempotency, reads |
| `tests/test_indicators.py` | Known bars in, known values out |
| `tests/test_ingest.py` | Row mapper: tuple order, UTC conversion, type coercion |
| `tests/conftest.py` | `conn` fixture over a temporary database |
| `tests/helpers.py` | Deterministic bar generator shared by tests |

---

## Task 1: Project scaffolding and config

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `agent/__init__.py`
- Create: `agent/config.py`

**Interfaces:**
- Consumes: nothing
- Produces: `agent.config.UNIVERSE: list[str]`, `agent.config.DB_PATH: pathlib.Path`, `agent.config.api_keys() -> tuple[str, str]`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "alpaca-options-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "alpaca-py>=0.33",
    "pandas>=2.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.env.example`**

```
ALPACA_API_KEY=your_key_id_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_PAPER_TRADE=true
```

- [ ] **Step 3: Create `agent/__init__.py`** — empty file.

- [ ] **Step 4: Create `agent/config.py`**

```python
"""Static configuration. No logic lives here."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "market.db"

# Free-tier websocket caps subscriptions at 30 symbols.
# 20 underlyings here; 10 slots reserved for held option contracts.
UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL",
    "TSLA", "AMD", "NFLX", "AVGO", "MU",
    "JPM", "XLF", "XLE", "COIN", "SMCI",
]

MAX_WS_SYMBOLS = 30


def api_keys() -> tuple[str, str]:
    """Read Alpaca credentials from the environment.

    Raises RuntimeError rather than returning None so a misconfigured
    process fails at startup instead of at the first API call.
    """
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set. "
            "Copy .env.example to .env and fill it in."
        )
    return key, secret
```

- [ ] **Step 5: Verify the universe fits the websocket cap**

Run: `python -c "from agent.config import UNIVERSE, MAX_WS_SYMBOLS; assert len(UNIVERSE) <= MAX_WS_SYMBOLS - 10, len(UNIVERSE); print(len(UNIVERSE), 'symbols OK')"`
Expected: `20 symbols OK`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example agent/
git commit -m "feat: project scaffolding and static config"
```

---

## Task 2: SQLite store

**Files:**
- Create: `agent/store.py`
- Create: `tests/conftest.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `agent.config.DB_PATH`
- Produces:
  - `connect(path: Path | str) -> sqlite3.Connection`
  - `upsert_bars(conn, rows: Iterable[tuple[str, str, float, float, float, float, int]]) -> int`
  - `recent_bars(conn, symbol: str, limit: int = 500) -> list[sqlite3.Row]` — ascending by `ts_utc`
  - `last_bar_ts(conn, symbol: str) -> str | None`
  - Bar tuple order is always `(symbol, ts_utc, o, h, l, c, v)`

- [ ] **Step 1: Write `tests/conftest.py` and `tests/helpers.py`**

`tests/conftest.py`:

```python
import pytest

from agent import store


@pytest.fixture
def conn(tmp_path):
    c = store.connect(tmp_path / "test.db")
    yield c
    c.close()
```

`tests/helpers.py`:

```python
from datetime import datetime, timedelta, timezone


def make_bars(symbol="SPY", n=10, start_price=100.0, step=1.0):
    """Deterministic ascending bars, one minute apart, from 2026-08-24T13:30:00Z."""
    t0 = datetime(2026, 8, 24, 13, 30, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        price = start_price + i * step
        ts = (t0 + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append((symbol, ts, price, price + 0.5, price - 0.5, price, 1000 + i))
    return rows
```

Also create an empty `tests/__init__.py` so `from tests.helpers import ...` resolves.

- [ ] **Step 2: Write the failing tests in `tests/test_store.py`**

```python
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
    # the three most recent, in ascending order
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError` or `AttributeError: module 'agent.store' has no attribute 'connect'`

- [ ] **Step 4: Write `agent/store.py`**

```python
"""All SQL lives here. Single writer: the ingest process."""
import sqlite3
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT    NOT NULL,
    ts_utc TEXT    NOT NULL,
    o      REAL    NOT NULL,
    h      REAL    NOT NULL,
    l      REAL    NOT NULL,
    c      REAL    NOT NULL,
    v      INTEGER NOT NULL,
    PRIMARY KEY (symbol, ts_utc)
);

CREATE TABLE IF NOT EXISTS equity (
    ts_utc TEXT PRIMARY KEY,
    value  REAL NOT NULL
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # WAL lets the dashboard read while ingest writes.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_bars(conn: sqlite3.Connection, rows: Iterable[tuple]) -> int:
    """Insert bars, replacing any with the same (symbol, ts_utc).

    Replay-safe: re-ingesting the same window is a no-op rather than a
    duplicate, which matters because reconnects backfill overlapping ranges.
    """
    rows = list(rows)
    conn.executemany(
        "INSERT OR REPLACE INTO bars (symbol, ts_utc, o, h, l, c, v) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def recent_bars(conn: sqlite3.Connection, symbol: str, limit: int = 500) -> list[sqlite3.Row]:
    """The most recent `limit` bars for `symbol`, oldest first."""
    cur = conn.execute(
        "SELECT * FROM (SELECT * FROM bars WHERE symbol = ? "
        "ORDER BY ts_utc DESC LIMIT ?) ORDER BY ts_utc ASC",
        (symbol, limit),
    )
    return cur.fetchall()


def last_bar_ts(conn: sqlite3.Connection, symbol: str) -> str | None:
    cur = conn.execute("SELECT MAX(ts_utc) AS ts FROM bars WHERE symbol = ?", (symbol,))
    return cur.fetchone()["ts"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_store.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add agent/store.py tests/
git commit -m "feat: SQLite store with replay-safe bar upsert"
```

---

## Task 3: Indicators

**Files:**
- Create: `agent/indicators.py`
- Test: `tests/test_indicators.py`

**Interfaces:**
- Consumes: bar rows in the shape `store.recent_bars` returns (mappings with keys `o`, `h`, `l`, `c`, `v`, `ts_utc`)
- Produces:
  - `ema(bars, period: int) -> float` — final EMA value
  - `atr(bars, period: int = 14) -> float` — Wilder's ATR
  - `rvol(bars, session_date: str, lookback_days: int = 5) -> float`

- [ ] **Step 1: Write the failing tests in `tests/test_indicators.py`**

```python
import pytest

from agent import indicators
from tests.helpers import make_bars


def rows(bars):
    """conftest tuples -> mappings shaped like sqlite3.Row."""
    keys = ("symbol", "ts_utc", "o", "h", "l", "c", "v")
    return [dict(zip(keys, b)) for b in bars]


def test_ema_of_flat_series_equals_the_price():
    bars = rows(make_bars(n=30, start_price=50.0, step=0.0))
    assert indicators.ema(bars, period=10) == pytest.approx(50.0)


def test_ema_trails_a_rising_series():
    bars = rows(make_bars(n=30, start_price=100.0, step=1.0))
    last_close = bars[-1]["c"]
    value = indicators.ema(bars, period=10)
    assert value < last_close
    assert value > bars[-10]["c"]


def test_ema_raises_when_not_enough_bars():
    with pytest.raises(ValueError):
        indicators.ema(rows(make_bars(n=3)), period=10)


def test_atr_converges_to_the_constant_true_range():
    # make_bars gives every bar a high/low spread of 1.0 and a close-to-close
    # step of 1.0, so true range is 1.0 on the first bar and 1.5 thereafter
    # (high - previous close). Wilder smoothing converges toward 1.5; with 200
    # bars the residual from the initial 1.0 is far below the tolerance.
    bars = rows(make_bars(n=200, start_price=100.0, step=1.0))
    assert indicators.atr(bars, period=14) == pytest.approx(1.5, abs=0.01)


def test_atr_has_not_converged_after_few_bars():
    # Guards the smoothing direction: a young ATR must sit below the limit,
    # not above it or already equal to it.
    bars = rows(make_bars(n=30, start_price=100.0, step=1.0))
    value = indicators.atr(bars, period=14)
    assert 1.4 < value < 1.5


def test_atr_is_zero_for_a_frozen_market():
    bars = rows(make_bars(n=30, start_price=100.0, step=0.0))
    flat = [{**b, "h": 100.0, "l": 100.0, "c": 100.0, "o": 100.0} for b in bars]
    assert indicators.atr(flat, period=14) == pytest.approx(0.0)


def test_rvol_is_one_when_today_matches_the_average():
    bars = []
    for day in range(24, 29):  # 24..28 Aug, five sessions
        for b in make_bars(n=10):
            ts = b[1].replace("2026-08-24", f"2026-08-{day}")
            bars.append((b[0], ts, b[2], b[3], b[4], b[5], 1000))
    value = indicators.rvol(rows(bars), session_date="2026-08-28", lookback_days=4)
    assert value == pytest.approx(1.0)


def test_rvol_detects_a_volume_spike():
    bars = []
    for day in range(24, 28):
        for b in make_bars(n=10):
            ts = b[1].replace("2026-08-24", f"2026-08-{day}")
            bars.append((b[0], ts, b[2], b[3], b[4], b[5], 1000))
    for b in make_bars(n=10):  # today, triple volume
        ts = b[1].replace("2026-08-24", "2026-08-28")
        bars.append((b[0], ts, b[2], b[3], b[4], b[5], 3000))
    value = indicators.rvol(rows(bars), session_date="2026-08-28", lookback_days=4)
    assert value == pytest.approx(3.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: FAIL — `AttributeError: module 'agent.indicators' has no attribute 'ema'`

- [ ] **Step 3: Write `agent/indicators.py`**

```python
"""Pure indicator functions. No I/O, no database, no network.

Each takes a sequence of bar mappings (as returned by store.recent_bars,
oldest first) and returns a single float.
"""
from typing import Sequence

import pandas as pd


def _frame(bars: Sequence[dict]) -> pd.DataFrame:
    return pd.DataFrame([dict(b) for b in bars])


def ema(bars: Sequence[dict], period: int) -> float:
    """Exponential moving average of closes; returns the final value."""
    if len(bars) < period:
        raise ValueError(f"need at least {period} bars, got {len(bars)}")
    closes = _frame(bars)["c"]
    return float(closes.ewm(span=period, adjust=False).mean().iloc[-1])


def atr(bars: Sequence[dict], period: int = 14) -> float:
    """Wilder's Average True Range; returns the final value."""
    if len(bars) < period:
        raise ValueError(f"need at least {period} bars, got {len(bars)}")
    df = _frame(bars)
    prev_close = df["c"].shift(1)
    true_range = pd.concat(
        [
            df["h"] - df["l"],
            (df["h"] - prev_close).abs(),
            (df["l"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder smoothing is an EMA with alpha = 1/period.
    return float(true_range.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def rvol(bars: Sequence[dict], session_date: str, lookback_days: int = 5) -> float:
    """Relative volume: today's volume so far divided by the mean volume
    over the same number of elapsed bars on the previous `lookback_days`
    sessions.

    Returns 0.0 when there is no prior history to compare against, so a
    caller thresholding on `rvol > 1.5` fails closed rather than firing.
    """
    df = _frame(bars)
    df["date"] = df["ts_utc"].str[:10]

    today = df[df["date"] == session_date]
    if today.empty:
        return 0.0
    elapsed = len(today)

    prior_dates = sorted(d for d in df["date"].unique() if d < session_date)
    prior_dates = prior_dates[-lookback_days:]
    if not prior_dates:
        return 0.0

    baselines = [
        df[df["date"] == d].head(elapsed)["v"].sum() for d in prior_dates
    ]
    mean_baseline = sum(baselines) / len(baselines)
    if mean_baseline == 0:
        return 0.0

    return float(today["v"].sum() / mean_baseline)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: 9 passed

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -v`
Expected: 15 passed

- [ ] **Step 6: Commit**

```bash
git add agent/indicators.py tests/test_indicators.py
git commit -m "feat: EMA, ATR and RVOL indicators"
```

---

## Task 4: Warm start (REST backfill)

**Blocked on:** Alpaca API keys in `.env`.

**Files:**
- Create: `agent/ingest.py`

**Interfaces:**
- Consumes: `agent.config.UNIVERSE`, `agent.config.DB_PATH`, `agent.config.api_keys`, `agent.store.connect`, `agent.store.upsert_bars`
- Produces: `warm_start(conn, symbols: list[str], days: int = 12) -> int` — returns rows written

- [ ] **Step 1: Write `agent/ingest.py` with warm start only**

```python
"""Market data ingestion: REST backfill on boot, then live websocket.

This module deliberately contains no trading logic. It writes rows.
"""
import logging
from datetime import datetime, timedelta, timezone

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from agent import config, store

log = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _to_row(symbol: str, bar) -> tuple:
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
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Minute,
        start=datetime.now(timezone.utc) - timedelta(days=days),
        feed=DataFeed.IEX,
    )
    bars = client.get_stock_bars(request)

    rows = [_to_row(sym, bar) for sym, series in bars.data.items() for bar in series]
    written = store.upsert_bars(conn, rows)
    log.info("warm start: %d bars across %d symbols", written, len(symbols))
    return written
```

- [ ] **Step 2: Run it against the live API**

Run: `python -c "from agent import config, ingest, store; c = store.connect(config.DB_PATH); print(ingest.warm_start(c, config.UNIVERSE))"`
Expected: a non-zero row count. Verified 2026-08-23: 67,369 bars, 20/20 symbols populated, 9 sessions (11-21 Aug). Re-running writes the same total, confirming the upsert is replay-safe against live data.

- [ ] **Step 3: Verify bars actually landed**

Run: `python -c "from agent import config, store; c = store.connect(config.DB_PATH); print([(s, store.last_bar_ts(c, s)) for s in config.UNIVERSE[:5]])"`
Expected: five `(symbol, timestamp)` pairs with recent dates, none `None`.

- [ ] **Step 4: Commit**

```bash
git add agent/ingest.py
git commit -m "feat: REST warm start backfill for the universe"
```

---

## Task 5: Live websocket stream

**Blocked on:** Task 4, and a session during US market hours (19:00–01:30 IST) to verify.

**Files:**
- Modify: `agent/ingest.py`

**Interfaces:**
- Consumes: everything from Task 4
- Produces: `run(conn) -> None` — blocking async entry point; `main() -> None` — script entry

- [ ] **Step 1: Append the stream to `agent/ingest.py`**

`StockDataStream.run()` is synchronous, owns its own event loop, and already
reconnects with exponential backoff (`_reconnect_delay`). Do not write a retry
loop — the library has one.

```python
from alpaca.data.live.stock import StockDataStream


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
```

- [ ] **Step 2: Run during market hours**

Run: `python -m agent.ingest`
Expected: warm start line, then the process stays alive. Leave it for three minutes.

- [ ] **Step 3: Confirm live bars are arriving**

In a second terminal, run twice about a minute apart:
`python -c "from agent import config, store; c = store.connect(config.DB_PATH); print(store.last_bar_ts(c, 'SPY'))"`
Expected: the timestamp advances by roughly one minute between the two runs. If it does not advance, the stream is not delivering and Task 5 is not done.

- [ ] **Step 4: Commit**

```bash
git add agent/ingest.py
git commit -m "feat: live IEX websocket bar stream"
```

---

## Phase 1 done when

- `python -m pytest` passes with 19 tests
- `python -m agent.ingest` backfills, then advances `last_bar_ts` during market hours
- `data/market.db` is gitignored and contains bars for all 20 symbols

## Later phases (to be planned separately)

| Phase | Contents | Plan written after |
|---|---|---|
| 2 | `screener.py` — entry/exit triggers, throttles, candidate queue | Phase 1 verified on live data |
| 3 | `decide.py` — Claude + MCP decision agent, dry-run mode | Phase 2 emitting candidates |
| 4 | `gates.py` + `execute.py` — risk limits and order placement | Phase 3 producing decisions |
| 5 | `dashboard.py` + `ops/` — FastAPI view, CLI cron scripts, deployment | Phase 4 placing paper orders |
