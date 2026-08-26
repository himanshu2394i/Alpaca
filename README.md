# Alpaca Options Agent

Autonomous paper-options trading agent for the lablab.ai × Alpaca hackathon.
Streams US equity bars, screens for momentum setups, confirms them with a
multi-timeframe Supertrend/RSI/EMA filter, optionally asks Claude to pick a
contract, enforces hard risk gates, and places limit orders.

## Architecture

Three processes share one SQLite database (`data/market.db`):

| Process | Command | Role |
|---------|---------|------|
| Ingest | `python -m agent.ingest` | REST warm start + live IEX websocket |
| Agent | `python -m agent.run` | Screener → decide → gates → execute |
| Dashboard | `python -m agent.dashboard` | Read-only HTML view |

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env
# fill in ALPACA_API_KEY, ALPACA_SECRET_KEY, ANTHROPIC_API_KEY

# Terminal 1 — market data
python -m agent.ingest

# Terminal 2 — agent (dry run by default)
python -m agent.run
python -m agent.run --deterministic   # no LLM, mid-delta fallback
python -m agent.run --live          # real paper orders

# Terminal 3 — dashboard
python -m agent.dashboard --host 0.0.0.0 --port 8080
```

## Strategy (hybrid)

**Intraday momentum** (primary): move from session open ≥ 0.5× ADR, RVOL ≥ 1.5,
price on the correct side of EMA(20).

**MTF confirmation** (cousin's rules, when enough history exists):

- **4H:** close above Supertrend(10/3), RSI(14) ≥ 50
- **15min:** entry price above EMA(200) for calls (below for puts)
- **Stops:** when 4H alert range is available, stop at alert low, target at 1:2 R:R

When MTF history is still warming up, momentum signals pass through without the
extra filter so the agent is not starved on day one.

## Risk controls

- Max 2% equity per trade, 10% deployed, 5 concurrent positions
- Daily loss halt −3%, drawdown halt −8% from peak
- No entries after 15:30 ET
- Live orders poll for 60s, cancel, then retry once at the ask/bid
- On boot, local positions are reconciled against Alpaca before trading
- Touch file `HALT` in repo root to stop entries (exits still run)

## Ops (Alpaca CLI)

Requires [Alpaca CLI](https://docs.alpaca.markets/docs/alpaca-cli) on the VM.
Trading path uses **Alpaca MCP**; these scripts use the **CLI** for ops and demos:

```bash
ops/cli_demo.sh        # account + clock + positions (judge-facing smoke)
ops/eod_snapshot.sh    # equity snapshot to logs/
ops/health.sh          # bars freshness + process check
ops/flatten.sh         # emergency close all positions
ops/live_health.py     # SQLite + service health summary
```

## Hackathon submission

| Artifact | Location |
|----------|----------|
| One-page write-up | [`docs/submission/ONE_PAGER.md`](docs/submission/ONE_PAGER.md) |
| Submit checklist | [`docs/submission/CHECKLIST.md`](docs/submission/CHECKLIST.md) |
| Social post drafts | [`docs/submission/SOCIAL_DRAFTS.md`](docs/submission/SOCIAL_DRAFTS.md) |
| Demo / slides outline | [`docs/submission/DEMO_OUTLINE.md`](docs/submission/DEMO_OUTLINE.md) |

Competition requires a **fresh $100k paper account** (created at/after kickoff). Do not submit the pre-kickoff throwaway account.

## Deploy (systemd)

Copy `deploy/systemd/*.service` to `/etc/systemd/system/` on a US-region Ubuntu
VM, set `WorkingDirectory` and `EnvironmentFile`, then:

```bash
sudo systemctl enable --now alpaca-ingest alpaca-agent alpaca-dashboard
```

## Tests

```bash
python -m pytest
python -m tools.replay        # measure screener fire rate on stored bars
```

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ALPACA_API_KEY` | yes | Alpaca paper API key |
| `ALPACA_SECRET_KEY` | yes | Alpaca secret |
| `ANTHROPIC_API_KEY` | for LLM mode | Claude decision layer |
| `ALPACA_PAPER_TRADE` | optional | defaults to paper |
