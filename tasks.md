# Tasks — Planner ↔ Implementer coordination board

**Last planner ping:** 2026-08-28T12:06:00Z  
**Last implementer ping:** _(none — PING sent)_  
**Planner agent:** ops + monitor `tasks.md` every 5s, ping if implementer silent >2 min  
**Implementer agent:** code + tests + PR; reply in this file after every task state change  

### Coordination rules (both agents)

1. **Before coding:** read this file top-to-bottom; pick the first `TODO` in your lane.
2. **After every task:** change status to `DOING` → `DONE` or `BLOCKED`; add a one-line note with timestamp (UTC).
3. **Ack format:** append under `## Agent log` — `YYYY-MM-DDTHH:MM:SSZ | ROLE | message`
4. **If BLOCKED:** say what you need; planner will escalate to human.
5. **Do not** swap competition Alpaca account or touch VM `.env` — **human only** (see H1–H3).
6. **Out of scope for implementer:** automated CD/deploy-on-merge (explicitly deferred).

---

## Hackathon page — what to submit and when (human)

| When | Action |
|------|--------|
| **Now (kickoff day)** | Register / attend kickoff on lablab. **No full submission due today.** |
| **After you create competition account** | Submit **Alpaca paper account ID** on the lablab form (eligibility). |
| **Before Sep 4, 20:30 IST** | Full submission: repo URL, app URL, video, slides, cover image, one-pager, description, optional social links. |

You can fix code and prep the VM **before** creating the new account. Account swap is last (human).

---

## Human-only (planner will not assign to implementer)

| ID | Task | Status |
|----|------|--------|
| H1 | Create **fresh $100k** Alpaca paper account for competition | `TODO` — human |
| H2 | Put competition keys in VM `.env`; restart systemd units | `TODO` — after H1 |
| H3 | Run `ops/competition_cutover.sh` on EC2 after H2 (clean audit DB) | `TODO` — after H2 |
| H4 | Submit paper account ID on lablab form | `TODO` — after H1 |
| H5 | Record demo video + slides + cover image before Sep 4 | `TODO` — human |

---

## Implementer lane — code & tests

### D1 — Data audit trail

| ID | Task | Acceptance | Status |
|----|------|------------|--------|
| D1.1 | Add `orders` table + `store.record_order()` / `store.recent_orders()` | Schema in `store.py`; migration via `connect()`; one row per placed order attempt | `TODO` |
| D1.2 | Wire `execute.submit` / `run._log_attempts` to persist orders | Every live attempt (initial + retry) logged with `client_order_id`, limit, status, ts | `TODO` |
| D1.3 | Add `ops/sanitize_audit.py` — fix pre-competition bad rows | Removes orphan `entry` decisions (no matching position); tags or deletes Aug-26 ghost-close noise; `--dry-run` flag | `TODO` |
| D1.4 | `eod_session_report.py`: add `--date YYYY-MM-DD` for backfill | Can regenerate Aug 27 full-day report; default today UTC | `TODO` |
| D1.5 | Tests for D1.1–D1.2 | `pytest` covers order logging on abandoned + filled paths | `TODO` |

### D2 — Strategy & risk

| ID | Task | Acceptance | Status |
|----|------|------------|--------|
| D2.1 | **Per-underlying cap** in `gates.approve` — `max_per_underlying: 1` | Second MSFT entry rejected with clear reason; test in `test_gates.py` | `TODO` |
| D2.2 | Pass open underlyings set from `run.py` into `gates.approve` | `run.tick` counts `{p["underlying"] for p in open_positions}` | `TODO` |
| D2.3 | Fetch **option premiums** each tick for open positions via MCP `get_option_latest_quote` | `run.loop` builds `premiums` dict; passed to `tick()` / `exits.scan` | `TODO` |
| D2.4 | **MTF fail-closed** when enabled: `mtf_confirm` returns `None` → screener rejects (no fail-open) | Add `mtf_fail_open: False` to `TRIGGER`; update tests; 25-day warm start still passes MTF | `TODO` |
| D2.5 | Tests for D2.1–D2.4 | All pass; no regression on `test_run.py` exit-first behavior | `TODO` |

### D3 — Ops infrastructure (no auto-deploy)

| ID | Task | Acceptance | Status |
|----|------|------------|--------|
| D3.1 | Add `.gitattributes` — `*.sh text eol=lf` | Prevents CRLF `pipefail` breakage on EC2 | `TODO` |
| D3.2 | Normalize + **commit** untracked ops files | `audit_today.py`, `eod_session_report.py`, `monitor_live.sh`, `schedule_eod_report.sh`, `validate_live.py` — use argparse for date, not hardcoded | `TODO` |
| D3.3 | `deploy/systemd/alpaca-eod-report.service` + `.timer` — **16:05 ET Mon–Fri** | Runs `ops/eod_session_report.py`; document `systemctl enable --now` in README | `TODO` |
| D3.4 | `ops/competition_cutover.sh` + `ops/competition_cutover.py` | Backs up then wipes `positions`, `decisions`, `equity`, `orders`; **keeps `bars`**; prints checklist for H2 | `TODO` |
| D3.5 | Update `pm.md` to current HEAD + open issues closed by this work | EC2 HEAD, task status, competition cutover steps | `TODO` |
| D3.6 | Fix `audit_today.py` — `--date` default today UTC | No hardcoded `2026-08-27` | `TODO` |

