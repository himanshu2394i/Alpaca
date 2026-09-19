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
"""The window that was actually scored, for the frozen record below."""

STRATEGY_CHANGED_ON = "2026-09-19"
"""The day the live strategy became intraday-only (entries 10:00-14:30 ET,
flat by 15:45 ET). Before it, this account ran the competition strategy
unchanged, with multi-day holds - the page says so rather than implying one
strategy throughout."""

NEW_ACCOUNT_SINCE = "2026-09-13"
"""First day of the current account. The 'Live now' section reflects this
account only - nothing before this date belongs to it."""

COMPETITION_RESULT = {
    "equity": 99_383.36,
    "pnl": -616.64,
    "pct": -0.0061664,
    "closed": 6,
    "win_rate": 2 / 6,
}
"""The judged outcome, frozen. Captured from the live database on 2026-09-13,
right before the account was switched and the audit tables were wiped
(ops/competition_cutover.py) - after that, this result no longer exists
anywhere the page could compute it live. It is a fact about a closed period
that will never change, so a constant is more honest here than a query that
would silently start returning zeroes once its source rows are gone.
"""

COMPETITION_TRADES = [
    # (symbol, qty, entry_price, exit_price, exit_reason)
    ("TSLA260911C00370000", 2, 8.25, 4.80, "premium -42% at or below -40%"),
    ("AAPL260909C00320000", 3, 5.25, 9.40, "premium +85% at or above 80%"),
    ("TSLA260918C00365000", 1, 11.70, 6.95, "premium -41% at or below -40%"),
    ("IWM260918P00290000", 6, 3.28, 2.18, "underlying 295.81 broke stop 295.34"),
    ("AVGO260918P00345000", 1, 9.95, 6.05, "underlying 353.64 broke stop 353.51"),
    ("MSTR260918C00140000", 2, 8.75, 9.95, "underlying 142.72 reached target 142.69"),
]
"""The 6 trades inside the judged window, frozen alongside COMPETITION_RESULT
for the same reason - captured before the cutover wipe removed their source
rows from `positions`."""


def competition_summary() -> dict:
    """The judged numbers: equity at the snapshot, and trades closed inside it.

    Frozen (see COMPETITION_RESULT) rather than queried - the window closed
    for good on 2026-09-03 and its source rows are gone after the account
    switch, so there is nothing left in the database to compute this from.
    """
    return dict(COMPETITION_RESULT)


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
    comp = competition_summary()
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

    def _frozen_row(t):
        symbol, qty, entry, exit_, reason = t
        return (symbol, qty, f"{entry:.2f}", f"{exit_:.2f}",
                f"{(exit_ - entry) * qty * CONTRACT_MULTIPLIER:+,.0f}", reason)

    closed_rows = [_frozen_row(t) for t in COMPETITION_TRADES]
    after_rows = [_closed_row(p) for p in store.closed_positions(conn)]
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

<h2>Live now &mdash; since {NEW_ACCOUNT_SINCE}</h2>
<div class="cards">
  <div class="card"><div class="k">Equity</div><div class="v">${s['equity']:,.0f}</div></div>
  <div class="card"><div class="k">Realised P&amp;L</div><div class="v">{s['realised']:+,.0f}</div></div>
  <div class="card"><div class="k">Open</div><div class="v">{s['open']}</div></div>
  <div class="card"><div class="k">Closed</div><div class="v">{s['closed']}</div></div>
  <div class="card"><div class="k">Win rate</div><div class="v">{wr}</div></div>
</div>
<p class="muted">A fresh paper account, trading since {NEW_ACCOUNT_SINCE}. Until
{STRATEGY_CHANGED_ON} it ran the competition strategy unchanged (multi-day holds);
from {STRATEGY_CHANGED_ON} it is intraday-only: entries 10:00&ndash;14:30 ET,
everything closed by 15:45 ET. The database was reset for the account switch
(audit tables cleared, market history kept), so everything below this line
belongs to this account only.</p>

{sparkline(store.equity_series(conn))}

<h2>Open positions</h2><div class="wrap">{_rows(
 ["contract","underlying","right","qty","entry","stop","target","expiry","thesis"],
 open_rows)}</div>

<h2>Closed positions &mdash; competition window (frozen)</h2><div class="wrap">{_rows(
 ["contract","qty","entry","exit","P&L","reason"], closed_rows)}</div>

<h2>Closed positions &mdash; since {NEW_ACCOUNT_SINCE}</h2><div class="wrap">{_rows(
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
