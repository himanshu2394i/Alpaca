#!/usr/bin/env python3
"""End-of-session report: decisions, trades, P&L, broker cross-check."""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
os.environ["PATH"] = f"{_root / '.venv' / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"

from agent import config, gates, store  # noqa: E402

CONTRACT_MULT = 100


async def broker_equity_and_positions():
    from agent import mcp_bridge

    async with mcp_bridge.session() as sess:
        acct = await mcp_bridge.call(sess, "get_account_info", {})
        pos = await mcp_bridge.call(sess, "get_all_positions", {})
    rows = pos.get("result") or pos.get("positions") or []
    if isinstance(rows, dict):
        items = list(rows.values())
    else:
        items = rows if isinstance(rows, list) else []
    syms = {}
    for row in items:
        if isinstance(row, dict) and row.get("symbol"):
            syms[str(row["symbol"])] = row
    return float(acct.get("equity") or 0), syms


def main() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = store.connect(config.DB_PATH)

    eq_rows = conn.execute(
        "SELECT ts_utc, value FROM equity WHERE ts_utc >= ? ORDER BY ts_utc",
        (today,),
    ).fetchall()
    vals = [float(r["value"]) for r in eq_rows] if eq_rows else []

    decisions = conn.execute(
        "SELECT ts_utc, symbol, action, detail FROM decisions "
        "WHERE ts_utc >= ? ORDER BY ts_utc",
        (today,),
    ).fetchall()

    open_pos = [dict(p) for p in store.open_positions(conn)]
    closed_today = conn.execute(
        "SELECT * FROM positions WHERE status='closed' AND exit_ts >= ?",
        (today,),
    ).fetchall()

    counts = {}
    for d in decisions:
        counts[d["action"]] = counts.get(d["action"], 0) + 1

    realized = 0.0
    for r in closed_today:
        if r["exit_price"] and r["entry_price"]:
            realized += (float(r["exit_price"]) - float(r["entry_price"])) * r["qty"] * CONTRACT_MULT

    lines = [
        f"# Session report — {today}",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} UTC",
        "",
        "## Equity",
    ]
    if vals:
        lines += [
            f"- Open snapshot: ${vals[0]:,.2f}",
            f"- Close snapshot: ${vals[-1]:,.2f}",
            f"- Session change: ${vals[-1] - vals[0]:+,.2f}",
            f"- Intraday high: ${max(vals):,.2f}",
            f"- Intraday low: ${min(vals):,.2f}",
            f"- Intraday swing: ${max(vals) - min(vals):,.0f} (mostly unrealized marks)",
        ]
    else:
        lines.append("- No equity rows today")

    try:
        broker_eq, broker_pos = asyncio.run(broker_equity_and_positions())
        lines += [
            "",
            "## Broker (Alpaca)",
            f"- Equity now: ${broker_eq:,.2f}",
            f"- Open option positions: {len(broker_pos)}",
        ]
        local_syms = {p["symbol"] for p in open_pos}
        if local_syms == set(broker_pos.keys()):
            lines.append("- Local/broker position sync: **OK**")
        else:
            lines.append(f"- Local/broker sync: **MISMATCH** local={local_syms} broker={set(broker_pos)}")
    except Exception as exc:
        lines += ["", "## Broker", f"- Cross-check failed: {exc}"]

    lines += [
        "",
        "## Decisions today",
        f"- Total rows: {len(decisions)}",
    ]
    for action, n in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"- `{action}`: {n}")

    lines += ["", "## Filled entries today"]
    entries = [d for d in decisions if d["action"] == "entry"]
    if not entries:
        lines.append("- None")
    for d in entries:
        lines.append(f"- {d['ts_utc']} {d['symbol']} — {d['detail']}")

    lines += ["", "## Exits today"]
    exits = [d for d in decisions if d["action"] == "exit"]
    if not exits:
        lines.append("- None")
    for d in exits:
        lines.append(f"- {d['ts_utc']} {d['symbol']} — {d['detail']}")

    lines += [
        "",
        f"## Realized P&L (closed today): ${realized:+,.2f}",
        "",
        "## Still open at close",
    ]
    if not open_pos:
        lines.append("- Flat")
    for p in open_pos:
        cost = p["entry_price"] * p["qty"] * CONTRACT_MULT
        lines.append(
            f"- {p['symbol']} qty={p['qty']} entry=${p['entry_price']:.2f} "
            f"cost≈${cost:,.0f} stop={p['stop_underlying']:.2f} tgt={p['target_underlying']:.2f}"
        )

    deployed = sum(p["entry_price"] * p["qty"] * CONTRACT_MULT for p in open_pos)
    if vals:
        lines += [
            "",
            "## Notes",
            f"- Deployed premium ≈ ${deployed:,.0f} ({deployed/vals[-1]:.1%} of equity)",
            "- Equity moves without new decisions = open options mark-to-market.",
            "- Throwaway pre-kickoff account; not competition $100k yet.",
        ]

    out = "\n".join(lines) + "\n"
    report_path = _root / "logs" / f"eod-report-{today}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(out, encoding="utf-8")
    print(out)
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
