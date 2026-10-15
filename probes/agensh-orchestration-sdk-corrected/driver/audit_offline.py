#!/usr/bin/env python3
"""Offline audit/replay of the first attempt (0 model calls).

For every first-attempt ``*__B__r0`` run this script:

1. recovers the **full** planner ``finish`` payload from the SDK native session
   DB (read-only source) via :mod:`sessiondb`;
2. reads the *emitted* (product-truncated) payload from the run's
   ``turns/planner.json`` for comparison;
3. re-runs the corrected strict program plan validation
   (``Experiment.validate_plan``) on the recovered full payload;
4. records the item keys that made the old reports non-conforming.

It never writes to the source and makes no network call.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from sessiondb import extract_best_finish_payload  # noqa: E402
from experiment import Experiment, copy_initial, read_snapshot  # noqa: E402

FIRST_ATTEMPT = Path(
    "/tmp/lightgravity-worktrees/agensh-sdk-20261015/probes/agensh-orchestration-sdk"
)
OUT = _HERE.parent / "evidence" / "phaseA" / "offline_replay.json"


def main() -> int:
    exp = Experiment(SimpleNamespace(mode="mock", runs_dir=str(_HERE.parent / "runs" / "mock"),
                                     resume=False, single=True, repeats=None))
    rows = []
    for run_dir in sorted((FIRST_ATTEMPT / "runs" / "formal").glob("*__B__r0")):
        task = run_dir.name.split("__")[0]
        full = None
        dbs = sorted((run_dir / "sessions" / "planner").glob("*.db"))
        if dbs:
            full = extract_best_finish_payload(dbs[0])
        turn_path = run_dir / "turns" / "planner.json"
        emitted = None
        if turn_path.exists():
            turn = json.loads(turn_path.read_text(encoding="utf-8"))
            emitted = turn.get("finish_payload")
            emitted_error = turn.get("finish_parse_error")
        else:
            emitted_error = None
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            copy_initial(task, ws)
            snap = read_snapshot(ws)
            valid, issues = exp.validate_plan(full, snap)
        item_keys = []
        if isinstance(full, dict):
            for item in full.get("plan") or []:
                if isinstance(item, dict):
                    item_keys.append(sorted(item.keys()))
        rows.append({
            "run_id": run_dir.name,
            "task": task,
            "full_chars": None if full is None else len(json.dumps(full, ensure_ascii=False, sort_keys=True)),
            "emitted_chars": None if emitted is None else len(json.dumps(emitted, ensure_ascii=False, sort_keys=True)),
            "emitted_parse_error": emitted_error,
            "emitted_truncated": bool(full is not None and emitted is not None
                                      and json.dumps(full, sort_keys=True) != json.dumps(emitted, sort_keys=True)),
            "old_plan_item_keys": item_keys,
            "new_schema_program_valid": valid is not None,
            "new_schema_issues": issues,
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "note": "offline replay of first-attempt B planner outputs vs corrected strict schema",
        "source": str(FIRST_ATTEMPT),
        "runs": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
