#!/usr/bin/env bash
# run_firefox_bidi_smoke.sh — one-command Firefox native-BiDi acceptance run.
#
# Scope: browser diagnostics evidence only. Starts the real probe HTTP server,
# runs the real Firefox BiDi smoke, prints both the server-side request log
# (the independent wire fact) and the browser-side result, then cleans up only
# the server process group it started.
#
# Usage:
#   cd probes/browser-diagnostics
#   ./run_firefox_bidi_smoke.sh [--mode all] [--deadline-ms 40000] \
#       [--firefox /path/to/firefox] [--profile-dir DIR]
#
# Notes on this host:
#   - The only working Firefox is the Ubuntu snap (156.0.1). Its confined
#     $HOME is ~/snap/firefox/current, so the temporary profile MUST live under
#     that path (the script defaults --profile-dir to $HOME/snap/firefox/current
#     when no other firefox is given). The system /usr/bin/firefox is a snap
#     shim and is not usable directly.
#   - Screenshot/`--screenshot` output is also confined; write it under the
#     snap $HOME too.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="all"
DEADLINE_MS=40000
FIREFOX_BIN="${FIREFOX_BIN:-firefox}"
PROFILE_DIR=""
SERVER_LIFETIME=120
SSE_EVENTS=3
SSE_INTERVAL_MS=100

while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --deadline-ms) DEADLINE_MS="$2"; shift 2 ;;
    --firefox) FIREFOX_BIN="$2"; shift 2 ;;
    --profile-dir) PROFILE_DIR="$2"; shift 2 ;;
    --server-lifetime) SERVER_LIFETIME="$2"; shift 2 ;;
    --sse-events) SSE_EVENTS="$2"; shift 2 ;;
    --sse-interval-ms) SSE_INTERVAL_MS="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Default temp-profile root that the snap Firefox can actually read/write.
if [ -z "$PROFILE_DIR" ]; then
  if [ -d "$HOME/snap/firefox/current" ]; then
    PROFILE_DIR="$HOME/snap/firefox/current"
  else
    PROFILE_DIR="$(mktemp -d)"
  fi
fi

READY="$(mktemp -t ff_bidi_ready.XXXXXX.json)"
SRV_LOG="$(mktemp -t ff_bidi_srv.XXXXXX.log)"
rm -f "$READY"

python3 "$HERE/http_probe_server.py" \
  --port 0 --ready-file "$READY" --lifetime "$SERVER_LIFETIME" \
  --sse-events "$SSE_EVENTS" --sse-interval-ms "$SSE_INTERVAL_MS" \
  > "$SRV_LOG" 2>&1 &
SRV=$!
cleanup() {
  # only our own server group (we started it in this shell); never touch others
  kill "$SRV" 2>/dev/null || true
  wait "$SRV" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 50); do
  [ -f "$READY" ] && break
  sleep 0.1
done
PORT="$(python3 -c "import json;print(json.load(open('$READY'))['port'])")"
echo "# probe server 127.0.0.1:$PORT (srclog=$SRV_LOG)"

set +e
node "$HERE/firefox_bidi_smoke.mjs" \
  --url "http://127.0.0.1:$PORT/page" \
  --mode "$MODE" --deadline-ms "$DEADLINE_MS" \
  --firefox "$FIREFOX_BIN" --profile-dir "$PROFILE_DIR"
RC=$?
set -e

echo "===== server-side request log (independent wire fact) ====="
cat "$SRV_LOG"
echo "===== smoke exit code: $RC ====="
exit "$RC"
