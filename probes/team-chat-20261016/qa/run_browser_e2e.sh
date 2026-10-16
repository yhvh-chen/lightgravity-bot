#!/usr/bin/env bash
# LG-050 QA: run the real-Firefox browser E2E against the candidate build.
#
# Starts the candidate team-mode server with the built frontend on a throwaway
# loopback port + data root, runs qa_browser_e2e.mjs, prints the server stderr
# (the independent wire fact) and stops only the server process group it started.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
PY="${PY:-/home/yhvh/code/lightgravity-bot/.venv/bin/python}"
FIREFOX_BIN="${FIREFOX_BIN:-/snap/bin/firefox}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/snap/firefox/current}"
DEADLINE_MS="${DEADLINE_MS:-90000}"
DATA_DIR="${DATA_DIR:-$(mktemp -d -t lg050-browser-XXXXXX)}"

SRV_LOG="$(mktemp -t lg050_browser_srv.XXXXXX.log)"
OUT_JSON="${OUT_JSON:-$HERE/qa-browser-results.json}"

cleanup() {
  if [ -n "${SRV_PID:-}" ] && kill -0 "$SRV_PID" 2>/dev/null; then
    kill "$SRV_PID" 2>/dev/null || true
    wait "$SRV_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

PYTHONPATH="$REPO_ROOT/backend" "$PY" "$HERE/qa_browser_server.py" \
  --frontend-dist "$REPO_ROOT/frontend/dist" --data-dir "$DATA_DIR" \
  > "$SRV_LOG" 2>&1 &
SRV_PID=$!

URL=""
for _ in $(seq 1 100); do
  if grep -q '^READY ' "$SRV_LOG"; then
    URL="$(grep -m1 '^READY ' "$SRV_LOG" | awk '{print $2}')"
    break
  fi
  if ! kill -0 "$SRV_PID" 2>/dev/null; then
    echo "server exited early:" >&2
    cat "$SRV_LOG" >&2
    exit 1
  fi
  sleep 0.1
done
if [ -z "$URL" ]; then
  echo "server never became ready" >&2
  cat "$SRV_LOG" >&2
  exit 1
fi
echo "# browser server $URL (log=$SRV_LOG)"

set +e
node "$HERE/qa_browser_e2e.mjs" \
  --url "$URL" --firefox "$FIREFOX_BIN" --profile-dir "$PROFILE_DIR" \
  --deadline-ms "$DEADLINE_MS" 2>&1 | tee "$OUT_JSON.raw"
RC=${PIPESTATUS[0]}
set -e

echo "===== candidate server log (independent wire fact) ====="
cat "$SRV_LOG"
echo "===== browser E2E exit=$RC ====="
exit "$RC"
