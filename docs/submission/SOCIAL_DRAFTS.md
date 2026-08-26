# Build-in-Public drafts (tag both lablab.ai and Alpaca)

Post during **28 Aug – 4 Sep 2026**. Submit up to **5 links**.

**X tags:** `@lablabai` `@AlpacaHQ`  
**LinkedIn:** mention lablab.ai and Alpaca company pages.

Copy, tweak in your voice, add a screenshot of the dashboard when you can.

---

## Post 1 — Kickoff / stack (Aug 28)

Building an autonomous **options** agent for the @lablabai × @AlpacaHQ hackathon.

Stack: live IEX bars → momentum + MTF filter → Claude decides → hard risk gates → Alpaca MCP limit orders. Ops via Alpaca CLI. Paper only.

Dashboard live while we prep the competition account.

#AI #AlgoTrading #Alpaca

---

## Post 2 — Risk above the model

Lesson from paper trading: the LLM should never be the last word.

Our Claude layer only picks among contracts that already passed delta/DTE/liquidity checks. Size, daily loss, and drawdown halts are deterministic — the model can’t bypass them.

Building in public for @lablabai @AlpacaHQ.

---

## Post 3 — Fill discipline (setback → fix)

We logged an “entry” before the limit filled. Next reconcile looked like a ghost position.

Fix: log `entry` only after `filled_qty > 0`; otherwise `abandoned` / `unfilled`. Bad broker payloads no longer wipe local positions.

@lablabai @AlpacaHQ #BuildInPublic

---

## Post 4 — Why zero trades isn’t always a bug

Quiet tape day: screener wants ≥ 0.5× ADR move and RVOL ≥ 1.5. Production gates stayed tight on purpose — P&L week isn’t a vanity fire-rate contest.

Autonomous ≠ always trading. @AlpacaHQ @lablabai

---

## Post 5 — Demo week / results (near submit)

Competition paper account live at $100k. Agent running unattended on Alpaca paper via MCP + CLI ops.

Repo + dashboard in our lablab submission. Grateful for the @lablabai × @AlpacaHQ week — sharing what worked and what we still won’t automate.

---

## Screenshot ideas

1. Dashboard equity + open positions  
2. Decision log row (`entry` / `skip` / `rejected`)  
3. Terminal: `ops/cli_demo.sh` JSON from Alpaca CLI  
4. Architecture one-liner from the README  
