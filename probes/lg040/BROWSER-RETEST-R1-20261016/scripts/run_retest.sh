#!/usr/bin/env bash
# LG-040 BROWSER RETEST R1 — one-command real-app + real-browser recheck.
#
# Starts (1) the loopback DENY proxy (0 model calls; refuses before HTTP),
# (2) the real product app against the SNAPSHOT COPY of the prior live data dir,
# then (3) the Firefox BiDi driver.
# Cleans up every process it started on exit (own process groups only).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROBE="$(cd "$HERE/.." && pwd)"
ROOT="$(cd "$PROBE/../../.." && pwd)"
VENV="$ROOT/.venv/bin/python"
[ -x "$VENV" ] || VENV="$(command -v python3)"
FIREFOX="/snap/bin/firefox"
RUN_DIR="${RUN_DIR:-/tmp/lg040-browser-retest-run}"
DEADLINE=90000

while [ $# -gt 0 ]; do
  case "$1" in
    --run-dir) RUN_DIR="$2"; shift 2 ;;
    --firefox) FIREFOX="$2"; shift 2 ;;
    --deadline-ms) DEADLINE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$RUN_DIR" "$PROBE/logs"
PROXY_PID=""; APP_PID=""
cleanup() {
  [ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null
  [ -n "$PROXY_PID" ] && kill "$PROXY_PID" 2>/dev/null
  sleep 1
  [ -n "$APP_PID" ] && kill -9 "$APP_PID" 2>/dev/null
  [ -n "$PROXY_PID" ] && kill -9 "$PROXY_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

# --- (1) DENY proxy (loopback, refuses before HTTP; ledger of attempts) ---
rm -f "$RUN_DIR/proxy_ready.json" "$RUN_DIR/ledger.json"
"$VENV" "$HERE/deny_proxy.py" \
  --port 0 --ledger "$RUN_DIR/ledger.json" --ready-file "$RUN_DIR/proxy_ready.json" \
  > "$PROBE/logs/deny-proxy.log" 2>&1 &
PROXY_PID=$!
for i in $(seq 1 60); do [ -f "$RUN_DIR/proxy_ready.json" ] && break; sleep 0.2; done
if [ ! -f "$RUN_DIR/proxy_ready.json" ]; then echo "FATAL: deny proxy not ready" >&2; cat "$PROBE/logs/deny-proxy.log" >&2; exit 3; fi
PPORT=$("$VENV" -c "import json;print(json.load(open('$RUN_DIR/proxy_ready.json'))['port'])")
echo "deny proxy port=$PPORT pid=$PROXY_PID"

# --- (2) real isolated app on the SNAPSHOT COPY data dir ---
rm -f "$RUN_DIR/app_ready.json"
DATA_DIR="$PROBE/evidence/snapshot/data"
[ -d "$DATA_DIR" ] || { echo "FATAL: snapshot data missing: $DATA_DIR" >&2; exit 3; }
"$VENV" "$HERE/launch_app.py" \
  --data-dir "$DATA_DIR" --ocr-base-url "http://127.0.0.1:$PPORT" --ocr-model qwen3.8-27b \
  --table-mode 1 --frontend-dist "$ROOT/frontend/dist" \
  --ready-file "$RUN_DIR/app_ready.json" \
  > "$PROBE/logs/app-retest.log" 2>&1 &
APP_PID=$!
for i in $(seq 1 150); do [ -f "$RUN_DIR/app_ready.json" ] && break; sleep 0.2; done
if [ ! -f "$RUN_DIR/app_ready.json" ]; then echo "FATAL: app not ready" >&2; tail -40 "$PROBE/logs/app-retest.log" >&2; exit 3; fi
APP_URL=$("$VENV" -c "import json;print(json.load(open('$RUN_DIR/app_ready.json'))['url'])")
echo "app url=$APP_URL pid=$APP_PID"

# --- (3) real Firefox BiDi driver ---
mkdir -p "$PROBE/evidence/run"
node "$HERE/lg040-retest-driver.mjs" \
  --url "$APP_URL" --out "$PROBE/evidence/run" --firefox "$FIREFOX" \
  --deadline-ms "$DEADLINE" --profile-dir "${HOME}/snap/firefox/current" 2>&1 | tee "$PROBE/logs/browser-retest.log"
RC=${PIPESTATUS[0]}
echo "browser exit=$RC"
echo "--- deny ledger (attempts must be 0) ---"
cat "$RUN_DIR/ledger.json" 2>/dev/null || echo "(no ledger)"
exit $RC
