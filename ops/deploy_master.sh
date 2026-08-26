#!/usr/bin/env bash
set -euo pipefail
cd /opt/alpaca-options-agent
git fetch origin
git checkout master
git reset --hard origin/master
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo cp deploy/systemd/*.timer /etc/systemd/system/ 2>/dev/null || true
sudo systemctl daemon-reload
sudo chown -R ubuntu:ubuntu data/
sudo systemctl restart alpaca-ingest alpaca-agent alpaca-dashboard
sleep 45
echo "HEAD=$(git rev-parse --short HEAD)"
systemctl is-active alpaca-ingest alpaca-agent alpaca-dashboard
.venv/bin/python - <<'PY'
from importlib import reload
import agent.screener as s
import agent.execute as e
import agent.reconcile as r
reload(s); reload(e); reload(r)
print("thresholds", s.TRIGGER["move_adr_mult"], s.TRIGGER["min_rvol"], "mtf", s.TRIGGER["mtf_enabled"])
assert s.TRIGGER["move_adr_mult"] == 0.50
assert s.TRIGGER["min_rvol"] == 1.5
assert s.TRIGGER["mtf_enabled"] is True
assert hasattr(e, "is_filled")
assert hasattr(r, "_broker_positions_usable")
from agent import config
print("universe", len(config.UNIVERSE))
assert len(config.UNIVERSE) == 30
print("post_deploy_ok")
PY
.venv/bin/python ops/live_health.py
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://127.0.0.1:8080/
journalctl -u alpaca-agent -n 8 --no-pager | grep -E "starting|halted|ERROR|reconcile" || journalctl -u alpaca-agent -n 5 --no-pager
echo "DEPLOY_MASTER_DONE"
