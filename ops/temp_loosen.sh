#!/usr/bin/env bash
set -euo pipefail
cd /opt/alpaca-options-agent

MODE="${1:-status}"

apply_demo() {
  python3 - <<'PY'
from pathlib import Path
p = Path("agent/screener.py")
text = p.read_text()
# Reset to known demo thresholds regardless of current state
import re
text = re.sub(r'"move_adr_mult":\s*[0-9.]+,', '"move_adr_mult": 0.35,', text, count=1)
text = re.sub(r'"min_rvol":\s*[0-9.]+,', '"min_rvol": 0.8,', text, count=1)
text = re.sub(r'"mtf_enabled":\s*(True|False),', '"mtf_enabled": False,', text, count=1)
p.write_text(text)
print("demo_thresholds_applied")
PY
  .venv/bin/python - <<'PY'
from importlib import reload
import agent.screener as s
reload(s)
print("TRIGGER", dict(s.TRIGGER))
assert s.TRIGGER["move_adr_mult"] == 0.35
assert s.TRIGGER["min_rvol"] == 0.8
assert s.TRIGGER["mtf_enabled"] is False
PY
  sudo systemctl restart alpaca-agent
  sleep 15
  systemctl is-active alpaca-agent
  journalctl -u alpaca-agent -n 8 --no-pager | grep -E "starting|halted|ERROR" || true
  echo "=== screener ==="
  .venv/bin/python ops/screener_why.py | tail -40
}

wait_decisions() {
  for i in $(seq 1 20); do
    NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    .venv/bin/python - <<'PY'
from agent import config, store
c = store.connect(config.DB_PATH)
n = c.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()["n"]
print("decision_count", n)
for r in c.execute(
    "SELECT ts_utc, symbol, action, detail, thesis FROM decisions "
    "ORDER BY ts_utc DESC LIMIT 12"
):
    detail = (r["detail"] or "")[:100]
    thesis = (r["thesis"] or "")[:80]
    print(f"  {r['ts_utc']} {r['symbol']} {r['action']} | {detail} | {thesis}")
raise SystemExit(0 if n > 0 else 1)
PY
    RC=$?
    echo "[poll $i] $NOW exit=$RC"
    if [ "$RC" -eq 0 ]; then
      echo "DECISIONS_FOUND"
      journalctl -u alpaca-agent --since "10 min ago" --no-pager | grep -E "tick:|entry|skip|model|gate|EXIT|no viable" | tail -30 || true
      .venv/bin/python ops/live_health.py
      return 0
    fi
    sleep 30
  done
  echo "NO_DECISIONS_AFTER_WAIT"
  .venv/bin/python ops/screener_why.py | tail -25
  journalctl -u alpaca-agent --since "10 min ago" --no-pager | grep -E "tick:|ERROR|halted|starting" | tail -20 || true
  return 1
}

revert_all() {
  git checkout -- agent/screener.py
  .venv/bin/python - <<'PY'
from importlib import reload
import agent.screener as s
reload(s)
print("TRIGGER", dict(s.TRIGGER))
assert s.TRIGGER["move_adr_mult"] == 0.50
assert s.TRIGGER["min_rvol"] == 1.5
assert s.TRIGGER["mtf_enabled"] is True
print("reverted_ok")
PY
  sudo systemctl restart alpaca-agent
  sleep 12
  systemctl is-active alpaca-agent
  journalctl -u alpaca-agent -n 5 --no-pager | grep -E "starting|halted|ERROR" || true
  .venv/bin/python ops/live_health.py
}

case "$MODE" in
  demo) apply_demo ;;
  wait) wait_decisions ;;
  revert) revert_all ;;
  status)
    .venv/bin/python - <<'PY'
from importlib import reload
import agent.screener as s
reload(s)
print("TRIGGER", dict(s.TRIGGER))
from agent import config, store
c = store.connect(config.DB_PATH)
print("decisions", c.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()["n"])
for r in c.execute("SELECT ts_utc, symbol, action, detail FROM decisions ORDER BY ts_utc DESC LIMIT 10"):
    print(r["ts_utc"], r["symbol"], r["action"], (r["detail"] or "")[:90])
PY
    ;;
  *)
    echo "usage: $0 demo|wait|revert|status" >&2
    exit 2
    ;;
esac
