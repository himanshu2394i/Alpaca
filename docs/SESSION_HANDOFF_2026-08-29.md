# Session handoff — 2026-08-29

Full context transfer for the next agent or session. Written because the current
session is approaching its context limit.

**Read this file top to bottom before doing anything.** It contains every question
asked, every finding, every decision, and every open item from the session that
produced `docs/ALPACA_HACKATHON_REFERENCE.md` and the current `README.md`.

---

## 0. Who and what

- **User:** Himanshu (`himanshu2394i`, REDACTED-EMAIL). Learning software
  engineering. Explicitly asked for explanations in plain language and said *"I don't
  know anything about finance."* Wants to be taught, not just handed output.
- **Project:** `D:\Devpost\2alpaca` — an autonomous options trading agent for the
  lablab.ai × Alpaca AI Trading Agents Hackathon.
- **Repo state at handoff:** branch `master`, HEAD `d240493`, 49 commits, no tags.
  Uncommitted: `README.md` (modified), `docs/ALPACA_HACKATHON_REFERENCE.md` (untracked).
- **Tests:** 211 passing, ~12s, no credentials needed. Verified this session.

---

## 1. Conversation log — every exchange in order

### Exchange 1 — "read all the documentation"

User pasted the hackathon URL and the full resource list from the event page
(Getting Started; Alpaca Skills; Trading API; Market Data API; JS SDK; Python SDK;
CLI; Trading MCP Server; Multi-Agent AI Trading System; Trading CLI Docs; SDKs &
OpenAPI Specs) and asked for all of it to be read.

**Method note that matters:** `WebFetch` returns **HTTP 403 on lablab.ai**. The
in-app browser (`mcp__Claude_Browser__*`) works. Alpaca docs return clean markdown
by appending `.md` to any URL; the full index is at
`https://docs.alpaca.markets/us/llms.txt`.

Output: the hackathon brief plus a gap analysis against the repo. All of it is now
consolidated in `docs/ALPACA_HACKATHON_REFERENCE.md`.

### Exchange 2 — the Rule Book hunt

User reported two questions they had asked LabLab admins, and the answers received:

> **Q1.** Rule Book says demo apps should use Streamlit, Replit, or Vercel. I'm
> deploying a Blazor WebAssembly app that publishes to plain static files and hosting
> it on Vercel. Is that compliant, since the framework isn't one of the three named?
>
> **Q2.** Is prep code written before kickoff allowed in the repo, or does all
> committed code need to be written during the window?

> **LabLab AdminAPP — 11:23 AM:** "1. Hosting your Blazor WebAssembly app on Vercel
> is compliant since Vercel is one of the allowed platforms for demo applications,
> even if the framework isn't specifically named. 2. All committed code must be
> written during the hackathon window; prep code written before kickoff should not be
> included in the repo."

User then asked: **"find this rule book"**.

**Found:** `https://lablab.ai/hackathon-rules`. Also read
`https://lablab.ai/delivering-your-hackathon-solution` (Submission Guidelines),
`https://lablab.ai/terms-of-use` §16 Participation Terms, and
`https://lablab.ai/ai-articles/hackathon-guidelines`.

**Findings:**

- Q1 answer **is** backed by written rule: *"Demo Application Platform: Use
  Streamlit, Replit, or Vercel."* It constrains the hosting platform, not the framework.
- Q2 answer is backed by **nothing**. No published lablab document addresses when code
  must be written. The event page even says *"get a head start on your project"*
  before kickoff.
- The Submission Guidelines page carries a stale "IBM Bob Report" requirement from a
  different event — these generic pages are not tailored per hackathon.

### Exchange 3 — the fabrication question

> User: *"so what do we do about the time building requirement should i make a new
> repo and we keep on adding pr and commits to it and finish in belieable 1 2 days"*

**This was declined.** Staging commits to look like 1–2 days of work when the code
took five days is fabricating evidence for judges, and falls under the Rule Book's
Ethical Conduct clause (disqualification, not a score deduction).

**Position taken, and it still stands:** back-dating or rewriting commit timestamps
is off the table. A fresh repo is fine; a *disguised* one is not. The distinction is
disclosure.

Practical argument recorded at the time: it wouldn't survive contact anyway — the
competition Alpaca account has timestamped activity, the EC2 box has logs and systemd
units predating kickoff, the old repo has dated PRs #1–#5, and any build-in-public
social post is dated.

### Exchange 4 — draft the message

> User: *"draft a mssg genenral one without the follow up"*

Two Discord drafts were produced asking for clarification on the code-timing standard
without framing it as a follow-up. **These were never needed** — see Exchange 5.

### Exchange 5 — official Alpaca guidelines land

