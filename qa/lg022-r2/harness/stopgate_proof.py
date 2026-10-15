"""LG-022 reverify R2 — stop-gate resolution proof (0 model calls).

R1 found a hard deadlock: a successful Run records non-empty ``session_refs`` but
``cleanup.status == "pending"``, and the old ``StoreResourceStopper`` required
``cleanup=="done"`` for sessions to count as stopped, so a real session-bearing
Run could never reach ``awaiting_acceptance``.

R2 added an authoritative ``SessionStopConfirmer`` port: the adapter proves each
SDK session/proxy actually stopped via its own close/stop facts.  This probe
drives the REAL ``StoreResourceStopper`` + ``VerificationService`` with three
shapes and asserts:

  R2A  real-shape Run + adapter CONFIRMED stop -> confirmed, awaiting_acceptance,
       ``session_refs`` preserved (never deleted), cleanup still ``pending``.
  R2B  real-shape Run + adapter UNKNOWN/open session -> unconfirmed, stays
       ``verifying``, slot not released, ``session_refs`` preserved.
  R2C  reviewer_cleanup present and not confirmed -> held even if worker stopped.
  R2D  control: cleanup=done -> passes without a confirmer (back-compat).
  R2E  no sessions -> passes.

It is a local deterministic mechanism proof (NOT a real SDK/DeepSeek run).

Run: .venv/bin/python qa/lg022-r2/harness/stopgate_proof.py <out_json>
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.store import FileStore  # noqa: E402
from lightgravity.store.ids import new_id  # noqa: E402
import lightgravity.coordinator  # noqa: E402,F401  (break import cycle)
from lightgravity.verify.service import VerificationService  # noqa: E402
from lightgravity.verify.stopgate import StoreResourceStopper  # noqa: E402


@dataclass
class _FakeConfirmation:
    """Mirror of adapter.StopConfirmation's public shape."""

    run_id: str
    confirmed: bool
    sessions_total: int
    sessions_stopped: int
    proxy_stopped: bool
    unknown_sessions: tuple[str, ...]
    problems: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "confirmed": self.confirmed,
            "sessions_total": self.sessions_total,
            "sessions_stopped": self.sessions_stopped,
            "proxy_stopped": self.proxy_stopped,
            "unknown_sessions": list(self.unknown_sessions),
            "problems": list(self.problems),
        }


class _Confirmer:
    """Controlled confirmer: reports confirmed iff every session was closed."""

    def __init__(self, closed: set[str], *, proxy_stopped: bool = True) -> None:
        self._closed = closed
        self._proxy = proxy_stopped
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def confirm_stopped(self, run_id: str, session_refs: tuple[str, ...]):
        self.calls.append((run_id, session_refs))
        unknown = tuple(s for s in session_refs if s not in self._closed)
        return _FakeConfirmation(
            run_id=run_id,
            confirmed=not unknown and self._proxy,
            sessions_total=len(session_refs),
            sessions_stopped=len(session_refs) - len(unknown),
            proxy_stopped=self._proxy,
            unknown_sessions=unknown,
            problems=tuple(
                ([f"{len(unknown)} session(s) not confirmed closed by the adapter"] if unknown else [])
                + ([] if self._proxy else ["loopback auth proxy not confirmed stopped"])
            ),
        )


def _seed(store: FileStore, *, session_refs, cleanup_status, reviewer_cleanup=None, team_refs=None):
    task_id = new_id("task")
    run_id = new_id("run")
    store.create(
        "task", task_id,
        {
            "phase": "verifying", "status": "in-progress", "title": "stopgate proof",
            "objective": "prove r2 stop gate", "acceptance_criteria": ["always satisfied"],
            "workspace_ref": "ws", "requirements_revision": 1, "deliverable_revision": 0,
            "authorized_checks": [],
            "acceptance": {"status": "pending", "requirements_revision": None,
                           "deliverable_revision": None, "evidence_refs": [],
                           "decided_at": None, "decision_ref": None},
            "queue": {"state": "not_queued", "owner": None},
            "active_run": run_id,
        },
        actor="probe", request_id=f"seed:{task_id}", body="# Task\n",
    )
    run_entity = {
        "task_ref": task_id, "attempt": 1, "state": "verifying", "plan_ref": "PLAN.md",
        "team_refs": list(team_refs or []), "subtask_refs": [], "session_refs": list(session_refs),
        "plan_hash": "0" * 64, "cleanup": {"status": cleanup_status}, "ended_at": None, "fail_reason": None,
    }
    if reviewer_cleanup is not None:
        run_entity["reviewer_cleanup"] = reviewer_cleanup
    store.create("run", run_id, run_entity, actor="probe", request_id=f"seed:{run_id}", body=f"# Run\n")
    return task_id, run_id


