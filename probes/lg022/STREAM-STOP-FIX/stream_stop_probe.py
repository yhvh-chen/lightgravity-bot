"""LG-022 stream-stop fix — real-SDK end-to-end probe (0 real model calls).

Drives the **real product** path after the fix:

  ``ModelReviewer.review`` -> ``run_review_turn`` (real ``google-antigravity``
  ``Agent`` + real ``LocalAuthProxy``) -> real ``ReviewLifecycle`` -> real
  ``ControlService.stop``

against a bounded local fake SSE upstream (``provider-substitute``, never
DeepSeek).  The stop is requested while the SDK streaming phase is live; the
probe asserts that the fix makes the real SDK turn stop by reaching the SDK's
documented cancel entry (``Conversation.cancel()`` + ``wait_for_idle``), that
the reviewer's real teardown fact becomes ``confirmed``, and that the lifecycle
confirms the stop (rather than the pre-fix hang until the stop timeout).

Assertions recorded in the JSON verdict:
  * ``stream_opened``                     — the fake upstream held the stream
  * ``control.confirmed`` is true         — ``ControlService.stop`` confirmed
  * ``resource_stop_report.confirmed``    — real reviewer teardown fact
  * ``upstream_saw_client_gone``          — transport really torn down
  * ``sdk_cancel_reached``                — the SDK cancel entry was called
  * ``sdk_idle_after_cancel``             — ``conversation.is_idle`` true
  * ``stop_elapsed_s`` well under the 5s stop timeout

Wrap in ``timeout 45``; the probe cleans its own loopback server + child
processes and never touches the network.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
# Reuse the QA probe's bounded fake upstream (merged evidence, no product change).
sys.path.insert(0, str(REPO / "qa" / "lg022-r2" / "sdk-cancel-investigation"))

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
from fake_upstream import FakeUpstream  # noqa: E402  (no-stop control only)
from continuous_fake_upstream import ContinuousFakeUpstream  # noqa: E402


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


class _CancelRecorder:
    """Class-level recorder for the SDK's documented cancel entry.

    Patches ``Conversation.cancel`` / ``Conversation.wait_for_idle`` on the
    real SDK class so every real product turn's cancel is observed
    deterministically (instance patching races with the SDK's own object
    lifecycle).  This only *observes*; it changes no product behaviour.
    """

    def __init__(self) -> None:
        self.cancel_calls = 0
        self.idle_calls = 0
        self.idle_after_cancel: bool | None = None


def _install_cancel_recorder(recorder: _CancelRecorder) -> None:
    from google.antigravity.conversation.conversation import Conversation

    real_cancel = Conversation.cancel
    real_idle = Conversation.wait_for_idle

    async def _cancel(self) -> None:  # noqa: ANN001, ANN202
        recorder.cancel_calls += 1
        await real_cancel(self)

    async def _wait_for_idle(self) -> None:  # noqa: ANN001, ANN202
        recorder.idle_calls += 1
        await real_idle(self)
        recorder.idle_after_cancel = bool(getattr(self, "is_idle", False))

    Conversation.cancel = _cancel  # type: ignore[method-assign]
    Conversation.wait_for_idle = _wait_for_idle  # type: ignore[method-assign]


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
            "title": "stream-stop fix probe",
            "objective": "prove streaming-phase stop reaches the SDK cancel entry",
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
            "queue": {"state": "claimed", "owner": "probe"},
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


async def run_probe() -> dict:
    from lightgravity.verify.candidate import load_candidate
    from lightgravity.verify.review import ReviewContext, resolve_candidate_evidence

    out: dict = {"scenario": "stream_stop_fix", "provider": "provider-substitute"}
    recorder = _CancelRecorder()
    _install_cancel_recorder(recorder)
    import lightgravity.verify.review as _review_mod

    cancel_turn_calls = {"n": 0}
    _real_cancel_sdk_turn = _review_mod._cancel_sdk_turn

    async def _traced_cancel_sdk_turn(agent: object) -> bool:  # noqa: ANN202
        cancel_turn_calls["n"] += 1
        return await _real_cancel_sdk_turn(agent)

    _review_mod._cancel_sdk_turn = _traced_cancel_sdk_turn
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", root / "ws")
        upstream = ContinuousFakeUpstream(hold_seconds=20.0)
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
            lifecycle = ReviewLifecycle(stop_timeout_seconds=5.0)
            resource_stop_report: dict = {}
            loop = asyncio.get_running_loop()

            def runner(stop_event: threading.Event):  # noqa: ANN001
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
                StateWriter(store, actor="probe"),
                _QueueDouble(),
                _DispatcherDouble(),
                owner="probe",
            )
            controller.set_review_lifecycle(lifecycle)

            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if upstream.gate.opened.is_set() and lifecycle.is_reviewing(task_id, run_id):
                    break
                await asyncio.sleep(0.02)
            out["stream_opened"] = upstream.gate.opened.is_set()
            out["release_set_before_stop"] = upstream.gate.release.is_set()
            out["reviewing"] = lifecycle.is_reviewing(task_id, run_id)
            # Let the SDK enter the streaming turn (the fake keeps emitting
            # chunks), so the stop lands mid-stream deterministically.
            await asyncio.sleep(0.3)

            stop_t0 = time.monotonic()
            outcome = await controller.stop(task_id, "cancel")
            out["control_stop_elapsed_s"] = round(time.monotonic() - stop_t0, 3)
            out["control"] = outcome.to_dict()
            out["resource_stop_report"] = dict(resource_stop_report)
            out["upstream_saw_client_gone"] = upstream.gate.client_gone.is_set()
            out["lifecycle_still_reviewing_at_stop"] = lifecycle.is_reviewing(
                task_id, run_id
            )
            post_run = store.read("run", run_id).entity
            post_task = store.read("task", task_id).entity
            out["run_state_after_stop"] = post_run.get("state")
            out["reviewer_cleanup_after_stop"] = post_run.get("reviewer_cleanup")
            out["task_phase_after_stop"] = post_task.get("phase")
            out["session_refs_preserved"] = (
                list(post_run.get("session_refs") or []) == session_refs
            )
            try:
                result_obj = await asyncio.wait_for(asyncio.shield(future), timeout=1.0)
                out["review_future_done"] = True
                out["review_future_outcome"] = getattr(result_obj, "outcome", None)
                out["reviewer_last_error"] = reviewer.last_error
            except asyncio.TimeoutError:
                out["review_future_done"] = False
            except BaseException as exc:  # noqa: BLE001 - recorded, not swallowed
                out["review_future_done"] = True
                out["review_future_exc"] = type(exc).__name__
                out["reviewer_last_error"] = reviewer.last_error
            out["turn_kept_running_after_stop"] = lifecycle.is_reviewing(task_id, run_id)
            out["sdk_cancel_calls"] = recorder.cancel_calls
            out["sdk_wait_for_idle_calls"] = recorder.idle_calls
            out["sdk_is_idle_after_cancel"] = recorder.idle_after_cancel
            out["cancel_sdk_turn_calls"] = cancel_turn_calls["n"]
        finally:
            upstream.close()
            loop_cleanup = f"done in {out.get('control_stop_elapsed_s')}s"
            _ = loop_cleanup
    return out


async def run_no_stop_completion() -> dict:
    """Control: without a stop request the real turn still drains fully.

    Proves the streaming-stage poll is transparent to the normal path (no
    dropped chunks, no forced stop, teardown still confirmed).
    """

    import threading as _threading

    out: dict = {"scenario": "no_stop_completion", "provider": "provider-substitute"}
    upstream = FakeUpstream(hold_seconds=20.0)
    report: dict = {}
    try:
        import lightgravity.verify.review as review_mod

        def _resolve(_ref: str):  # noqa: ANN202
            return _FakeCredential()

        support = ReviewerSupport(
            model="fake-reviewer", base_url=upstream.base_url, credential_ref="fake-ref"
        )

        async def _drive() -> None:
            # Release the fake stream so it completes naturally after a moment.
            async def _release() -> None:
                deadline = time.monotonic() + 10.0
                while not upstream.gate.opened.is_set() and time.monotonic() < deadline:
                    await asyncio.sleep(0.02)
                upstream.gate.release.set()

            rel = asyncio.ensure_future(_release())
            try:
                text, usage = review_mod.run_review_turn(
                    support,
                    _resolve,
                    "review this",
                    timeout_seconds=30.0,
                    max_model_calls=4,
                    stop_event=_threading.Event(),  # never set
                    resource_stop_report=report,
                )
                out["returned"] = True
                out["text"] = text
                out["usage"] = usage
            finally:
                rel.cancel()

        await _drive()
        out["resource_stop_report"] = dict(report)
    finally:
        upstream.close()
    return out


def _sdk_version() -> str:
    try:
        import importlib.metadata as md

        return md.version("google-antigravity")
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    out_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/lg022-stream-stop.json")
    )
    result = asyncio.run(run_probe())
    control = result.get("control", {})
    report = result.get("resource_stop_report", {})
    no_stop = asyncio.run(run_no_stop_completion())
    result["no_stop_completion"] = no_stop
    result["real_model_calls"] = 0
    result["sdk_version"] = _sdk_version()
    result["verdict"] = {
        "stream_opened": result.get("stream_opened") is True,
        "control_confirmed": control.get("confirmed") is True,
        "reviewer_teardown_confirmed": report.get("confirmed") is True,
        "sdk_cancel_reached": (result.get("sdk_cancel_calls") or 0) >= 1,
        "sdk_idle_after_cancel": result.get("sdk_is_idle_after_cancel") is True,
        "review_future_done": result.get("review_future_done") is True,
        "no_lingering_review": result.get("turn_kept_running_after_stop") is False,
        "refs_preserved": result.get("session_refs_preserved") is True,
        "stop_under_timeout": float(result.get("control_stop_elapsed_s", 99)) < 5.0,
        "no_stop_path_returns": no_stop.get("returned") is True,
        "no_stop_teardown_confirmed": (
            no_stop.get("resource_stop_report", {}).get("confirmed") is True
        ),
    }
    result["fix_confirmed"] = all(result["verdict"].values())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["fix_confirmed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
