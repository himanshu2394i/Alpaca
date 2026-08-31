# Alpaca AI Trading Agents Hackathon — Reference

Consolidated from the lablab.ai event page, the lablab Rule Book / Submission
Guidelines / Terms of Use, and all 11 Alpaca resources linked from the event page.
Compiled 2026-08-28. **Updated 2026-08-29** with Alpaca's official guidelines and FAQ.

> **Authority note.** Where Alpaca's official guidance (§16) differs from the generic
> lablab pages or from an individual admin answer, **§16 governs** — it is the
> sponsor's written, event-specific ruling. Two items were corrected on 2026-08-29:
> pre-kickoff work is **permitted with disclosure** (§4), and Basic-plan **latest
> option quotes are real-time**, not delayed (§10).

---

## 1. Event facts

| | |
|---|---|
| Event page | https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon |
| Dates | 28 Aug – 4 Sep 2026 |
| Hackathon window (Alpaca) | Fri 28 Aug 09:30 ET → Fri 4 Sep 09:30 ET |
| Kickoff event (lablab) | 28 Aug 2026, 20:30 IST (11:00 ET) |
| **Agent must start trading** | **Mon 31 Aug 09:30 ET** (19:00 IST) from the competition account |
| **Official P&L window** | **Mon 31 Aug 09:30 ET → Fri 4 Sep 09:30 ET** |
| **Equity snapshot** | **EOD Thursday 3 Sep** — includes Sep 3 expiry exercises/assignments |
| Submissions close | **4 Sep 2026, 20:30 IST** (11:00 ET) |
| Format | Online, 7 days |
| Prize pool | $6,300 (AlpacaDB, Inc. pays $6,000 directly in USD) |
| Teams | 1–6 people |
| Discord | https://discord.gg/lablabai |

### Prizes

| Place | Prize |
|---|---|
| 1st | $2,500 + $300 Featherless credits |
| 2nd | $1,500 |
| 3rd | $1,000 |
| Social engagement (2 teams) | $500/team + 1-month Algo Trader Plus per member |

Prize terms: 18+; not open to Alpaca employees/contractors/household or sanctioned
countries; paid to **one individual**, not a team or company; W-9 (US) or W-8BEN
(non-US) + government photo ID + bank details required; paid within 90 days of
event end after sanctions screening. US winners over $600 get a 1099-MISC. Non-US
payments default to 30% US withholding absent a valid treaty claim on the W-8BEN.
Documentation must be completed within 90 days of notification or the prize is
forfeited. Judging is final.

### Schedule

| Time (IST) | Item |
|---|---|
| Aug 28 20:30 | Kick-off |
| Aug 28 20:35 | lablab.ai opening words |
| Aug 28 20:40 | Alpaca opening words |
| Aug 28 20:45 | Introduction to the Challenge |
| Aug 28 20:55 | Hackathon Guide |
| Aug 28 21:30 | Discord Q&A |
| Sep 4 20:30 | End of submissions |

### Speakers, mentors and judges

Pawel Czech (CEO) · Chiranjeev Shah (Technical Content Marketing Associate) ·
Tony Lee (Chief Brokerage Officer) · Grace Gao (Product Manager) ·
Brandon Meyerowitz (Team Lead, Trading API)

---

## 2. Challenge requirements

Main challenge: **Options Alpha Agents**.

> Build an autonomous AI trading agent designed to generate P&L using Alpaca's
> trading platform. Develop a clear, testable trading strategy and demonstrate how
> your agent identifies opportunities, makes trading decisions, manages positions,
> and performs over the course of the competition.

### Core requirements — all three, not pick-one

1. **Autonomous agents** — must build autonomous AI trading agents using Alpaca's Trading API.
2. **MCP or CLI** — must use either Alpaca's MCP server or its CLI tools.
3. **Options trading** — all strategies must incorporate options trading.

### Account requirements

- Development: use any paper account you like. Prototyping and trading in a testing
  account before the official window is explicitly permitted.
- Judging: a **brand-new** Alpaca paper trading account created for this hackathon.
  Projects run on an existing or reused account are **not eligible for judging**.
- Competition account starting balance must be **$100,000**.
- The **same email address** may be used to create the new paper account.
- The agent must **begin trading from the competition account on Mon 31 Aug 09:30 ET**.
  Trades in a testing account before then do not count.
- One-page write-up covering AI logic, risk gates, and Alpaca infrastructure implementation.
- **A UI is not required.** If the agent runs autonomously and only places orders, the
  GitHub repo is sufficient; a hosted link is needed only if the submission includes a
  demo app judges must open.
- **The repo may stay private during the hackathon** (Alpaca FAQ). Note the lablab
  Submission Guidelines still warn that a private repo at judging time may lower the
  score — make it public before submitting.

### Extra challenge — Build in Public

Share progress on X and LinkedIn while building. Tag `@lablabai` / lablab.ai and
`@AlpacaHQ` / Alpaca. Up to **5 social post links** may be submitted.

### Technology partner

**Featherless AI** — serverless inference for open-source models. $25 credits per
participant, first-come-first-served, pay-per-request until credits run out.
Partner prize eligibility requires the partner tech to be actually integrated into
the submitted project.

---

## 3. Submission checklist

| Group | Item |
|---|---|
| Basic info | Project title |
| | Short description (≤255 chars) |
| | Long description (≥100 words) |
| | Technology & category tags |
| Media | Cover image — PNG or JPG, 16:9 |
| | Video presentation — MP4, max 5 minutes |
| | Slide presentation — PDF |
| Code & demo | Public GitHub repository |
| | Demo application platform |
| | Application URL |
| Alpaca | **Alpaca paper trading account ID** — required for judging |
| Optional | Up to 5 social post links (X / LinkedIn) |

The account ID is how judges identify your trading activity and evaluate P&L.

### Judging criteria (event page — 5, unweighted)

