#!/usr/bin/env bash
# LG-027 browser QA driver: start the real local service (serving frontend/dist),
# seed a fixture Task, run the CDP browser check, then stop the process.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PORT="${LG027_PORT:-8010}"
OUT="${LG027_OUT:-/tmp/lg027-browser}"
DATA="$(mktemp -d /tmp/lg027-browser-data-XXXXXX)"
SECRETS="$(mktemp -d /tmp/lg027-browser-secrets-XXXXXX)"
TOKEN="lg027-browser-token"
LOG="$DATA/server.log"

mkdir -p "$OUT"
cd "$REPO"

LIGHTGRAVITY_RUNTIME_TOKEN="$TOKEN" \
uv run python -m lightgravity start \
  --host 127.0.0.1 --port "$PORT" \
  --data-dir "$DATA" --workspace-root "$DATA/workspaces" \
  --secret-store "$SECRETS" >"$LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1; then break; fi
  sleep 0.25
done

# Seed a real Task so the Settings detour has a real Task scope to return to.
# Capture the server-generated id and pass it to the browser check so the
# "keeps current Task scope" assertion is against a genuinely existing Task.
FIXTURE_JSON=$(curl -sf -X POST "http://127.0.0.1:$PORT/api/v1/tasks" \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"lg027-browser-fixture","title":"lg027 fixture","objective":"fixture","acceptance_criteria":["x"],"workspace_ref":"ws"}') || FIXTURE_JSON='{}'
FIXTURE_TASK="$(printf '%s' "$FIXTURE_JSON" | uv run python -c 'import json,sys; print(json.load(sys.stdin).get("task_id", ""))' 2>/dev/null || true)"
echo "fixture_task=$FIXTURE_TASK"

LG027_BASE_URL="http://127.0.0.1:$PORT" LG027_OUT="$OUT" LG027_FIXTURE_TASK="$FIXTURE_TASK" \
  node "$REPO/probes/lg027/scripts/lg027_browser.mjs"

echo "data_dir=$DATA"
echo "server_log=$LOG"
