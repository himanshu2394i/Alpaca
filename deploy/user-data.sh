#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y git python3 python3-venv python3-pip

install -d -o ubuntu -g ubuntu /opt/alpaca-options-agent
sudo -u ubuntu git clone --branch feat/hybrid-mtf-and-ops \
  https://github.com/himanshu2394i/Alpaca.git /opt/alpaca-options-agent

cd /opt/alpaca-options-agent
sudo -u ubuntu python3 -m venv .venv
sudo -u ubuntu .venv/bin/pip install --upgrade pip
sudo -u ubuntu .venv/bin/pip install -e ".[dev]"

install -m 644 deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload

install -d -o ubuntu -g ubuntu /opt/alpaca-options-agent/data
install -d -o ubuntu -g ubuntu /opt/alpaca-options-agent/logs

cat >/opt/alpaca-options-agent/SETUP.txt <<'EOF'
Add secrets before starting services:

  sudo nano /opt/alpaca-options-agent/.env

Required:
  ALPACA_API_KEY=...
  ALPACA_SECRET_KEY=...
  ALPACA_PAPER_TRADE=true
  ANTHROPIC_API_KEY=...   # omit if using --deterministic

Then:
  sudo systemctl enable --now alpaca-ingest alpaca-agent alpaca-dashboard

Dashboard: http://<this-server-public-ip>:8080
Dry run is default on the agent until you edit alpaca-agent.service to use --live.
EOF
chown ubuntu:ubuntu /opt/alpaca-options-agent/SETUP.txt