1. **P&L Performance** — trading performance of the agent in the paper environment.
2. **Technology Implementation** — how effectively the project uses Alpaca's Trading API, MCP server, CLI.
3. **Creativity & Originality** — concept, strategy, agent behaviour, approach.
4. **Presentation & Execution** — clarity of communication, demo of the agent in action, reasoning behind strategy and results.
5. **Social engagement** — both content quality and engagement generated (likes, comments, shares).

Note: the generic lablab Rule Book lists a *different*, older four-item criteria set
(Presentation / Business value / Application of technology / Originality). The event
page criteria are the ones that apply here.

### How Alpaca actually scores it (§16)

- Performance is measured on **total account equity, not cash balance**, at the
  official close.
- **No risk-adjusted metrics.** Sharpe, Sortino and maximum drawdown are explicitly
  *not* used — the answer to that question is just "total account equity."
- **P&L is not the sole factor.** It is combined with "the creativity, autonomy, and
  robustness of the agent trading workflow."
- **No live scoreboard** for this competition.
- Backtests and simulated shocks may be included in the write-up and repo as evidence
  of guardrails, but official P&L is the live paper account at the snapshot.

---

## 4. lablab rules — what is written, and what is not

### Rule Book — https://lablab.ai/hackathon-rules

Sections: Introduction · Submission Guidelines (Basic Information, Cover Image and
Presentation, Application Components) · Judging Criteria · Technical Issues and
Manual Submission · Ethical Conduct · Mentor and Organizer Participation · Judge's
Code of Conduct · Mini Hackathon Specific Rules.

Key clauses:

- "Failure to adhere to submission guidelines may result in a lower score or exclusion from the hackathon."
- **"Demo Application Platform: Use Streamlit, Replit, or Vercel."**
- "Public GitHub Repository: Mandatory for storing your code."
- Manual submission available for **6 hours post-hackathon** with a valid reason and
  prior approval from organizers or mentors.
- Ethical Conduct: plagiarism or gaming the voting system leads to immediate
  disqualification. lablab/partners may remove a participant for cheating,
  tampering, unauthorized automation, fraudulent behaviour, "or in any other manner
  we consider grounds for disqualification."
- Organizers may participate but are not prize-eligible; mentors/organizers who
  participate cannot judge.

### Submission Guidelines — https://lablab.ai/delivering-your-hackathon-solution

Adds format detail (5-min MP4 video, PDF slides, ≥100-word long description) and:
"If you submit a private repository, judges won't be able to fully review your work,
which may lower your overall score." Demo platform guidance: Streamlit for Python
web apps, Replit for online code execution, **Vercel to host web apps**.

Caveat: this page still carries a stale "IBM Bob Report" requirement from a
different event. These generic pages are not tailored per hackathon.

### Terms of Use §16 Participation Terms — https://lablab.ai/terms-of-use

The binding legal section, linked from Alpaca's own prize terms. Requires:
**"All submissions by participants must be original work, open source, and compliant
with the MIT License unless specified otherwise."** Prizes distributable within 90
days. lablab not liable for third-party sponsor commitments. lablab reserves the
right to amend, modify or cancel any part of the hackathon.

§17 Prize Money Payout Policy: contact prize@lablab.ai; USD only; ACH (US) or SWIFT
(non-US); 90-day document deadline with permanent forfeiture and no exceptions.

### Pre-kickoff code — RESOLVED 2026-08-29

**Pre-existing work is permitted, and must be disclosed.** Alpaca's official FAQ
(§16) answers this directly:

| Question | Official answer |
|---|---|
| May I reuse or depend on my own pre-existing library or application? | **Yes.** Judging is scoped to the agent submitted during the event. |
| May I set up infrastructure, boilerplate, or other supporting components before kickoff? | **Yes.** |
| If pre-event work is permitted, must it be disclosed in the README or final submission? | **Yes.** |
| Can I use a repository created before kickoff if it contains only a README, LICENSE, and .gitignore? | Yes, although creating a fresh repository is recommended. |

This is the "core functionality in-window, prior scaffolding disclosed" standard.
Judging is explicitly scoped to *the agent submitted during the event* — its options
workflow via Trading API with MCP or CLI, competition-account performance, and the
creativity, autonomy and robustness of the workflow.

#### Supersedes the earlier admin ruling

On 2026-08-28 a LabLab admin answered in Discord: *"All committed code must be
written during the hackathon window; prep code written before kickoff should not be
included in the repo."* That answer appears in no published lablab document — not
the Rule Book, Submission Guidelines, Terms of Use §16, or the Hackathon Guidelines
article — and it is **contradicted by the sponsor's own written FAQ above**.
Alpaca's guidance governs. The same admin exchange confirmed Blazor WebAssembly on
Vercel is compliant, which §16 also independently confirms.

The event page's Guidelines section is consistent with the FAQ:

> "Before the kickoff, browse the AI Tech and tutorials pages to read up on the
> available technologies and **get a head start on your project**."

#### What this repo must do

First commit: **2026-08-23T04:28:30+05:30**, five days before kickoff. Of 48
commits, roughly 45 predate the window — MCP bridge, screener, risk gates,
execution, exits, orchestration loop, LLM decision layer, dashboard, deploy/ops.

Required action is **disclosure, not restructuring**:

- [ ] Tag the last pre-kickoff commit as the baseline.
- [ ] README section stating what existed at kickoff and what was built in-window.
- [ ] Repeat the disclosure in the lablab submission long description.

A fresh repo is "recommended" but not required. Keeping the history plus an honest
baseline satisfies the rule and preserves the audit trail.

Back-dating or rewriting commit timestamps remains off the table — it falls under
the Ethical Conduct disqualification clause, and is now pointless as well as
prohibited.

---

## 5. Alpaca resource index

All 11 links from the event page, with their real URLs.

