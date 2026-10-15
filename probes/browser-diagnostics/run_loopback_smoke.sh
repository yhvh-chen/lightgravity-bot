#!/usr/bin/env bash
# Bounded real-browser loopback-HTTP acceptance, end to end.
#
# Starts the marker server, runs the loopback smoke (file:// shell + fetch),
# prints the server log so you can see the GET + RESP 200, then cleans up the
# server process group. Nothing here hardcodes a user home or a browser path:
# pick the binary with CHROME_BIN or --chrome.
#
# Usage:
#   ./run_loopback_smoke.sh [--chrome /path/to/chrome] [--port 0] \
#     [--path fetch|nav] [--deadline-ms 12000] [--server-lifetime 60]
#
# Env:
#   CHROME_BIN   browser binary (default: google-chrome on PATH)
#
# Exit code: 0 if the smoke reported ok=true, else 1.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chrome="${CHROME_BIN:-google-chrome}"
port=0
path_mode=fetch
deadline_ms=12000
server_lifetime=60

while [ $# -gt 0 ]; do
  case "$1" in
    --chrome) chrome="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --path) path_mode="$2"; shift 2 ;;
    --deadline-ms) deadline_ms="$2"; shift 2 ;;
    --server-lifetime) server_lifetime="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

tmp="$(mktemp -d "${TMPDIR:-/tmp}/lg-loopback.XXXXXX")"
ready="$tmp/ready.json"
srv_log="$tmp/server.log"
srv_pid=""

cleanup() {
  # kill only the server group we started
  if [ -n "$srv_pid" ]; then
    kill -- "-$srv_pid" 2>/dev/null || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT

setsid python3 "$here/marker_server.py" --port "$port" --ready-file "$ready" \
  --lifetime "$server_lifetime" --cors >"$srv_log" 2>&1 &
srv_pid=$!

for _ in $(seq 1 50); do
  [ -f "$ready" ] && break
  sleep 0.1
done
if [ ! -f "$ready" ]; then
  echo "marker server did not become ready" >&2
  exit 1
fi
bound_port="$(python3 -c "import json;print(json.load(open('$ready'))['port'])")"
echo "marker server on 127.0.0.1:$bound_port (pid group $srv_pid)"
echo "browser: $chrome"
echo "path: $path_mode"

set +e
node "$here/loopback_smoke.mjs" \
  --url "http://127.0.0.1:$bound_port/marker" \
  --chrome "$chrome" --path "$path_mode" --deadline-ms "$deadline_ms"
rc=$?
set -e

echo "--- server log (Chrome's GET must appear here) ---"
cat "$srv_log"
exit "$rc"
