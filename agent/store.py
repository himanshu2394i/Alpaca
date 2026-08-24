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

-- Every decision the agent reached, including the ones to do nothing. This is
-- the audit trail and the demo artifact: a rejection with its reason is more
-- informative than a trade without one.
CREATE TABLE IF NOT EXISTS decisions (
    ts_utc  TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    action  TEXT NOT NULL,   -- entry | exit | rejected | no_contract
    detail  TEXT NOT NULL DEFAULT '',
    thesis  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (ts_utc, symbol, action)
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # ingest and the trading loop are two separate writer processes on this
    # file; Python's 5s default lock-wait is too short for a bulk warm-start
    # write (tens of thousands of rows) to complete without a concurrent
    # writer hitting "database is locked". 15s gives real headroom, and
    # upsert_bars batching one write into one lock acquisition removes most
    # of the actual contention this was masking.
    conn = sqlite3.connect(path, isolation_level=None, timeout=15.0)
    conn.row_factory = sqlite3.Row
    # WAL lets the dashboard read while ingest writes.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_bars(conn: sqlite3.Connection, rows: Iterable[tuple]) -> int:
    """Insert bars, replacing any with the same (symbol, ts_utc).

    Replay-safe: re-ingesting the same window is a no-op rather than a
    duplicate, which matters because reconnects backfill overlapping ranges.

    Wrapped in one explicit transaction: under isolation_level=None
    (autocommit), executemany with no transaction commits each row
    individually - a large batch then holds and re-acquires the write lock
    once per row instead of once total, and a failure partway through leaves
    the earlier rows committed instead of rolling back.
    """
    rows = list(rows)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO bars (symbol, ts_utc, o, h, l, c, v) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
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
    # The OCC symbol already encodes call/put. If the stored `right` disagrees,
    # exits.levels() has assigned inverted stop and target prices and every exit
    # check will fire on the wrong direction. Fail here, loudly.
    from agent.gates import parse_occ

    _, _, symbol_right, _ = parse_occ(symbol)
    if symbol_right != right:
        raise ValueError(
            f"right {right!r} contradicts symbol {symbol} (which is a {symbol_right})"
        )

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


def record_decision(conn: sqlite3.Connection, ts_utc: str, symbol: str,
                    action: str, detail: str = "", thesis: str = "") -> None:
    """Log one decision, including decisions not to trade."""
    conn.execute(
        "INSERT OR REPLACE INTO decisions (ts_utc, symbol, action, detail, thesis) "
        "VALUES (?, ?, ?, ?, ?)",
        (ts_utc, symbol, action, detail, thesis),
    )


def recent_decisions(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM decisions ORDER BY ts_utc DESC LIMIT ?", (limit,)
    ).fetchall()


def closed_positions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM positions WHERE status = 'closed' ORDER BY exit_ts DESC"
    ).fetchall()


def equity_series(conn: sqlite3.Connection, limit: int = 2000) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM (SELECT * FROM equity ORDER BY ts_utc DESC LIMIT ?) "
        "ORDER BY ts_utc ASC", (limit,)
    ).fetchall()
