#!/usr/bin/env bash
# LG-021 first-version frontend QA driver.
#
# Starts the REAL one-process product server (lightgravity CLI: frontend/dist +
# /api/v1) on a dedicated loopback port with an isolated temp data dir and
# workspace, seeds real fixtures, then drives real Firefox (native BiDi) over
# real same-origin HTTP.
#
# Safety: only its own temp dir / process group / profile are used or removed.
# Never touches the existing root 8123 service, other worktrees or their PIDs.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
FIREFOX_BIN="${FIREFOX_BIN:-/snap/bin/firefox}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/snap/firefox/current}"

TMP="$(mktemp -d -t lg021-qa.XXXXXX)"
DATA="$TMP/data"
WS="$TMP/workspace"
SHOTS="$TMP/shots"
mkdir -p "$DATA" "$WS" "$SHOTS" "$HERE/../evidence"
SERVER_LOG="$TMP/server.log"
echo "# tmp=$TMP"

SEED_JSON="$(cd "$REPO" && uv run python "$HERE/seed_lg021_fixtures.py" "$DATA" "$WS" 2>"$TMP/seed.err")"
echo "# seeded=$SEED_JSON"
echo "$SEED_JSON" > "$TMP/seed.json"

PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
echo "# port=$PORT"

# Runtime token: injected only via process env (never written to the repo).
export LIGHTGRAVITY_RUNTIME_TOKEN="lg021-qa-token-$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')"

cd "$REPO/backend"
uv run python -m lightgravity start \
  --data-dir "$DATA" --workspace-root "$WS" \
  --host 127.0.0.1 --port "$PORT" \
  --frontend-dist "$REPO/frontend/dist" \
  --no-executor \
  > "$SERVER_LOG" 2>&1 &
SRV=$!
cleanup() {
  # only our own server process; never siblings/root
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
  echo "server not ready"; tail -40 "$SERVER_LOG"; exit 1
fi
echo "# server ready"

# Wire facts from the server side, independent of the browser.
curl -s "http://127.0.0.1:$PORT/api/v1/tasks" > "$TMP/api-tasks.json" || true
curl -s "http://127.0.0.1:$PORT/api/v1/notifications" > "$TMP/api-notifications.json" || true
echo "# api tasks: $(head -c 200 "$TMP/api-tasks.json")"
echo "# api notifications: $(head -c 200 "$TMP/api-notifications.json")"

set +e
node "$HERE/lg021_browser_qa.mjs" \
  --url "http://127.0.0.1:$PORT/" \
  --firefox "$FIREFOX_BIN" \
  --profile-dir "$PROFILE_DIR" \
  --out-dir "$SHOTS" \
  --deadline-ms 140000
RC=$?
set -e

echo "# browser qa exit=$RC"
# Copy screenshots + raw server log into evidence (own temp only).
cp -f "$TMP/evidence/browser-qa-results.json" "$HERE/../evidence/browser-qa-results.json" 2>/dev/null || true
cp -f "$SHOTS"/*.png "$HERE/../evidence/" 2>/dev/null || true
cp -f "$TMP/api-tasks.json" "$HERE/../evidence/api-tasks.json" 2>/dev/null || true
cp -f "$TMP/api-notifications.json" "$HERE/../evidence/api-notifications.json" 2>/dev/null || true
cp -f "$TMP/seed.json" "$HERE/../evidence/seed.json" 2>/dev/null || true
tail -20 "$SERVER_LOG" > "$HERE/../evidence/server-tail.log" 2>/dev/null || true
ls -1 "$HERE/../evidence/"
exit $RC