| # | Resource | URL |
|---|---|---|
| 01 | Getting Started | https://docs.alpaca.markets/us/docs/getting-started |
| 02 | Alpaca Skills | https://github.com/alpacahq/alpaca-skills |
| 02 | Trading API | https://docs.alpaca.markets/us/docs/getting-started-with-trading-api |
| 02 | Market Data API | https://docs.alpaca.markets/us/docs/getting-started-with-alpaca-market-data |
| 02 | Alpaca JS SDK | https://github.com/alpacahq/alpaca-trade-api-js |
| 02 | Alpaca Python SDK | https://github.com/alpacahq/alpaca-py |
| 02 | Alpaca CLI | https://github.com/alpacahq/cli |
| 03 | Trading MCP Server | https://docs.alpaca.markets/us/docs/alpaca-mcp-server |
| 03 | Multi-Agent AI Trading System | https://alpaca.markets/learn/building-a-multi-agent-ai-trading-system-on-alpaca |
| 04 | Trading CLI Documentation | https://docs.alpaca.markets/us/docs/alpacas-cli |
| 04 | SDKs & OpenAPI Specs | https://docs.alpaca.markets/us/docs/sdks-and-tools |

Additional links from Alpaca's official guidance (§16):

| Resource | URL |
|---|---|
| **MCP server repo — full setup docs per AI agent** | https://github.com/alpacahq/alpaca-mcp-server |
| Trading API (overview) | https://docs.alpaca.markets/us/docs/trading-api |

Full docs index: **https://docs.alpaca.markets/us/llms.txt**
Any docs page returns clean markdown by appending `.md` to its URL.

Community: https://forum.alpaca.markets/ · https://alpaca.markets/slack · https://github.com/alpacahq

---

## 6. Trading MCP Server

https://docs.alpaca.markets/us/docs/alpaca-mcp-server

Local only, `stdio` transport, no remote URL, no OAuth.

```bash
uvx alpaca-mcp-server
```

Claude Code:

```bash
claude mcp add alpaca --scope user --transport stdio uvx alpaca-mcp-server --env ALPACA_API_KEY=your_key --env ALPACA_SECRET_KEY=your_secret
```

Cursor (`~/.cursor/mcp.json`) / Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "uvx",
      "args": ["alpaca-mcp-server"],
      "env": {
        "ALPACA_API_KEY": "your_key",
        "ALPACA_SECRET_KEY": "your_secret"
      }
    }
  }
}
```

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ALPACA_API_KEY` | yes | — | API key ID |
| `ALPACA_SECRET_KEY` | yes | — | Secret key |
| `ALPACA_PAPER_TRADE` | no | `true` | Paper vs live |
| `ALPACA_TOOLSETS` | no | all | Restrict tool categories |

### Tool list — 65 tools

**Account & Portfolio (6)** — `get_account_info`, `get_account_config`,
`update_account_config`, `get_portfolio_history`, `get_account_activities`,
`get_account_activities_by_type`

**Orders (9)** — `place_stock_order`, `place_crypto_order`, `place_option_order`
(single or multi-leg), `get_orders`, `get_order_by_id`, `get_order_by_client_id`,
`replace_order_by_id`, `cancel_order_by_id`, `cancel_all_orders`

**Positions (6)** — `get_all_positions`, `get_open_position`, `close_position`,
`close_all_positions`, `exercise_options_position`, `do_not_exercise_options_position`

**Watchlists (7)** — `create_watchlist`, `get_watchlists`, `get_watchlist_by_id`,
`update_watchlist_by_id`, `delete_watchlist_by_id`, `add_asset_to_watchlist_by_id`,
`remove_asset_from_watchlist_by_id`

**Assets & Market Info (8)** — `get_all_assets`, `get_asset`, `get_option_contracts`,
`get_option_contract`, `get_calendar`, `get_clock`,
`get_corporate_action_announcements`, `get_corporate_action_announcement`

**Stock Data (9)** — `get_stock_bars`, `get_stock_quotes`, `get_stock_trades`,
`get_stock_latest_bar`, `get_stock_latest_quote`, `get_stock_latest_trade`,
`get_stock_snapshot`, `get_most_active_stocks`, `get_market_movers`

**Crypto Data (8)** — `get_crypto_bars`, `get_crypto_quotes`, `get_crypto_trades`,
`get_crypto_latest_bar`, `get_crypto_latest_quote`, `get_crypto_latest_trade`,
`get_crypto_snapshot`, `get_crypto_latest_orderbook`

**Options Data (7)** — `get_option_bars`, `get_option_trades`,
`get_option_latest_trade`, `get_option_latest_quote`,
**`get_option_snapshot` (includes greeks and IV)**, `get_option_chain`,
`get_option_exchange_codes`

**Fixed Income (1)** — `get_fixed_income_latest_quotes`

**Index Data (2)** — `get_index_latest_values`, `get_index_values`

**News & Corporate Actions (2)** — `get_corporate_actions`, `get_news`

---

## 7. Alpaca CLI

https://github.com/alpacahq/cli · https://docs.alpaca.markets/us/docs/alpacas-cli

**Alpha preview.** Commands, flags and output formats may change without notice
between releases. Pin the version on any deployed box.

Built for agents, not humans: no confirmation prompts, no "are you sure?" dialogs.
`position close-all` liquidates the portfolio immediately. `order cancel-all`
cancels everything without listing first. Paper is the default; live requires an
explicit opt-in.

### Install

```bash
go install github.com/alpacahq/cli/cmd/alpaca@latest
```

```bash
brew install alpacahq/tap/cli
```

### Auth

```bash
alpaca profile login                              # OAuth, paper only
alpaca profile login --api-key                    # API keys, paper
alpaca profile login --api-key --live             # API keys, live
alpaca profile login --api-key --name prod --live
alpaca profile switch prod
alpaca profile list
alpaca profile logout <name>
```

Profiles stored in `~/.config/alpaca/profiles/` at 0600. OAuth is paper-only; live
needs API keys. For scripts, CI and agents prefer env vars so secrets never touch disk.

Credential lookup order:

