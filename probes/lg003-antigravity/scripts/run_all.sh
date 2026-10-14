#!/usr/bin/env bash
# LG-003 reproducible probe runner.
#
# Usage:
#   ./scripts/run_all.sh            # offline probes + canned event test
#   LG003_LIVE=1 ./scripts/run_all.sh   # also run bounded live DeepSeek probes
#
# Live mode requires DEEPSEEK_API_KEY in the environment. The key is read by
# the local proxy and is never echoed, logged, or written to disk.
#
# All spawned processes are terminated on exit.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
EVIDENCE="$ROOT/evidence"
mkdir -p "$EVIDENCE"

CANNED_PORT=18083
LIVE_PORT=18082
PROXY_PIDS=()

cleanup() {
  for pid in "${PROXY_PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${CANNED_PORT}/tcp" 2>/dev/null || true
    fuser -k "${LIVE_PORT}/tcp" 2>/dev/null || true
  fi
}
trap cleanup EXIT

start_proxy() {
  local mode="$1" port="$2" log="$3" maxcalls="$4"
  rm -f "$log"
  python3 "$HERE/openai_compat_proxy.py" --mode "$mode" --port "$port" \
    --log "$log" --max-calls "$maxcalls" >"$EVIDENCE/proxy_${mode}.out" 2>&1 &
  local pid=$!
  PROXY_PIDS+=("$pid")
  sleep 1
}

run() {
  local name="$1"; shift
  echo "== $name =="
  timeout 180 uv run python "$@" >"$EVIDENCE/${name}.json" 2>"$EVIDENCE/${name}.stderr"
  local code=$?
  echo "exit=$code"
  return $code
}

cd "$ROOT"

run p01_environment        scripts/p01_environment.py
run p02_offline_capabilities scripts/p02_offline_capabilities.py
run p03_runtime_handshake   scripts/p03_runtime_handshake.py

start_proxy canned "$CANNED_PORT" "$EVIDENCE/p04_proxy_requests.jsonl" 3
run p04_canned_events scripts/p04_canned_events.py --port "$CANNED_PORT" --workspace /tmp/lg003-ws-canned
if command -v fuser >/dev/null 2>&1; then fuser -k "${CANNED_PORT}/tcp" 2>/dev/null || true; fi

if [[ "${LG003_LIVE:-0}" == "1" ]]; then
  start_proxy deepseek "$LIVE_PORT" "$EVIDENCE/p05_proxy_requests.jsonl" 30
  for scenario in text file structured budget cancel resume; do
    run "p05_live_${scenario}" scripts/p05_live_deepseek.py --scenario "$scenario" \
      --base-url "http://127.0.0.1:${LIVE_PORT}/v1" --workspace /tmp/lg003-live-ws
  done
  run p06_skills_file   scripts/p06_skills.py --scenario file
  run p06_skills_inline scripts/p06_skills.py --scenario inline --workspace /tmp/lg003-skills-ws-inline
  run p07_web_read_url  scripts/p07_web_tools.py --scenario read_url
  run p07_web_search    scripts/p07_web_tools.py --scenario search_web --workspace /tmp/lg003-web-ws-search
else
  echo "Skipping live probes (set LG003_LIVE=1 and DEEPSEEK_API_KEY to run)."
fi

echo "Evidence written to $EVIDENCE"
