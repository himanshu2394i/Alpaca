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
    wr = f"{s['win_rate']:.0%}" if s["win_rate"] is not None else "-"

    open_rows = [
        (p["symbol"], p["underlying"], p["right"], p["qty"], f"{p['entry_price']:.2f}",
         f"{p['stop_underlying']:.2f}", f"{p['target_underlying']:.2f}",
         p["expiry"], p["thesis"])
        for p in store.open_positions(conn)
    ]
    closed_rows = [
        (p["symbol"], p["qty"], f"{p['entry_price']:.2f}",
         f"{p['exit_price']:.2f}" if p["exit_price"] is not None else "-",
         f"{(p['exit_price'] - p['entry_price']) * p['qty'] * CONTRACT_MULTIPLIER:+,.0f}"
         if p["exit_price"] is not None else "-",
         p["exit_reason"] or "-")
        for p in store.closed_positions(conn)
    ]
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

<div class="cards">
  <div class="card"><div class="k">Equity</div><div class="v">${s['equity']:,.0f}</div></div>
  <div class="card"><div class="k">Realised P&amp;L</div><div class="v">{s['realised']:+,.0f}</div></div>
  <div class="card"><div class="k">Open</div><div class="v">{s['open']}</div></div>
  <div class="card"><div class="k">Closed</div><div class="v">{s['closed']}</div></div>
  <div class="card"><div class="k">Win rate</div><div class="v">{wr}</div></div>
</div>

{sparkline(store.equity_series(conn))}

<h2>Open positions</h2><div class="wrap">{_rows(
 ["contract","underlying","right","qty","entry","stop","target","expiry","thesis"],
 open_rows)}</div>

<h2>Closed positions</h2><div class="wrap">{_rows(
 ["contract","qty","entry","exit","P&L","reason"], closed_rows)}</div>

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
