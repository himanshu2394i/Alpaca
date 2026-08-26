#!/usr/bin/env bash
# Quick health check: Alpaca account reachable + local bar freshness.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Alpaca account ==="
alpaca account get --output json | python -c "import sys,json; d=json.load(sys.stdin); print('equity', d.get('equity'), 'status', d.get('status'))"

echo "=== Bar freshness (SPY) ==="
python - <<'PY'
from agent import config, store
c = store.connect(config.DB_PATH)
ts = store.last_bar_ts(c, "SPY")
print("SPY last bar:", ts or "NONE")
PY

echo "=== HALT file ==="
if [[ -f "$ROOT/HALT" ]]; then echo "HALT present — entries disabled"; else echo "ok"; fi