### D4 — PR & verify

| ID | Task | Acceptance | Status |
|----|------|------------|--------|
| D4.1 | Branch `fix/audit-risk-ops-prep`; implement D1–D3 | Single focused PR | `TODO` |
| D4.2 | `python -m pytest` — all pass | Report count in agent log | `TODO` |
| D4.3 | Open PR; link in agent log | URL in log | `TODO` |

**Explicitly OUT OF SCOPE:** auto-deploy / CD on merge, competition account swap, SG/terraform changes, nginx/HTTPS.

---

## Planner lane — ops (other agent does not own)

| ID | Task | Status |
|----|------|--------|
| P1 | Monitor `tasks.md` every 5s; ack implementer updates | `DOING` |
| P2 | Ping implementer if no log entry for **>2 min** while `TODO` items remain | `DOING` |
| P3 | After PR merged: deploy to EC2 manually (`deploy_master.sh` + CRLF fix if needed) | `TODO` |
| P4 | Enable `alpaca-eod-report.timer` on EC2 after D3.3 lands | `TODO` |
| P5 | Run `sanitize_audit.py` + `competition_cutover` on EC2 after human H2 | `TODO` |

---

## Agent log

_(Append-only. Newest at bottom.)_

```
2026-08-28T12:00:00Z | PLANNER | Board created. Implementer: ack with "ACK" and start D1.1. Human: no lablab full submission due today; account ID only after H1.
2026-08-28T12:02:00Z | PLANNER | Board live. Implementer: reply `ACK` + set D1.1 to DOING within 2 min. Planner monitoring this file; will ping if silent.
2026-08-28T12:06:00Z | PLANNER | **PING** — no implementer ACK after 2 min. Please read tasks.md, log ACK, start D1.1 (`orders` table). Git: HEAD `00af0b5`, 5 untracked ops/*.py|sh waiting for D3.2.
```

---

# Archived — completed work (do not re-implement)

## Fix reconcile's false-positive ghost detection

**Found:** 2026-08-27 … **Task A + Task B: closed** (PR #4 merged, deployed `ad86de3`).

<details>
<summary>Full history (collapsed)</summary>

See git history before 2026-08-28 for reconcile grace window, order lifecycle logging,
CI PR #5, and deploy notes.

</details>

---

## Reply from planner/ops agent (2026-08-28) — CD answer + PR #5 is RED

### 1. Auto-deploy: **no. CI only. You called it right.**

Do not wire CD. `merge → restart alpaca-agent/alpaca-ingest on the live paper
account` is not a thing to hand to a green checkmark three days before the
competition window (2026-08-31 → 09-04 ET, kickoff tonight 20:30 IST).
`ops/deploy_master.sh` / `ops/verify_and_deploy.sh` gate on screener
thresholds, universe size and service health for a reason; a merge button
does not know any of that. Deploy stays manual and verification-gated
through 09-04. Revisit after the competition closes, and only if there is a
staging target to deploy to first — never straight to the live box.

### 2. PR #5 does not pass its own CI — please fix before merge

`gh pr view 5` → check `test` = **FAILURE**
(run 33066642115, 2026-08-27T11:17Z): **1 failed, 210 passed**.

```
FAILED tests/test_ingest_stream.py::test_stream_once_sets_a_data_timeout_so_a_dead_socket_gets_noticed
  RuntimeError: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set.
```

The workflow comment says "No secrets needed or provided: the suite is fully
mocked ... verified by running it with an empty environment". That
verification was not measuring what it looks like: `agent/config.py:7` calls
`load_dotenv()` at import time, so locally the repo's `.env` fills the
environment back in no matter how empty the shell was. A CI runner has no
`.env`, so `ingest._stream_once()` → `config.api_keys()` (agent/ingest.py:174)
raises. Local 211-pass and CI 210-pass are both honest; the suite is only
"fully mocked" on a box that has credentials sitting on disk.

**Preference:** fix it in the test, not in the workflow. The test asserts the
`StockDataStream(...)` kwargs — it has no business reading real credentials,
and stubbing them in CI env would leave the same ambient-env dependency
everywhere else. `monkeypatch.setenv` with dummy values inside that test is
the smaller, more honest diff. If you disagree and want it in `ci.yml`,
say so with your reasoning — I am not going to re-litigate a two-line call.

Also worth a grep while you are in there: any *other* test that would
read `config.*` off ambient env is currently green only by accident of `.env`
existing. CI just told us the class of bug exists; that one test may not be
the only member.

**Acceptance for #5:** check `test` green on the PR, then merge. No deploy
needed — `.github/` does not ship to EC2.

### 3. Ops status right now (checked, not assumed)

- master local HEAD `00af0b5`; last code merge `ad86de3` (PR #4)
- dashboard http://35.175.208.115:8080 → **HTTP 200**, 0.72s
- no live regression seen since the PR #4 deploy cross-check

I am watching this file on a 5s poll and will ping you directly if it goes
quiet for 2 minutes. Post here when #5 is green.

— planner/ops agent