User pasted Alpaca's **"Official guidelines from Alpaca"** post plus the full FAQ.
This is now reproduced verbatim in `docs/ALPACA_HACKATHON_REFERENCE.md` §16.

**It resolved Exchange 2–4 in the user's favour:**

| FAQ question | Official answer |
|---|---|
| May I reuse or depend on my own pre-existing library or application? | **Yes** |
| May I set up infrastructure, boilerplate, or supporting components before kickoff? | **Yes** |
| Must pre-event work be disclosed in the README or final submission? | **Yes** |
| Repo created before kickoff with only README/LICENSE/.gitignore? | Yes, though a fresh repo is recommended |

**The admin's Q2 answer is contradicted by the sponsor's own written FAQ.** Alpaca's
guidance governs. No new repo needed, no restructuring — **disclosure only**.

Other decisive facts from that post (all now in §16):

- Hackathon window: **Fri 28 Aug 09:30 ET → Fri 4 Sep 09:30 ET**
- Agent must begin trading the competition account **Mon 31 Aug 09:30 ET** (19:00 IST)
- **Official P&L window: Mon 31 Aug 09:30 ET → Fri 4 Sep 09:30 ET**
- **Equity snapshot: EOD Thursday 3 Sep**, including exercises/assignments for
  options expiring that day
- Judged on **total account equity, not cash balance**
- **No** Sharpe / Sortino / max drawdown — they were asked directly and said equity
- P&L is not the sole factor; combined with creativity, autonomy, robustness
- No scoreboard
- Repo **may be private during** the hackathon
- **UI not required** — repo alone suffices if the agent only places orders
- **No restrictions on options strategies**
- Blazor WASM on Vercel confirmed compliant (independently of the admin)
- **Basic plan latest option quotes and chains are REAL-TIME.** The 15-minute limit
  applies only to historical bars and trades. Dashboard charts lag; rely on API data.
- Both free and paid data tiers permitted; no automatic OPRA/Algo Trader Plus access

> User: *"include these to in that alpaca hackathon reference"* — done.

**This corrected an earlier error in that doc**, which had said the free indicative
feed was 15-minute delayed. It is not, for the latest quote. The correction is marked
inline in §10.

### Exchange 6 — the README

> User: *"write the full readme for me to so i can see whats working today and how i
> currently kind of have very little idea of how things are made"*

All 13 agent modules were read and the test suite run before writing. README rewritten.

**Bug discovered while reading:** see §4 below.

### Exchange 7 — show it

> User: *"show me the readme for now"* — file sent, rendered.

### Exchange 8 — make it a handover doc

> User: *"write the architecture and everything there in readme make it so a junior
> can take on this project"*

`indicators.py` (full), `tests/conftest.py`, `tests/helpers.py`, `tools/replay.py`
and the systemd units were read. README rewritten as a handover document with three
Mermaid diagrams, module contracts, an extension guide, a debugging playbook, an
incidents section, and a 25-term glossary.

### Exchange 9 — two problems

> User: *"the arhcitecture flowchart dont load"* [interrupted]
> *"idk anyhting about finance so im not able to understand shit from this readme
> give me a list of topics to study to understand it"*

**Two open items from this, one still unresolved:**

1. **Mermaid diagrams do not render for the user. NOT YET FIXED.** See §5.
2. A six-tier study list was produced (market basics → price data → indicators →
   options → risk management → optional spreads). **It was delivered in chat only and
   is not written to any file.** Reproduced in §6 below so it isn't lost.

### Exchange 10 — Paper Trading Skill email

User pasted Alpaca's 26 Aug marketing email announcing the Paper Trading Skill.

The real `SKILL.md` was read (not the announcement). **Finding: it is a
confirmation-gated, human-in-the-loop workflow** — *"Default: confirmation ON"*, no
order submitted without a preview and permission. **Not usable** as the execution path
for an autonomous agent, which is the hackathon's first core requirement.

**Two facts extracted that matter:**

- **`bracket`, `oco` and `oto` are equities-only.** An options order cannot carry a
  broker-side stop-loss or take-profit. The agent *must* manage its own exits — which
  is exactly what `agent/exits.py` does. **This validates the architecture**; it is
  worth saying in the demo.
- **`mleg` carries up to 4 legs** — enough for an iron condor, and the ceiling.

Also: the skill uses `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`, while MCP and CLI use
`ALPACA_API_KEY` / `ALPACA_SECRET_KEY`. Both exist.

### Exchange 11 — Backtest Skill

> User: *"read that backtest skill too"*

Read in full. CLI-based, deterministic, produces a fixed artifact bundle. Details in
`docs/ALPACA_HACKATHON_REFERENCE.md` §8.

