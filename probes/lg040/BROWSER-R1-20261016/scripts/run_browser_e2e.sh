#!/usr/bin/env bash
# LG-040 BROWSER owner — one-command real-app + real-browser E2E runner.
#
# Starts (1) the persistent reservation proxy, (2) the isolated real product app
# with OCR base URL pointing at the proxy, then (3) the Firefox BiDi driver.
# Cleans up every process it started on exit (own process groups only).
#
# Modes:
#   --mode live   real OCR through the proxy (spends the frozen POST budget)
#   --mode dry    OCR base URL points at a dead loopback port (no model call;
#                 exercises upload/Files/search/formal/download/auth paths)
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROBE="$(cd "$HERE/.." && pwd)"
ROOT="$(cd "$PROBE/../../.." && pwd)"
VENV="$ROOT/.venv/bin/python"
[ -x "$VENV" ] || VENV="$(command -v python3)"

MODE="live"
RUN_DIR="/tmp/lg040-browser-run"
FIREFOX="/snap/bin/firefox"
DEADLINE=180000
while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
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

# --- (1) reservation proxy ---
rm -f "$RUN_DIR/proxy_ready.json" "$RUN_DIR/ledger.json"
"$VENV" "$HERE/ocr_reservation_proxy.py" \
  --port 0 --ledger "$RUN_DIR/ledger.json" --cap 2 --get-cap 2 \
  --ready-file "$RUN_DIR/proxy_ready.json" > "$PROBE/logs/proxy-$MODE.log" 2>&1 &
PROXY_PID=$!
for i in $(seq 1 60); do [ -f "$RUN_DIR/proxy_ready.json" ] && break; sleep 0.2; done
if [ ! -f "$RUN_DIR/proxy_ready.json" ]; then echo "FATAL: proxy not ready" >&2; cat "$PROBE/logs/proxy-$MODE.log" >&2; exit 3; fi
PPORT=$("$VENV" -c "import json;print(json.load(open('$RUN_DIR/proxy_ready.json'))['port'])")
echo "proxy port=$PPORT pid=$PROXY_PID"

if [ "$MODE" = "dry" ]; then
  OCR_BASE="http://127.0.0.1:1"   # dead: OCR honestly unavailable, 0 model calls
else
  OCR_BASE="http://127.0.0.1:$PPORT"
fi
echo "OCR base = $OCR_BASE"

# --- (2) real isolated app ---
rm -f "$RUN_DIR/app_ready.json"
rm -rf "$RUN_DIR/data"
"$VENV" "$HERE/launch_app.py" \
  --data-dir "$RUN_DIR/data" --ocr-base-url "$OCR_BASE" --ocr-model qwen3.8-27b \
  --table-mode 1 --ready-file "$RUN_DIR/app_ready.json" \
  > "$PROBE/logs/app-$MODE.log" 2>&1 &
APP_PID=$!
for i in $(seq 1 150); do [ -f "$RUN_DIR/app_ready.json" ] && break; sleep 0.2; done
if [ ! -f "$RUN_DIR/app_ready.json" ]; then echo "FATAL: app not ready" >&2; tail -30 "$PROBE/logs/app-$MODE.log" >&2; exit 3; fi
APP_URL=$("$VENV" -c "import json;print(json.load(open('$RUN_DIR/app_ready.json'))['url'])")
echo "app url=$APP_URL pid=$APP_PID"

# --- (3) real Firefox BiDi driver ---
mkdir -p "$PROBE/evidence/$MODE"
LIVE_FLAG=""
[ "$MODE" = "live" ] && LIVE_FLAG="--live"
node "$HERE/lg040-browser-e2e.mjs" \
  --url "$APP_URL" --out "$PROBE/evidence/$MODE" --firefox "$FIREFOX" \
  --deadline-ms "$DEADLINE" --profile-dir "${HOME}/snap/firefox/current" $LIVE_FLAG 2>&1 | tee "$PROBE/logs/browser-$MODE.log"
RC=${PIPESTATUS[0]}
echo "browser exit=$RC"
echo "--- ledger ---"
cat "$RUN_DIR/ledger.json" 2>/dev/null || echo "(no ledger)"
exit $RC
