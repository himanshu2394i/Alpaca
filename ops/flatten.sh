#!/usr/bin/env bash
# Emergency flatten: cancel open orders and close all option positions.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
touch "$ROOT/HALT"
echo "HALT file created — agent will stop new entries."

echo "Cancelling open orders..."
alpaca order cancel-all || true

echo "Closing positions..."
python - <<'PY'
import asyncio, json, subprocess, sys

async def main():
    from agent import mcp_bridge
    async with mcp_bridge.session() as sess:
        positions = await mcp_bridge.call(sess, "get_all_positions", {})
        snaps = positions.get("positions") or positions.get("snapshots") or positions
        if isinstance(snaps, dict):
            items = snaps.values()
        elif isinstance(snaps, list):
            items = snaps
        else:
            items = []
        for p in items:
            sym = p.get("symbol") or p.get("asset_id")
            if not sym:
                continue
            print("closing", sym)
            await mcp_bridge.call(sess, "close_position", {"symbol": sym})

asyncio.run(main())
PY

echo "flatten complete"
