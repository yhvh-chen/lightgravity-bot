#!/usr/bin/env bash
# LG-024 Stage A private startup smoke test.
#
# Starts the real one-process service on a DEDICATED loopback port and a
# DEDICATED data dir under probes/lg024/smoke/_data (never :8123, never the
# main worktree data), with --no-executor so no real SDK/model generation is
# wired.  Probes health / version / static UI / protected write, then stops and
# verifies real termination.  Bounded polling (<=90s per wait).
#
# Records PID/port/status/exit codes under this directory (mode 700/600).
# Never prints tokens, credentials or .env contents.  Does not touch :8123.
#
# Usage: bash probes/lg024/smoke/run-smoke.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || cd "$HERE/../../.." && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
cd "$REPO"

PORT="${LG024_SMOKE_PORT:-18432}"
HOST=127.0.0.1
DATA="$HERE/_data"
SECRETS="$HERE/_secrets"
LOG="$HERE/smoke-record.log"
OUT="$HERE/smoke-result.json"

umask 077
mkdir -p "$DATA" "$SECRETS"
: > "$LOG"

log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

# Refuse to use the main worktree's busy port.
if [[ "$PORT" == "8123" ]]; then
  log "refuse: port 8123 is reserved for the main worktree service"; exit 2
fi
if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  log "refuse: port $PORT already in use"; exit 2
fi

log "== env =="
log "repo=$REPO head=$(git rev-parse --short HEAD)"
log "port=$PORT host=$HOST data=$DATA"
log "no-executor=1 (real SDK/model generation stays OFF)"

EXIT_START=0
EXIT_HEALTH=0
EXIT_VERSION=0
EXIT_UI=0
EXIT_PROTECTED=0
EXIT_STOP=0

# --- start (foreground in background shell), bounded ---
LG_PID=""
log "== start =="
uv run lightgravity start --data-dir "$DATA" --workspace-root "$DATA/workspaces" \
  --secret-store "$SECRETS" --host "$HOST" --port "$PORT" --no-executor \
  >"$HERE/start.out" 2>&1 &
LG_PID=$!
log "launcher pid=$LG_PID"

# Poll health up to 90s.
deadline=$(( $(date +%s) + 90 ))
HEALTH_OK=0
while [[ $(date +%s) -lt $deadline ]]; do
  code=$(curl -s -o "$HERE/health.json" -w '%{http_code}' "http://$HOST:$PORT/api/v1/health" 2>/dev/null || true)
  if [[ "$code" == "200" ]]; then HEALTH_OK=1; break; fi
  sleep 1
done
if [[ "$HEALTH_OK" == "1" ]]; then
  log "health: HTTP 200 $(cat "$HERE/health.json")"
else
  EXIT_HEALTH=1
  log "health: FAILED within 90s; start.out tail:"; tail -20 "$HERE/start.out" | tee -a "$LOG"
fi

# version
if [[ "$HEALTH_OK" == "1" ]]; then
  vcode=$(curl -s -o "$HERE/version.json" -w '%{http_code}' "http://$HOST:$PORT/api/v1/version" 2>/dev/null || true)
  log "version: HTTP $vcode $(head -c 300 "$HERE/version.json" 2>/dev/null)"
  [[ "$vcode" == "200" ]] || EXIT_VERSION=1
fi

# static UI (index.html served when frontend dist exists)
if [[ "$HEALTH_OK" == "1" ]]; then
  ucode=$(curl -s -o "$HERE/index.html" -w '%{http_code}' "http://$HOST:$PORT/" 2>/dev/null || true)
  log "index: HTTP $ucode bytes=$(wc -c < "$HERE/index.html" 2>/dev/null || echo 0)"
  # No frontend dist is expected in Stage A (built only when needed); record, do not fail.
fi

# protected write without token must be denied (sensitive settings write).
if [[ "$HEALTH_OK" == "1" ]]; then
  pcode=$(curl -s -o "$HERE/protected.json" -w '%{http_code}' -X POST \
    -H 'Content-Type: application/json' -d '{}' \
    "http://$HOST:$PORT/api/v1/settings/connections" 2>/dev/null || true)
  log "protected-write (no token): HTTP $pcode $(head -c 200 "$HERE/protected.json" 2>/dev/null)"
  case "$pcode" in
    401|403|405|422) : ;;          # denied (or method/validation) => protection intact
    *) EXIT_PROTECTED=1; ;;
  esac
fi

# --- stop ---
log "== stop =="
uv run lightgravity stop --data-dir "$DATA" --secret-store "$SECRETS" --timeout 10 >>"$LOG" 2>&1
STOP_RC=$?
log "stop exit=$STOP_RC"
# Ensure the launcher we spawned is really gone.
sleep 1
if kill -0 "$LG_PID" 2>/dev/null; then
  log "launcher still alive; sending TERM"
  kill -TERM "$LG_PID" 2>/dev/null || true
  sleep 2
fi
if kill -0 "$LG_PID" 2>/dev/null; then
  log "launcher still alive after TERM; KILL"
  kill -KILL "$LG_PID" 2>/dev/null || true
  EXIT_STOP=1
fi
# Port must be free.
if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  log "port $PORT still listening => stop FAILED"; EXIT_STOP=1
else
  log "port $PORT released"
fi

# --- summary ---
cat > "$OUT" <<JSON
{
  "head": "$(git rev-parse HEAD)",
  "port": $PORT,
  "no_executor": true,
  "health_200": $([[ "$HEALTH_OK" == "1" ]] && echo true || echo false),
  "exit_health": $EXIT_HEALTH,
  "exit_version": $EXIT_VERSION,
  "exit_ui_recorded_only": $EXIT_UI,
  "exit_protected": $EXIT_PROTECTED,
  "exit_stop": $EXIT_STOP,
  "real_model_generation": 0
}
JSON
chmod 600 "$OUT" "$LOG" 2>/dev/null || true
log "result written: $OUT"
cat "$OUT"

# Overall exit: 0 only if health ok and stop clean.
if [[ "$EXIT_HEALTH" == "0" && "$EXIT_STOP" == "0" && "$EXIT_PROTECTED" == "0" ]]; then
  exit 0
fi
exit 1
