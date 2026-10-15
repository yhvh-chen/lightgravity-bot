"""LG-022 stream-stop QA — offline re-evaluation of the captured main chain.

The live main-chain run captured real evidence (real DeepSeek, phase ledger
count 5/10, one fixture).  Two predicates in the *first* harness revision were
assertion bugs (not product defects):

  * ``worker_connection_pin_present`` read ``pin['ref']`` but the Run
    ``connection_pin`` records the connection as ``connection_id`` (with
    ``role='worker'``); the pin itself is real.
  * ``control_on_terminal_not_applicable`` expected HTTP 200
    ``state=not_applicable``; the API actually rejects a control action on a
    terminal/decided Task with HTTP 409 ``illegal_transition`` (the stricter,
    honest contract -- no fabricated stop).

This re-evaluator applies the corrected predicates to the SAME captured JSON so
the second main chain is NOT re-run (one fixture, no extra generation).  It
writes the corrected verdict to the given output path and leaves the raw
``main-chain.json`` untouched as the source of truth.

Run: .venv/bin/python qa/lg022-stream/harness/main_chain_reeval.py <raw.json> <out.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WORKER_CONN = "deepseek-worker-qa-stream"


def _steps(raw: dict) -> dict:
    return {s["name"]: s for s in raw["steps"]}


def main() -> int:
    raw = json.loads(Path(sys.argv[1]).read_text())
    out_path = Path(sys.argv[2])
    steps = _steps(raw)
    run = (raw.get("task_after_run") or {}).get("run") or {}
    pin = run.get("connection_pin") or {}
    acc = (raw.get("accept_response") or {}).get("acceptance") or {}

    status = steps.get("control_on_terminal_rejected_no_fabricated_stop")
    # If the corrected harness name is absent, fall back to the raw captured
    # 409 evidence for the same behaviour.
    if status is None:
        legacy = steps.get("control_on_terminal_not_applicable", {})
        terminal_control_ok = (
            legacy.get("code", 0) >= 400 and legacy.get("state") is None
        )
    else:
        terminal_control_ok = status.get("ok") is True

    verdict = {
        "health_ok": steps.get("health_ok", {}).get("ok") is True,
        "worker_default_pinned": steps.get("worker_default_pinned", {}).get("ok") is True,
        "reviewer_default_pinned": steps.get("reviewer_default_pinned", {}).get("ok") is True,
        "protected_write_requires_token": steps.get("protected_write_requires_token", {}).get("ok") is True,
        "execution_ready": steps.get("execution_ready", {}).get("ok") is True,
        "reviewer_wired_model": steps.get("reviewer_wired_model", {}).get("ok") is True,
        "ledger_persistent_single_path": steps.get("ledger_persistent_single_path", {}).get("ok") is True,
        "task_created": steps.get("task_created", {}).get("ok") is True,
        "duplicate_task_idempotent": steps.get("duplicate_task_idempotent", {}).get("ok") is True,
        "run_reached_awaiting_acceptance": steps.get("run_reached_awaiting_acceptance", {}).get("ok") is True,
        "status_query_not_blocked": steps.get("status_query_not_blocked", {}).get("ok") is True,
        "real_artifact_written": steps.get("real_artifact_written", {}).get("ok") is True,
        "real_session_refs_recorded": steps.get("real_session_refs_recorded", {}).get("ok") is True,
        "cleanup_not_fabricated_done": steps.get("cleanup_not_fabricated_done", {}).get("ok") is True,
        "reviewer_real_teardown_recorded": steps.get("reviewer_real_teardown_recorded", {}).get("ok") is True,
        # corrected predicate: connection_pin is keyed by connection_id + role
        "worker_connection_pin_present": (
            isinstance(pin, dict) and pin.get("connection_id") == WORKER_CONN
            and pin.get("role") == "worker"
        ),
        "accept_confirmed_bound": steps.get("accept_confirmed_bound", {}).get("ok") is True,
        "accept_candidate_ref_matches_run": acc.get("candidate_ref") == run.get("id"),
        "accept_plan_hash_matches_run": acc.get("candidate_plan_hash") == run.get("plan_hash"),
        "accept_requirements_revision_matches": acc.get("requirements_revision") == raw.get("requirements_revision"),
        "duplicate_accept_idempotent": steps.get("duplicate_accept_idempotent", {}).get("ok") is True,
        "stale_accept_rejected": steps.get("stale_accept_rejected", {}).get("ok") is True,
        # corrected predicate: terminal control is rejected (409), never a fake stop
        "control_on_terminal_rejected_no_fabricated_stop": terminal_control_ok,
        "ledger_persistent_final": steps.get("ledger_persistent_final", {}).get("ok") is True,
        "ledger_history_present_single_path": steps.get("ledger_history_present_single_path", {}).get("ok") is True,
        "real_generation_within_limit": (
            (raw.get("final_generation") or {}).get("count", 99)
            <= (raw.get("final_generation") or {}).get("limit", 0)
        ),
    }
    out = {
        "source_raw": str(Path(sys.argv[1])),
        "candidate_head": raw.get("candidate_head"),
        "phase_data_dir": raw.get("phase_data_dir"),
        "phase_limit": raw.get("phase_limit"),
        "real_generation_count": (raw.get("final_generation") or {}).get("count"),
        "corrections": [
            "worker_connection_pin_present keyed by connection_id+role (was pin['ref'])",
            "control_on_terminal expected 409 illegal_transition (was HTTP200 not_applicable)",
        ],
        "verdict": verdict,
        "ok": all(verdict.values()),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
