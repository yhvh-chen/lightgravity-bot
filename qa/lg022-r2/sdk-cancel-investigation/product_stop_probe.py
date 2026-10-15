"""Product-wiring stop probe — real product ReviewLifecycle + real SDK reviewer.

Reproduces the prior ``review_cancel_sdk_proof.py`` question but:
  * uses the **bounded** fake upstream from ``fake_upstream.py`` (staged release
    + hard hold timeout), so the probe can never hang past its budget and we
    never mistake an SDK request timeout for a cancel failure;
  * keeps the process within ``timeout 45``.

It drives the real product path:
  ``ModelReviewer.review`` -> ``run_review_turn`` (real Agent + LocalAuthProxy,
  loopback fake upstream) -> real ``ReviewLifecycle`` -> real ``ControlService.stop``
with a real-shape Run and non-empty ``session_refs``.

It answers: when a stop is requested *during the SDK streaming phase*, does the
real SDK turn actually stop (``resource_stop_report`` populated, upstream sees
client gone, run cancelled), or does the product report ``unconfirmed`` because
its stop path never reaches the SDK cancel entry?

0 real model calls.  Run: .venv/bin/python <this> <out.json>
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lightgravity.adapter.proxy as _proxy_module  # noqa: E402

_proxy_module.AUTHORIZED_UPSTREAM_HOSTS = frozenset({"api.deepseek.com", "127.0.0.1"})

import lightgravity.coordinator  # noqa: E402,F401
from lightgravity.coordinator.control import ControlService  # noqa: E402
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.store.ids import new_id  # noqa: E402
from lightgravity.verify.review import ModelReviewer, ReviewerSupport  # noqa: E402
from lightgravity.verify.review_lifecycle import (  # noqa: E402
    ReviewLifecycle,
    run_review_off_loop,
)
from fake_upstream import FakeUpstream  # noqa: E402


class _FakeCredential:
    def reveal(self) -> str:
        return "sk-fake-local-upstream-not-a-secret"


class _QueueDouble:
    def enqueue(self, task_id: str) -> str:  # noqa: ANN001
        return "not_queued"


class _DispatcherDouble:
    async def cancel(self, task_id: str, run_id: str):  # noqa: ANN001
        from lightgravity.adapter.execution import CancelResult

        return CancelResult(
            confirmed=False, state="not_found", reason="worker already returned"
        )


def _seed(store: FileStore) -> tuple[str, str, list[str]]:
    task_id = new_id("task")
    run_id = new_id("run")
    session_refs = ["sess_worker_real_a", "sess_worker_real_b"]
    store.create(
        "task",
        task_id,
        {
            "phase": "verifying",
            "status": "in-progress",
            "title": "product-wiring stop proof",
            "objective": "probe product reviewer stop boundary",
            "acceptance_criteria": ["reviewer turns are real SDK turns"],
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
            "queue": {"state": "claimed", "owner": "qa-probe"},
            "active_run": run_id,
        },
        actor="probe",
        request_id=f"seed:{task_id}",
        body="# Task\n",
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
            "session_refs": list(session_refs),
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="probe",
        request_id=f"seed:{run_id}",
        body="# Run\n",
    )
    return task_id, run_id, session_refs


async def _probe(*, stop_timeout: float) -> dict:
    from lightgravity.verify.candidate import load_candidate
    from lightgravity.verify.review import ReviewContext, resolve_candidate_evidence

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", root / "ws")
        upstream = FakeUpstream(hold_seconds=20.0)
        out: dict = {"provider": "provider-substitute", "real_model_calls": 0}
        try:
            task_id, run_id, session_refs = _seed(store)
            reviewer = ModelReviewer(
                ReviewerSupport(
                    model="fake-reviewer",
                    base_url=upstream.base_url,
                    credential_ref="fake-ref",
                ),
                lambda ref: _FakeCredential(),
                timeout_seconds=30.0,
            )
            lifecycle = ReviewLifecycle(stop_timeout_seconds=stop_timeout)
            resource_stop_report: dict = {}
            loop = asyncio.get_running_loop()

            def runner(stop_event):  # noqa: ANN001
                candidate = load_candidate(store, task_id)
                context = ReviewContext(
                    task_id=task_id,
                    run_id=run_id,
                    candidate=candidate,
                    store=store,
                    resolved_evidence=resolve_candidate_evidence(store, candidate),
                    stop_event=stop_event,
                    resource_stop_report=resource_stop_report,
                )
                return reviewer.review(context)

            future = run_review_off_loop(loop, lifecycle, task_id, run_id, runner)
            controller = ControlService(
                store,
                StateWriter(store, actor="qa-probe"),
                _QueueDouble(),
                _DispatcherDouble(),
                owner="qa-probe",
            )
            controller.set_review_lifecycle(lifecycle)

            # Wait (bounded) for the stream to open and the lifecycle to report
            # reviewing.
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if upstream.gate.opened.is_set() and lifecycle.is_reviewing(task_id, run_id):
                    break
                await asyncio.sleep(0.02)
            out["stream_opened"] = upstream.gate.opened.is_set()
            out["reviewing"] = lifecycle.is_reviewing(task_id, run_id)

            stop_t0 = time.monotonic()
            outcome = await controller.stop(task_id, "cancel")
            out["control_stop_elapsed_s"] = round(time.monotonic() - stop_t0, 3)
            out["control"] = outcome.to_dict()

            # Give the reviewer thread a moment, then read the real teardown fact.
            await asyncio.sleep(0.5)
            out["resource_stop_report_at_stop"] = dict(resource_stop_report)
            out["upstream_saw_client_gone"] = upstream.gate.client_gone.is_set()
            out["lifecycle_still_reviewing"] = lifecycle.is_reviewing(task_id, run_id)

            post_run = store.read("run", run_id).entity
            post_task = store.read("task", task_id).entity
            out["run_state_after"] = post_run.get("state")
            out["task_phase_after"] = post_task.get("phase")
            out["session_refs_preserved"] = (
                list(post_run.get("session_refs") or []) == session_refs
            )

            # Now release the gate so the held turn can finish, and confirm the
            # future resolves (proves the turn was only stopped by the wait_for
            # timeout / release, not by the product stop path).
            upstream.gate.release.set()
            try:
                result = await asyncio.wait_for(asyncio.shield(future), timeout=15.0)
                out["review_future_resolved_after_release"] = True
                out["review_outcome"] = getattr(result, "outcome", str(result))
            except asyncio.TimeoutError:
                out["review_future_resolved_after_release"] = False
            except BaseException as exc:  # noqa: BLE001
                out["review_future_resolved_after_release"] = False
                out["review_future_exc"] = f"{type(exc).__name__}: {exc}"

            out["product_stop_reached_sdk_cancel"] = bool(
                resource_stop_report.get("confirmed") is True
                and resource_stop_report.get("agent_closed") is True
                and resource_stop_report.get("proxy_stopped") is True
            )
        finally:
            upstream.close()
        return out


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/lg022-product-stop.json")
    stop_timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    result = asyncio.run(_probe(stop_timeout=stop_timeout))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
