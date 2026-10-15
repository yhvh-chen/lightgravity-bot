#!/usr/bin/env python3
"""Offline re-check of the calibration acceptance harness (0 model calls).

The first calibration attempt consumed its full 2-turn budget and the model did
everything the protocol requires; only the acceptance helper was wrong (it
checked both fixture files although a single edit turn only holds one lease).
This script re-runs the *corrected* acceptance helper against the artefacts
already on disk.  It makes no network/model call and does not rewrite
``CALIBRATION_RAW.json`` (the raw record is preserved unchanged).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from calibrate import _accept  # noqa: E402
from experiment import Experiment, read_snapshot  # noqa: E402
from types import SimpleNamespace  # noqa: E402

ROOT = _HERE.parent
RAW = ROOT / "runs" / "calibration" / "CALIBRATION_RAW.json"
OUT = ROOT / "evidence" / "phaseB" / "CALIBRATION_RECHECK.json"


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    plan = raw.get("plan")
    lease = None
    if plan:
        for item in plan["plan"]:
            if item["worker"] == "w1" and item["files"]:
                lease = item["files"][0]
    staging = ROOT / "runs" / "calibration" / "staging" / "r1-w1"
    acc = _accept(staging, lease) if lease else {"passed": False, "error": "no lease"}

    # Re-derive the substantive protocol checks from the raw record.
    turns = {t["logical"]: t for t in raw.get("turns", [])}
    planner = turns.get("planner", {})
    edit = turns.get("edit-w1", {})
    decisions = edit.get("hook_decisions") or []
    read_ok = any(d.get("tool") == "view_file" and d.get("paths") and d.get("allow") for d in decisions)
    write_ok = any(d.get("tool") in ("create_file", "edit_file", "write_to_file")
                   and d.get("paths") and d.get("allow") for d in decisions)
    checks = {
        "bounds_turns_le_2": raw.get("turns_run", 99) <= 2,
        "bounds_http_le_12": raw.get("http_used", 10**9) <= 12,
        "bounds_tokens_le_60000": raw.get("tokens_used", 10**9) <= 60_000,
        "bounds_wall_le_180": raw.get("wall_used", 10**9) <= 180,
        "planner_plan_valid": bool(plan),
        "planner_payload_present": (planner.get("finish_payload_chars") or 0) > 0,
        "planner_finish_source_hook": planner.get("finish_source") == "hook",
        "planner_session_db_matches_hook": planner.get("session_db_matches_hook") is True,
        "edit_payload_present": (edit.get("finish_payload_chars") or 0) > 0,
        "edit_not_emitted_truncated": edit.get("emitted_truncated") is False,
        "edit_finish_source_hook": edit.get("finish_source") == "hook",
        "edit_session_db_matches_hook": edit.get("session_db_matches_hook") is True,
        "single_output_limit_upstream": all(
            (ra or {}).get("output_limit_fields") == ["max_tokens"]
            for t in raw.get("turns", []) for ra in (t.get("relay_request_after") or [])),
        "edit_plan_injected": edit.get("plan_injected") is True,
        "edit_read_path_nonempty": read_ok,
        "edit_write_path_nonempty": write_ok,
        "planner_stop_confirmed": (planner.get("stop_evidence") or {}).get("status") == "confirmed",
        "edit_stop_confirmed": (edit.get("stop_evidence") or {}).get("status") == "confirmed",
        "leased_file_written_and_correct": acc.get("passed") is True,
    }
    result = {
        "note": "offline re-check of the single 2-turn calibration attempt; no new model samples",
        "raw_http_used": raw.get("http_used"),
        "raw_tokens_used": raw.get("tokens_used"),
        "raw_turns_run": raw.get("turns_run"),
        "lease": lease,
        "acceptance_recheck": acc,
        "checks": checks,
        "all_passed": all(checks.values()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
