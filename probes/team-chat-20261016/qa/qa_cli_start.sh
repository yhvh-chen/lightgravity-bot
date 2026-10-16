#!/usr/bin/env bash
# LG-050 QA: verify the documented CLI user/start flow on the candidate.
#
# * create admin+member exactly as documented (password via getpass stdin,
#   never argv);
# * start the real one-process service in team mode with the built frontend;
# * check anonymous /auth/me, login, an admin read, and the LAN/Host boundary
#   (default loopback only; a non-allowed Host / cross-origin Origin is refused);
# * stop the server and confirm the loopback bind is released.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
PY="${PY:-/home/yhvh/code/lightgravity-bot/.venv/bin/python}"
DATA="$(mktemp -d -t lg050-cli-XXXXXX)"
DIST="$REPO_ROOT/frontend/dist"
PW="qa-throwaway-pass-123!"

free_port() {
  "$PY" - <<'EOF'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()
EOF
}
PORT="$(free_port)"
echo "# data=$DATA port=$PORT dist=$DIST"

run_cli() { PYTHONPATH="$REPO_ROOT/backend" "$PY" -m lightgravity.cli "$@"; }

echo "===== user add (documented getpass flow) ====="
printf '%s\n%s\n' "$PW" "$PW" | run_cli user add --username alice --role admin --data-dir "$DATA"
printf '%s\n%s\n' "$PW" "$PW" | run_cli user add --username bob --role member --data-dir "$DATA"
echo "===== user list (no secrets) ====="
run_cli user list --data-dir "$DATA"

echo "===== start (team mode, loopback, built frontend) ====="
LIGHTGRAVITY_TEAM_MODE=1 PYTHONPATH="$REPO_ROOT/backend" "$PY" -m lightgravity.cli start \
  --data-dir "$DATA" --workspace-root "$DATA/workspaces" --secret-store "$DATA/secrets" \
  --host 127.0.0.1 --port "$PORT" --frontend-dist "$DIST" --no-executor --daemon

cleanup() { run_cli stop --data-dir "$DATA" >/dev/null 2>&1 || true; }
trap cleanup EXIT

BASE="http://127.0.0.1:$PORT"
for _ in $(seq 1 60); do
  if curl -fsS "$BASE/api/v1/health" >/dev/null 2>&1; then break; fi
  sleep 0.25
done

echo "===== anonymous /auth/me ====="
curl -sS "$BASE/api/v1/auth/me"; echo
echo "===== browser page carries empty team token ====="
curl -sS "$BASE/" | grep -o '__LG_RUNTIME_TOKEN__="[^"]*"' | head -1 || echo "(token marker not found)"

echo "===== login (cookie jar) ====="
JAR="$(mktemp)"
curl -sS -c "$JAR" -H 'Content-Type: application/json' \
  -d "{\"username\":\"alice\",\"password\":\"$PW\"}" "$BASE/api/v1/auth/login"; echo
echo "===== admin /auth/me + /tasks ====="
curl -sS -b "$JAR" "$BASE/api/v1/auth/me"; echo
curl -sS -o /dev/null -w 'GET /tasks -> %{http_code}\n' -b "$JAR" "$BASE/api/v1/tasks"

echo "===== anonymous business read is 401 ====="
curl -sS -o /dev/null -w 'anon GET /tasks -> %{http_code}\n' "$BASE/api/v1/tasks"

echo "===== LAN / Host boundary (default loopback only) ====="
curl -sS -o /dev/null -w 'Host evil.example -> %{http_code}\n' -H 'Host: evil.example' "$BASE/api/v1/health"
curl -sS -o /dev/null -w 'Origin http://evil.example -> %{http_code}\n' -H 'Origin: http://evil.example' "$BASE/api/v1/health"

echo "===== stop ====="
run_cli stop --data-dir "$DATA"
sleep 0.5
curl -sS -o /dev/null -w 'after stop -> %{http_code}\n' --max-time 3 "$BASE/api/v1/health" || echo "after stop -> connection refused (expected)"
echo "===== CLI/START SMOKE DONE ====="
