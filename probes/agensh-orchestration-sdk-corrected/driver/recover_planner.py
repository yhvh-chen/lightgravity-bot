#!/usr/bin/env python3
"""Offline recovery of untruncated planner outputs from the SDK native session DBs.

The product ``AntigravityExecutor`` truncates emitted tool-argument strings at
2000 chars (``executor._bounded``), so a verbose planner ``finish`` payload is
lost from the event stream.  The SDK's own session sqlite store keeps the full
payload; this script extracts it *offline* (no model calls) and re-runs the same
program plan validation.

This does **not** change what the workers saw: the driver had already discarded
the plan at run time.  The recovery is reported as a validity diagnostic only.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve()
PROBE_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_HERE))

from experiment import copy_initial, read_snapshot, writable_paths  # noqa: E402

FORMAL = PROBE_ROOT / "runs" / "formal"
_DEC = json.JSONDecoder()


def extract_full_payload(db_path: Path) -> dict | None:
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    payloads = [r[0] for r in cur.execute("select step_payload from steps order by idx")]
    try:
        payloads += [r[0] for r in cur.execute("select data from gen_metadata order by idx")]
    except sqlite3.Error:
        pass
    con.close()
    for payload in payloads:
        text = payload.decode("utf-8", "replace") if isinstance(payload, (bytes, bytearray)) else str(payload)
        for key in ('{"plan"', '{"findings"', '{"interface_notes"'):
            start = 0
            while True:
                i = text.find(key, start)
                if i < 0:
                    break
                try:
                    obj, _ = _DEC.raw_decode(text, i)
                    if isinstance(obj, dict) and ("plan" in obj or "interface_notes" in obj):
                        return obj
                except Exception:  # noqa: BLE001
                    pass
                start = i + 1
    return None


def validate_plan(plan: dict | None, snapshot: dict[str, str]) -> tuple[dict | None, list[str]]:
    issues: list[str] = []
    if not isinstance(plan, dict) or not isinstance(plan.get("plan"), list):
        return None, ["plan_not_a_list"]
    writable = set(writable_paths(snapshot))
    seen: dict[str, str] = {}
    cleaned: list[dict] = []
    for item in plan["plan"]:
        if not isinstance(item, dict):
            issues.append("plan_item_not_object")
            continue
        worker = item.get("worker")
        if worker not in ("w1", "w2"):
            issues.append(f"plan_bad_worker:{worker}")
            continue
        files = item.get("files")
        if not isinstance(files, list):
            issues.append("plan_files_missing_or_not_list")
            continue
        kept: list[str] = []
        for f in files:
            if not isinstance(f, str) or f not in writable:
                issues.append(f"plan_unwritable_file:{f}")
                continue
            if f in seen and seen[f] != worker:
                issues.append(f"plan_shared_writer:{f}")
                continue
            seen[f] = worker
            kept.append(f)
        cleaned.append({"worker": worker, "objective": str(item.get("objective") or ""), "files": kept})
    if not cleaned:
        return None, issues or ["plan_empty"]
    return {"plan": cleaned}, issues


def main() -> int:
    out = []
    for run_dir in sorted(FORMAL.glob("*__B__r0")):
        task = run_dir.name.split("__")[0]
        dbs = sorted((run_dir / "sessions" / "planner").glob("*.db"))
        payload = extract_full_payload(dbs[0]) if dbs else None
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            copy_initial(task, ws)
            snap = read_snapshot(ws)
            valid, issues = validate_plan(payload, snap)
        item_keys = []
        if payload:
            for item in payload.get("plan") or []:
                if isinstance(item, dict):
                    item_keys.append(sorted(item.keys()))
        out.append({
            "run_id": run_dir.name, "task": task,
            "recovered": payload is not None,
            "payload_top_keys": sorted(payload.keys()) if payload else None,
            "plan_item_keys": item_keys,
            "program_valid": valid is not None,
            "program_issues": issues,
        })
    (PROBE_ROOT / "evidence" / "planner_recovery.json").write_text(
        json.dumps({"note": "offline recovery from SDK native session store; not the executed plan",
                    "runs": out}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
