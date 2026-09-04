"""Read-only web view over market.db.

Standard library only. The page is one route rendering SQLite into HTML, so a
web framework would add dependencies to install on the VM for behaviour we do
not need. The equity curve is inline SVG rather than a charting library so the
page renders with no external network at all.

# ponytail: ThreadingHTTPServer, fine for a handful of viewers; put it behind
# a reverse proxy if it ever needs to serve real traffic.
"""
import html
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent import config, store

CONTRACT_MULTIPLIER = 100

COMPETITION = {
    "start": "2026-08-31",       # first session of the official P&L window
    "end": "2026-09-03",         # EOD Thursday - the judged equity snapshot
    "start_equity": 100_000.0,
}
"""The window that was actually scored.

The agent keeps trading after the window closes, so the live cards on their own
misrepresent the judged result. Both are shown, each labelled - the scored
numbers lead, the live ones sit underneath. Nothing is filtered out of the
tables; post-window rows are separated rather than hidden.
"""


def competition_summary(conn: sqlite3.Connection, window: dict = COMPETITION) -> dict:
    """The judged numbers: equity at the snapshot, and trades closed inside it."""
    rows = [r for r in store.equity_series(conn, limit=20000)
            if r["ts_utc"][:10] <= window["end"]]
    final = float(rows[-1]["value"]) if rows else window["start_equity"]

    closed = [p for p in store.closed_positions(conn)
              if p["exit_ts"] and p["exit_ts"][:10] <= window["end"]
              and p["exit_price"] is not None]
    realised = sum((p["exit_price"] - p["entry_price"]) * p["qty"] * CONTRACT_MULTIPLIER
                   for p in closed)
    wins = sum(1 for p in closed if p["exit_price"] > p["entry_price"])

    return {
        "equity": final,
        "pnl": final - window["start_equity"],
        "pct": (final - window["start_equity"]) / window["start_equity"],
        "closed": len(closed),
        "realised": realised,
        "win_rate": (wins / len(closed)) if closed else None,
    }


def summary(conn: sqlite3.Connection) -> dict:
    """Headline numbers for the top of the page."""
    equity_rows = store.equity_series(conn)
    closed = store.closed_positions(conn)

    realised = sum(
        (r["exit_price"] - r["entry_price"]) * r["qty"] * CONTRACT_MULTIPLIER
        for r in closed if r["exit_price"] is not None
    )
    wins = sum(1 for r in closed
               if r["exit_price"] is not None and r["exit_price"] > r["entry_price"])

    return {
        "equity": float(equity_rows[-1]["value"]) if equity_rows else 0.0,
        "open": len(store.open_positions(conn)),
        "closed": len(closed),
        "realised": realised,
        "win_rate": (wins / len(closed)) if closed else None,
    }


def sparkline(rows, width: int = 720, height: int = 140) -> str:
    """Inline SVG equity curve."""
    if not rows:
        return '<p class="muted">no equity history yet</p>'

    values = [float(r["value"]) for r in rows]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0            # a flat series must not divide by zero
    step = width / max(len(values) - 1, 1)

    points = " ".join(
        f"{i * step:.1f},{height - (v - lo) / span * (height - 10) - 5:.1f}"
        for i, v in enumerate(values)
    )
    colour = "#2e9e5b" if values[-1] >= values[0] else "#c0392b"
    return (
        f'<svg viewBox="0 0 {width} {height}" class="spark" '
        f'preserveAspectRatio="none" role="img" aria-label="equity curve">'
        f'<polyline points="{points}" fill="none" stroke="{colour}" '
        f'stroke-width="2"/></svg>'
    )


