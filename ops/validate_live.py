#!/usr/bin/env python3
"""Cross-check local SQLite vs Alpaca broker; validate decision semantics."""
import asyncio
import os
import sys
from pathlib import Path

# Ensure venv tools (alpaca-mcp-server) are on PATH when run from cron/ssh.
_root = Path(__file__).resolve().parents[1]
_venv_bin = _root / ".venv" / "bin"
os.environ["PATH"] = f"{_venv_bin}{os.pathsep}{os.environ.get('PATH', '')}"

from agent import config, gates, store


def _check_decisions(conn) -> list[str]:
    issues = []
    rows = conn.execute(
        "SELECT ts_utc, symbol, action, detail FROM decisions ORDER BY ts_utc"
    ).fetchall()

    # entry rows must have open or closed position for that symbol (same day or after)
    for r in rows:
        if r["action"] != "entry":
            continue
        pos = conn.execute(
            "SELECT status FROM positions WHERE symbol=? AND entry_ts <= ? "
            "ORDER BY entry_ts DESC LIMIT 1",
            (r["symbol"], r["ts_utc"]),
        ).fetchone()
        if not pos:
            issues.append(
                f"ORPHAN ENTRY: {r['ts_utc']} {r['symbol']} entry but no position row"
            )

    # abandoned/canceled should not have opened a position at that ts
    for r in rows:
        if r["action"] not in ("abandoned", "canceled", "broker_rejected"):
            continue
        pos = conn.execute(
            "SELECT entry_ts FROM positions WHERE symbol=? AND status='open' "
            "AND entry_ts = ?",
            (r["symbol"], r["ts_utc"]),
        ).fetchone()
        if pos:
            issues.append(
                f"BAD: {r['action']} at {r['ts_utc']} but open position opened same ts"
            )

    return issues


async def _broker_snapshot():
    from agent import mcp_bridge

    async with mcp_bridge.session() as sess:
        acct = await mcp_bridge.call(sess, "get_account_info", {})
        pos = await mcp_bridge.call(sess, "get_all_positions", {})
        return acct, pos


def _broker_options(payload: dict) -> dict[str, dict]:
    rows = payload.get("result") or payload.get("positions") or []
    if isinstance(rows, dict):
        items = rows.values()
    else:
        items = rows if isinstance(rows, list) else []
    out = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "")
        if sym and sym[0].isalpha() and len(sym) > 10:
            out[sym] = row
    return out


async def main() -> int:
    conn = store.connect(config.DB_PATH)
    local = {p["symbol"]: dict(p) for p in store.open_positions(conn)}
    acct, payload = await _broker_snapshot()
    remote = _broker_options(payload)

    equity = float(acct.get("equity") or 0)
    print(f"broker_equity={equity:,.2f}")
    print(f"local_open={len(local)}  broker_open={len(remote)}")

    ok = True
    for sym, pos in local.items():
        if sym not in remote:
            print(f"MISMATCH local-only: {sym} qty={pos['qty']}")
            ok = False
        else:
            bq = int(float(remote[sym].get("qty") or 0))
            if bq != pos["qty"]:
                print(f"MISMATCH qty {sym}: local={pos['qty']} broker={bq}")
                ok = False
            else:
                print(f"OK  {sym} qty={pos['qty']} entry={pos['entry_price']}")

    for sym in remote:
        if sym not in local:
            print(f"MISMATCH broker-only: {sym} qty={remote[sym].get('qty')}")
            ok = False

    deployed = sum(p["entry_price"] * p["qty"] * gates.CONTRACT_MULTIPLIER
                   for p in local.values())
    print(f"local_deployed=${deployed:,.0f}  ({deployed/equity:.1%} of equity)" if equity else "")

    print("\n=== decision integrity ===")
    issues = _check_decisions(conn)
    if issues:
        ok = False
        for i in issues:
            print(f"ISSUE: {i}")
    else:
        print("OK  all entry rows have positions; no abandoned-as-entry")

    print("\n=== recent decisions (last 12) ===")
    for r in conn.execute(
        "SELECT ts_utc, symbol, action, detail FROM decisions "
        "ORDER BY ts_utc DESC LIMIT 12"
    ):
        print(f"{r['ts_utc']}  {r['action']:12s}  {r['symbol']}")

    print("\n=== exit scan (why no sells?) ===")
    from agent import exits
    underlyings = {}
    for u in set(p["underlying"] for p in local.values()):
        ts = store.last_bar_ts(conn, u)
        if ts:
            bar = conn.execute(
                "SELECT c FROM bars WHERE symbol=? ORDER BY ts_utc DESC LIMIT 1", (u,)
            ).fetchone()
            if bar:
                underlyings[u] = float(bar["c"])
    premiums = {}  # would need chain fetch; show underlying vs stops only
    today = "2026-08-27"
    for sym, pos in local.items():
        u = pos["underlying"]
        und = underlyings.get(u)
        sig = exits.check(pos, und, None, today)
        stop, tgt = pos["stop_underlying"], pos["target_underlying"]
        und_s = f"{und:.2f}" if und else "?"
        print(f"  {sym}: und={und_s} stop={stop:.2f} tgt={tgt:.2f} "
              f"exit={sig.reason if sig else 'hold'}")

    print(f"\nVALIDATION={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