1. `ALPACA_API_KEY` + `ALPACA_SECRET_KEY`
2. Profile `access_token`
3. Profile `api_key` + `secret_key`

A partial env bundle falls through to the active profile. OAuth tokens cannot be
supplied via env vars.

### Configuration

| Variable | Description |
|---|---|
| `ALPACA_API_KEY` | API key; must be set with `ALPACA_SECRET_KEY` |
| `ALPACA_SECRET_KEY` | Secret key |
| `ALPACA_LIVE_TRADE` | `true` routes to live; anything else routes to paper |
| `ALPACA_PROFILE` | Profile name |
| `ALPACA_OUTPUT` | `json` or `csv` |
| `ALPACA_CONFIG_DIR` | Defaults to `~/.config/alpaca` |
| `ALPACA_QUIET` | Suppress warnings, hints, colour |
| `ALPACA_VERBOSE` | HTTP request summaries on stderr |
| `ALPACA_DEBUG` | Headers and bodies on stderr |
| `ALPACA_TRACE` | HTTP timing breakdown on stderr |

Global flags: `--csv`, `--jq`, `--profile`, `--verbose`, `--debug`, `--trace`,
`--quiet`, `--schema`, `--timeout`.

### Command areas

Trading: `order`, `position`, `option`, `locate`, `clock`, `calendar`
Account/assets: `account`, `asset`, `watchlist`, `wallet`, `corporate-action`
Market data: `data`, `data crypto`, `data option`, `data forex`, `data index`, `data meta`, `data screener`, `data news`
Utilities: `profile`, `api`, `doctor`, `update`, `version`, `completion`

#### Account

```bash
alpaca account get
alpaca account config get
alpaca account config set
alpaca account activity list
alpaca account portfolio
```

#### Orders

```bash
alpaca order submit --symbol AAPL --side buy --qty 10 --type market
alpaca order submit --symbol AAPL --side buy --qty 10 --type limit --limit-price 185
alpaca order list
alpaca order list --status all
alpaca order get --order-id <id>
alpaca order replace --order-id <id> --qty 20
alpaca order cancel --order-id <id>
alpaca order cancel-all
alpaca order get-by-client-id --client-order-id <id>
```

#### Positions

```bash
alpaca position list
alpaca position get --symbol AAPL
alpaca position close --symbol AAPL
alpaca position close-all
```

#### Options

```bash
alpaca option contracts --underlying-symbol AAPL
alpaca option get --symbol-or-id AAPL250620C00200000
alpaca option exercise --symbol-or-id <contract>
alpaca option do-not-exercise --symbol-or-id <contract>
```

#### Options market data

```bash
alpaca data option chain --underlying-symbol AAPL
alpaca data option snapshot --symbol AAPL250620C00200000
alpaca data option latest-quotes --symbol AAPL250620C00200000
```

#### Stock market data

```bash
alpaca data bars --symbol AAPL --start 2025-01-01 --timeframe 1Day
alpaca data quotes --symbol AAPL --start 2025-06-01
alpaca data trades --symbol AAPL --start 2025-06-01
alpaca data latest-bar --symbol AAPL
alpaca data latest-quote --symbol AAPL
alpaca data latest-trade --symbol AAPL
alpaca data snapshot --symbol AAPL
alpaca data screener most-actives
alpaca data screener movers
```

#### Other data

```bash
alpaca data news --symbol AAPL
alpaca data corporate-actions --symbols AAPL --types dividend
alpaca clock
alpaca calendar
```

#### Watchlists

```bash
alpaca watchlist list
alpaca watchlist create --name "Tech Stocks" --symbols AAPL,MSFT,NVDA
alpaca watchlist add --watchlist-id <id> --symbol GOOGL
alpaca watchlist remove --watchlist-id <id> --symbol GOOGL
alpaca watchlist delete --watchlist-id <id>
```

#### Raw API escape hatch

```bash
alpaca api GET /v2/account
```

### Agent-friendly features

```bash
alpaca order submit --symbol AAPL --side buy --qty 10 --type market --dry-run
alpaca order list --schema
alpaca --help-all
```

Pass `--client-order-id` on unattended submissions so retries after ambiguous
failures do not create duplicate orders.

Retries 429 and 5xx with exponential backoff, up to 3 attempts, respecting
`Retry-After`. Errors are JSON on stderr:

```json
{"error":"rate limited","code":0,"status":429,"hint":"Rate limited. Reduce request frequency or add delays between calls."}
```

Exit codes: `0` success · `1` API or general error · `2` auth error.

Diagnostics: `alpaca doctor`, plus `--verbose` / `--trace` / `--debug`.
Credentials are always scrubbed from diagnostic output.

---

## 8. Alpaca Skills

https://github.com/alpacahq/alpaca-skills — Apache 2.0

Open agent skills for the Trading and Broker APIs. Each skill is a `SKILL.md` with
step-by-step instructions an AI coding assistant follows. Prerequisite: the Alpaca CLI.

```bash
npx skills add alpacahq/alpaca-skills
```

```bash
npx skills add alpacahq/alpaca-skills --list
```

```bash
npx skills add alpacahq/alpaca-skills --skill alpaca-trading-backtest
```

Manual install — Claude Code: copy into `~/.claude/skills/`. Cursor: `.cursor/skills/`.

Trading API skills (the relevant ones here):

| Name | Title |
|---|---|
| `alpaca-trading-backtest` | Trading API Backtesting |
| `alpaca-trading-paper-trading` | Paper Trading (generic, SDK-agnostic) |
| `alpaca-trading-paper-trading-cli` | Paper Trading (CLI) |
| `alpaca-trading-paper-trading-mcp` | Paper Trading (MCP Server) |

### Paper Trading Skill — what it actually is

Announced by Alpaca 2026-08-26. Read the real `SKILL.md`, not the announcement:
it is a **human-in-the-loop, confirmation-gated workflow**, not an autonomous
execution library. Its documented flow is: restate the strategy in plain language →
ask you to confirm the restatement → gather every order parameter with attribution
(provided / inferred / defaulted) → show a preview table with a buying-power check →
ask permission → submit → report lifecycle.

