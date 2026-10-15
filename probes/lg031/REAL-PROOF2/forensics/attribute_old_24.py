#!/usr/bin/env python3
"""LG-031 REAL-PROOF2 — read-only forensics for the previous proof's 24 calls.

Attribution only.  This script:

* reads the **old** proof's persisted physical ledger
  (``REAL-PROOF/fixtures/formal/data/generation/generation.jsonl``) and the
  redacted raw event copy (``REAL-PROOF/fixtures/raw-evidence/formal-real.raw.json``);
* maps each persistent ``reserved`` entry to the adapter execution window
  (3 selection + 3 execution sessions) by timestamp containment, so the 24
  calls are attributed to selection / execute / verify;
* checks the per-session cap (12) was **not** the binding constraint;
* derives the root cause (shared cap 24 exhausted) and the number of
  pre-forward rejections.

It **never** prints prompts, headers, tool arguments, model text or credentials,
**never** scans unrelated/tmp user data and **never** writes to the old repo.
Output is a redacted JSON under ``evidence/`` plus a short stdout summary.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

OLD = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/lg031-real-proof/probes/lg031/REAL-PROOF"
)
LEDGER = OLD / "fixtures" / "formal" / "data" / "generation" / "generation.jsonl"
RAW = OLD / "fixtures" / "raw-evidence" / "formal-real.raw.json"
OUT = Path(__file__).resolve().parents[1] / "evidence" / "old-24-attribution.json"

PHASE_OF_SLOT = {
    "slot_run_01M50F8XGQTQB6JVBM1YAVZ401_0": ("selection", "alpha-slot"),
    "subtask_01M50F8XM0DEA3KERSSMFJB0D6": ("execute", "alpha"),
    "slot_run_01M50F8XGQTQB6JVBM1YAVZ401_1": ("selection", "beta-slot"),
    "subtask_01M50F8XM01G8P8SW0K4TXXSNS": ("execute", "beta"),
    "slot_run_01M50F8XGQTQB6JVBM1YAVZ401_2": ("selection", "verify-slot"),
    "subtask_01M50F8XM08QQDBG8XHYGGYJ8K": ("execute", "verify"),
}


def _epoch(ts: str) -> float:
    return _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=_dt.timezone.utc
    ).timestamp()


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    events = raw["events"]

    windows: list[dict] = []
    for ev in events:
        if ev.get("type") == "adapter.execution_started":
            ex = ev.get("execution", {})
            windows.append(
                {
                    "id": ex.get("subtask_id") or ex.get("execution_id"),
                    "start": ev["at"],
                    "end": None,
                }
            )
        elif ev.get("type") == "adapter.execution_finished":
            for w in windows:
                if w["end"] is None:
                    w["end"] = ev["at"]
                    break

    reserved = [
        json.loads(line)
        for line in LEDGER.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    attributed: dict[str, int] = {}
    detail: list[dict] = []
    for entry in reserved:
        t = float(entry["ts"])
        match = None
        for w in windows:
            a = _epoch(w["start"])
            b = _epoch(w["end"]) if w["end"] else float("inf")
            if a - 1.0 <= t <= b + 1.0:
                match = w["id"]
                break
        phase, label = PHASE_OF_SLOT.get(match, ("unknown", "unknown"))
        key = f"{phase}:{label}"
        attributed[key] = attributed.get(key, 0) + 1
        detail.append({"count": entry["count"], "phase": phase, "session": label})

    selection_calls = sum(v for k, v in attributed.items() if k.startswith("selection:"))
    execute_calls = sum(v for k, v in attributed.items() if k.startswith("execute:"))
    per_session = {
        label: sum(1 for d in detail if d["session"] == label)
        for _, label in PHASE_OF_SLOT.values()
    }
    unclassified = sum(v for k, v in attributed.items() if k.startswith("unknown"))
    max_session = max(per_session.values()) if per_session else 0

    snapshot = raw["ledger_snapshot"]
    rejects = [
        e
        for e in events
        if e.get("type") == "adapter.error"
        and "budget exhausted" in str(e.get("message", ""))
    ]
    tool_calls = [e for e in events if e.get("type") == "adapter.tool_call"]

    # A per-session cap of 12 exists (context budget max_model_calls=12); the
    # shared cap is 24.  If no session reached 12, the shared cap was binding.
    root_cause = (
        "shared_cap_24_exhausted"
        if max_session < 12 and snapshot.get("remaining") == 0
        else "unknown"
    )

    result = {
        "source_old_ledger": str(LEDGER),
        "source_old_raw": str(RAW),
        "old_ledger_snapshot": snapshot,
        "old_total_reserved": len(reserved),
        "attribution": {
            "selection_total": selection_calls,
            "execute_total": execute_calls,
            "unclassified": unclassified,
            "per_session": per_session,
            "by_phase": attributed,
        },
        "per_session_cap": 12,
        "max_session_calls": max_session,
        "shared_cap": 24,
        "pre_forward_rejections": len(rejects),
        "pre_forward_rejection_reason": (
            str(rejects[0].get("message", ""))[:120] if rejects else None
        ),
        "tool_call_events": len(tool_calls),
        "tool_call_names": sorted({str(e.get("name")) for e in tool_calls}),
        "sdk_session_count": raw.get("sdk_session_count"),
        "run_session_refs_count": raw.get("run_session_refs_count"),
        "sessions_in_run_refs": raw.get("sessions_in_run_refs"),
        "root_cause": root_cause,
        "per_session_cap_binding": max_session >= 12,
        "notes": (
            "attribution uses timestamp containment of persistent ledger reserves "
            "in the adapter execution windows; no prompt/args/credentials recorded"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result["attribution"], indent=2, sort_keys=True))
    print(
        json.dumps(
            {
                "root_cause": root_cause,
                "per_session_cap_binding": result["per_session_cap_binding"],
                "pre_forward_rejections": result["pre_forward_rejections"],
                "out": str(OUT),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
