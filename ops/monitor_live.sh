#!/usr/bin/env bash
# Monitor decisions + equity every N seconds during RTH. Logs anomalies.
set -euo pipefail
cd /opt/alpaca-options-agent
export PATH="/opt/alpaca-options-agent/.venv/bin:/usr/local/bin:/usr/bin:/bin"
set -a && source .env && set +a

INTERVAL="${1:-120}"
LOG="${2:-logs/monitor-$(date -u +%Y%m%d).log}"
mkdir -p logs

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] monitor start interval=${INTERVAL}s" | tee -a "$LOG"

while true; do
  STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    echo "=== $STAMP ==="
    .venv/bin/python ops/live_health.py 2>&1 | head -20
    .venv/bin/python ops/validate_live.py 2>&1 || true
    echo "--- last agent ticks ---"
    journalctl -u alpaca-agent --since "3 min ago" --no-pager 2>&1 \
      | grep -E "tick:|exit|halted|abandoned|entry not" | tail -8 || true
  } >> "$LOG" 2>&1
  echo "$STAMP logged" >> "$LOG.summary"
  sleep "$INTERVAL"
done
