#!/usr/bin/env bash
# Offline validation of the round-2 driver before the formal run. No network.
set -u
cd "$(dirname "$0")/.."
OUT=evidence/offline
mkdir -p "$OUT"
LOG="$OUT/offline_run_log.txt"
: > "$LOG"

echo "### fixture initial hashes" | tee -a "$LOG"
python3 - <<'PY' | tee -a "$LOG"
import hashlib
from pathlib import Path
for task in ("t1_independent", "t2_interface", "t3_evolving"):
    for sub in ("initial", "reference"):
        h = hashlib.sha256()
        base = Path("fixtures") / task / sub
        for p in sorted(base.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(base).as_posix().encode()); h.update(b"\0")
                h.update(p.read_bytes()); h.update(b"\0")
        print(f"{task}/{sub}: {h.hexdigest()}")
PY

echo "=== validate_fixtures.py (initial must fail, reference must pass) ===" | tee -a "$LOG"
python3 driver/validate_fixtures.py 2>&1 | tee -a "$LOG"

echo "=== protocol_selftest.py (claims/messages/leases/recovery/env) ===" | tee -a "$LOG"
python3 driver/protocol_selftest.py 2>&1 | tee -a "$LOG"

echo "=== offline_llm_selftest.py (SSE bounds, usage, thinking payload) ===" | tee -a "$LOG"
python3 driver/offline_llm_selftest.py 2>&1 | tee -a "$LOG"

echo "=== mock full experiment (18 samples) ===" | tee -a "$LOG"
rm -rf runs_mock
python3 driver/run_experiment.py --mock --runs-dir runs_mock 2>&1 | tail -25 | tee -a "$LOG"

echo "=== mock resume (must add no calls) ===" | tee -a "$LOG"
BEFORE=$(python3 -c "import json;print(json.load(open('runs_mock/summary.json'))['state']['http_requests'])")
python3 driver/run_experiment.py --mock --runs-dir runs_mock --resume >/dev/null 2>&1
python3 - <<PY | tee -a "$LOG"
import json
s = json.load(open("runs_mock/summary.json"))
b = s["state"]
print("http before resume:", $BEFORE, "after:", b["http_requests"])
print("budget:", {k: b[k] for k in ("http_requests","normal_calls","retry_calls","total_tokens","usage_unknown_calls","reserved_tokens")})
print("per-sample final:", {r["run_id"]: f'{r["final_passed"]}/{r["final_total"]}' for r in s["samples"]})
print("sot issues:", {r["run_id"]: r["sot_issues"] for r in s["samples"] if r["sot_issues"]})
PY

echo "=== mock analysis (recomputed from raw) ===" | tee -a "$LOG"
python3 driver/analyze_results.py --runs-dir runs_mock --out "$OUT/mock_analysis.json" \
  > "$OUT/mock_analysis_stdout.txt" 2>&1
tail -5 "$OUT/mock_analysis_stdout.txt" | tee -a "$LOG"

echo | tee -a "$LOG"
echo "OFFLINE CHECKS DONE" | tee -a "$LOG"
