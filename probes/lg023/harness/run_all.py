#!/usr/bin/env python3
"""LG-023 controlled runner: exactly 4 attempts (2 samples x 2 arms x 1).

Runs each attempt once via ``run_attempt.py`` in a fresh subprocess (so the
process-global ledger is re-read from disk every time and no in-memory carryover
can hide a reset).  Attempts never re-run: if an attempt fails it is recorded as
a real failure, not retried.

Writes ``evidence/summary.json`` with completion rate, first-round pass rate,
full-cycle elapsed, generation requests per stage, usage, and cost placeholders.

Usage::

    LIGHTGRAVITY_GENERATION_LEDGER_DIR=... DEEPSEEK_API_KEY=... \
        uv run python probes/lg023/harness/run_all.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent
EVIDENCE = PROBE / "evidence"
LEDGER_DIR = os.environ.get("LIGHTGRAVITY_GENERATION_LEDGER_DIR") or str(PROBE / "ledger")

#: Fixed attempt order: sample, arm.  Each appears exactly once.
ATTEMPTS = (
    ("s1_independent", "A"),
    ("s1_independent", "B"),
    ("s2_interface", "A"),
    ("s2_interface", "B"),
)


def _run_one(sample: str, arm: str) -> dict:
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(HERE / "run_attempt.py"), "--sample", sample, "--arm", arm],
        capture_output=True,
        text=True,
        env={**os.environ, "LIGHTGRAVITY_GENERATION_LEDGER_DIR": LEDGER_DIR},
        timeout=900,
    )
    elapsed = round(time.monotonic() - started, 2)
    result_path = EVIDENCE / f"{sample}__{arm}.json"
    if result_path.exists():
        data = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        data = {"status": "no_result", "sample": sample, "arm": arm}
    data["host_elapsed_seconds"] = elapsed
    data["returncode"] = proc.returncode
    data["stderr_tail"] = proc.stderr[-2000:]
    return data


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    records = []
    for sample, arm in ATTEMPTS:
        print(f"=== attempt {sample} arm {arm} ===", flush=True)
        records.append(_run_one(sample, arm))

    summary = {
        "attempts": len(records),
        "records": records,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "ledger_dir": LEDGER_DIR,
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"attempts": len(records), "elapsed_seconds": summary["elapsed_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
