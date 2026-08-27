# Tasks

## Fix reconcile's false-positive ghost detection

**Found:** 2026-08-27, reading the live EC2 dashboard (http://35.175.208.115:8080) and
cross-checking against Alpaca directly via the MCP bridge (`get_all_positions`,
`get_orders`).

**What happened:** MSFT260918C00500000 order (`acdcc179-ef18-4593-bba3-1e17687f7cbe`)
submitted 2026-08-26T18:26:46.554Z, filled 2026-08-26T18:26:46.663Z (109ms later,
qty 1 @ 10.20 — confirmed via `get_orders`). Reconcile ran at 18:27:30Z — 44 seconds
*after* the real fill — and still closed the position locally as a "ghost" (decision
log: `reconcile / closed ghost local position`). The position sat invisible to the
local system until the next service restart's boot-time reconcile re-imported it at
21:59:05Z, 3.5 hours later (decision log: `reconcile / imported 1x from broker`).

**Why it matters:** for that 3.5-hour window, local risk math (deployed-capital %,
concurrent-position count in `gates.approve`) was blind to a real, filled position
with real cost basis ($1,020). It happened to be harmless this time because nothing
else was trying to enter concurrently, but the failure mode is structural, not a
one-off: reconcile can force-close a position that demonstrably existed at the
broker well before reconcile ran.

**Ground truth for verification:** account is currently holding
MSFT260918C00500000, qty 1, avg_entry 10.20 (confirmed live via MCP
`get_all_positions`). Check `reconcile.py` for what "is this position at the broker"
query it's running and why it returned a negative 44+ seconds after a confirmed fill
— likely a stale read, a pagination/eventual-consistency gap on the Alpaca API, or a
symbol-matching bug. Add a regression test that reproduces "position exists at
broker, reconcile must not close it locally" using a fixture timed to fire shortly
after a fill.

## Decision log doesn't record order outcomes past the initial entry

**Found:** same session, same cross-check.

**What happened:** AAPL260918C00315000 — two orders, both real:
- `ca62c377-86b9-4f47-b2c0-1d78858e1261` submitted 18:27:40.918Z @ limit 7.21,
  unfilled, canceled 18:28:41.537Z (65s later, matching `execute.py`'s
  cancel-and-retry-on-timeout design)
- `ac1fe946-4e1a-4f5d-a02d-fa0feda4d3be` (client_order_id suffix `-r`, the retry)
  submitted 18:28:41.548Z @ limit 7.24 (crossed further toward the ask, per the
  retry rule), never filled, expired 20:00:08Z at end of trading day (TIF=day)

No position was ever opened — correct outcome, `execute.py`'s retry logic worked as
designed. But the decision log (`store.recent_decisions`) shows only the initial
`entry` line at 18:27:30 and nothing after — no record of the cancel, the retry
order, or the expiry. Anyone reading the dashboard sees an "entry" that appears to
vanish with no explanation, and has to cross-reference the broker's own order
history (as done here, via MCP `get_orders`) to find out what actually happened.

**Fix:** call `store.record_decision(...)` from `execute.py` (or wherever the
retry/cancel/expiry is currently only logged via `log.info`/`log.warning`) so the
full order lifecycle — submitted, canceled, retried, filled, or expired — is
visible in the same decision log the dashboard renders. At minimum: a `canceled`
and an `expired` action type, distinct from `entry`/`exit`/`rejected`/`skip`/
`no_contract`/`reconcile` which already exist.

## Notes for whoever picks these up

- Both were found by comparing the dashboard against Alpaca's own API directly
  (`get_all_positions`, `get_orders` via `agent/mcp_bridge.py`) — that cross-check
  is the fastest way to verify a fix: after changing reconcile or the decision
  logging, re-run the same query and confirm the local dashboard now matches
  broker ground truth without a manual reboot needed.
- Neither issue caused any real financial harm this time (MSFT gain of +$60 is
  real and correctly reflected once reconcile caught up; AAPL never risked capital
  since it never filled). The concern is trustworthiness of the local view during
  live competition hours, not P&L to date.
- EC2 instance: `alpaca-options-agent` (i-06aac474ea732cdeb, us-east-1, profile
  `alpaca-hackathon`), dashboard at http://35.175.208.115:8080.

---

## Reply from implementer agent (2026-08-27) — do not implement in this chat; this is your brief

Good find. Both match what we saw live yesterday. Here is what is already on
`master` vs what you should still implement, plus how to do it.

### Already shipped (do not re-do)

On `master` @ `314cc93` (deployed to EC2 as of merge of PR #1 + #3):

1. **`agent/reconcile.py` — MCP payload shape**  
   Live `get_all_positions` returns `{ "result": [ ... ] }`, not `"positions"`.
   Old parser fell through to an empty remote set → **every** local row looked
   like a ghost. That is the most likely root cause of the 18:27:30 MSFT ghost
   close. Parser now prefers `result` / `positions` / `snapshots` with empty-list
   safety (`[]` is not falsy-skipped).  
   Also: `_broker_positions_usable()` — if payload has `error` or no usable
   envelope, **skip ghost closes** (do not wipe locals).

2. **`agent/run.py` + `execute.is_filled()` — no fake entries**  
   `entry` is logged only after a real fill (or dry-run sim). Otherwise
   `abandoned` / `unfilled` / `rejected`. `is_filled` requires status in
   filled/partial **and** `filled_qty > 0`.  
   So the AAPL “dashboard shows entry then silence” bug from **pre-fill logging**
   is fixed for new ticks. The historical 18:27:30 `entry` row on the DB is
   stale history from before that deploy.

Verify on the box before coding more ghosts: restart agent once, confirm
`get_all_positions` → MSFT stays open locally and no new `closed ghost` for it.

### Still yours to implement

#### Task A — Reconcile false ghost (harden beyond payload parse)

Even with the `result` fix, add defense in depth so a brief Alpaca lag after a
fill cannot close a just-opened local row.

**Implementation sketch:**

1. In `reconcile()`, before `close_position(... "reconcile: not at broker")`:
   - If local `entry_ts` is newer than ~N minutes (suggest **2–5 min**), **skip**
     ghost close and append a note like `deferred ghost check {sym} (recent entry)`.
   - Optional stronger check: `get_order_by_client_id` / recent orders for that
     OCC symbol; if a fill exists, treat as present even if positions lag.
2. Tests in `tests/test_reconcile.py` (TDD):
   - Fixture: local open position + remote payload that **includes** the OCC
     symbol under `"result"` → must **not** close (regression for the live shape).
   - Fixture: local open with `entry_ts` 30s ago + remote empty usable list →
     must **not** close (grace window).
   - Fixture: local open with `entry_ts` hours ago + remote empty → **does** close
     as ghost (keep current behavior for true orphans).
3. Do **not** call reconcile every tick unless you have a strong reason; today it
   is boot-only (`run.loop`). The 18:27 reconcile was almost certainly a
   **service restart** during the demo, not a mid-tick reconcile.

#### Task B — Decision log order lifecycle

Current state after fill-only logging: final `abandoned` / `unfilled` / `entry`
is recorded from `run.py`, but **`execute.submit` / `_attempt` still only
`log.warning`** for cancel + retry. Dashboard never sees intermediate steps.

**Implementation sketch:**

1. Prefer **not** giving `execute.py` a raw `conn` if you can avoid it — keep
   execute pure. Options:
   - **(Preferred)** Have `submit` return a richer result, e.g.
     `{"status": "abandoned", "attempts": [{"client_order_id", "status",
     "limit_price", ...}, ...]}` and let `run.py` call `store.record_decision`
     once per attempt (`submitted` / `canceled` / `unfilled` / `filled` /
     `abandoned`).
   - Or pass an optional `on_event(action, detail)` callback into `submit`.
2. Minimum actions to add (string `action` column, same table):  
   `submitted`, `canceled`, `retry`, `filled` (if you want fill distinct from
   `entry`), `expired` (only if you learn expiry from poll; today poll stops at
   60s and cancel — true `expired` at 20:00 may only appear if you re-query
   later; optional follow-up).
3. Keep `entry` = “local position opened” (fill confirmed). Do not reintroduce
   logging `entry` before fill.
4. Tests:
   - `tests/test_execute.py`: submit path with FakeMCP that times out then fills
     on retry → result includes both attempts’ statuses.
   - `tests/test_run.py`: unfilled/abandoned live tick → decisions contain
     `abandoned` (already) **plus** at least one `canceled` or `retry` if you
     wire attempt events through.

### Constraints

- Options-only; no stocks/crypto scope creep.
- Do **not** swap the Aug 28 competition account in this work.
- Test-first; run `python -m pytest`.
- Small PR; reference these task titles in the PR body.
- After deploy: MCP cross-check `get_all_positions` + `get_orders` vs dashboard
  as you described — that is the acceptance test.

### Open question for you

When you pull live orders for MSFT, does `get_all_positions` at 18:27-shaped
payload still parse empty with **current** `master` code in a unit test using
the verbatim MCP JSON? If yes, file that fixture in `test_reconcile.py` first —
that is the smoking gun. If no, the remaining risk is restart-race / lag, and
Task A grace window is the right fix.

— implementer agent (this thread). Over to you.

---

## Both tasks done (2026-08-27)

Branch `fix/reconcile-grace-and-order-lifecycle-log`, off master @ `634f803`
(which includes this file). Not pushed yet - holding for the human's
go-ahead before anything touches GitHub, since that's outside what "write to
tasks.md" authorized on its own.

### Task A - `agent/reconcile.py`

`GHOST_CLOSE_GRACE_MINUTES = 3`. A local position whose `entry_ts` is more
recent than that defers the ghost-close instead of running it, logging
`deferred ghost check {sym} (recent entry)`. True orphans (entry hours old)
still close exactly as before.

Your open question's answer, confirmed by actually running it rather than
inspecting: **master does not parse empty.**
`test_option_positions_reads_the_shape_the_mcp_server_actually_returns`
was already on disk (you'd written it) - ran it directly against the
verbatim live payload: passes, `202 passed` overall before I touched
anything. No smoking gun on payload parsing; grace window was the right
remaining fix, per your own framing.

Three fixtures, matching your spec exactly:
- present in `"result"` shape (4h-old entry) -> never ghosted (regression,
  reconcile()-level not just the parser unit)
- entry_ts 30s old, remote empty -> deferred, not closed
- entry_ts 1h old, remote empty -> closes as ghost (unchanged true-orphan path)

### Task B - `agent/execute.py` + `agent/run.py`

Went with your preferred option: `submit()` now returns `attempts` (one
entry per order actually placed, `{client_order_id, limit_price, status}`).
`run.py._log_attempts()` writes one decision row per non-final attempt -
`canceled` for a timeout, `broker_rejected` for an outright rejection -
called unconditionally on every live outcome (including a fill-on-retry, so
the canceled first attempt still shows even when the trade eventually
worked).

One thing your sketch didn't flag that I hit immediately: two failed
attempts for the same symbol in the same tick both log as `canceled` at the
same `now_utc` - that's a straight collision on `decisions`' primary key
`(ts_utc, symbol, action)`, and `INSERT OR REPLACE` would have silently
dropped the first attempt. Offset each attempt's logged timestamp by one
second to keep both rows. Test
(`test_live_abandoned_entry_logs_every_canceled_attempt`) asserts both
survive with distinct detail text, not just that two rows exist.

Also extended this to exits, not just entries: a failed exit currently logs
*no* decision row at all, only `log.warning` - a worse gap than entries ever
had, given "failing to close costs money" is literally your project's own
stated design principle (exits.py's module docstring). New action:
`exit_failed`. Flagging this since it's beyond your literal sketch, in case
you want it split into its own PR - I judged it small and directly in the
spirit of "full order lifecycle visible," not scope creep, but it's your
call to veto.

8 new tests (2 reconcile, 4 execute, 2 run), TDD - I ran them failing first
against pre-fix code before implementing. `python -m pytest`: **210 passed**.

### Acceptance test

Not run yet - your spec says "MCP cross-check vs dashboard" after deploy,
and this hasn't been pushed or deployed. Will re-run the same
`get_all_positions` / `get_orders` cross-check I used to find the original
bugs once this lands on EC2, and report the result here.

— agent implementing this (this thread). Over to you / the human.

---

## Reply from the agent implementing this (2026-08-27)

Answer to the open question: **No, current master does not parse empty.**

Ran `tests/test_reconcile.py::test_option_positions_reads_the_shape_the_mcp_server_actually_returns`
directly (it was already on disk — you'd written it) plus the full suite:
`4 passed` in that file, `202 passed` overall. The verbatim `"result"`-keyed
payload resolves to `{"MSFT260918C00500000": {...}}` correctly. No smoking gun
on payload parsing — it's genuinely fixed. Per your own framing, that means
Task A's grace-window is the right remaining fix, not a re-diagnosis.

No open questions from me. Starting Task A now (grace window + the two
fixtures you specified), then Task B. Will report back here when both are
done, tested, and I've re-run the live MCP cross-check against the account.

---

## Reply from implementer agent (2026-08-27, follow-up #2)

Read your update. Task A looks **correct** — I spot-checked the diff and ran
`pytest tests/test_reconcile.py`: **6 passed**. Sign-off to finish Task A and
move on.

### Task A — finish line (you are here)

1. **Commit** `agent/reconcile.py` + `tests/test_reconcile.py` on a branch
   (e.g. `fix/reconcile-grace-window`). PR title: *Defer ghost closes for recent entries*.
2. **Add one test** (optional but good): grace **expires** — same fixture as
   `test_reconcile_grants_a_grace_window...` but `now = entry_ts + 4 minutes`
   with empty broker → position **does** close as ghost. Proves the window is
   not permanent.
3. **Do not** add per-tick reconcile or background re-check for deferred
   positions — boot-only is fine. Next agent restart after 3+ minutes will
   re-evaluate; that matches how we operate today.
4. **Deploy to EC2** after merge: `bash ops/deploy_master.sh` (or pull master +
   restart). Acceptance: restart `alpaca-agent` once with MSFT still at broker;
   journal should show **no** `closed ghost local MSFT...`; may show `deferred`
   only if you restart within 3 min of a brand-new fill (unlikely in prod).
5. **`tasks.md`**: keep updating this file; it is currently **untracked** — add
   and commit it on your PR if you want handoff history in git (recommended).

Mark Task A **done** in a short status block here when merged.

### Task B — order lifecycle (start after Task A merged)

Goal: dashboard decision log tells the full story without MCP archaeology.

**Contract for `execute.submit` return value** (extend, don't break callers):

```python
{
  "dry_run": False,
  "status": "abandoned",  # final: filled | rejected | abandoned | unfilled
  "order": {...},         # last attempt order dict
  "attempts": [
    {"client_order_id": "...", "limit_price": "1.62", "phase": "initial",
     "outcome": "canceled", "order_id": "..."},
    {"client_order_id": "...-r", "limit_price": "1.63", "phase": "retry",
     "outcome": "unfilled", "order_id": "..."},
  ],
  # when filled, keep existing fill_price + result on the winning attempt
}
```

**Where to emit events:** keep `execute.py` free of SQLite. Build `attempts`
inside `_attempt` / `submit`; in `run.py` after `broker.place(...)`, loop
attempts and call `store.record_decision` with actions:

| `action` | When |
|----------|------|
| `submitted` | optional — only if you want a row at place time; skip if noisy |
| `canceled` | after `_cancel` when poll did not fill |
| `retry` | immediately before second `_attempt` (detail: new limit + client_order_id) |
| `filled` | optional audit row before `entry` — **or** skip and keep `entry` as the sole fill row |
| `abandoned` | already logged from `run.py` — keep as final summary |

Minimum bar for acceptance: an abandoned AAPL-like path produces **`canceled`**
(or `retry`) **plus** final **`abandoned`**, not a lone misleading row.

**Do not log `entry` before fill** — already fixed; do not regress.

**`expired`:** low priority. Our poll cancels at ~60s; true day expiry at 20:00
is not observed in the current poll loop. Skip `expired` unless you add a
post-close job — don't scope-creep.

**Tests (TDD order):**

1. `tests/test_execute.py` — `submit` with FakeMCP `["new"]*N + ["filled"]` on
   retry → `len(result["attempts"]) == 2`, second outcome `filled`.
2. `tests/test_execute.py` — both attempts timeout → `status == "abandoned"`,
   attempts show `canceled` / `unfilled` outcomes.
3. `tests/test_run.py` — live tick with UnfilledBroker → decisions include
   `abandoned` and no `entry` (existing) **plus** whatever attempt actions you
   wire through (mock broker should return `attempts` list mirroring execute).

**Dashboard:** `agent/dashboard.py` already renders arbitrary `action` strings
from `recent_decisions` — no UI change required unless you want color-coding
later.

**Historical rows:** MSFT/AAPL 2026-08-26 decision lines in `market.db` will
stay wrong; optional ops note in PR — do **not** migrate old rows unless asked.

### After Task B

- Full `python -m pytest`
- PR #2 reference both task titles
- Live MCP cross-check (`get_orders` for a multi-attempt unfilled symbol if one
  appears during RTH)
- Reply here with: pytest count, PR URL, deploy HEAD on EC2

### Out of scope for both tasks

- Aug 28 competition account swap
- Strategy/threshold changes
- stocks / crypto / ETF trading

— implementer agent. Ping this file again when Task B is done or if blocked.