Explicit design points:

- **"Default: confirmation ON."** No order is submitted without a preview.
- **Hard block on live credentials** — a non-`paper-` base URL stops the agent.
- Aimed at "a Trading API user working with your own account and local workspace",
  i.e. an agent you are talking to, not a long-running daemon.

**Implication for this project:** it is not a drop-in for `agent/execute.py`. Our
agent must run unattended — the hackathon's first core requirement is *autonomous*
agents — and a per-order confirmation prompt is the opposite of that. Its value here
is as reference material and as a judge-facing demo path, not as the trading loop.

Note also that the skill uses **`APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`** (the
SDK/REST names), whereas the MCP server and CLI use `ALPACA_API_KEY` /
`ALPACA_SECRET_KEY`. Both name pairs exist; do not assume one works everywhere.

### Backtesting Skill — what it actually is

**CLI-based**, deterministic, artifact-producing historical backtest workflow.
Pipeline: `strategy idea → formalized rules → confirmed assumptions → CLI data fetch
→ local script → artifacts → report`. It explicitly forbids "bypassing the Alpaca CLI
by switching to direct HTTP calls", so running it is a genuine, visible CLI usage.

**Artifact contract** — every run creates
`runs/YYYY-MM-DD_symbol_strategy_timeframe/` containing:

```
notes.md  strategy_spec.json  config.json  run.py
raw/        bars_SYMBOL.json quotes_SYMBOL.json trades_SYMBOL.json
            calendar.json corporate_actions.json
normalized/ bars_SYMBOL.csv quotes_SYMBOL.csv
summary.json  report.md  trades.csv  round_trips.csv
equity.csv  benchmark_equity.csv
data_fingerprint.json  warnings.json  fee_source.json
```

`report.md` must lead with a **Performance vs Benchmarks** table: Total Return,
Annualised Return, Max Drawdown, Sharpe, Final Equity — strategy row against a
benchmark row.

**The "Teaching Five"** — what the in-chat summary must lead with:
total return vs benchmark · max drawdown · number of trades · win rate ·
Sharpe vs benchmark.

**Fill models:** `next_open` (default — signal on bar T close, fill at T+1 open),
`time_based`, and `same_bar` (only on explicit request, with a documented look-ahead
warning).

**Run considerations it requires resolving** before running: fill timing,
quote-aware vs bar-proxy fills, dividends, splits, execution friction, activity fees,
market hours, calendar decisions, benchmark choice, look-ahead bias, survivorship
bias, out-of-sample validation, and overfitting risk.

> **Critical caveat for this project.** The skill's own guardrail list forbids
> "claiming support for unsupported products — **options require explicit contract
> selection and fill logic**." It does **not** backtest options out of the box. A
> realistic scope here is to backtest the *screener signal on the underlying*
> (validating the entry edge), and state plainly that it is a signal backtest, not an
> options P&L backtest.

It also offers an optional **paper forward-validation handoff** producing
`paper_config.json`, `strategy_runtime.py`, `risk_limits.json`,
`alpaca_order_adapter.py`, `reconciliation_plan.md` — all of which this project
already has equivalents for in `agent/`.

Required disclosure text for any backtest artifact is specified verbatim in the
skill, plus a link to the Brokerage Fee Schedule:
`https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf`

Broker API skills (not relevant to this hackathon): integration, account-onboarding,
funding-transfers, journals, trading-orders, market-data, sse-events,
reconciliation-idempotency, rate-limits-resilience, money-precision.

---

## 9. Options trading

https://docs.alpaca.markets/us/docs/options-trading

### Levels

| Level | Permitted |
|---|---|
| 0 | Options trading disabled |
| 1 | Sell covered calls (needs underlying shares); sell cash-secured puts |
| 2 | Level 1 + buy calls, buy puts |
| 3 | Level 2 + buy call spreads, buy put spreads (multi-leg) |

Paper environment enables options by default. Production requires a formal request.

### Symbology

OCC standard. `AAPL240119C00100000` = AAPL Jan 19 2024 $100 Call.
Contract details via `/v2/options/contracts` (expiration, strike, tradability).

### Order rules

Same Orders API as equities and crypto. Restrictions:

- Whole-number quantities only; **no notional values**
- Time in force: `day` or `gtc` only
- Extended hours: disabled
- Types: `market`, `limit`, `stop`, `stop_limit` — **stop orders single-leg only**
- Buying power computed as execution price × 100 × contracts

### Order-constraint matrix (from the Paper Trading Skill)

The clearest published summary of what combinations the API accepts:

| Asset class | Order types | Time in force | Order classes |
|---|---|---|---|
| `us_equity` | market, limit, stop, stop_limit, trailing_stop | day, gtc, opg, cls, ioc, fok | simple, bracket, oco, oto |
| **`us_option`** | **market, limit, stop, stop_limit** (stop types single-leg only) | **day, gtc** | **simple, mleg** |
| `crypto` | market, limit, stop_limit | gtc, ioc | simple |

> **Architecturally important: `bracket`, `oco` and `oto` are equities-only.**
> An options order **cannot** carry a broker-side stop-loss or take-profit. The agent
> must track and close its own option positions — which is exactly what
> `agent/exits.py` does. This validates the current design; it is not a shortcut.

Further constraints:

- **`mleg` carries up to 4 legs** — enough for an iron condor, and the ceiling.
- `position_intent`: `buy_to_open`, `buy_to_close`, `sell_to_open`, `sell_to_close`.
- Notional orders cannot be combined with `qty` and **cannot be replaced** (cancel and
  resubmit). Options cannot use notional at all.
- `client_order_id` max 128 chars.
- Alpaca's own sources disagree on the options row: the OpenAPI spec blob says
  `market`/`limit` with `day` only, while the Options Trading page and the Placing
  Orders matrix both allow `gtc` and allow `stop`/`stop_limit` single-leg. The skill
  follows the two product pages and advises defaulting to `day` as the conservative
  choice, letting Alpaca reject rather than pre-blocking.

