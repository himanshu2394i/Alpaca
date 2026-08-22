# Autonomous Alpaca Options Agent — Design

**Date:** 2026-08-23
**Event:** lablab.ai × Alpaca AI Trading Agents Hackathon (28 Aug – 4 Sep 2026)
**Working name:** `alpaca-options-agent` (product name chosen before submission)

## Goal

An autonomous agent that trades US equity options in an Alpaca paper account,
generating P&L across the competition window (31 Aug – 4 Sep 2026) without human
intervention, and producing a legible record of why it made each trade.

## Hackathon constraints

Failing any of these disqualifies the submission.

| Requirement | How this design satisfies it |
|---|---|
| Autonomous AI agent | Event-driven loop; no human in the trade path |
| Alpaca MCP server **or** CLI | Both — MCP for the agent's tools and order placement, CLI for the ops layer |
| Options trading | Every position is an options contract; no equity trades |
| Brand-new paper account | Prototype on a throwaway; competition account opened 28 Aug |
| $100,000 starting balance | Set at account creation |
| One-page write-up | AI logic, risk gates, Alpaca infrastructure |

Submission also needs a public GitHub repo, an Application URL (the dashboard),
a cover image, a video, slides, and the paper account ID.

## Platform constraints that shape the design

Alpaca free market-data tier:

- Stocks: real-time via **websocket, IEX only**; REST is **delayed 15 minutes**
- Options: **indicative** pricing, not real-time OPRA
- **30 symbol cap** on websocket subscriptions
- 200 REST calls/minute

Consequences, and they are load-bearing:

1. Signals are read from the **underlying**, which has free real-time data. The
   option chain is used only to select a contract and set a limit price.
2. No strategy may depend on option microstructure or on reacting faster than
   the market. There is no latency edge available and we should not pretend to one.
3. Universe is capped at ~20 underlyings, leaving ~10 websocket slots for the
   option contracts actually held.
4. Every options round trip pays a wide bid-ask spread. Trade infrequently and
   with conviction; churn loses to spread before strategy is even tested.

Alpaca options rules: limit/market/stop/stop_limit; stop is single-leg only;
TIF day or GTC; no extended hours; whole contracts only. Approval levels — L1
covered call and cash-secured put, L2 long calls/puts, L3 debit spreads. The
paper account's actual level is verified on day 1 via `alpaca account get`.

## Architecture

```
Alpaca IEX websocket (real-time, free)
  |  1-min bars + quotes, 20 underlyings
  v
ingest.py (asyncio)  ---writes-->  market.db (SQLite)
  |                                     |
  | on bar close                        | reads
  v                                     v
screener.py  — deterministic
  EMA / ATR / RVOL / opening range
  + stop & target checks on open positions
  |
  | asyncio.Queue
  v
decide()  — Claude + Alpaca MCP tools
  reads chain, greeks, news -> proposes a trade
  |
  | Decision(contract, qty, limit, stop, target, thesis)
  v
gates.py  — deterministic, no LLM
  size, exposure, liquidity, halt conditions
  |
  | approved only
  v
execute.py -> MCP place_option_order
  limit at mid + buffer, reconcile fill
```

The deterministic screener finds candidates, the LLM decides, deterministic
gates approve or reject. An ensemble that both finds and approves its own trades
has nothing preventing it from sizing 40% of the book into one contract.

### Components

| Module | Responsibility | Depends on |
|---|---|---|
| `ingest.py` | Subscribe to websocket, write bars to SQLite. No logic. | alpaca-py |
| `store.py` | SQLite schema, reads/writes. Single writer. | sqlite3 (stdlib) |
| `indicators.py` | EMA, ATR, RVOL, opening range. Pure functions over DataFrames. | pandas |
| `screener.py` | Entry/exit triggers + throttles. Emits candidates. | store, indicators |
| `decide.py` | The LLM decision agent. One function, swappable. | Claude SDK, MCP |
| `gates.py` | Hard risk limits. Pure, no I/O. | — |
| `execute.py` | Place order via MCP, poll, reconcile. | MCP |
| `dashboard.py` | FastAPI read-only view over market.db. | FastAPI |
| `ops/` | CLI-based cron scripts: EOD snapshot, health, flatten. | alpaca CLI |

