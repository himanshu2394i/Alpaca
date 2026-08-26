#!/usr/bin/env bash
set -euo pipefail
cd /opt/alpaca-options-agent
git fetch origin
git reset --hard origin/feat/hybrid-mtf-and-ops
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo cp deploy/systemd/*.timer /etc/systemd/system/ 2>/dev/null || true
sudo systemctl daemon-reload
sudo chown -R ubuntu:ubuntu data/
sudo systemctl restart alpaca-ingest alpaca-agent alpaca-dashboard
sleep 45
echo "HEAD=$(git rev-parse --short HEAD)"
systemctl is-active alpaca-ingest alpaca-agent alpaca-dashboard
ps -o user,pid,cmd -C python
ls -la data/market.db*
journalctl -u alpaca-ingest -n 8 --no-pager
journalctl -u alpaca-agent -n 6 --no-pager | grep -E "starting|halted|ERROR" || true
.venv/bin/python ops/live_health.py
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://127.0.0.1:8080/
