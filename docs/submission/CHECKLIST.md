# Hackathon submission checklist

Use this before **Sep 4, 2026 20:30 IST** (End of Submissions).

## Eligibility (blocking)

- [ ] **Brand-new** Alpaca paper account created for this hackathon (not the throwaway/dev account)
- [ ] Starting balance set to **$100,000**
- [ ] Options approval sufficient for long calls/puts (paper)
- [ ] Competition keys only in VM `.env` (never committed)
- [ ] Submit **Alpaca paper trading account ID** on the lablab form

## Required deliverables

- [ ] Project title + short + long description
- [ ] Cover image
- [ ] Video presentation (2–3 min: dashboard → decision → order → position)
- [ ] Slide presentation
- [ ] Public GitHub repo: https://github.com/himanshu2394i/Alpaca
- [ ] Application URL: http://35.175.208.115:8080 (or updated host)
- [ ] One-page write-up: `docs/submission/ONE_PAGER.pdf` (or paste from `ONE_PAGER.md`)
- [ ] Technology tags (Alpaca Trading API, MCP, CLI, options, agents)

## Social engagement (optional $500 track — up to 5 links)

- [ ] Post 1–5 on X and/or LinkedIn during 28 Aug–4 Sep
- [ ] Each post tags **lablab.ai** and **Alpaca** (`@lablabai` / `@AlpacaHQ` on X)
- [ ] Paste links into submission — drafts in `docs/submission/SOCIAL_DRAFTS.md`

## Day-of competition (31 Aug)

- [ ] Create fresh $100k paper account (you)
- [ ] Run `python ops/competition_cutover.py --apply` on VM (wipes audit trail, keeps bars)
- [ ] Put competition keys in VM `.env`; restart systemd units
- [ ] Confirm dashboard + agent `dry_run=False` + equity ≈ 100000
- [ ] Submit **Alpaca paper account ID** on lablab
- [ ] **Freeze strategy logic** after cutover (tuning params only)

## Pre-submit smoke test

```bash
# on VM
systemctl is-active alpaca-ingest alpaca-agent alpaca-dashboard
ops/health.sh
ops/cli_demo.sh
.venv/bin/python ops/live_health.py
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/
```