## Data pipeline

**Storage: SQLite**, one file. `sqlite3` is stdlib, it survives crashes, it is
queryable for the demo, and there is exactly one writer. A real database would
be pure operational overhead for a seven-day project.

**Process model: one asyncio process, no broker.** An `asyncio.Queue` is the
event bus.

**Warm start:** on boot, REST-backfill ~5 days of 1-min bars before streaming.
The 15-minute REST delay is irrelevant for history, and indicators are then live
immediately rather than after an hour of accumulation.

**Timezones:** everything stored UTC, converted to ET only at the display edge.

**Universe:** ~20 liquid underlyings with tight option spreads — SPY, QQQ, IWM,
AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AMD and similar. Hardcoded, reviewed
once before go-live, not dynamically selected.

### Schema

| Table | Columns / purpose |
|---|---|
| `bars` | `(symbol, ts_utc, o, h, l, c, v)`, PK `(symbol, ts_utc)` — idempotent on replay |
| `positions` | open options positions with entry thesis, stop, target |
| `decisions` | every agent call: input context, output, rationale — the demo artifact |
| `orders` | submitted orders and fills, reconciled against Alpaca on boot |
| `equity` | per-minute equity snapshot — the P&L curve for judging |

## Strategy

Directional momentum on the underlying, expressed as long calls or long puts.

**Entry trigger:** underlying has moved more than 1.0 x ATR(14) from session
open, with RVOL above 1.5, and price on the correct side of EMA(20).

**Exit trigger** (evaluated continuously on open positions): underlying breaches
stop at 1 x ATR against, or target at 2 x ATR in favour; or premium -40% / +80%;
or DTE below 2; or the 4 Sep close.

**Throttles:** 60-minute per-symbol cooldown, max 3 entries/day, max 5
concurrent positions.

**Clock wakeups** exist only for safety, never for signals: 09:30 ET state
reconciliation, 15:45 ET risk review.

## Decision agent

```python
def decide(candidate, context, portfolio) -> Decision
```

Input: the screener's candidate, a recent bar summary, headlines from Alpaca's
free news API, current positions, remaining risk budget.

The agent uses MCP tools (`get_option_chain`, `get_option_snapshot`) to inspect
strikes, Greeks and implied volatility itself, then returns structured JSON:
contract symbol, quantity, limit price, stop, target, thesis, confidence.

**The agent may only ENTER the candidate it was given, or SKIP.** It cannot
invent a symbol. This is a structural gate, not a prompt instruction.

Model: `claude-sonnet-5`. The reasoning is bounded and Sonnet is fast and cheap
enough to run for a week.

This single function is the seam. A multi-agent debate ensemble can replace it
later without touching anything upstream or downstream — deferred deliberately
so the fragile component is off the critical path.

## Risk gates

Deterministic, applied after the agent and before execution. No agent output can
override them.

```python
RISK = {
  "max_position_pct":   0.02,   # $2,000 per trade on $100k
  "max_deployed_pct":   0.10,   # 10% in options at any time
  "max_concurrent":     5,
  "daily_loss_halt":   -0.03,   # -$3,000 -> stop trading for the day
  "drawdown_halt":     -0.08,   # -$8,000 from peak -> flatten and stop
  "no_entry_after":    "15:30", # ET
  "dte_range":         (3, 45),
  "min_open_interest":  500,
  "max_spread_pct":     0.10,   # reject if bid-ask > 10% of mid
  "delta_range":       (0.35, 0.55),
}
```

Plus a kill switch: if a file named `HALT` exists in the working directory,
nothing trades.

These values are a calibration knob, not doctrine. 2% per trade makes account
destruction nearly impossible, which matters because a -60% equity curve is an
unrecoverable demo regardless of how good the engineering is.

## Execution

