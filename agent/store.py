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

-- One row per fill. A contract may appear several times over the competition,
-- so the key is (symbol, entry_ts) and "is it open" is a status column rather
-- than a row's existence.
CREATE TABLE IF NOT EXISTS positions (
    symbol            TEXT    NOT NULL,
    entry_ts          TEXT    NOT NULL,
    underlying        TEXT    NOT NULL,
    right             TEXT    NOT NULL,
    qty               INTEGER NOT NULL,
    entry_price       REAL    NOT NULL,
    entry_underlying  REAL    NOT NULL,
    stop_underlying   REAL    NOT NULL,
    target_underlying REAL    NOT NULL,
    expiry            TEXT    NOT NULL,
    thesis            TEXT    NOT NULL DEFAULT '',
    status            TEXT    NOT NULL DEFAULT 'open',
    exit_price        REAL,
    exit_ts           TEXT,
    exit_reason       TEXT,
    PRIMARY KEY (symbol, entry_ts)
);

CREATE INDEX IF NOT EXISTS positions_open ON positions(status);
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


def open_position(
    conn: sqlite3.Connection, symbol: str, underlying: str, right: str, qty: int,
    entry_price: float, entry_ts: str, entry_underlying: float,
    stop_underlying: float, target_underlying: float, expiry: str, thesis: str = "",
) -> None:
    """Record a filled entry.

    Refuses to open a contract that is already open. Two live positions in the
    same contract would double the intended risk and make exit accounting
    ambiguous - far better to fail loudly here than to discover it at exit.
    """
    already = conn.execute(
        "SELECT 1 FROM positions WHERE symbol = ? AND status = 'open'", (symbol,)
    ).fetchone()
    if already:
        raise ValueError(f"{symbol} is already open")

    conn.execute(
        "INSERT INTO positions (symbol, entry_ts, underlying, right, qty, "
        "entry_price, entry_underlying, stop_underlying, target_underlying, "
        "expiry, thesis) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (symbol, entry_ts, underlying, right, qty, entry_price, entry_underlying,
         stop_underlying, target_underlying, expiry, thesis),
    )


def open_positions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every currently open position, oldest first."""
    return conn.execute(
        "SELECT * FROM positions WHERE status = 'open' ORDER BY entry_ts"
    ).fetchall()


def close_position(
    conn: sqlite3.Connection, symbol: str, exit_price: float, exit_ts: str,
    exit_reason: str,
) -> None:
    """Mark the open row for `symbol` closed and record why."""
    conn.execute(
        "UPDATE positions SET status = 'closed', exit_price = ?, exit_ts = ?, "
        "exit_reason = ? WHERE symbol = ? AND status = 'open'",
        (exit_price, exit_ts, exit_reason, symbol),
    )


def record_equity(conn: sqlite3.Connection, ts_utc: str, value: float) -> None:
    """Snapshot account equity. This is the P&L curve the demo shows."""
    conn.execute("INSERT OR REPLACE INTO equity (ts_utc, value) VALUES (?, ?)",
                 (ts_utc, value))