**Critical finding:** the skill's own guardrails forbid *"claiming support for
unsupported products — options require explicit contract selection and fill logic."*
**It does not backtest options out of the box.**

**Second critical finding:** `tools/replay.py` **is not a backtest.** It measures
screener *fire rate* — candidates per day, idle sessions. No P&L, no equity curve, no
win rate, no benchmark, no drawdown. **The project currently has zero evidence that
the entry signal is profitable.**

### Exchange 12 — this document

> User: *"So our agent limit is about to be reached. Can you make a document which
> includes the full context of our chat?"*

---

## 2. Files created or modified this session

| File | State | What it is |
|---|---|---|
| `docs/ALPACA_HACKATHON_REFERENCE.md` | **untracked, new** | ~1,150 lines. 16 sections. Rules, judging, timeline, full Alpaca API/CLI/MCP reference, both Skills, options mechanics, market data, gap analysis, and Alpaca's official FAQ verbatim in §16. |
| `README.md` | **modified, uncommitted** | Rewritten as a junior-onboarding handover doc. |
| `docs/SESSION_HANDOFF_2026-08-29.md` | this file | Context transfer. |

**Nothing has been committed this session.** No code was changed — only documentation.

---

## 3. Decisions taken and why

| Decision | Reasoning |
|---|---|
| **Do not fabricate commit history** | Ethical Conduct clause = disqualification. Also unnecessary once Alpaca's FAQ landed. |
| **Keep the existing repo, disclose the baseline** | Alpaca FAQ permits pre-existing work with disclosure. A fresh repo is "recommended" but not required, and keeping history preserves the audit trail. |
| **Alpaca's official guidance overrides lablab generic pages and admin answers** | It is the sponsor's written, event-specific ruling. Recorded as an authority note at the top of the reference doc. |
| **Do not adopt the Paper Trading Skill for execution** | It is confirmation-gated; the agent must be autonomous. |
| **Scope any backtest to the underlying, not options** | The skill cannot do options; historical option data only exists from Feb 2024 anyway. Backtest the screener signal and label it honestly. |

---

## 4. The bug — highest priority

**Premium-based exits never fire in the live loop.**

Mechanism, verified by reading the code:

1. `run.loop()` calls `tick()` **without** a `premiums` argument
2. `tick()` signature defaults it: `premiums = premiums or {}`
3. `exits.scan()` passes `premiums.get(position["symbol"])` → always `None`
4. `exits.check()` guards the premium block with `if premium is not None and ...`
5. Therefore the **−40% premium stop** and **+80% premium target** never trigger

Only underlying-based stop/target and the forced exits (DTE ≤ 2, competition end)
actually work. Two of six exit conditions are dead.

**This runs during the scored P&L window.** It is tracked as `D2.3` in `tasks.md`.

**Fix shape:** in `run.loop()`, call `get_option_latest_quote` (MCP) for each open
position, build `{occ_symbol: mid_price}`, pass it into `tick(..., premiums=...)`.
Add a test in `tests/test_run.py` asserting the dict reaches `exits.scan`.

---

## 5. Open items

Ordered by priority. Items 1 and 2 are time-critical.

| # | Item | Notes |
|---|---|---|
| 1 | **Fix premium exits** (§4) | Broken in the P&L path. `D2.3`. |
| 2 | **Monday cutover — H1/H2/H3** | Fresh $100k paper account, keys onto the VM, `ops/competition_cutover.sh`. **Hard deadline: Mon 31 Aug 09:30 ET = 19:00 IST.** Human-only. |
| 3 | **Tag `pre-kickoff-baseline`** | README already references this tag; **it does not exist**. Last pre-kickoff commit is `286f74d` (2026-08-28T17:52:13+05:30), before both the 19:00 IST Alpaca window start and the 20:30 IST lablab kickoff. Run: `git tag pre-kickoff-baseline 286f74d` |
| 4 | **Fix Mermaid rendering in README** | User reported diagrams don't load. Unresolved. Options: verify plain ```mermaid fences, or replace with ASCII diagrams which always render. |
| 5 | Backtest via `alpaca-trading-backtest` | Scoped to the underlying signal. Strong judging evidence; no deadline. |
| 6 | `mleg` multi-leg spreads | Highest creativity upside, largest build. Up to 4 legs. |
| 7 | Commit this session's docs | `README.md` + both docs files are uncommitted. |
| 8 | Remaining `tasks.md` lanes | D1.1–D1.5, D2.1/D2.2/D2.4/D2.5, D3.1–D3.6, D4.x — all still `TODO`. |
| 9 | H4/H5 | Submit account ID on lablab; record video, slides, cover image before 4 Sep. |

---

## 6. The study list (delivered in chat, preserved here)

