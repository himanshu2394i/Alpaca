#!/usr/bin/env bash
# End-of-day equity snapshot via Alpaca CLI. Cron: 5 16 * * 1-5 ET
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OUT="$LOG_DIR/eod-${STAMP}.json"

echo "[$STAMP] snapshot -> $OUT"
alpaca account get --output json > "$OUT"
alpaca position list --output json > "$LOG_DIR/positions-${STAMP}.json"
echo "done"
