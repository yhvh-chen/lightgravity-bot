#!/usr/bin/env bash
# Offline validation of the driver before the formal pilot. No network, no model calls.
set -u
cd "$(dirname "$0")/.."
OUT=evidence/offline
mkdir -p "$OUT"
echo "### fixture initial hashes" | tee "$OUT/fixture_hashes.txt"
python3 - <<'PY' | tee -a "$OUT/fixture_hashes.txt"
import hashlib, json
from pathlib import Path
for task in ("t1_independent", "t2_interface", "t3_evolving"):
    h = hashlib.sha256()
    base = Path("fixtures") / task / "initial"
    for p in sorted(base.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(base).as_posix().encode()); h.update(b"\0")
            h.update(p.read_bytes()); h.update(b"\0")
    print(f"{task}: {h.hexdigest()}")
PY

echo | tee "$OUT/run_log.txt"
echo "=== validate_fixtures.py ===" | tee -a "$OUT/run_log.txt"
python3 driver/validate_fixtures.py 2>&1 | tee -a "$OUT/run_log.txt"

echo "=== offline_llm_selftest.py ===" | tee -a "$OUT/run_log.txt"
python3 driver/offline_llm_selftest.py 2>&1 | tee -a "$OUT/run_log.txt"

echo "=== mock pilot (full 9 samples, exercises retry + conflict) ===" | tee -a "$OUT/run_log.txt"
rm -rf runs_mock
python3 driver/run_pilot.py --mock --runs-dir runs_mock 2>&1 | tail -5 | tee -a "$OUT/run_log.txt"

echo "=== mock resume (must add no calls) ===" | tee -a "$OUT/run_log.txt"
python3 driver/run_pilot.py --mock --runs-dir runs_mock --resume >/dev/null 2>&1
python3 - <<'PY' | tee -a "$OUT/run_log.txt"
import json
s = json.load(open("runs_mock/summary.json"))
b = s["pilot_state"]
print("mock budget:", {k: b[k] for k in ("http_requests","normal_calls","retry_calls","total_tokens","usage_unknown_calls")})
print("mock per-sample final:", {r["run_id"]: f'{r["final_passed"]}/{r["final_total"]}' for r in s["samples"]})
print("mock sot issues:", {r["run_id"]: r["sot_issues"] for r in s["samples"]})
PY

echo | tee -a "$OUT/run_log.txt"
echo "OFFLINE CHECKS DONE" | tee -a "$OUT/run_log.txt"
