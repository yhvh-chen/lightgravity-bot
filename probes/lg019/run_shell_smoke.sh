#!/usr/bin/env bash
# LG-019 product shell notification smoke driver.
#
# Seeds a temp data dir with a durable failed-phase event, starts the REAL
# one-process product server (lightgravity CLI serving frontend/dist + /api/v1)
# on a loopback port, then drives real Firefox (native BiDi) against it.
#
# Scope: evidence only. Uses only its own temp dir/PIDs; never touches the
# existing root 8123 service or other worktrees.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
FIREFOX_BIN="${FIREFOX_BIN:-/snap/bin/firefox}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/snap/firefox/current}"

TMP="$(mktemp -d -t lg019-shell.XXXXXX)"
DATA="$TMP/data"
WS="$TMP/workspace"
mkdir -p "$DATA" "$WS"
SERVER_LOG="$TMP/server.log"

echo "# tmp=$TMP"

TASK_ID="$(cd "$REPO" && uv run python "$HERE/seed_notification.py" "$DATA" "$WS")"
echo "# seeded task=$TASK_ID"

PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
echo "# port=$PORT"

cd "$REPO/backend"
uv run python -m lightgravity start \
  --data-dir "$DATA" --workspace-root "$WS" \
  --host 127.0.0.1 --port "$PORT" \
  --frontend-dist "$REPO/frontend/dist" \
  --no-executor \
  > "$SERVER_LOG" 2>&1 &
SRV=$!
cleanup() {
  kill "$SRV" 2>/dev/null || true
  wait "$SRV" 2>/dev/null || true
}
trap cleanup EXIT

READY=0
for _ in $(seq 1 80); do
  if curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1; then READY=1; break; fi
  sleep 0.25
done
if [ "$READY" != "1" ]; then
  echo "server not ready"; tail -30 "$SERVER_LOG"; exit 1
fi
echo "# server ready"

set +e
node "$HERE/lg019_shell_smoke.mjs" \
  --url "http://127.0.0.1:$PORT/" \
  --firefox "$FIREFOX_BIN" \
  --profile-dir "$PROFILE_DIR" \
  --out "$HERE/evidence/shell-smoke.json" \
  --deadline-ms 60000
RC=$?
set -e

echo "===== server-side notification requests (independent wire fact) ====="
grep -E "GET /api/v1/notifications|POST /api/v1/notifications" "$SERVER_LOG" | tail -20 || true
echo "===== smoke exit code: $RC ====="
exit "$RC"