def _case(label, *, session_refs, cleanup_status, confirmer=None, reviewer_cleanup=None):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws = root / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", ws)
        task_id, run_id = _seed(store, session_refs=session_refs, cleanup_status=cleanup_status,
                                reviewer_cleanup=reviewer_cleanup)
        stopper = StoreResourceStopper(store, session_confirmer=confirmer)
        # Standalone report from an independent stopper (does not disturb the
        # one verify_and_prepare drives); both share the same confirmer.
        report_stopper = StoreResourceStopper(store, session_confirmer=confirmer)
        stop = report_stopper.stop(task_id, run_id).to_dict()
        # Mirror the REAL app wiring (api/app.py): the default VerificationService
        # receives the same confirmer-bearing stopper, not a fresh default one.
        service = VerificationService(store, stopper=stopper)
        try:
            vres = service.verify_and_prepare(task_id, request_id=f"probe:{label}").to_dict()
        except Exception as exc:  # noqa: BLE001
            vres = {"error": f"{type(exc).__name__}: {exc}"}
        run_after = store.read("run", run_id).entity
        return {
            "label": label,
            "session_refs_before": list(session_refs),
            "session_refs_after": list(run_after.get("session_refs") or []),
            "cleanup_after": run_after.get("cleanup"),
            "stop_confirmed": stop.get("confirmed"),
            "stop_sessions_stopped": stop.get("sessions_stopped"),
            "stop_problems": stop.get("problems"),
            "verify_state": vres.get("state"),
            "verify_phase": vres.get("phase"),
            "task_phase_after": store.read("task", task_id).entity.get("phase"),
        }


def main() -> int:
    confirmed_conf = _Confirmer(closed={"sess_a", "sess_b"})
    open_conf = _Confirmer(closed={"sess_a"})  # sess_b still open -> unknown
    out = {
        "evidence_kind": "local-deterministic-stopgate-r2",
        "real_model_calls": 0,
        "note": "Proves the R2 authoritative-stop-confirmation gate releases real-shape Runs and holds unknown/active ones.",
        "cases": [
            _case("R2A_real_shape_adapter_confirmed", session_refs=["sess_a", "sess_b"],
                  cleanup_status="pending", confirmer=confirmed_conf),
            _case("R2B_real_shape_open_session_held", session_refs=["sess_a", "sess_b"],
                  cleanup_status="pending", confirmer=open_conf),
            _case("R2C_reviewer_not_confirmed_held", session_refs=["sess_a"],
                  cleanup_status="pending", confirmer=_Confirmer(closed={"sess_a"}),
                  reviewer_cleanup={"status": "pending", "confirmed": False}),
            _case("R2D_control_cleanup_done_backcompat", session_refs=["sess_a", "sess_b"],
                  cleanup_status="done"),
            _case("R2E_control_no_sessions", session_refs=[], cleanup_status="pending",
                  confirmer=_Confirmer(closed=set())),
        ],
    }
    a, b, c, d, e = out["cases"]
    out["adapter_confirmer_called"] = bool(confirmed_conf.calls)
    out["verdict"] = {
        "R2A_awaiting_and_refs_preserved": (
            a["stop_confirmed"] is True and a["task_phase_after"] == "awaiting_acceptance"
            and a["session_refs_after"] == ["sess_a", "sess_b"] and a["cleanup_after"] == {"status": "pending"}
        ),
        "R2B_unknown_held_and_refs_preserved": (
            b["stop_confirmed"] is False and b["task_phase_after"] == "verifying"
            and b["session_refs_after"] == ["sess_a", "sess_b"]
        ),
        "R2C_reviewer_held": c["stop_confirmed"] is False and c["task_phase_after"] == "verifying",
        "R2D_cleanup_done_backcompat": d["stop_confirmed"] is True and d["task_phase_after"] == "awaiting_acceptance",
        "R2E_no_sessions": e["stop_confirmed"] is True and e["task_phase_after"] == "awaiting_acceptance",
    }
    out["all_pass"] = all(out["verdict"].values())
    out_path = Path(sys.argv[1])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"verdict": out["verdict"], "all_pass": out["all_pass"]}, indent=2))
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
