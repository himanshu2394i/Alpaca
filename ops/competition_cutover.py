#!/usr/bin/env python3
"""Wipe competition audit tables; keep bar history for indicator warmup.

Run once when switching to the official $100k paper account. Backs up the DB
first. Does not touch .env — update API keys separately, then restart services.

Usage:
  python ops/competition_cutover.py              # dry-run
  python ops/competition_cutover.py --apply      # backup + wipe
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "market.db"

WIPE_TABLES = ("decisions", "positions", "equity")


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for table in WIPE_TABLES:
        out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    out["bars"] = conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="backup market.db and wipe audit tables")
    args = parser.parse_args()

    if not DB.exists():
        print(f"No database at {DB}")
        return

    conn = sqlite3.connect(DB)
    before = counts(conn)
    print("Before:", before)

    if not args.apply:
        print("Dry run — pass --apply to backup and wipe", WIPE_TABLES)
        print("bars kept:", before["bars"])
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = DB.with_suffix(f".pre-competition-{stamp}.bak")
    shutil.copy2(DB, backup)
    print(f"Backup: {backup}")

    for table in WIPE_TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    after = counts(conn)
    conn.close()
    print("After:", after)
    print("Done. Update .env with competition keys, then:")
    print("  sudo systemctl restart alpaca-ingest alpaca-agent alpaca-dashboard")


if __name__ == "__main__":
    main()
