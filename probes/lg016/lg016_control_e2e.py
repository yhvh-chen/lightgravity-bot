#!/usr/bin/env python3
"""LG-016 bounded real-SDK control/recovery evidence harness.

Not product code and not a pytest test.  It exercises the **product** control
path against the pinned SDK (``google-antigravity==0.1.22``) + loopback auth
proxy + real DeepSeek upstream:

1. real execution reaches ``executing``;
2. the product ``POST /tasks/{id}/actions`` ``pause``/``cancel`` path asks the
   real executor to stop and only writes the terminal phase after the adapter
   confirms the stop (docs/08 §9);
3. the same Run's real session is closed through the adapter ``close`` path and
   the loopback proxy / SDK harness processes are gone afterwards;
4. a restart scan over a Run whose worker died never auto-replays it and marks
   ``recovery_required``.

Hard caps: ``--max-proxy-calls`` per execution and ``--model-calls-cap`` in
total.  The credential is read only from the process environment and never
written to the evidence file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_LG010 = _REPO / "probes" / "lg010"
sys.path.insert(0, str(_REPO / "backend"))
sys.path.insert(0, str(_LG010))

import httpx  # noqa: E402

from lg010_e2e import (  # noqa: E402
    MODEL,
    UPSTREAM,
    RecordingExecutor,
    SingleNodePlanner,
    _find_harness_pids,
    _shrink,
    build_resources,
    build_workspace,
)
from lightgravity.adapter import AntigravityExecutor, DirectoryArtifactSink  # noqa: E402
from lightgravity.api.app import create_app  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.coordinator import GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.coordinator.recovery import RecoveryScanner  # noqa: E402
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.store import FileStore, new_id  # noqa: E402

EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"
EVIDENCE_PATH = EVIDENCE_DIR / "lg016-control-evidence.json"
BLOCK_MARKER = "LG016_CANCEL_TARGET"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _git_head() -> str:
    import subprocess

    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


async def _wait_for_phase(
    client: httpx.AsyncClient,
    task_id: str,
    phases: set[str],
    *,
    timeout: float,
    poll: float = 0.25,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = (await client.get(f"/api/v1/tasks/{task_id}")).json()
        if last.get("phase") in phases:
            return last
        await asyncio.sleep(poll)
    raise TimeoutError(f"task {task_id} did not reach {sorted(phases)}; last={last}")


async def run_cancel_case(
    client: httpx.AsyncClient,
    recording: RecordingExecutor,
    *,
    action: str,
    timeout: float,
) -> dict[str, Any]:
    """Start a real run and stop it through the product control endpoint."""

    objective = (
        "Write a long essay about the history of computing, at least 40 "
        "paragraphs. Do not stop early; keep writing until finished."
    )
    create = await client.post(
        "/api/v1/tasks",
        json={
            "request_id": f"lg016-{action}-create",
            "title": f"LG-016 real {action}",
            "objective": objective,
            "acceptance_criteria": ["never reached: run is stopped by control"],
            "workspace_ref": "demo-repo",
        },
    )
    created = create.json()
    task_id = created["task_id"]

    detail = await _wait_for_phase(
        client, task_id, {"executing", "failed", "cancelled"}, timeout=timeout
    )
    reached_executing = detail.get("phase") == "executing"
    run_id = detail.get("run", {}).get("id") if isinstance(detail.get("run"), dict) else None

    control = await client.post(
        f"/api/v1/tasks/{task_id}/actions",
        json={"action": action, "request_id": f"lg016-{action}-ctl"},
    )
    body = control.json()
    confirmed = control.status_code == 200 and body.get("confirmed") is True
    final = (await client.get(f"/api/v1/tasks/{task_id}")).json()
    run_detail = final.get("run") if isinstance(final.get("run"), dict) else {}
    results = recording.results[-1] if recording.results else None
    return {
        "action": action,
        "task_id": task_id,
        "run_id": run_id,
        "reached_executing": reached_executing,
        "control_status": control.status_code,
        "control_body": _shrink(body),
        "confirmed": confirmed,
        "final_phase": final.get("phase"),
        "final_queue_state": (final.get("queue") or {}).get("state"),
        "run_state": run_detail.get("state"),
        "run_cleanup": run_detail.get("cleanup"),
        "executor_state": getattr(results, "state", None),
        "executor_stop_confirmed": getattr(results, "stop_confirmed", None),
        "executor_stop_reason": getattr(results, "stop_reason", None),
        "session_ref": (
            results.session_ref.to_dict() if results and results.session_ref else None
        ),
    }


async def run_close_case(
    executor: AntigravityExecutor,
    session_ref: Any,
) -> dict[str, Any]:
    """Close a real session through the adapter close path (idempotent)."""

    outcome: dict[str, Any] = {"session_ref": session_ref.to_dict() if session_ref else None}
    if session_ref is None:
        outcome["skipped"] = "no session_ref from the real run"
        return outcome
    try:
        await executor.close(session_ref)
        outcome["close_returned"] = True
    except Exception as exc:  # noqa: BLE001 - report, never fake a clean close
        outcome["close_error"] = f"{type(exc).__name__}: {exc}"
    sessions_after = getattr(executor, "_sessions", {})
    outcome["sessions_tracked_after"] = len(sessions_after)
    return outcome


def run_restart_recovery_case(store: FileStore, task_id: str, run_id: str) -> dict[str, Any]:
    """Restart scan over a Run whose worker died: never auto-replayed."""

    scanner = RecoveryScanner(store, StateWriter(store, actor="lg016-recovery"))
    report = scanner.scan()
    decisions = {d.task_id: d for d in report.decisions}
    decision = decisions.get(task_id)
    entity = store.read("task", task_id).entity
    return {
        "interrupted_task_id": task_id,
        "interrupted_run_id": run_id,
        "decision_action": decision.action if decision else None,
        "decision_alive": decision.alive if decision else None,
        "decision_reason": decision.reason if decision else None,
        "phase_after_scan": entity.get("phase"),
        "queue_after_scan": (entity.get("queue") or {}).get("state"),
        "recovery_required": task_id in report.to_dict()["recovery_required"],
    }


def _session_from_events(recording: RecordingExecutor) -> Any:
    """Recover the real SessionRef the adapter emitted at session start."""

    from lightgravity.adapter import SessionRef  # noqa: PLC0415

    for event in reversed(recording.events):
        if event.get("type") == "adapter.session_started":
            data = event.get("session") or {}
            if data.get("session_id"):
                return SessionRef(
                    session_id=str(data["session_id"]),
                    conversation_id=data.get("conversation_id"),
                    state=str(data.get("state", "created")),
                    save_dir=data.get("save_dir"),
                )
    return None


def _write_report(report: dict[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {EVIDENCE_PATH}", file=sys.stderr)


async def amain(args: argparse.Namespace) -> int:
    secret = os.environ.get("DEEPSEEK_API_KEY") or ""
    report: dict[str, Any] = {
        "task": "LG-016",
        "kind": "real-sdk-control-and-recovery",
        "at": _now(),
        "python": platform.python_version(),
        "platform": f"{sys.platform}-{platform.machine()}",
        "head": _git_head(),
        "model_requested": MODEL,
        "upstream": UPSTREAM,
        "credential": {"source": "env:DEEPSEEK_API_KEY", "present": bool(secret)},
        "hard_caps": {
            "max_proxy_calls_per_execution": args.max_proxy_calls,
            "model_calls_cap_total": args.model_calls_cap,
            "recovery_new_cap": 4,
        },
        "findings": [],
        "limitations": [],
    }
    if not secret:
        report["limitations"].append(
            "DEEPSEEK_API_KEY was not present; the real SDK cancel/close path "
            "could not run (no stub substituted)."
        )
        _write_report(report)
        return 2

    root = Path(tempfile.mkdtemp(prefix="lg016-e2e-"))
    before = _find_harness_pids()
    report["process_check"] = {"localharness_pids_before": before}
    try:
        data_dir = root / "bot-data"
        workspace_root = data_dir / "workspaces"
        secret_store = root / "secrets"
        workspace_root.mkdir(parents=True, exist_ok=True)
        build_workspace(workspace_root)

        store = FileStore(data_dir, workspace_root)
        build_resources(store)
        executor = AntigravityExecutor(
            store,
            artifacts=DirectoryArtifactSink(root / "artifacts"),
            workspace_root=workspace_root,
            max_proxy_calls=args.max_proxy_calls,
            model_calls_cap=args.model_calls_cap,
            cancel_timeout=15.0,
            upstream_timeout=180.0,
        )
        recording = RecordingExecutor(executor)
        catalog = RoleCatalog({"implementation": ["developer"], "verification": ["developer"]})
        dispatcher = GraphDispatcher(
            store,
            recording,
            catalog=catalog,
            planner=SingleNodePlanner(),
            max_parallel=1,
        )
        settings = Settings(
            data_dir=data_dir, workspace_root=workspace_root, secret_store=secret_store
        )
        app = create_app(settings, store=store, dispatcher=dispatcher, executor=recording)

        session_ref = None
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver", timeout=300.0
            ) as client:
                report["real_executor_wired"] = bool(app.state.context.real_executor)
                cancel_case = await run_cancel_case(
                    client, recording, action="cancel", timeout=args.timeout
                )
                report["cancel_case"] = cancel_case
                session_ref = _session_from_events(recording)
                if session_ref is None and recording.results and recording.results[-1].session_ref:
                    session_ref = recording.results[-1].session_ref
                report["close_case"] = await run_close_case(executor, session_ref)

                # A second real run stopped via pause exercises the pausing path.
                pause_case = await run_cancel_case(
                    client, recording, action="pause", timeout=args.timeout
                )
                report["pause_case"] = pause_case

                # Restart recovery: a Task whose Run was mid-execution when the
                # process died.  The scan must never auto-replay it.
                interrupted_task = _synthetic_interrupted_task(store)
                active_run = store.read("task", interrupted_task).entity.get("active_run")
                report["restart_case"] = run_restart_recovery_case(
                    store, interrupted_task, str(active_run)
                )

                report["model_calls_this_run"] = recording.model_calls_made
                report["model_calls_previous_attempts"] = args.prior_calls
                total = args.prior_calls + recording.model_calls_made
                report["model_calls_total"] = total
                report["within_new_recovery_cap"] = recording.model_calls_made <= 4
                report["within_worst_case_cap_8"] = total <= 8

                if not report["cancel_case"]["confirmed"]:
                    report["findings"].append(
                        {
                            "severity": "high",
                            "issue": "real cancel was not confirmed as stopped",
                            "evidence": report["cancel_case"],
                        }
                    )
                if report["cancel_case"]["final_phase"] != "cancelled":
                    report["findings"].append(
                        {
                            "severity": "high",
                            "issue": "cancel did not reach cancelled after confirmation",
                            "evidence": report["cancel_case"]["final_phase"],
                        }
                    )
                if report["restart_case"]["decision_action"] != "recovery_required":
                    report["findings"].append(
                        {
                            "severity": "high",
                            "issue": "restart scan did not mark recovery_required",
                            "evidence": report["restart_case"],
                        }
                    )
    finally:
        if args.keep:
            print(f"kept temp root: {root}", file=sys.stderr)
        else:
            shutil.rmtree(root, ignore_errors=True)

    after = _find_harness_pids()
    report["process_check"]["localharness_pids_after"] = after
    report["process_check"]["leaked"] = sorted(set(after) - set(before))
    if report["process_check"]["leaked"]:
        report["findings"].append(
            {
                "severity": "high",
                "issue": "localharness processes leaked after control/close",
                "evidence": report["process_check"]["leaked"],
            }
        )
    _write_report(report)
    passed = not report["findings"]
    print(
        json.dumps(
            {
                "passed": passed,
                "model_calls_this_run": report["model_calls_this_run"],
                "cancel_confirmed": report["cancel_case"]["confirmed"],
                "cancel_phase": report["cancel_case"]["final_phase"],
                "pause_phase": report["pause_case"]["final_phase"],
                "recovery_required": report["restart_case"]["recovery_required"],
                "leaked": report["process_check"]["leaked"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if passed else 1


def _synthetic_interrupted_task(store: FileStore) -> str:
    """A queued Task is not usable for recovery; build a real interrupted one."""

    from lg010_e2e import _create_resource  # noqa: PLC0415

    task_id = new_id("task")
    store.create(
        "task",
        task_id,
        {
            "title": "interrupted",
            "status": "in-progress",
            "phase": "executing",
            "objective": "interrupted",
            "acceptance_criteria": [],
            "active_run": None,
            "queue": {"state": "not_queued", "order": 0, "owner": None, "lease_expires_at": None},
            "acceptance": {"status": "pending"},
        },
        actor="lg016-e2e",
        request_id=f"task:{task_id}",
        body="# interrupted\n",
    )
    run_id = new_id("run")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "executing",
            "plan_ref": "PLAN.md",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": [],
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
            "worker_pid": 424242,
        },
        actor="lg016-e2e",
        request_id=f"run:{run_id}",
        body="# Run\n",
    )
    StateWriter(store, actor="lg016-e2e").set_active_run(task_id, run_id)
    return task_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-proxy-calls", type=int, default=4)
    parser.add_argument("--model-calls-cap", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--prior-calls", type=int, default=0)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if args.max_proxy_calls * 2 > args.model_calls_cap:
        parser.error("max-proxy-calls*2 must not exceed model-calls-cap")
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
