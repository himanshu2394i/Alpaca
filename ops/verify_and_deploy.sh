#!/usr/bin/env bash
set -euo pipefail
cd /opt/alpaca-options-agent

echo "=== TIME ==="
TZ=America/New_York date
date -u

echo "=== GIT ==="
git fetch origin
git rev-parse --short HEAD
git status --short | head -20

echo "=== ENSURE PRODUCTION SCREENER ==="
git checkout -- agent/screener.py
.venv/bin/python - <<'PY'
from importlib import reload
import agent.screener as s
reload(s)
print("runtime_thresholds",
      s.TRIGGER["move_adr_mult"],
      s.TRIGGER["min_rvol"],
      "mtf", s.TRIGGER["mtf_enabled"])
assert s.TRIGGER["move_adr_mult"] == 0.50
assert s.TRIGGER["min_rvol"] == 1.5
assert s.TRIGGER["mtf_enabled"] is True
from agent import config
print("universe", len(config.UNIVERSE))
assert len(config.UNIVERSE) == 30
print("screener_production_ok")
PY

echo "=== SERVICES ==="
systemctl is-active alpaca-ingest alpaca-agent alpaca-dashboard
ps -o user,pid,cmd -C python

echo "=== HEALTH ==="
.venv/bin/python ops/live_health.py

echo "=== LOGGING ==="
.venv/bin/python - <<'PY'
from agent import config, store
c = store.connect(config.DB_PATH)
eq = c.execute("SELECT COUNT(*) AS n FROM equity").fetchone()["n"]
dec = c.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()["n"]
bars = c.execute("SELECT COUNT(*) AS n FROM bars").fetchone()["n"]
print(f"rows equity={eq} decisions={dec} bars={bars}")
print("last_5_equity:")
for r in c.execute("SELECT ts_utc, value FROM equity ORDER BY ts_utc DESC LIMIT 5"):
    print(" ", r["ts_utc"], r["value"])
print("decisions:")
for r in c.execute("SELECT ts_utc, symbol, action, detail FROM decisions ORDER BY ts_utc"):
    print(" ", r["ts_utc"], r["symbol"], r["action"], (r["detail"] or "")[:90])
print("open_positions", len(store.open_positions(c)))
PY

echo "=== INGEST ==="
journalctl -u alpaca-ingest -n 6 --no-pager

echo "=== AGENT ==="
journalctl -u alpaca-agent -n 12 --no-pager | grep -E "starting|halted|ERROR|tick:|entry|WARNING agent" || journalctl -u alpaca-agent -n 5 --no-pager

echo "=== DASH ==="
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://127.0.0.1:8080/

# Redeploy clean HEAD so runtime matches git
echo "=== REDEPLOY CLEAN HEAD ==="
git reset --hard origin/feat/hybrid-mtf-and-ops
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo chown -R ubuntu:ubuntu data/
sudo systemctl restart alpaca-ingest alpaca-agent alpaca-dashboard
sleep 50
echo "HEAD=$(git rev-parse --short HEAD)"
systemctl is-active alpaca-ingest alpaca-agent alpaca-dashboard
.venv/bin/python - <<'PY'
from importlib import reload
import agent.screener as s
reload(s)
print("post_deploy", s.TRIGGER["move_adr_mult"], s.TRIGGER["min_rvol"], s.TRIGGER["mtf_enabled"])
assert s.TRIGGER["move_adr_mult"] == 0.50 and s.TRIGGER["min_rvol"] == 1.5 and s.TRIGGER["mtf_enabled"] is True
PY
.venv/bin/python ops/live_health.py
journalctl -u alpaca-ingest -n 8 --no-pager | grep -E "warm start|streaming|subscribed" || true
journalctl -u alpaca-agent -n 6 --no-pager | grep -E "starting|halted|ERROR" || true
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://127.0.0.1:8080/
echo "VERIFY_AND_DEPLOY_DONE"