### Multi-leg (`mleg`)

https://docs.alpaca.markets/us/docs/options-level-3-trading

```json
{
  "order_class": "mleg",
  "qty": "1",
  "type": "limit",
  "limit_price": "0.6",
  "time_in_force": "day",
  "legs": [
    {
      "symbol": "AAPL250117P00200000",
      "ratio_qty": "1",
      "side": "buy",
      "position_intent": "buy_to_open"
    },
    {
      "symbol": "AAPL250117C00250000",
      "ratio_qty": "1",
      "side": "buy",
      "position_intent": "buy_to_open"
    }
  ]
}
```

| Leg field | Meaning |
|---|---|
| `symbol` | OCC contract identifier |
| `side` | `buy` or `sell` |
| `ratio_qty` | Relative proportion; must be simplest form (GCD = 1) |
| `position_intent` | `buy_to_open`, `sell_to_open`, `buy_to_close`, `sell_to_close` |

Supported: long call spread, long put spread, iron condor (4 legs), call spread rolls.

Restrictions:

- **No equity legs** — cannot mix stock and options in one mleg order
- **Covered legs only** — all shorts must be covered within the same order
- Ratios must be simplified (GCD = 1)
- Max loss computed per expiration date; the largest requirement applies

**Margin — universal spread rule.** Ignore premiums, model each option's piecewise
linear intrinsic payoff, combine all positions, find theoretical max loss. Margin =
absolute value of worst-case loss. Recognises offsetting exposure across positions,
so it is often cheaper than spread-by-spread calculation.

```
Cost Basis = Maintenance Margin + (Net Option Price × 100)
```

### Exercise and assignment

- **Auto-exercise:** ITM contracts exercise automatically at expiry. Threshold $0.01 ITM.
- **Manual:** `POST /v2/positions/{symbol_or_contract_id}/exercise`. Requests between
  market close and midnight are rejected.
- **Assignment:** no websocket for non-trade activities — **REST polling required**.
- **Forced liquidation:** insufficient buying power triggers automatic position
  liquidation within 1 hour before expiry.

---

## 10. Market data

### Plans and feeds

| Feed | Basic (free) | Algo Trader Plus |
|---|---|---|
| IEX | yes | yes |
| SIP real-time | no | yes |
| SIP 15-min delayed | yes | yes |
| OTC | no | broker-partner subscription only |

Stock websockets: `wss://stream.data.alpaca.markets/v2/iex` ·
`wss://stream.data.alpaca.markets/v2/sip`

### Options data

> **Corrected 2026-08-29.** An earlier draft of this doc said the free `indicative`
> feed is 15-minute delayed. That is wrong for the data the agent actually trades on
> — see the real-time note below.

- Feeds: **`indicative`** (free Basic plan) and **`opra`** (paid Algo Trader Plus,
  full consolidated OPRA).
- **Both tiers are permitted.** Participants do **not** automatically receive Algo
  Trader Plus or OPRA access during the event.
- **Latest option quotes and chains are real-time on Basic.** The 15-minute
  restriction applies only to **historical bars and trades**, not the latest quote.
- Dashboard charts may lag — **agents should rely on API data**, not the dashboard.
- Historical option data exists only **from February 2024 onward**.
- Websocket: `wss://stream.data.alpaca.markets/v1beta1/{feed}`
  (sandbox: `wss://stream.data.sandbox.alpaca.markets/v1beta1/{feed}`)
- **msgpack only** — unlike stock and crypto streams. SDKs handle this; requests
  need `Content-Type: application/msgpack`.
- Message types: trades (`T: "t"`) and quotes (`T: "q"`).
- **Cannot subscribe to `*` for option quotes** — too many symbols.
- Greeks and IV come from `get_option_snapshot` (MCP) / `alpaca data option snapshot`
  (CLI), not the websocket trade/quote channels.

---

## 11. Trading API basics

| | |
|---|---|
| Paper base URL | `https://paper-api.alpaca.markets/v2/` |
| Live base URL | `https://api.alpaca.markets/v2/` |

Every response carries an `X-Request-ID` header — save it for support enquiries.

### Paper trading environment

https://docs.alpaca.markets/us/docs/paper-trading

- Accounts are **created and deleted**, not reset. Dashboard → account number in
  upper left → "Open New Paper Account". Generate new API keys for the new account.
- Default starting balance $100,000. **Balance cannot be changed after creation** —
  you create a new account instead.
- Paper needs its own API credentials, separate from live.

Not simulated: market impact and information leakage, latency slippage, limit-order
queue position, price improvement, regulatory fees, dividends, borrow fees.
No order-fill emails. Fills can exceed actual available liquidity, since paper does
not apply live's NBBO quantity check.

---

## 12. SDKs and OpenAPI specs

https://docs.alpaca.markets/us/docs/sdks-and-tools

| Language | Repo | Install |
|---|---|---|
| Python | https://github.com/alpacahq/alpaca-py | `pip install alpaca-py` |
| .NET/C# | https://github.com/alpacahq/alpaca-trade-api-csharp | NuGet `Alpaca.Markets` |
| Node.js | https://github.com/alpacahq/alpaca-trade-api-js | `npm install @alpacahq/alpaca-trade-api` |
| Go | https://github.com/alpacahq/alpaca-trade-api-go | `go get github.com/alpacahq/alpaca-trade-api-go` |
| Java | https://github.com/alpacahq/alpaca-java | Maven `markets.alpaca/alpaca-java` |

OpenAPI specs:

- Trading API — https://docs.alpaca.markets/openapi/trading-api.json
- Market Data API — https://docs.alpaca.markets/openapi/market-data-api.json
- Broker API — https://docs.alpaca.markets/openapi/broker-api.json