The user asked for topics to study, knowing no finance. Six tiers, dependency-ordered.
Roughly two days of focused reading; the finance surface in this codebase is ~20
concepts.

**Tier 1 — Market basics (half a day).** Stock/exchange/broker · **bid, ask, spread,
mid** (`gates.Contract.mid`, `.spread_pct`) · **market vs limit order** (`execute.py`
uses limit only) · volume · **RTH** (`indicators._is_rth`) · paper trading.
*Skip: market makers, dark pools, Level 2.*

**Tier 2 — Price data (2–3 hours).** OHLCV bars/candlesticks (the `bars` table *is*
this) · timeframes and resampling (`indicators.resample_bars`) · UTC vs ET and DST.

**Tier 3 — Indicators (half a day).** EMA · ATR/true range · **ADR** (the 0.5-ADR
trigger) · **RVOL** · RSI · Supertrend · multi-timeframe analysis. Plus the concept of
**trend vs mean reversion** — why the EMA(20) check exists.

**Tier 4 — Options (a full day; this is the big one).** In order: what an option
contract is → calls vs puts → strike/expiry/premium → **the 100 multiplier** →
**OCC symbology** (`gates.parse_occ`) → ITM/ATM/OTM and **auto-exercise at ≥$0.01**
→ intrinsic vs extrinsic → **theta/time decay** → **delta** (the 0.35–0.55 band) →
gamma and the **gamma cliff** (why `min_dte: 2`) → IV → options liquidity (why
`prev_volume ≥ 500`).
*Skip: vega, rho, vol surfaces, pin risk, early assignment.*

**Tier 5 — Risk management (2–3 hours).** Position sizing as % equity (2%) · stop
loss / take profit · reward-to-risk (1:2 in `exits.levels`) · **drawdown vs daily
loss** (−8% vs −3%) · peak equity / high-water mark · portfolio exposure caps ·
**equity vs cash / mark-to-market** (the hackathon judges total equity).

**Tier 6 — optional, for the unbuilt gaps.** Vertical spreads · iron condor ·
multi-leg max-loss margining.

**One-day path:** Tier 1 → Tier 4 items 1–6 and 9 → Tier 5.

**Resources:** Investopedia for individual terms; the OCC's *Characteristics and Risks
of Standardized Options* (linked at the bottom of the README) for options
authoritatively; Alpaca's own options docs for platform mechanics.

**Offered but not yet done:** a "trading concepts explained in your own code" section
that maps each concept to the exact function implementing it, so the finance is
learned by reading the existing codebase.

---

## 7. Facts worth not rediscovering

**Tooling**
- `WebFetch` gets **403 from lablab.ai**. Use the in-app browser.
- Alpaca docs: append `.md` to any URL for clean markdown. Index at
  `https://docs.alpaca.markets/us/llms.txt`.
- A large `cat > file <<'EOF'` heredoc failed in this environment; the `Write` tool
  works.

**Rules**
- Alpaca's official FAQ **overrides** lablab's generic pages and individual admin
  answers.
- Judged on **total equity**, not cash. **No risk-adjusted metrics.**
- Snapshot **EOD Thu 3 Sep**, including that day's expiry exercises/assignments.
- Repo may be private during the event; **make it public before submitting** — the
  lablab guidelines penalise a private repo at judging.
- UI not required.

**Platform**
- Basic-plan **latest option quotes are real-time**; only historical bars/trades are
  15-min delayed.
- **`bracket`/`oco`/`oto` are equities-only** — options cannot carry broker-side
  stops. Self-managed exits are mandatory, not a shortcut.
- `mleg` supports **up to 4 legs**.
- Options TIF: Alpaca's own sources disagree (`day` only per OpenAPI vs `day`+`gtc`
  per two product pages). Default `day`; let Alpaca reject rather than pre-blocking.
- Historical option data exists only **from February 2024**.
- Websocket cap is **30 symbols** on the free tier, and Alpaca rejects the *entire*
  subscription past the cap rather than trimming — hence `config.MAX_WS_SYMBOLS`.

**Codebase**
- `tools/replay.py` is a **fire-rate measurement, not a backtest**. No P&L evidence
  exists for the strategy.
- 211 tests pass without credentials or network — `gates.py` and `indicators.py` are
  pure; `tick()` takes a fake broker; `decide()` takes an injected client.
- `decide.decide()` is the documented **swappable seam** for a multi-agent ensemble.

---

## 8. Where to start

1. Read `README.md` (architecture, module reference, debugging playbook).
2. Read `docs/ALPACA_HACKATHON_REFERENCE.md` §16 first — it is authoritative — then §4
   for the rules position and §14 for the gap list.
3. Read `tasks.md` for the coordination board and human-only items.
4. Then fix §4 above.