Limit orders, never market — with indicative pricing and wide spreads, market
orders donate the account.

Entry limit price is `mid + 25% of the half-spread`, never above the ask. Exit
limit is `mid - 25% of the half-spread`, never below the bid. Submit via MCP
`place_option_order` with TIF `day`, poll status for 60 seconds, then cancel and
retry once at the ask (entry) or bid (exit); if that also fails, abandon and log.

On boot, reconcile local `orders` and `positions` against Alpaca before trading,
so a restart never double-fills.

## Ops layer (Alpaca CLI)

Cron-driven, deterministic, no LLM: EOD equity snapshot via `alpaca account
get`, position dump via `alpaca position list --jq`, and a one-line emergency
flatten. This makes the CLI requirement genuine rather than decorative.

## Dashboard

Single-file FastAPI serving one HTML page reading `market.db`: equity curve,
open positions, and the decision log with each thesis. Chart.js from CDN, no
build step, no frontend framework. This page is the Application URL for the
submission.

## Deployment

A $6/month Ubuntu VM in a US region, systemd unit with `Restart=always`. Not
Docker, not Kubernetes. US region reduces latency to Alpaca and removes the
user's laptop from the critical path during 19:00-01:30 IST market hours.

## Testing

The websocket is the untestable part, so `ingest.py` stays thin — it only writes
rows. Everything with logic reads from SQLite, so tests seed a fixture database
with known bars and assert on outputs.

- `test_indicators.py` — known bars in, known EMA/ATR/RVOL out
- `test_screener.py` — fails if a trigger fires when it should not, or misses one
- `test_gates.py` — every limit has a case that must be rejected

No mocking of the websocket, no fixture framework. Tests are written before the
module they cover.

**Dry-run mode** is a first-class feature, not an afterthought: the full pipeline
runs and logs decisions without placing orders. This is how the agent is
validated on a live tape before any order is real.

## Error handling

| Failure | Response |
|---|---|
| Websocket disconnect | Reconnect with backoff; on reconnect, REST-backfill the gap |
| Process crash | systemd restarts; warm start + reconciliation on boot |
| MCP tool error | Retry once, then SKIP the candidate and log |
| Agent returns malformed JSON | Retry once with the parse error, then SKIP |
| Order rejected by Alpaca | Log with reason, do not retry blindly |
| Data staleness (no bars for 5 min during RTH) | Halt entries, alert, keep exits live |

Exits must survive conditions that halt entries. Being unable to close a
position is far worse than being unable to open one.

## Timeline

| Day | Deliverable |
|---|---|
| Mon 24 Aug | Repo, keys, `ingest.py` streaming into SQLite, warm start |
| Tue 25 Aug | Indicators + screener + tests, triggers firing on live tape |
| Wed 26 Aug | Decision agent + MCP wiring, dry-run mode |
| Thu 27 Aug | Gates + execution, first real paper orders on throwaway account |
| Fri 28 Aug | Kickoff. Fresh competition account. Deploy to VM. Dashboard live |
| Sat-Sun 29-30 Aug | Parameter tuning, write-up, social posts. No logic changes |
| Mon 31 Aug | **Live on the competition account** |
| Tue-Thu 1-3 Sep | Monitor. Parameter tuning only, never strategy logic |
| Fri 4 Sep | Final session, flatten decision, video, submit |

## Open items

- **lablab rulebook** on pre-kickoff code. If building before kickoff is
  restricted, prototype on a throwaway and re-commit clean at kickoff.
- **Alpaca account** — assumed not yet created; first task on 24 Aug.
- **VM provider** — assumed the user is willing to rent a small VM.
- **Paper options approval level** — verified on day 1; if L3 is unavailable,
  the design is unaffected because it trades single-leg long options only.

## Explicitly not building

- Multi-agent debate ensemble (deferred; swaps into `decide()` if time allows)
- Backtesting harness beyond what `alpaca-skills` provides
- Credit spreads or multi-leg strategies
- Dynamic universe selection
- Any real-money trading path
