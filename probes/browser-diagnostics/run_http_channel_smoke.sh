#!/usr/bin/env bash
# One-command real-HTTP acceptance run for a real browser (LG-013/021/027).
#
# Starts the real HTTP probe server (real HTML page + real JSON API + real SSE
# stream), then drives a real Chrome against it and prints the server log so
# you can see exactly which requests the browser made on the wire.
#
# Modes (passed through to http_channel_smoke.mjs):
#   all       doc-int + channel + bridge (default)
#   doc-int   attempt CDP Fetch interception of the main Document nav
#   channel   real browser fetch + real SSE (the working transport)
#   bridge    subresource transparent bridge (Node GET -> Fetch.fulfillRequest)
#
# Nothing here hardcodes a user home or a browser path; pick the browser with
# CHROME_BIN or --chrome. Only the server process group this script starts is
# cleaned up.
#
# Usage:
#   ./run_http_channel_smoke.sh [--chrome /path/to/chrome] [--mode all|…] \
#     [--port 0] [--deadline-ms 12000] [--server-lifetime 90]
#
# Exit code: 0 if the selected smoke modes reported ok (doc-int is informational).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chrome="${CHROME_BIN:-google-chrome}"
mode=all
port=0
deadline_ms=12000
server_lifetime=90

while [ $# -gt 0 ]; do
  case "$1" in
    --chrome) chrome="$2"; shift 2 ;;
    --mode) mode="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --deadline-ms) deadline_ms="$2"; shift 2 ;;
    --server-lifetime) server_lifetime="$2"; shift 2 ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

tmp="$(mktemp -d "${TMPDIR:-/tmp}/lg-http-smoke.XXXXXX")"
ready="$tmp/ready.json"
srv_log="$tmp/server.log"
srv_pid=""

cleanup() {
  if [ -n "$srv_pid" ]; then
    kill -- "-$srv_pid" 2>/dev/null || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT

setsid python3 "$here/http_probe_server.py" --port "$port" --ready-file "$ready" \
  --lifetime "$server_lifetime" --cors >"$srv_log" 2>&1 &
srv_pid=$!

for _ in $(seq 1 50); do
  [ -f "$ready" ] && break
  sleep 0.1
done
if [ ! -f "$ready" ]; then
  echo "probe server did not become ready" >&2
  cat "$srv_log" >&2 || true
  exit 1
fi
bound_port="$(python3 -c "import json;print(json.load(open('$ready'))['port'])")"
base="http://127.0.0.1:$bound_port"
echo "probe server: $base (pid group $srv_pid)"
echo "browser: $chrome"
echo "mode: $mode"

set +e
node "$here/http_channel_smoke.mjs" --base-url "$base" \
  --chrome "$chrome" --mode "$mode" --deadline-ms "$deadline_ms"
rc=$?
set -e

echo "--- server log (what the browser actually sent) ---"
cat "$srv_log"
exit "$rc"
