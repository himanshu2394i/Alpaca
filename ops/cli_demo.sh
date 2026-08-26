#!/usr/bin/env bash
# Judge-facing Alpaca CLI smoke demo — account, clock, positions as JSON.
# Pair with MCP-based agent trading to show both required stack pieces.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v alpaca >/dev/null 2>&1; then
  echo "alpaca CLI not found on PATH" >&2
  exit 1
fi

echo "=== alpaca account get ==="
alpaca account get --output json

echo "=== alpaca clock get ==="
alpaca clock get --output json || alpaca market-clock get --output json || true

echo "=== alpaca position list ==="
alpaca position list --output json

echo "CLI_DEMO_OK"
