#!/usr/bin/env bash
# LG-024 Stage B: unpack + install + start smoke from the L0 package.
#
# Unpacks the L0 tarball to an isolated scratch dir, creates INDEPENDENT data /
# secret-store dirs, runs an offline dependency install, starts the real
# one-process service on a NEW loopback port with --no-executor (real SDK/model
# generation stays OFF), probes health / version / index / static asset /
# protected write, then stops and verifies real termination + port release.
#
# Never touches :8123 or any existing data root. Never prints tokens/credentials.
# Private artifacts stay 700/600 under probes/lg024/STAGE-B/smoke-unpack/.
#
# Usage: bash probes/lg024/STAGE-B/smoke-unpack.sh <tarball>
set -uo pipefail

TARBALL="${1:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$TARBALL" || ! -e "$TARBALL" ]]; then
  echo "usage: $0 <tarball>" >&2
  exit 2
fi

PORT="${LG024_UNPACK_PORT:-18433}"
HOST=127.0.0.1
WORK="$HERE/smoke-unpack"
DATA="$WORK/data"
SECRETS="$WORK/secrets"
LOG="$WORK/smoke-unpack.log"
OUT="$WORK/smoke-unpack.json"

umask 077
rm -rf "$WORK"
mkdir -p "$DATA" "$SECRETS"
: > "$LOG"
log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

if [[ "$PORT" == "8123" ]]; then log "refuse: 8123 reserved"; exit 2; fi
if ss -ltn 2>/dev/null | grep -q ":$PORT "; then log "refuse: port $PORT in use"; exit 2; fi

log "== unpack =="
tar -xzf "$TARBALL" -C "$WORK"
PKG="$(find "$WORK" -maxdepth 1 -type d -name 'lightgravity-bot-L0-*' | head -1)"
if [[ -z "$PKG" ]]; then log "FAIL: no package dir after unpack"; exit 1; fi
log "package=$PKG"
cd "$PKG" || { log "FAIL: cd"; exit 1; }

log "== install (offline) =="
uv sync --offline --no-progress >>"$LOG" 2>&1
SYNC_RC=$?
log "uv sync --offline exit=$SYNC_RC"
[[ $SYNC_RC -eq 0 ]] || { log "FAIL: offline install failed (cache miss? record as limitation)"; echo "{\"offline_install\":false}" > "$OUT"; chmod 600 "$OUT" "$LOG"; exit 1; }

log "== start (port $PORT, no-executor, frontend-dist) =="
LG_PID=""
uv run lightgravity start --data-dir "$DATA" --workspace-root "$DATA/workspaces" \
  --secret-store "$SECRETS" --host "$HOST" --port "$PORT" --no-executor \
  --frontend-dist "$PKG/frontend/dist" >"$WORK/start.out" 2>&1 &
LG_PID=$!
log "launcher pid=$LG_PID"

EXIT_HEALTH=0; EXIT_VERSION=0; EXIT_UI=0; EXIT_ASSET=0; EXIT_PROTECTED=0; EXIT_STOP=0

deadline=$(( $(date +%s) + 90 ))
HEALTH_OK=0
while [[ $(date +%s) -lt $deadline ]]; do
  code=$(curl -s -o "$WORK/health.json" -w '%{http_code}' "http://$HOST:$PORT/api/v1/health" 2>/dev/null || true)
  [[ "$code" == "200" ]] && { HEALTH_OK=1; break; }
  sleep 1
done
if [[ "$HEALTH_OK" == "1" ]]; then
  log "health: 200 $(cat "$WORK/health.json")"
else
  EXIT_HEALTH=1; log "health: FAILED; start.out tail:"; tail -20 "$WORK/start.out" | tee -a "$LOG"
fi

if [[ "$HEALTH_OK" == "1" ]]; then
  vcode=$(curl -s -o "$WORK/version.json" -w '%{http_code}' "http://$HOST:$PORT/api/v1/version" 2>/dev/null || true)
  log "version: $vcode $(head -c 200 "$WORK/version.json" 2>/dev/null)"
  [[ "$vcode" == "200" ]] || EXIT_VERSION=1

  ucode=$(curl -s -o "$WORK/index.html" -w '%{http_code}' "http://$HOST:$PORT/" 2>/dev/null || true)
  log "index: $ucode bytes=$(wc -c < "$WORK/index.html" 2>/dev/null || echo 0)"
  [[ "$ucode" == "200" ]] || EXIT_UI=1

  # Extract the built JS asset path from index.html and fetch it.
  asset="$(grep -oE '/assets/[A-Za-z0-9._-]+\.js' "$WORK/index.html" | head -1)"
  if [[ -n "$asset" ]]; then
    acode=$(curl -s -o "$WORK/asset.js" -w '%{http_code}' "http://$HOST:$PORT$asset" 2>/dev/null || true)
    log "static-asset $asset: $acode bytes=$(wc -c < "$WORK/asset.js" 2>/dev/null || echo 0)"
    [[ "$acode" == "200" ]] || EXIT_ASSET=1
  else
    log "static-asset: none referenced in index.html"; EXIT_ASSET=1
  fi

  pcode=$(curl -s -o "$WORK/protected.json" -w '%{http_code}' -X POST \
    -H 'Content-Type: application/json' -d '{}' \
    "http://$HOST:$PORT/api/v1/settings/connections" 2>/dev/null || true)
  log "protected-write (no token): $pcode $(head -c 160 "$WORK/protected.json" 2>/dev/null)"
  case "$pcode" in 401|403|405|422) : ;; *) EXIT_PROTECTED=1 ;; esac
fi

log "== stop =="
uv run lightgravity stop --data-dir "$DATA" --secret-store "$SECRETS" --timeout 10 >>"$LOG" 2>&1
log "stop exit=$?"
sleep 1
if kill -0 "$LG_PID" 2>/dev/null; then
  log "launcher still alive; TERM"; kill -TERM "$LG_PID" 2>/dev/null || true; sleep 2
fi
if kill -0 "$LG_PID" 2>/dev/null; then
  log "launcher still alive; KILL"; kill -KILL "$LG_PID" 2>/dev/null || true; EXIT_STOP=1
fi
if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  log "port $PORT still listening => stop FAILED"; EXIT_STOP=1
else
  log "port $PORT released"
fi

cat > "$OUT" <<JSON
{
  "package_dir": "$(basename "$PKG")",
  "port": $PORT,
  "offline_install": true,
  "no_executor": true,
  "health_200": $([[ "$HEALTH_OK" == "1" ]] && echo true || echo false),
  "exit_health": $EXIT_HEALTH,
  "exit_version": $EXIT_VERSION,
  "exit_ui": $EXIT_UI,
  "exit_static_asset": $EXIT_ASSET,
  "exit_protected": $EXIT_PROTECTED,
  "exit_stop": $EXIT_STOP,
  "real_model_generation": 0
}
JSON
chmod 600 "$OUT" "$LOG" 2>/dev/null || true
cat "$OUT"
if [[ "$EXIT_HEALTH" == "0" && "$EXIT_VERSION" == "0" && "$EXIT_UI" == "0" && "$EXIT_ASSET" == "0" && "$EXIT_PROTECTED" == "0" && "$EXIT_STOP" == "0" ]]; then
  exit 0
fi
exit 1
