"""Decisive product-wiring comparison: current stop path vs SDK-cancel fix.

Two scenarios, both with the SAME bounded local fake SSE upstream and the SAME
real product ``ModelReviewer`` / ``run_review_turn`` / ``ReviewLifecycle`` /
``ControlService``:

  A. **Current product stop path** (as shipped): request a stop during the SDK
     streaming phase via ``ControlService.stop`` -> the product only sets a
     cooperative ``threading.Event``; the real SDK turn is never told to cancel,
     so the turn does not stop within the stop timeout -> honest ``unconfirmed``
     with slot/refs retained.

  B. **Fix direction (probe-only, product NOT modified)**: same real SDK turn,
     but the probe calls the SDK's documented cancel entry
     (``conversation.cancel()`` + ``wait_for_idle()``) during streaming -> the
     real turn stops promptly and the reviewer's ``resource_stop_report`` becomes
     ``confirmed``.

B uses a probe-local wrapper that mimics what a fixed product would do (poll the
stop event during the streaming iteration and call ``conversation.cancel()``).
It does NOT modify product source; it only demonstrates the minimal fix on the
same real SDK objects.

0 real model calls.  Wrap in ``timeout 45``.
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
            "title": "decisive product stop probe",
            "objective": "compare product stop path against SDK cancel fix",
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


# --------------------------------------------------------------------------- #
# Scenario A: current product stop path
# --------------------------------------------------------------------------- #


async def scenario_a_current_product() -> dict:
    from lightgravity.verify.candidate import load_candidate
    from lightgravity.verify.review import ReviewContext, resolve_candidate_evidence

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", root / "ws")
        upstream = FakeUpstream(hold_seconds=20.0)
        out: dict = {"scenario": "A_current_product", "provider": "provider-substitute"}
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
            out["resource_stop_report_at_stop"] = dict(resource_stop_report)
            out["upstream_saw_client_gone_at_stop"] = upstream.gate.client_gone.is_set()
            out["lifecycle_still_reviewing_at_stop"] = lifecycle.is_reviewing(task_id, run_id)
            post_run = store.read("run", run_id).entity
            post_task = store.read("task", task_id).entity
            out["run_state_after_stop"] = post_run.get("state")
            out["task_phase_after_stop"] = post_task.get("phase")
            out["session_refs_preserved"] = (
                list(post_run.get("session_refs") or []) == session_refs
            )
            out["turn_kept_running_after_stop"] = lifecycle.is_reviewing(task_id, run_id)
        finally:
            upstream.close()
        return out


# --------------------------------------------------------------------------- #
# Scenario B: probe-local SDK-cancel fix direction
# --------------------------------------------------------------------------- #


async def scenario_b_sdk_cancel_fix() -> dict:
    """Mimic a fixed product turn: poll stop during streaming + SDK cancel.

    Uses the real SDK ``Agent`` / ``Conversation`` objects directly (not product
    source) with the real product proxy and fake upstream, demonstrating that
    calling the documented ``conversation.cancel()`` during the streaming phase
    stops the real turn and lets the reaper observe a confirmed teardown.
    """

    import google.antigravity as ag
    from google.antigravity import Agent, types

    import threading

    upstream = FakeUpstream(hold_seconds=20.0)
    proxy = _proxy_module.LocalAuthProxy(
        credential=_FakeCredential(),
        upstream_url=_proxy_module.upstream_chat_completions(upstream.base_url),
        max_calls=4,
    )
    out: dict = {"scenario": "B_sdk_cancel_fix", "provider": "provider-substitute"}
    agent = None
    stop_event = threading.Event()
    resource_stop_report: dict = {}
    try:
        proxy.start()
        config = ag.LocalOpenAIAgentConfig(
            base_url=proxy.base_url,
            model="fake-reviewer",
            system_instructions="fake reviewer",
            capabilities=types.CapabilitiesConfig(enabled_tools=[], enable_subagents=False),
            workspaces=None,
        )
        agent = Agent(config)
        await agent.__aenter__()
        conversation = agent.conversation
        response = await agent.chat("review this")

        async def turn() -> None:
            # Fix direction: poll the stop event WHILE awaiting the next stream
            # chunk (the product's current code only polls around send(), which
            # returns immediately, so it never observes the stop mid-stream).
            # On stop, call the documented SDK cancel entry and wait for idle.
            chunks = 0
            aiter = response.chunks.__aiter__()
            try:
                while True:
                    if stop_event.is_set():
                        await conversation.cancel()
                        await conversation.wait_for_idle()
                        break
                    try:
                        await asyncio.wait_for(
                            aiter.__anext__(), timeout=0.05
                        )
                        chunks += 1
                    except asyncio.TimeoutError:
                        continue
                    except StopAsyncIteration:
                        break
            finally:
                out["chunks_before_stop"] = chunks

        turn_task = asyncio.ensure_future(turn())
        deadline = time.monotonic() + 10.0
        while not upstream.gate.opened.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        out["stream_opened"] = upstream.gate.opened.is_set()

        stop_t0 = time.monotonic()
        stop_event.set()
        try:
            await asyncio.wait_for(asyncio.shield(turn_task), timeout=6.0)
            out["turn_stopped_within_6s"] = True
        except asyncio.TimeoutError:
            out["turn_stopped_within_6s"] = False
        out["stop_elapsed_s"] = round(time.monotonic() - stop_t0, 3)
        out["is_idle_after_cancel"] = conversation.is_idle
        out["upstream_saw_client_gone"] = upstream.gate.client_gone.is_set()
    finally:
        agent_closed = True
        proxy_stopped = True
        if agent is not None:
            try:
                await asyncio.wait_for(agent.__aexit__(None, None, None), timeout=15.0)
            except BaseException:  # noqa: BLE001
                agent_closed = False
        try:
            proxy_stopped = bool(proxy.stop(timeout=5.0))
        except BaseException:  # noqa: BLE001
            proxy_stopped = False
        resource_stop_report.update(
            {
                "agent_closed": agent_closed,
                "proxy_stopped": proxy_stopped,
                "confirmed": agent_closed and proxy_stopped,
            }
        )
        out["resource_stop_report"] = dict(resource_stop_report)
        upstream.close()
    return out


async def _main() -> dict:
    a = await scenario_a_current_product()
    b = await scenario_b_sdk_cancel_fix()
    verdict = {
        "A_current_product_unconfirmed": (
            a.get("control", {}).get("confirmed") is False
            and a.get("control", {}).get("state") == "unconfirmed"
        ),
        "A_current_product_turn_kept_running": a.get("turn_kept_running_after_stop") is True,
        "A_current_product_no_teardown_fact": a.get("resource_stop_report_at_stop") == {},
        "A_current_product_no_sdk_cancel_reached": a.get("upstream_saw_client_gone_at_stop") is False,
        "A_refs_and_slot_preserved": a.get("session_refs_preserved") is True,
        "B_sdk_cancel_stops_turn": b.get("turn_stopped_within_6s") is True,
        "B_sdk_cancel_idle": b.get("is_idle_after_cancel") is True,
        "B_confirmed_teardown": b.get("resource_stop_report", {}).get("confirmed") is True,
    }
    return {
        "provider": "provider-substitute",
        "real_model_calls": 0,
        "sdk_version": _sdk_version(),
        "A_current_product": a,
        "B_sdk_cancel_fix": b,
        "verdict": verdict,
        "product_defect_confirmed": all(
            [
                verdict["A_current_product_unconfirmed"],
                verdict["A_current_product_turn_kept_running"],
                verdict["A_current_product_no_teardown_fact"],
                verdict["A_current_product_no_sdk_cancel_reached"],
                verdict["A_refs_and_slot_preserved"],
            ]
        ),
        "fix_direction_works": all(
            [
                verdict["B_sdk_cancel_stops_turn"],
                verdict["B_sdk_cancel_idle"],
                verdict["B_confirmed_teardown"],
            ]
        ),
    }


def _sdk_version() -> str:
    try:
        import importlib.metadata as md

        return md.version("google-antigravity")
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/lg022-decisive.json")
    result = asyncio.run(_main())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
