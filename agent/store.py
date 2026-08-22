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
