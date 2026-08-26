# Project Memory — Alpaca Options Agent

**Last updated:** 2026-08-27 (pre-kickoff IST)  
**Event:** lablab.ai × Alpaca AI Trading Agents Hackathon  
**Competition window:** 2026-08-31 → 2026-09-04 (ET)  
**Kickoff:** 2026-08-28 20:30 IST  
**Repo:** https://github.com/himanshu2394i/Alpaca  
**Default branch:** `master`  
**Live HEAD (EC2):** `1a7d216` (merged PR #1) — Application URL http://35.175.208.115:8080

---

## One-liner

Autonomous paper-options agent: stream US equity bars → momentum screener + MTF filter → Claude picks contract → risk gates → limit orders. SQLite audit trail + dashboard.

---

## Architecture

Three processes, one SQLite file (`data/market.db`):

| Process | Command | Writes |
|---------|---------|--------|
| `agent.ingest` | REST warm start + IEX websocket | `bars` |
| `agent.run` | screener → decide → gates → execute | `positions`, `decisions`, `equity` |
| `agent.dashboard` | HTTP :8080 | read-only |

External: Alpaca MCP server (stdio, local keys), Anthropic API (optional).

```
ingest → market.db ← run (tick every 60s)
              ↑
         dashboard
```

**Universe (30 underlyings):** SPY, QQQ, IWM, DIA, AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AMD, NFLX, AVGO, MU, JPM, XLF, XLE, COIN, SMCI, PLTR, MSTR, HOOD, ARM, APP, CVNA, NET, RDDT, SHOP, SOXL — at the 30-symbol websocket cap. The last 10 are high-beta names added 2026-08-26; median 30d ADR 5.2% vs 2.5% for the original 20. No slots remain for streaming held options.

---

## Strategy (hybrid — current production logic)

**Primary:** Intraday momentum on universe  
- Move from session open ≥ 0.5× ADR, RVOL ≥ 1.5, price vs EMA(20)  
- Tuned via `python -m tools.replay` on stored IEX bars  

**MTF confirmation** (cousin's rules, when enough history exists):  
- **4H:** close above Supertrend(10/3), RSI(14) ≥ 50 (calls; mirrored for puts)  
- **15m:** entry above EMA(200) for calls (below for puts)  
- **Stops:** 4H alert low/high → 1:2 R:R when MTF confirms  
- **Warmup:** if MTF can't compute yet, momentum signal passes (fail open)  

**Not implemented from cousin's full system:** marubozu-only alerts, 50% retrace wait, 15m EMA trail after target.

**LLM:** Claude via strict tool schema; `--deterministic` skips LLM (mid-delta fallback).

---

## Risk controls

| Gate | Value |
|------|-------|
| Max per trade | 2% equity |
| Max deployed | 10% |
| Max concurrent | 5 |
| Daily loss halt | −3% |
| Drawdown halt | −8% from peak |
| No entries after | 15:30 ET |
| Kill switch | `HALT` file in repo root |

**Execution:** limit orders only; poll 60s → cancel → retry once at ask/bid; positions open/close only on fill. Boot reconciliation vs Alpaca via `agent/reconcile.py`.

---

## Deployment (live)

| | |
|---|---|
| **AWS account** | `REDACTED-AWS-ACCOUNT-ID` |
| **CLI profile** | `alpaca-hackathon` |
| **Region** | `us-east-1` |
| **Instance** | `i-06aac474ea732cdeb` |
| **Public IP** | `35.175.208.115` |
| **Application URL** | http://35.175.208.115:8080 |
| **Security group** | `alpaca-agent-sg` (`sg-03d56c48b770d018e`) — ports 22, 8080 open to `0.0.0.0/0` |
| **SSH user** | `ubuntu` |
| **SSH key pair (AWS)** | `alpaca-agent-key` |
| **SSH key (dev machine)** | `~/.ssh/alpaca-agent-key.pem` (reformatted PEM; temp copy at `%LOCALAPPDATA%\Temp\alpaca-agent-key-fixed.pem`) |
| **App path** | `/opt/alpaca-options-agent` |
| **Branch on VM** | `master` @ `1a7d216` (PR #1 merged) |
| **Secrets** | `/opt/alpaca-options-agent/.env` (copied from local `.env`; not in git) |

**Systemd units:** `alpaca-ingest`, `alpaca-agent`, `alpaca-dashboard` — all **active** as of 2026-08-26.  
**Agent mode:** `--live` (paper orders, `dry_run=False`) — intentional for pre-kickoff testing through 2026-08-28.

### EC2 bootstrap notes (learned during deploy)

1. First instance (`13.217.26.204`) was terminated; replaced with current instance using new key pair.
2. `pip install -e ".[dev]"` can fail on EC2 (setuptools flat-layout discovers `ops/`, `deploy/`, `data/`). **Workaround:** install deps from `pyproject.toml` directly, or merge the `[tool.setuptools.packages.find] include = ["agent*"]` fix (staged locally, not yet pushed).
3. Bootstrap `user-data.sh` may finish before systemd units exist — manually `sudo cp deploy/systemd/*.service /etc/systemd/system/` if needed.
4. Agent/ingest need explicit `Environment=PATH=.../.venv/bin:...` in systemd so `alpaca-mcp-server` is found (fix staged locally).
5. Dashboard verified HTTP 200 on VM after services started.

---

## Git state (2026-08-26)

**Branch:** `feat/hybrid-mtf-and-ops`  
**Remote:** `origin` → https://github.com/himanshu2394i/Alpaca.git  

**Commits on feature branch (ahead of master):**
- `a118ee9` — hybrid MTF screener filter + ops/deploy scaffolding
- `d656950` — order fill polling + boot position reconciliation

**Included in latest push (pre-open safety + deploy):**
- `pm.md`, `pyproject.toml` setuptools fix, systemd PATH + EOD timer
- `deploy/user-data.sh`, data-staleness halt, ingest gap fill

---

## Local dev

```bash
cp .env.example .env   # ALPACA_*, ANTHROPIC_*
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python -m agent.ingest
python -m agent.run              # dry run default
python -m agent.run --live       # paper orders
python -m agent.run --deterministic
python -m agent.dashboard --host 0.0.0.0 --port 8080
python -m pytest                 # 193 tests
python -m tools.replay           # screener fire-rate tuning
```

**AWS profile (local):**
```powershell
$env:AWS_PROFILE = "alpaca-hackathon"
aws sts get-caller-identity   # expect Account REDACTED-AWS-ACCOUNT-ID
```

---

## What's done

- [x] Data pipeline (warm start + IEX websocket + SQLite)
- [x] Indicators, screener, exits, gates, execute, MCP bridge, decide
- [x] Hybrid MTF filter (Supertrend/RSI/EMA200)
- [x] Order fill polling + boot reconciliation
- [x] Dashboard (stdlib HTTP)
- [x] README, ops scripts, systemd units
- [x] GitHub repo + PR #1
- [x] EC2 deploy + all three services running
- [x] Live paper mode (`--live`) on VM for pre-kickoff testing
- [x] Dashboard reachable at Application URL (HTTP 200)
- [x] Data-staleness halt (no bars 5 min during RTH → block entries, keep exits)
- [x] Websocket gap filler on stream exit/reconnect (`ingest.fill_gap`)
- [x] EOD snapshot systemd timer (`alpaca-eod-snapshot.timer`)
- [x] setuptools package discovery fix + systemd PATH for venv binaries

---

## Checklist

### Now → 2026-08-28 (test on throwaway paper account)

- [x] Merge PR #1 into `master`; EC2 on merged HEAD
- [x] Fill-only entry logging + ghost-reconcile harden + ops health scripts
- [x] Submission pack: one-pager, checklist, social drafts, demo outline (`docs/submission/`)
- [x] Judge-facing `ops/cli_demo.sh` (Alpaca CLI)
- [ ] Optional: attend kickoff / Discord Q&A
- [ ] Verify Alpaca paper options approval level (L2+ for long calls/puts)
- [ ] Rotate AWS access keys if they were ever pasted in chat
- [ ] Save SSH key permanently under `~/.ssh/`

### 2026-08-28 kickoff

- [ ] Create **fresh competition paper account** ($100k)
- [ ] Update VM `.env` with new keys; restart services; confirm equity ≈ 100000
- [ ] Consider fresh `data/market.db` or wipe positions / decisions for clean audit
- [ ] First Build-in-Public post (`docs/submission/SOCIAL_DRAFTS.md`)
- [ ] **Freeze strategy logic** after this date

### 2026-08-29 – 30

- [x] One-page write-up draft (`docs/submission/ONE_PAGER.md`) — export PDF for submit
- [ ] Cover image, slides, demo video (`docs/submission/DEMO_OUTLINE.md`)
- [ ] Parameter tuning only — no logic changes

### 2026-08-31 – 2026-09-04

- [ ] Competition account live
- [ ] Monitor; flatten by Sep 4 close
- [ ] Submit on lablab (repo, Application URL, video, paper account ID, ≤5 social links)

### Backlog (optional)

- [ ] `orders` table for fill audit trail
- [ ] nginx + HTTPS for dashboard

---

## Key files

| Path | Role |
|------|------|
| `agent/run.py` | Main loop, `--live`, `--deterministic` |
| `agent/screener.py` | Momentum + MTF filter |
| `agent/indicators.py` | EMA, ATR, RVOL, RSI, Supertrend, `mtf_confirm` |
| `agent/execute.py` | Limit orders, fill polling |
| `agent/reconcile.py` | Boot position sync |
| `agent/config.py` | Universe, DB path, env loading |
| `deploy/systemd/` | Production units |
| `deploy/user-data.sh` | EC2 bootstrap |
| `ops/` | EOD snapshot, health, flatten, CLI demo, live health |
| `docs/submission/` | One-pager, checklist, social drafts, demo outline |
| `docs/superpowers/specs/2026-08-23-alpaca-options-agent-design.md` | Original design |
| `pm.md` | This project memory file |

---

## Decisions log

| Date | Decision |
|------|----------|
| 2026-08-26 | Hybrid strategy: keep momentum screener, add cousin's MTF as filter (not full replace) |
| 2026-08-26 | MTF fail-open during warmup so day-one trading isn't starved |
| 2026-08-26 | Deploy EC2 t3.small us-east-1; dashboard as Application URL |
| 2026-08-26 | Pre-kickoff testing with `--live` on throwaway paper account until Aug 28 |
| 2026-08-26 | Two-process model (ingest + run) due to alpaca-py event loop ownership |
| 2026-08-26 | Relaunch EC2 with `alpaca-agent-key` after original `algotrading.pem` unavailable locally |
| 2026-08-26 | Halt new entries when bars are >5 min stale during RTH; exits stay live |
| 2026-08-26 | On stream exit, REST gap-fill then reconnect ingest |
| 2026-08-26 | Widen universe 20 -> 30 with high-beta names; consumes the reserved option slots |
| 2026-08-26 | Warm start 12 -> 25 calendar days, sized off MTF's 200x15m bars (it fails open when short) |

---

## Explicitly not building

- Multi-agent LLM debate
- Credit spreads / multi-leg
- Dynamic universe selection
- Real-money path
- Full cousin strategy replacement (marubozu + 50% retrace state machine)

---

## Secrets — never commit

- `.env` (Alpaca + Anthropic keys)
- `*.pem` SSH keys
- `data/market.db*`
- Rotated AWS access keys if ever pasted in chat

---

## Useful SSH / ops

```bash
ssh -i ~/.ssh/alpaca-agent-key.pem ubuntu@35.175.208.115

# logs
journalctl -u alpaca-ingest -f
journalctl -u alpaca-agent -f
journalctl -u alpaca-dashboard -f

# restart
sudo systemctl restart alpaca-ingest alpaca-agent alpaca-dashboard

# emergency
touch /opt/alpaca-options-agent/HALT   # stops entries, exits still run
bash /opt/alpaca-options-agent/ops/flatten.sh

# switch to dry run
sudo sed -i 's/ --live//' /etc/systemd/system/alpaca-agent.service
sudo systemctl daemon-reload && sudo systemctl restart alpaca-agent
```

---

## Test status

**193 tests pass** (`python -m pytest`) as of 2026-08-26.

---

## Handoff for next session

1. Watch RTH on dashboard; confirm bars advancing and no unexpected staleness halts.
2. Merge PR #1 when healthy; keep VM on `feat/hybrid-mtf-and-ops` or switch to `master`.
3. On **Aug 28**, swap VM `.env` to competition Alpaca account; freeze strategy logic.
4. Optional: SG IP restriction, `orders` table, nginx/HTTPS.
5. Submission assets (write-up, video, slides) before Aug 31.