def _rows(headers, records) -> str:
    if not records:
        return '<p class="muted">nothing yet</p>'
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in rec) + "</tr>"
        for rec in records
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render(conn: sqlite3.Connection) -> str:
    """The whole page. Every database value is escaped: thesis and detail text
    is model-written, and must never be able to become markup."""
    s = summary(conn)
    comp = competition_summary(conn)
    wr = f"{s['win_rate']:.0%}" if s["win_rate"] is not None else "-"
    comp_wr = f"{comp['win_rate']:.0%}" if comp["win_rate"] is not None else "-"

    open_rows = [
        (p["symbol"], p["underlying"], p["right"], p["qty"], f"{p['entry_price']:.2f}",
         f"{p['stop_underlying']:.2f}", f"{p['target_underlying']:.2f}",
         p["expiry"], p["thesis"])
        for p in store.open_positions(conn)
    ]

    def _closed_row(p):
        return (p["symbol"], p["qty"], f"{p['entry_price']:.2f}",
                f"{p['exit_price']:.2f}" if p["exit_price"] is not None else "-",
                f"{(p['exit_price'] - p['entry_price']) * p['qty'] * CONTRACT_MULTIPLIER:+,.0f}"
                if p["exit_price"] is not None else "-",
                p["exit_reason"] or "-")

    all_closed = store.closed_positions(conn)
    in_window = [p for p in all_closed
                 if p["exit_ts"] and p["exit_ts"][:10] <= COMPETITION["end"]]
    after = [p for p in all_closed
             if not (p["exit_ts"] and p["exit_ts"][:10] <= COMPETITION["end"])]
    closed_rows = [_closed_row(p) for p in in_window]
    after_rows = [_closed_row(p) for p in after]
    decision_rows = [
        (d["ts_utc"], d["symbol"], d["action"], d["detail"], d["thesis"])
        for d in store.recent_decisions(conn, limit=60)
    ]

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>Alpaca Options Agent</title>
<style>
 :root {{ color-scheme: light dark; }}
 body {{ font: 14px/1.5 ui-sans-serif, system-ui, sans-serif; margin: 0 auto;
        max-width: 1100px; padding: 24px; }}
 h1 {{ font-size: 20px; margin: 0 0 4px; }}
 h2 {{ font-size: 15px; margin: 28px 0 8px; text-transform: uppercase;
       letter-spacing: .06em; opacity: .7; }}
 .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }}
 .card {{ border: 1px solid rgba(128,128,128,.35); border-radius: 8px;
          padding: 10px 16px; min-width: 120px; }}
 .card .v {{ font-size: 22px; font-variant-numeric: tabular-nums; }}
 .card .k {{ font-size: 11px; text-transform: uppercase; opacity: .6; }}
 .spark {{ width: 100%; height: 140px; border: 1px solid rgba(128,128,128,.35);
           border-radius: 8px; }}
 table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }}
 th, td {{ text-align: left; padding: 6px 10px;
           border-bottom: 1px solid rgba(128,128,128,.25); }}
 th {{ font-size: 11px; text-transform: uppercase; opacity: .6; }}
 .muted {{ opacity: .6; }}
 .wrap {{ overflow-x: auto; }}
</style></head><body>
<h1>Alpaca Options Agent</h1>
<p class="muted">Paper trading &middot; auto-refreshes every 30s</p>

<h2>Competition result &mdash; {COMPETITION['start']} to {COMPETITION['end']} (judged window)</h2>
<div class="cards">
  <div class="card"><div class="k">Final equity</div><div class="v">${comp['equity']:,.0f}</div></div>
  <div class="card"><div class="k">P&amp;L</div><div class="v">{comp['pnl']:+,.0f}</div></div>
  <div class="card"><div class="k">Return</div><div class="v">{comp['pct']:+.2%}</div></div>
  <div class="card"><div class="k">Closed</div><div class="v">{comp['closed']}</div></div>
  <div class="card"><div class="k">Win rate</div><div class="v">{comp_wr}</div></div>
</div>
<p class="muted">Official P&amp;L window: 31 Aug 09:30 ET &rarr; 4 Sep 09:30 ET,
scored on total account equity at the EOD 3 Sep snapshot. Started at
$100,000.</p>

<h2>Live now &mdash; after the window, still trading</h2>
<div class="cards">
  <div class="card"><div class="k">Equity</div><div class="v">${s['equity']:,.0f}</div></div>
  <div class="card"><div class="k">Realised P&amp;L</div><div class="v">{s['realised']:+,.0f}</div></div>
  <div class="card"><div class="k">Open</div><div class="v">{s['open']}</div></div>
  <div class="card"><div class="k">Closed</div><div class="v">{s['closed']}</div></div>
  <div class="card"><div class="k">Win rate</div><div class="v">{wr}</div></div>
</div>
<p class="muted">The agent keeps running past the competition. On 4 Sep a
deadline rule force-exited every position each tick while entries stayed open,
so one contract was repeatedly bought and re-sold before it was caught and
fixed &mdash; those round trips are in the post-window table below, and they
fall entirely outside the judged window above.</p>

{sparkline(store.equity_series(conn))}

<h2>Open positions</h2><div class="wrap">{_rows(
 ["contract","underlying","right","qty","entry","stop","target","expiry","thesis"],
 open_rows)}</div>

<h2>Closed positions &mdash; competition window</h2><div class="wrap">{_rows(
 ["contract","qty","entry","exit","P&L","reason"], closed_rows)}</div>

<h2>Closed positions &mdash; after the window</h2><div class="wrap">{_rows(
 ["contract","qty","entry","exit","P&L","reason"], after_rows)}</div>

<h2>Decision log</h2><div class="wrap">{_rows(
 ["time (UTC)","symbol","action","detail","thesis"], decision_rows)}</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        conn = store.connect(config.DB_PATH)
        try:
            body = render(conn).encode("utf-8")
        finally:
            conn.close()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # the default logger writes to stderr on every request


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Serve the agent dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dashboard on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
