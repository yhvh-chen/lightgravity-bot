#!/usr/bin/env python3
"""LG-023 evidence aggregation (no model calls).

Reads every ``runs/*/result.json`` plus the shared ledger and emits
``evidence/aggregate.json`` and a human table.  Nothing here changes any sample,
gate or budget; it only summarizes what actually ran.

Usage::

    uv run python probes/lg023/harness/aggregate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent
RUNS = PROBE / "runs"
LEDGER = PROBE / "ledger" / "generation" / "generation.count.json"
OUT = PROBE / "evidence" / "aggregate.json"


def main() -> int:
    records = []
    for run_dir in sorted(RUNS.iterdir()):
        result_path = run_dir / "result.json"
        if not result_path.is_file():
            continue
        data = json.loads(result_path.read_text(encoding="utf-8"))
        machine = data.get("machine_gate") or {}
        review = data.get("review") or {}
        gate = data.get("acceptance_gate") or {}
        records.append({
            "run_dir": run_dir.name,
            "sample": data.get("sample"),
            "arm": data.get("arm"),
            "dispatcher_state": data.get("dispatcher_state"),
            "summary": str(data.get("plan_source"))[:200],
            "worker_count": data.get("worker_count"),
            "machine_pass": data.get("machine_pass"),
            "machine": f"{machine.get('passed')}/{machine.get('total')}",
            "review_validated_outcome": review.get("validated_outcome") or review.get("outcome"),
            "review_status": review.get("status"),
            "accept_reachable": gate.get("accept_reachable"),
            "verify_state": gate.get("verify_state"),
            "verify_messages": gate.get("verify_messages"),
            "attempt_generation_requests": data.get("attempt_generation_requests"),
            "elapsed_seconds": data.get("elapsed_seconds"),
            "sample_delivered": data.get("sample_delivered"),
            "handoff_refs": data.get("handoff_refs"),
            "tool_calls": [t.get("name") for t in (data.get("tool_calls") or [])],
            "usage": {
                "worker": review.get("usage"),
            },
        })

    ledger_count = None
    if LEDGER.is_file():
        try:
            ledger_count = json.loads(LEDGER.read_text(encoding="utf-8")).get("count")
        except ValueError:
            ledger_count = "unknown"

    payload = {
        "records": records,
        "global_ledger_count": ledger_count,
        "global_limit": 48,
        "frozen_attempt_limit": 12,
        "note": "cost/usage unknown where the provider did not report it; never 0",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
