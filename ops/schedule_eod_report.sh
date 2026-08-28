#!/usr/bin/env bash
set -eu
cd /opt/alpaca-options-agent
export PATH="/opt/alpaca-options-agent/.venv/bin:/usr/local/bin:/usr/bin:/bin"
set -a && source .env && set +a

WAIT=$(.venv/bin/python - <<'PY'
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("America/New_York"))
target = now.replace(hour=16, minute=5, second=0, microsecond=0)
if target <= now:
    target += timedelta(days=1)
print(int((target - now).total_seconds()))
PY
)
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] EOD report in ${WAIT}s (~16:05 ET)"
sleep "$WAIT"
.venv/bin/python ops/eod_session_report.py | tee -a "logs/eod-report-run.log"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] EOD report done"
