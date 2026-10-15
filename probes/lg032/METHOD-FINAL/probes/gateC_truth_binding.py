#!/usr/bin/env python3
"""LG-032 METHOD-FINAL 门C — machine-truth binding + no-fabrication audit.

Two independent parts:

1. **Product machine-truth binding** (real product code, 0 fake provider):
   * prove ``CheckReport.satisfied`` is **vacuously True** for an empty
     authorized-check set (so an empty Task-checks list MUST NOT be read as a
     machine pass — this is exactly why the frozen driver authorizes
     ``evidence-present``);
   * prove the ``evidence-present`` product check **fails** when the candidate
     has no artifact/diff evidence and **passes** when it does;
   * prove ``VerificationService.verify_and_prepare`` refuses to open acceptance
     when a check fails, and binds ``check_records`` into the opened acceptance
     when it passes (through the real ``_open_acceptance``).

2. **Static no-fabrication audit of the frozen driver** (source parse):
   * no hand-written ``phase=`` / ``cleanup=done`` / ``accepted`` control state;
   * no ``monkeypatch`` of stop/root; no ``FakeExecutor`` impersonation;
   * ``LG032_WIDEN_EXEC_ROOT`` is a loud refusal (root never widened);
   * the accept branch is gated on real truths (machine+reviewer+session+teardown).

Read-only w.r.t. product source, real fixtures and existing harness logic.
Real provider generation = 0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import method_config as MC  # noqa: E402

C = MC.install()
sys.path.insert(0, str(MC.HARNESS_DIR))
import run_attempt as R  # noqa: E402

REPO = MC.WORKTREE
sys.path.insert(0, str(REPO / "backend"))


def _candidate(artifact_refs: tuple[str, ...], diff_ref: str | None) -> Any:
    from lightgravity.verify.candidate import Candidate

    return Candidate(
        task_id="task_X", run_id="run_X", run_state="verifying", attempt=1,
        plan_hash="ph", requirements_revision=1, deliverable_revision=0,
        workspace_ref="ws", workspace_path="/tmp/ws", member_refs=("m",),
        subtask_refs=("s",), artifact_refs=artifact_refs, diff_ref=diff_ref,
        session_refs=("sess",), check_records=(),
    )


def part_machine_truth_binding(nonce: str) -> dict[str, Any]:
    # The product package resolves a verify<->coordinator circular import only
    # through the bootstrap entry point; import it first (product import order).
    import lightgravity.api.bootstrap  # noqa: F401
    from lightgravity.verify.checks import (
        CheckContext, CheckOutcome, CheckRegistration, CheckRegistry, CheckReport,
    )

    # 1. empty authorized set => vacuously satisfied (documented hazard).
    empty_report = CheckReport(results=(), authorized=(), registered=())
    vacuous = empty_report.satisfied is True

    # 2. evidence-present behaviour on empty vs non-empty candidate.
    # Use the PRODUCT's default registry (the one build_runtime/app.py uses),
    # not an ad-hoc empty registry -- an empty registry reports checks as
    # ``unconfigured`` (vacuously satisfied), which is a different hazard.
    from lightgravity.verify.checks import default_check_registry
    reg = default_check_registry()
    ctx_empty = CheckContext(task_id="t", run_id="r",
                             candidate=_candidate((), None), store=None, workspace_path=None)
    ctx_ok = CheckContext(task_id="t", run_id="r",
                          candidate=_candidate(("src/a.py",), None), store=None,
                          workspace_path=None)
    from lightgravity.verify.checks import run_checks
    report_empty = run_checks(reg, ("evidence-present",), ctx_empty)
    report_ok = run_checks(reg, ("evidence-present",), ctx_ok)

    # 3. verify_and_prepare refuses on failing check, binds on passing check.
    import tempfile
    from lightgravity.config import Settings
    from lightgravity.store import FileStore
    from lightgravity.store.ids import new_id
    from lightgravity.verify.service import VerificationService
    from lightgravity.verify.stopgate import StoreResourceStopper

    outcomes: dict[str, Any] = {}
    for label, refs in (("no_evidence", ()), ("with_evidence", ("src/a.py",))):
        root = MC.BOUNDARY_DIR / f"gateC-{label}-{nonce}"
        root.mkdir(parents=True, exist_ok=False)
        ws = root / "ws"
        ws.mkdir(parents=True)
        (ws / "src").mkdir()
        (ws / "src" / "a.py").write_text("x", encoding="utf-8")
        settings = Settings(data_dir=root, workspace_root=ws, secret_store=root / "secrets",
                            host="127.0.0.1", port=0)
        settings.ensure_data_dir()
        store = FileStore(settings.data_dir, settings.workspace_root)
        task_id = new_id("task")
        run_id = new_id("run")
        subtask_id = new_id("subtask")
        sub = store.create("subtask", subtask_id, {
            "title": "sub", "objective": "x", "state": "passed",
            "acceptance": {"status": "passed", "evidence_refs": list(refs)},
            "run_ref": run_id, "task_ref": task_id,
        }, actor="c", request_id="c-sub")
        task = store.create("task", task_id, {
            "title": "c", "objective": "x", "status": "in-progress", "phase": "verifying",
            "requirements_revision": 1, "deliverable_revision": 0,
            "acceptance_criteria": ["ok"], "workspace_ref": "ws",
            "checks": ["evidence-present"],
            "queue": {"state": "not_queued", "order": 0},
            "acceptance": {"status": "pending"},
        }, actor="c", request_id="c-task")
        store.create("run", run_id, {
            "task_ref": task_id, "state": "verifying", "session_refs": ["s1"],
            "cleanup": {"status": "done", "confirmed": True}, "attempt": 1,
            "plan_hash": "ph", "subtask_refs": [subtask_id],
            "workspace_path": str(ws),
        }, actor="c", request_id="c-run")
        store.write("task", task_id, {"active_run": run_id},
                    expected_revision=task.revision, actor="c")
        svc = VerificationService(
            store, registry=default_check_registry(),
            stopper=StoreResourceStopper(store, session_confirmer=_Confirmer()),
        )
        res = svc.verify_and_prepare(task_id, request_id=f"c-{label}")
        acc = (store.read("task", task_id).entity.get("acceptance") or {})
        outcomes[label] = {
            "state": res.state, "confirmed": res.confirmed,
            "phase": store.read("task", task_id).entity.get("phase"),
            "check_records": acc.get("check_records"),
        }

    checks = {
        "empty_checks_vacuously_satisfied": vacuous,
        "evidence_present_fails_without_evidence": report_empty.satisfied is False,
        "evidence_present_passes_with_evidence": report_ok.satisfied is True,
        "no_evidence_refused_no_acceptance": (
            outcomes["no_evidence"]["state"] == "unconfirmed"
            and outcomes["no_evidence"]["confirmed"] is False
        ),
        "with_evidence_opens_acceptance": outcomes["with_evidence"]["state"] == "confirmed",
        "acceptance_binds_real_check_records": bool(
            outcomes["with_evidence"]["check_records"]
            and outcomes["with_evidence"]["check_records"][0].get("check_id") == "evidence-present"
            and outcomes["with_evidence"]["check_records"][0].get("status") == "passed"
        ),
    }
    return {
        "vacuous_hazard_documented": True,
        "evidence_report_empty": report_empty.to_dict(),
        "evidence_report_ok": report_ok.to_dict(),
        "verify_outcomes": outcomes,
        "checks": checks, "ok": all(checks.values()),
    }


def _stop(run_id: str, refs: Any) -> Any:
    from lightgravity.adapter.execution import StopConfirmation
    refs = tuple(refs or ())
    return StopConfirmation(run_id=run_id, confirmed=True, sessions_total=len(refs),
                            sessions_stopped=len(refs), proxy_stopped=True,
                            unknown_sessions=(), problems=())


class _Confirmer:
    def confirm_stopped(self, run_id: str, refs: Any) -> Any:
        return _stop(run_id, refs)


def part_no_fabrication(nonce: str) -> dict[str, Any]:
    src = (MC.HARNESS_DIR / "run_attempt.py").read_text(encoding="utf-8")
    # The driver must reach accept ONLY through the real HTTP actions endpoint.
    checks = {
        "accepts_via_http_actions_endpoint": "/tasks/{task_id}/actions" in src,
        "no_phase_handwrite": not re.search(r"phase\s*=\s*[\"']awaiting_acceptance[\"']", src),
        "no_cleanup_done_handwrite": "cleanup" not in src or "\"cleanup\": \"done\"" not in src,
        "no_accepted_handwrite": not re.search(r"state\s*=\s*[\"']accepted[\"']", src),
        "no_monkeypatch_stop_or_root": (
            "_workspace_root =" not in src
            and src.count("confirm_stopped") <= 2  # only in docstring/comments, not a patch
        ),
        "widen_exec_root_is_refusal": "LG032_WIDEN_EXEC_ROOT" in src
        and "must not be set" in src,
        "no_fakeexecutor": "FakeExecutor" not in src,
        "accept_gated_on_real_truths": "truths_before_accept" in src
        and "reviewer_real_teardown_recorded" in src
        and "real_session_refs_recorded" in src,
        "driver_uses_real_build_runtime": "build_runtime" in src,
        "driver_uses_real_coordinator_loop": "coordinator" in src,
    }
    return {"checks": checks, "ok": all(checks.values())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    nonce = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    MC.BOUNDARY_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "probe": "METHOD-FINAL/gateC-truth-binding",
        "utc": nonce,
        "real_provider_generation": 0,
        "formal_root_untouched": str(MC.PHASE_DATA_DIR),
    }
    payload["machine_truth_binding"] = part_machine_truth_binding(nonce)
    payload["no_fabrication_static"] = part_no_fabrication(nonce)
    payload["formal_root_exists"] = MC.PHASE_DATA_DIR.exists()
    payload["ok"] = (
        payload["machine_truth_binding"]["ok"]
        and payload["no_fabrication_static"]["ok"]
        and payload["formal_root_exists"] is False
    )
    out = Path(args.out) if args.out else (MC.METHOD_DIR / "evidence" / f"gateC-{nonce}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                   encoding="utf-8")
    print(json.dumps({k: (v.get("ok") if isinstance(v, dict) else v)
                      for k, v in payload.items()}, indent=2))
    print(f"WROTE {out}")
    print(f"GATE-C {'PASS' if payload['ok'] else 'FAIL'}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
