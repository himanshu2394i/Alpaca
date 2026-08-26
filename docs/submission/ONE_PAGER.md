# One-page write-up — Alpaca Options Alpha Agent

**Project:** Autonomous paper-options trading agent  
**Event:** lablab.ai × Alpaca AI Trading Agents Hackathon (28 Aug – 4 Sep 2026)  
**Stack:** Alpaca Trading API · Alpaca MCP server · Alpaca CLI · Claude (optional) · Python

---

## AI logic

The agent runs a 60-second tick loop against live IEX equity bars stored in SQLite.

1. **Screen (deterministic).** For each underlying in a 30-name liquid universe, require session move ≥ 0.5× ADR, relative volume ≥ 1.5, and price on the correct side of EMA(20). A multi-timeframe filter then confirms when history allows: 4H Supertrend + RSI, 15m EMA(200). During warmup the MTF layer fails open so day-one trading is not starved.
2. **Decide (AI).** Claude receives only contracts that already passed liquidity/delta/DTE gates and chooses enter vs skip with a short thesis. `--deterministic` mode skips the LLM and picks a mid-delta contract — useful for demos and outages.
3. **Nothing the model says can bypass risk.** Hard gates run after the LLM. Rejected and skipped decisions are written to an audit log the dashboard can show.

Exits are rule-based (stop / target / time), not LLM-driven.

---

## Risk gates

| Control | Value |
|---------|-------|
| Size per trade | ≤ 2% of equity |
| Max options deployed | ≤ 10% of equity |
| Max concurrent positions | 5 |
| Daily loss halt | −3% |
| Peak drawdown halt | −8% |
| No new entries after | 15:30 ET |
| Contract filters | DTE 3–45, delta 0.35–0.55, spread ≤ 10%, min prior volume |
| Kill switch | `HALT` file stops entries; exits still run |
| Data safety | No bars for 5 minutes during RTH → halt new entries |

**Execution:** limit orders only via MCP `place_option_order`. Poll ≤ 60s → cancel → one retry at the ask/bid. Local positions open only on a true fill (`filled_qty > 0`). Unfilled attempts log `abandoned` / `unfilled`, never a fake `entry`. Boot reconcile syncs SQLite to Alpaca and refuses to wipe locals on a bad broker payload.

---

## Alpaca infrastructure

| Layer | Role |
|-------|------|
| **Trading / Market Data API** | IEX bar stream + REST warm start (`agent.ingest`); account equity |
| **MCP server** | Option chains, quotes, place/cancel/close, positions, account — used by the live agent loop |
| **Alpaca CLI** | Ops: `ops/health.sh`, `ops/eod_snapshot.sh`, `ops/cli_demo.sh` (account, positions, clock) |
| **Paper trading** | All development and competition trading on Alpaca paper; agent runs `--live` on EC2 |

**Runtime:** three systemd services on a US-East VM — ingest, agent, read-only dashboard. Application URL: public dashboard on port 8080.

---

## What judges should notice

- Options-only P&L path with explicit risk above the model  
- Full autonomy on a schedule (not a notebook that “places one trade”)  
- MCP for trading path + CLI for ops (both required stack pieces)  
- Fill discipline and reconcile so paper P&L matches broker reality  