Community SDKs: `Petersoj/alpaca-java` (Java), `d-e-s-o/apca` and
`wmzhai/alpaca-rust` (Rust SDKs), `d-e-s-o/apcacli` (Rust CLI).

---

## 13. Reference architecture — Multi-Agent AI Trading System

https://alpaca.markets/learn/building-a-multi-agent-ai-trading-system-on-alpaca

Alpaca's own published reference. Useful as a contrast: it is **stock-only** —
options are listed as future work — so it does not satisfy this hackathon's options
requirement on its own.

```
Market Data Layer (Alpaca + external)
    |
Regime-Aware Screener (S&P 500)
    |
5 Parallel Research Agents (isolated, no cross-visibility)
    |
Critic Agent (structural validation vs investment_memo.yaml)
    |
Human Decision Gate (APPROVE / REJECT / REVISE)
    |
Risk Guard (deterministic Python, no LLM)
    |
Alpaca Execution + Position Monitor (every 15 min)
```

| Agent | Focus | Inputs |
|---|---|---|
| Momentum | Breakouts, relative strength | Price, volume, RSI |
| Macro | Sector rotation, factor plays | FRED, yield curve, VIX |
| StatArb | Pairs, spread dislocations | Rolling correlation, dislocation scores |
| Contrarian | Oversold bounces, sentiment unwinds | Insider activity, sentiment |
| Exotic | Calendar effects, earnings binaries | Earnings calendar, volume patterns |

Agents run in parallel via Python async against one shared SQLite `market_snapshot`
table. Proposal schema requires `ticker`, `direction`, `thesis`, `entry_conditions`,
`exits {take_profit_pct, stop_loss_pct, time_stop_days}`, `macro_alignment`
(WITH/AGAINST), `confidence_score`.

Risk guard rules: 10% max single position, 30% max sector concentration, 1.0x
leverage cap, drawdown halts at 5% daily / 10% weekly / 15% total.

Reported paper results (18 days, 25 closed trades, ~48% win rate): Macro +$1,046,
Momentum +$413, Contrarian −$232. Hypothetical — paper trading only.

Notable design choice: **the risk layer is pure Python with no LLM involvement.**

---

## 14. Gaps between this repo and the available surface

Recorded 2026-08-28, revised 2026-08-29 against Alpaca's official guidance.

| Gap | Detail |
|---|---|
| Multi-leg unused | Only single-leg orders are placed. FAQ confirms the MCP server places **single-leg and multi-leg** option orders, and that there are **no restrictions on options strategies**. Level 3 `mleg` spreads score on Creativity and cut buying-power usage via the universal spread rule. |
| Greeks unread | FAQ confirms MCP can "retrieve quotes and Greeks". `get_option_snapshot` returns greeks and IV on the free tier; the agent only fetches `get_option_latest_quote` for premiums. |
| Expiry-day exposure | ITM ≥ $0.01 auto-exercises; insufficient BP forces liquidation 1h before expiry. **Sharpened by the scoring rule:** equity is snapshotted EOD Thu 3 Sep *including* Sep 3 expiry exercises and assignments. Positions expiring 3 Sep directly move the judged number. |
| Assignment blind | No websocket for non-trade activities. Short-leg assignment is only visible via REST polling — and it lands inside the scoring snapshot. |
| Equity, not cash | Judged on **total account equity**. Open positions count at mark. No need to flatten to cash before the snapshot; no risk-adjusted metrics are scored. |
| Competition start gate | Agent must trade the new account from **Mon 31 Aug 09:30 ET**. Nothing enforces this in code today — the cutover is manual (H1–H3). |
| CLI drift risk | Alpaca CLI is alpha and may change flags between releases. Pin the version on EC2. |
| ~~Feed unverified~~ | **Resolved.** Latest option quotes are real-time on the free Basic plan; the 15-min limit applies only to historical bars and trades. Exit pricing off `get_option_latest_quote` is sound. |

---

## 15. Disclosures

Paper trading is a simulation; it does not involve actual securities transactions or
real funds. Paper-trading results are hypothetical and do not represent actual
trading or guarantee future results.

lablab and Alpaca are unaffiliated and each responsible for their own liabilities.

