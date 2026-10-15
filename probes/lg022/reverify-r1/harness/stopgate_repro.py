"""LG-022 reverify R1 — focused STOPGATE reproduction (0 model calls).

The real-chain run (`evidence/real-chain.json`) ended in phase ``verifying``
with a Run whose ``session_refs`` are populated (2 real SDK sessions) and
``cleanup.status == "pending"``.  This probe rebuilds exactly that Run shape in a
throwaway store and drives the REAL ``StoreResourceStopper`` + ``VerificationService.verify_and_prepare``
to show, deterministically, *why* the Task never reaches ``awaiting_acceptance``.

It is a *local deterministic* reproduction of the mechanism observed in the real
chain; it is NOT a real SDK/DeepSeek run and makes **no** network calls.

Run: uv run python probes/lg022/reverify-r1/harness/stopgate_repro.py <out_json>
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.store import FileStore  # noqa: E402
from lightgravity.store.ids import new_id  # noqa: E402
import lightgravity.coordinator  # noqa: E402,F401  (break verify<->coordinator import cycle)
from lightgravity.verify.service import VerificationService  # noqa: E402
from lightgravity.verify.stopgate import StoreResourceStopper  # noqa: E402


def _seed(store: FileStore, *, session_refs: list[str], cleanup_status: str) -> tuple[str, str]:
    """Build a Task in ``verifying`` with a Run shaped like the real-chain one."""
    task_id = new_id("task")
    run_id = new_id("run")
    ws = store.workspace_root if hasattr(store, "workspace_root") else None
    store.create(
        "task",
        task_id,
        {
            "phase": "verifying",
            "status": "in-progress",
            "title": "stopgate repro",
            "objective": "reproduce verifying->awaiting_acceptance stop gate",
            "acceptance_criteria": ["always satisfied"],
            "workspace_ref": "ws",
            "requirements_revision": 1,
            "deliverable_revision": 0,
            "authorized_checks": [],
            "acceptance": {
                "status": "pending",
                "requirements_revision": None,
                "deliverable_revision": None,
                "evidence_refs": [],
                "decided_at": None,
                "decision_ref": None,
            },
            "queue": {"state": "not_queued", "owner": None},
            "active_run": run_id,
        },
        actor="probe",
        request_id=f"seed:{task_id}",
        body="# Task repro\n",
    )
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "verifying",
            "plan_ref": "PLAN.md",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": session_refs,
            "plan_hash": "0" * 64,
            "cleanup": {"status": cleanup_status},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="probe",
        request_id=f"seed:{run_id}",
        body=f"# Run {run_id}\n",
    )
    return task_id, run_id


def _case(label: str, session_refs: list[str], cleanup_status: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws = root / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", ws)
        try:
            task_id, run_id = _seed(store, session_refs=session_refs, cleanup_status=cleanup_status)
        except TypeError:
            # FileStore signature fallback
            store = FileStore(root / "data")
            task_id, run_id = _seed(store, session_refs=session_refs, cleanup_status=cleanup_status)
        stopper = StoreResourceStopper(store)
        stop = stopper.stop(task_id, run_id).to_dict()
        service = VerificationService(store)
        try:
            res = service.verify_and_prepare(task_id, request_id=f"probe:{label}")
            vres = res.to_dict()
        except Exception as exc:  # noqa: BLE001
            vres = {"error": f"{type(exc).__name__}: {exc}"}
        return {
            "label": label,
            "session_refs": session_refs,
            "cleanup_status": cleanup_status,
            "stop_report": stop,
            "verify_state": vres.get("state"),
            "verify_phase": vres.get("phase"),
            "verify_messages": vres.get("messages"),
            "verify_confirmed": vres.get("confirmed"),
            "task_phase_after": store.read("task", task_id).entity.get("phase"),
        }


def main() -> int:
    out = {
        "evidence_kind": "local-deterministic-stopgate",
        "real_model_calls": 0,
        "note": (
            "Reproduces the real-chain Run shape (session_refs populated, "
            "cleanup=pending) to isolate why verify_and_prepare cannot open "
            "awaiting_acceptance."
        ),
        "cases": [
            # exact real-chain shape
            _case("real_chain_shape", ["sess_a", "sess_b"], "pending"),
            # control: no sessions -> gate passes
            _case("control_no_sessions", [], "pending"),
            # control: cleanup done -> gate passes
            _case("control_cleanup_done", ["sess_a", "sess_b"], "done"),
        ],
    }
    out["deadlock_reproduced"] = (
        out["cases"][0]["verify_state"] == "unconfirmed"
        and out["cases"][0]["task_phase_after"] == "verifying"
        and out["cases"][0]["stop_report"]["confirmed"] is False
    )
    out_path = Path(sys.argv[1])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("WROTE", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
