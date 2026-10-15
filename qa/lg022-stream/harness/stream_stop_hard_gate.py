"""LG-022 stream-stop QA — FIRST OFFLINE HARD GATE (0 real model calls).

Independent re-verification of the ``fix/lg022-stream`` wiring: the reviewer
stop request must reach the SDK's *documented* cancel entry during the real
**streaming** phase and only confirm after the real Agent + loopback proxy have
exited.

Composition (all REAL product objects, provider substituted by a local fake SSE):
  * real ``google-antigravity==0.1.22`` ``Agent`` / ``Conversation`` / ``LocalAuthProxy``;
  * real product ``ModelReviewer`` -> ``run_review_turn``;
  * real ``ReviewLifecycle`` (worker thread + cooperative ``stop_event``);
  * real ``ControlService.stop`` (pause/cancel) with the lifecycle attached;
  * real ``StateWriter`` / ``FileStore`` (Run seeded with fixture session_refs --
    the refs are fixtures, the SDK Conversation/Agent are real).

Scenarios and assertions (recorded in the JSON verdict):
  S1 CANCEL mid-stream  -> reaches SDK cancel, observes real idle, confirms only
                           after real teardown, no lingering review, refs kept.
  S2 PAUSE  mid-stream  -> same stop reach; task lands paused via the legal
                           verifying -> waiting_user -> paused two-step.
  S3 UNKNOWN-HELD       -> a reviewer that ignores stop keeps the slot
                           (ControlService returns unconfirmed; refs kept; no
                           terminal write).  Uses a deterministic double that
                           never acknowledges -- explicitly NOT used to claim a
                           real SDK cancel.
  S4 NORMAL DRAIN       -> with no stop, the real SDK stream drains fully
                           (chunks preserved, teardown confirmed) -- the polling
                           loop does not corrupt a successful stream.

Bounded single process; wrap in ``timeout 90``.  Cleans its own loopback server
and child processes.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "backend"))

import lightgravity.adapter.proxy as _proxy_module  # noqa: E402

# The fake upstream is loopback; allow it explicitly (product normally only
# authorises the real provider host).  Observe-only for this probe.
_proxy_module.AUTHORIZED_UPSTREAM_HOSTS = frozenset({"api.deepseek.com", "127.0.0.1"})

import lightgravity.coordinator  # noqa: E402,F401
from lightgravity.coordinator.control import ControlService  # noqa: E402
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.store.ids import new_id  # noqa: E402
from lightgravity.verify.review import ModelReviewer, ReviewerSupport, ReviewContext, resolve_candidate_evidence  # noqa: E402
from lightgravity.verify.candidate import load_candidate  # noqa: E402
from lightgravity.verify.review_lifecycle import ReviewLifecycle, run_review_off_loop  # noqa: E402
from lightgravity.verify.review_lifecycle import ReviewStopped  # noqa: E402
from fake_sse_upstream import FakeSseUpstream  # noqa: E402


class _FakeCredential:
    def reveal(self) -> str:
        return "sk-fake-local-upstream-not-a-secret"


class _QueueDouble:
    def enqueue(self, task_id: str) -> str:
        return "not_queued"


class _DispatcherDouble:
    async def cancel(self, task_id: str, run_id: str):
        from lightgravity.adapter.execution import CancelResult

        return CancelResult(confirmed=False, state="not_found", reason="worker already returned")


class _CancelRecorder:
    """Observe the SDK's documented cancel entry (real Conversation class patch).

    Observation only: it counts calls and captures whether ``is_idle`` is true
    after ``wait_for_idle`` returns on the real Conversation object.  It changes
    no product behaviour.
    """

    def __init__(self) -> None:
        self.cancel_calls = 0
        self.idle_calls = 0
        self.idle_after_cancel: bool | None = None
        self.cancel_before_teardown: bool | None = None  # set by teardown ordering


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


def _seed(store: FileStore, *, phase: str = "verifying") -> tuple[str, str, list[str]]:
    """Seed a Run whose session_refs are FIXTURE refs (form, not a real session).

    The real SDK Conversation/Agent created by ``run_review_turn`` are real; the
    Run's ``session_refs`` here are seeded fixtures that stand in for the
    worker's sessions a real run would record.  This is stated explicitly so the
    form is never mistaken for a real DeepSeek session.
    """

    task_id = new_id("task")
    run_id = new_id("run")
    session_refs = ["sess_fixture_worker_a", "sess_fixture_worker_b"]
    store.create(
        "task", task_id,
        {
            "phase": phase, "status": "in-progress", "title": "stream-stop QA hard gate",
            "objective": "prove streaming-phase stop reaches the SDK cancel entry",
            "acceptance_criteria": ["reviewer turns are real SDK turns"],
            "workspace_ref": "ws", "requirements_revision": 1, "deliverable_revision": 0,
            "authorized_checks": [],
            "acceptance": {
                "status": "pending", "requirements_revision": None,
                "deliverable_revision": None, "evidence_refs": [],
                "decided_at": None, "decision_ref": None,
            },
            "queue": {"state": "claimed", "owner": "qa-probe"},
            "active_run": run_id,
        },
        actor="qa-probe", request_id=f"seed:{task_id}", body="# Task\n",
    )
    store.create(
        "run", run_id,
        {
            "task_ref": task_id, "attempt": 1, "state": "verifying", "plan_ref": "PLAN.md",
            "team_refs": [], "subtask_refs": [],
            "session_refs": list(session_refs), "cleanup": {"status": "pending"},
            "ended_at": None, "fail_reason": None,
        },
        actor="qa-probe", request_id=f"seed:{run_id}", body="# Run\n",
    )
    return task_id, run_id, session_refs


def _make_reviewer(base_url: str, timeout: float = 30.0) -> ModelReviewer:
    return ModelReviewer(
        ReviewerSupport(model="qa-fake-reviewer", base_url=base_url, credential_ref="fake-ref"),
        lambda ref: _FakeCredential(),
        timeout_seconds=timeout,
    )


async def _drive_control(
    scenario: str, store_root: Path, action: str, *, upstream: FakeSseUpstream,
) -> dict:
    store = FileStore(store_root / "data", store_root / "ws")
    (store_root / "ws").mkdir(parents=True, exist_ok=True)
    task_id, run_id, session_refs = _seed(store)
    reviewer = _make_reviewer(upstream.base_url)
    lifecycle = ReviewLifecycle(stop_timeout_seconds=5.0)
    resource_stop_report: dict = {}
    loop = asyncio.get_running_loop()

    def runner(stop_event: threading.Event):
        candidate = load_candidate(store, task_id)
        context = ReviewContext(
            task_id=task_id, run_id=run_id, candidate=candidate, store=store,
            resolved_evidence=resolve_candidate_evidence(store, candidate),
            stop_event=stop_event, resource_stop_report=resource_stop_report,
        )
        return reviewer.review(context)

    future = run_review_off_loop(loop, lifecycle, task_id, run_id, runner)
    controller = ControlService(
        store, StateWriter(store, actor="qa-probe"), _QueueDouble(), _DispatcherDouble(),
        owner="qa-probe",
    )
    controller.set_review_lifecycle(lifecycle)

    out: dict = {"scenario": scenario, "action": action, "provider": "provider-substitute"}
    # Wait until the real SDK turn is streaming.
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if upstream.gate.opened.is_set() and lifecycle.is_reviewing(task_id, run_id):
            break
        await asyncio.sleep(0.02)
    out["stream_opened"] = upstream.gate.opened.is_set()
    out["reviewing_before_stop"] = lifecycle.is_reviewing(task_id, run_id)
    await asyncio.sleep(0.3)  # let several chunks stream

    stop_t0 = time.monotonic()
    outcome = await controller.stop(task_id, action)
    out["control_stop_elapsed_s"] = round(time.monotonic() - stop_t0, 3)
    out["control"] = outcome.to_dict()
    out["resource_stop_report"] = dict(resource_stop_report)
    # Transport-level teardown is a *soft* observation: give the fake handler a
    # bounded window to see the closed socket before we release it ourselves.
    # The authoritative teardown facts are the SDK Agent close + proxy stop.
    for _ in range(20):
        if upstream.gate.client_gone.is_set():
            break
        await asyncio.sleep(0.02)
    out["upstream_saw_client_gone"] = upstream.gate.client_gone.is_set()
    out["lifecycle_still_reviewing_at_stop"] = lifecycle.is_reviewing(task_id, run_id)
    post_run = store.read("run", run_id).entity
    post_task = store.read("task", task_id).entity
    out["run_state_after_stop"] = post_run.get("state")
    out["task_phase_after_stop"] = post_task.get("phase")
    out["reviewer_cleanup_after_stop"] = post_run.get("reviewer_cleanup")
    out["session_refs_preserved"] = list(post_run.get("session_refs") or []) == session_refs
    out["session_refs_are_fixture"] = True  # honest: seeded form, not a real session

    try:
        result = await asyncio.wait_for(asyncio.shield(future), timeout=2.0)
        out["review_future_done"] = True
        out["review_future_outcome"] = getattr(result, "outcome", None)
    except asyncio.TimeoutError:
        out["review_future_done"] = False
    except ReviewStopped:
        out["review_future_done"] = True
        out["review_future_stopped"] = True
    except BaseException as exc:  # noqa: BLE001 - recorded, not swallowed
        out["review_future_done"] = True
        out["review_future_exc"] = type(exc).__name__
    out["no_lingering_review"] = not lifecycle.is_reviewing(task_id, run_id)
    out["reviewer_last_error"] = reviewer.last_error
    return out


async def _run_unknown_held(store_root: Path) -> dict:
    """A reviewer that never acknowledges the stop must keep the slot (held).

    Deterministic double -- explicitly NOT a real SDK cancel claim.
    """

    store = FileStore(store_root / "data2", store_root / "ws2")
    (store_root / "ws2").mkdir(parents=True, exist_ok=True)
    task_id, run_id, session_refs = _seed(store)
    lifecycle = ReviewLifecycle(stop_timeout_seconds=0.5)
    release = threading.Event()

    def runner(stop_event: threading.Event):
        # Ignore the cooperative stop entirely; block until the harness releases.
        release.wait(timeout=5.0)
        return "ignored-stop"

    loop = asyncio.get_running_loop()
    future = run_review_off_loop(loop, lifecycle, task_id, run_id, runner)
    controller = ControlService(
        store, StateWriter(store, actor="qa-probe"), _QueueDouble(), _DispatcherDouble(),
        owner="qa-probe",
    )
    controller.set_review_lifecycle(lifecycle)

    out: dict = {"scenario": "S3_unknown_held", "action": "cancel",
                 "kind": "deterministic-double (NOT a real SDK cancel)"}
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not lifecycle.is_reviewing(task_id, run_id):
        await asyncio.sleep(0.01)
    start = time.monotonic()
    outcome = await controller.stop(task_id, "cancel")
    out["control_stop_elapsed_s"] = round(time.monotonic() - start, 3)
    out["control"] = outcome.to_dict()
    post_run = store.read("run", run_id).entity
    post_task = store.read("task", task_id).entity
    out["run_state_after_stop"] = post_run.get("state")
    out["task_phase_after_stop"] = post_task.get("phase")
    out["session_refs_preserved"] = list(post_run.get("session_refs") or []) == session_refs
    out["still_reviewing_held"] = lifecycle.is_reviewing(task_id, run_id)
    release.set()
    try:
        await asyncio.wait_for(asyncio.shield(future), timeout=3.0)
    except BaseException:  # noqa: BLE001
        pass
    return out


async def _run_normal_drain(store_root: Path) -> dict:
    """No stop: real SDK stream drains fully; teardown confirmed (no regression)."""

    upstream = FakeSseUpstream(hold_seconds=20.0)
    try:
        import threading as _threading

        import lightgravity.verify.review as review_mod

        report: dict = {}
        support = ReviewerSupport(model="qa-fake-reviewer", base_url=upstream.base_url,
                                  credential_ref="fake-ref")

        async def _release() -> None:
            deadline = time.monotonic() + 10.0
            while not upstream.gate.opened.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(0.02)
            upstream.gate.release.set()

        rel = asyncio.ensure_future(_release())
        try:
            text, usage = review_mod.run_review_turn(
                support, lambda ref: _FakeCredential(), "review this",
                timeout_seconds=30.0, max_model_calls=4,
                stop_event=_threading.Event(),  # never set
                resource_stop_report=report,
            )
        finally:
            rel.cancel()
        return {
            "scenario": "S4_normal_drain", "provider": "provider-substitute",
            "returned": True, "text": text, "usage": usage,
            "resource_stop_report": dict(report),
            "chunks_sent": upstream.gate.chunks_sent,
        }
    finally:
        upstream.close()


def _sdk_version() -> str:
    try:
        import importlib.metadata as md

        return md.version("google-antigravity")
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    out_path = Path(sys.argv[1])
    result: dict = {"real_model_calls": 0, "sdk_version": _sdk_version()}
    recorder = _CancelRecorder()
    _install_cancel_recorder(recorder)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # S1 cancel mid-stream
        up1 = FakeSseUpstream(hold_seconds=20.0)
        try:
            result["S1_cancel_stream"] = asyncio.run(
                _drive_control("S1_cancel_stream", root / "s1", "cancel", upstream=up1)
            )
        finally:
            up1.close()

        # S2 pause mid-stream
        up2 = FakeSseUpstream(hold_seconds=20.0)
        try:
            result["S2_pause_stream"] = asyncio.run(
                _drive_control("S2_pause_stream", root / "s2", "pause", upstream=up2)
            )
        finally:
            up2.close()

        # S3 unknown-held (deterministic double)
        result["S3_unknown_held"] = asyncio.run(_run_unknown_held(root / "s3"))

        # S4 normal drain (real SDK)
        result["S4_normal_drain"] = asyncio.run(_run_normal_drain(root / "s4"))

    result["sdk_cancel_calls"] = recorder.cancel_calls
    result["sdk_wait_for_idle_calls"] = recorder.idle_calls
    result["sdk_is_idle_after_cancel"] = recorder.idle_after_cancel

    s1 = result["S1_cancel_stream"]
    s2 = result["S2_pause_stream"]
    s3 = result["S3_unknown_held"]
    s4 = result["S4_normal_drain"]

    def _teardown_confirmed(sc: dict) -> bool:
        rep = sc.get("resource_stop_report", {})
        return rep.get("confirmed") is True and rep.get("agent_closed") is True \
            and rep.get("proxy_stopped") is True

    result["verdict"] = {
        "S1_stream_opened": s1.get("stream_opened") is True,
        "S1_control_confirmed": s1.get("control", {}).get("confirmed") is True,
        "S1_control_state_confirmed": s1.get("control", {}).get("state") == "confirmed",
        "S1_sdk_cancel_reached": recorder.cancel_calls >= 1,
        "S1_sdk_idle_observed": result.get("sdk_is_idle_after_cancel") is True,
        "S1_real_teardown_confirmed": _teardown_confirmed(s1),
        "S1_review_stopped": s1.get("no_lingering_review") is True,
        "S1_run_cancelled": s1.get("run_state_after_stop") == "cancelled",
        "S1_refs_preserved": s1.get("session_refs_preserved") is True,
        "S1_stop_under_timeout": float(s1.get("control_stop_elapsed_s", 99)) < 5.0,

        "S2_stream_opened": s2.get("stream_opened") is True,
        "S2_control_confirmed": s2.get("control", {}).get("confirmed") is True,
        "S2_real_teardown_confirmed": _teardown_confirmed(s2),
        "S2_review_stopped": s2.get("no_lingering_review") is True,
        "S2_task_paused": s2.get("task_phase_after_stop") == "paused",
        "S2_run_paused": s2.get("run_state_after_stop") == "paused",
        "S2_refs_preserved": s2.get("session_refs_preserved") is True,
        "S2_stop_under_timeout": float(s2.get("control_stop_elapsed_s", 99)) < 5.0,

        "S3_unknown_unconfirmed": s3.get("control", {}).get("confirmed") is False
            and s3.get("control", {}).get("state") == "unconfirmed",
        "S3_slot_held_no_terminal": s3.get("task_phase_after_stop")
            not in {"cancelled", "paused"},
        "S3_refs_preserved": s3.get("session_refs_preserved") is True,

        "S4_drain_returned": s4.get("returned") is True,
        "S4_teardown_confirmed": s4.get("resource_stop_report", {}).get("confirmed") is True,
        "S4_chunks_preserved": (s4.get("chunks_sent") or 0) >= 2
            and "tick-0" in (s4.get("text") or ""),
    }
    result["hard_gate_pass"] = all(result["verdict"].values())
    # Transport-level closure is reported but not gated: the SDK read side can be
    # torn down without the fake writer observing EPIPE within the window.  The
    # gated teardown facts are the real SDK Agent close + loopback proxy stop +
    # observed Conversation idle (docs/08 §9 authoritative stop confirmation).
    result["observations"] = {
        "S1_upstream_saw_client_gone": s1.get("upstream_saw_client_gone"),
        "S2_upstream_saw_client_gone": s2.get("upstream_saw_client_gone"),
        "S1_stop_elapsed_s": s1.get("control_stop_elapsed_s"),
        "S2_stop_elapsed_s": s2.get("control_stop_elapsed_s"),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["hard_gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