Securities brokerage services provided by Alpaca Securities LLC (dba "Alpaca
Clearing"), member FINRA/SIPC, a wholly-owned subsidiary of AlpacaDB, Inc.
Technology and services offered by AlpacaDB, Inc. Crypto services via Alpaca Crypto
LLC (FinCEN MSB, NMLS # 2160858), not a member of SIPC or FINRA.

Options trading is not suitable for all investors due to its inherent high risk,
which can potentially result in significant losses. Certain complex options
strategies carry additional risk. Read Characteristics and Risks of Standardized
Options before investing in options:
https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document

All investments involve risk, including possible loss of principal.

---

## 16. Official Alpaca guidance and FAQ — 2026-08-29

Posted by Alpaca as "Official guidelines". **Authoritative for this event** — it
overrides the generic lablab pages and individual admin answers where they differ.

### Required for submission

- Create a **new paper account with a $100,000 starting balance**. The same email
  may be reused if you already have an Alpaca account.
- Your agent should **begin trading from this account on Monday, 31 August at
  09:30 ET**.
- **Do not use your testing account** for the official P&L measurement.

### Timeline

| Item | When |
|---|---|
| Hackathon window | Fri 28 Aug 09:30 ET → Fri 4 Sep 09:30 ET |
| Official P&L measurement | Mon 31 Aug 09:30 ET → Fri 4 Sep 09:30 ET |
| Equity snapshot | **EOD Thursday 3 Sep**, including any exercises/assignments for options expiring 3 Sep |
| Weekend prep | A paper account may be created now to develop and test over the weekend |

### Market data

Participants may use either:

- Alpaca's **free** market data subscription, which provides the **indicative**
  options feed, or
- **Algo Trader Plus**, which includes the **OPRA** options feed.

Both tiers are permitted. **Participants will not automatically receive Algo Trader
Plus or OPRA access during the event.**

### Judging

Evaluated on a combination of:

- Trading performance and P&L during the official scoring window, judged using
  **total account equity, not cash balance**
- The **creativity, autonomy, and robustness** of the agent trading workflow

P&L is an important factor, but **winners will not be selected on P&L alone**.

### UI requirements

**A user interface is not required.** The evaluation is primarily of the autonomous
agent workflow and its trading performance.

### Technical resources listed

| Resource | URL |
|---|---|
| Getting Started | https://docs.alpaca.markets/us/docs/getting-started |
| Trading API docs | https://docs.alpaca.markets/us/docs/trading-api |
| Trading API (getting started) | https://docs.alpaca.markets/us/docs/getting-started-with-trading-api |
| Market Data API | https://docs.alpaca.markets/us/docs/getting-started-with-alpaca-market-data |
| Alpaca Skills | https://github.com/alpacahq/alpaca-skills |
| Alpaca JS SDK | https://github.com/alpacahq/alpaca-trade-api-js |
| MCP server — full agent setup docs | https://github.com/alpacahq/alpaca-mcp-server |

---

### FAQ — full text

**How will submissions be judged? Is the competition based only on P&L?**
Submissions will be evaluated based on a combination of trading performance,
measured by total account equity, and the creativity, autonomy, and robustness of
the agent trading workflow. Winners will not be selected based on P&L alone.

**Will judges consider risk-adjusted metrics such as Sharpe ratio, Sortino ratio, or
maximum drawdown?**
Performance will be judged using total account equity at the official hackathon close.

**How will Alpaca track account performance?**
Alpaca will track total account equity.

**Will there be an ongoing scoreboard, as there was in the previous Alpaca
competition?**
No scoreboard for this competition, but we will try to incorporate this for the next
challenge.

**What is the official P&L measurement window?**
Monday 31 August 09:30 ET through Friday 4 September 09:30 ET. We will be looking at
the portfolio's total equity as of EOD Thursday 3 September. Any option exercises and
assignments for options expiring on 3 September will be reflected in the EOD value.

**When should my agent begin trading for the competition?**
From the official competition paper account on Monday 31 August at 09:30 ET. Trades
made in a testing account before then will not count toward the official measurement.

**Do I need a new paper account for the official submission?**
Yes. You must use a new paper account with a starting balance of $100,000 for the
official measurement period. An account used for testing should not be used for the
official measurement.

**Can I use my existing email address to create the new paper account?**
Yes.

**Can I test before the official measurement window begins?**
Yes. You may prototype and trade using a testing account before the official window.
For the competition, use a new $100,000 paper account beginning Monday 31 August at
09:30 ET.

**Does trading after Friday 4 September 09:30 ET count toward the score?**
No. The measurement window ends at 09:30 ET on Friday 4 September, when a snapshot of
total account equity will be taken.

**Will agents trade on live market data or be evaluated through simulations or
backtests?**
Agents will trade using live market data during the official measurement window.
Final performance will be based on the dedicated Alpaca paper trading account, not a
historical backtest.

**Can I include historical backtests or simulated market shocks if live market
conditions are flat?**
Yes. You may include backtests and simulated shocks in the project write-up and
repository as additional evidence of the agent's guardrails. Official P&L will still
be based on the live paper account at the Friday snapshot, and judges will evaluate
the workflow alongside the equity result.

**Must the GitHub repository be public during the hackathon?**
No. It may remain private during the hackathon.

**Can I use a repository created before kickoff if it contains only a README,
LICENSE, and .gitignore?**
Yes, although creating a fresh repository is recommended.

**May I reuse or depend on my own pre-existing library or application?**
Yes. Judging is scoped to the agent submitted during the event, including its options
workflow using the Trading API with MCP or CLI, competition paper-account
performance, and the creativity, autonomy, and robustness of the workflow.

**May I set up infrastructure, boilerplate, or other supporting components before
kickoff?**
Yes.

**If pre-event work is permitted, must it be disclosed in the README or final
submission?**
Yes.

**Is Alpaca MCP required, or is the Trading API or CLI sufficient?**
You can use Alpaca's MCP or CLI and use your preferred language. If for whatever
reason you want to use an SDK to implement your bot, explain clearly your reasons and
prioritize the official SDKs.

**What is the recommended way to use Alpaca MCP with an AI agent?**
See the Alpaca MCP server documentation for setup instructions for your selected AI
agent.

**Does the Alpaca MCP server support options data and trading?**
Yes. The official Alpaca MCP server can fetch contracts and option chains, retrieve
quotes and Greeks, and place single-leg and multi-leg option orders. Using alpaca-py
is optional if you want to manage the trading loop in your own code.

**What options market data is available in paper trading?**
The latest option quotes and chains available through the API are real-time. The free
Basic plan includes Alpaca's Indicative options feed, while Algo Trader Plus provides
full OPRA data. On Basic, the 15-minute restriction applies to historical bars and
trades, not the latest quote. Dashboard charts may lag, so agents should rely on API
data.

**Will participants automatically receive OPRA or Algo Trader Plus access?**
No. Both free and paid market data tiers are permitted.

**Which options order types are supported in paper trading through MCP?**
MCP option orders support market, limit, stop, and stop limit orders. Trailing-stop
orders are for stocks. A risk agent can monitor an options position and submit a
market or limit order to close it.

**Are there any restrictions on options trading strategies?**
No.

**Does an autonomous agent need to be hosted?**
No. If the agent runs autonomously and only places orders, a GitHub repository is
sufficient. A hosted link is needed only if the submission includes a demo app that
judges must open.

**Can I deploy a Blazor WebAssembly app on Vercel?**
Yes. A Blazor WebAssembly app published as static HTML, JavaScript, and WebAssembly
files and hosted on Vercel is compliant.

**Are there restrictions on model providers or hosting infrastructure?**
No. There are no restrictions on the model provider or hosting infrastructure.
