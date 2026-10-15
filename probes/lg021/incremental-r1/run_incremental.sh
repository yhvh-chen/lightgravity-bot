#!/usr/bin/env bash
# LG-021 incremental QA driver (incremental-r1).
#
# Starts the REAL one-process product server (lightgravity CLI: frontend/dist +
# /api/v1) on a dedicated loopback port with an ISOLATED temp data dir and
# workspace, seeds real fixtures, then drives real Firefox (native BiDi) over
# real same-origin HTTP for the LG-021 incremental gap-closing checks only.
#
# Safety: only its own temp dir / process group / profile are used or removed.
# Never touches the existing root 8123 service, other worktrees or their PIDs.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
FIREFOX_BIN="${FIREFOX_BIN:-/snap/bin/firefox}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/snap/firefox/current}"

TMP="$(mktemp -d -t lg021-incr.XXXXXX)"
DATA="$TMP/data"
WS="$TMP/workspace"
SHOTS="$TMP/shots"
mkdir -p "$DATA" "$WS" "$SHOTS" "$HERE/evidence"
SERVER_LOG="$TMP/server.log"
echo "# tmp=$TMP"

# Reuse the already-validated real seed (independent data root).
SEED_JSON="$(cd "$REPO" && uv run python "$HERE/../scripts/seed_lg021_fixtures.py" "$DATA" "$WS" 2>"$TMP/seed.err")"
echo "$SEED_JSON" > "$TMP/seed.json"

PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
echo "# port=$PORT"

export LIGHTGRAVITY_RUNTIME_TOKEN="lg021-incr-token-$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')"

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
  echo "server not ready"; tail -40 "$SERVER_LOG"; exit 1
fi
echo "# server ready"

# The probe logs progress to stderr and prints ONLY the JSON result to stdout,
# so the evidence file stays valid JSON.
set +e
node "$HERE/incremental_qa.mjs" \
  --url "http://127.0.0.1:$PORT/" \
  --firefox "$FIREFOX_BIN" \
  --profile-dir "$PROFILE_DIR" \
  --out-dir "$SHOTS" \
  --deadline-ms 90000 \
  > "$HERE/evidence/incremental-results.json" 2> "$HERE/evidence/incremental-progress.log"
RC=$?
set -e

echo "# incremental probe exit=$RC"
tail -60 "$HERE/evidence/incremental-progress.log" || true

# copy screenshots + server tail into evidence (own temp only)
cp -f "$SHOTS"/*.png "$HERE/evidence/" 2>/dev/null || true
cp -f "$TMP/seed.json" "$HERE/evidence/seed.json" 2>/dev/null || true
tail -30 "$SERVER_LOG" > "$HERE/evidence/server-tail.log" 2>/dev/null || true
echo "# data root: $DATA"
exit $RC
