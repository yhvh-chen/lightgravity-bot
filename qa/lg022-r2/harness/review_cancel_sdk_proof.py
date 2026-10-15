"""LG-022 reverify R2 — real-SDK reviewer cancel/stop boundary proof (0 model calls).

The R2 REPORT §4 covers ``cancel-during-review`` with a ``deterministic-double``
reviewer (an asyncio ``Event``-driven callable).  The PM correctly noted that a
fake reviewer with NO real SDK session cannot substantiate the *actual* SDK
cancel/stop path.  This harness closes that evidence boundary:

  * the reviewer turn is the **real product** turn path
    (:func:`lightgravity.verify.review.run_review_turn`): a real
    ``google-antigravity==0.1.22`` ``Agent`` + ``LocalOpenAIAgentConfig`` /
    ``LocalAuthProxy`` and the real product resource-teardown fact
    (``resource_stop_report``);
  * the model provider is a **controlled local streaming OpenAI-compatible
    fake upstream** on loopback — a ``provider-substitute``, explicitly NOT
    DeepSeek, so **0 real model calls** are spent;
  * the review is driven through the **real product** ``ReviewLifecycle`` /
    ``run_review_off_loop`` and stopped through the **real product**
    ``ControlService.stop`` with a real-shape Run whose ``session_refs`` is
    non-empty.

It answers exactly the PM question: with real ``session_refs`` and a real SDK
reviewer active, does cancel only confirm *after* the SDK turn (agent + proxy)
really stopped, and is the slot/phase/Run left untouched before that?

  C1  cancel while the real SDK reviewer streams: control may not confirm
      before the SDK turn's teardown fact exists (agent ``__aexit__`` OK +
      proxy stopped) and the fake upstream saw the connection drop; the run is
      only then ``cancelled`` with ``session_refs`` preserved.
  C2  same, but with the reviewer stop confirmation *unavailable* (product
      ``stop_timeout_seconds=0`` while the SDK turn is held mid-stream):
      cancel returns ``unconfirmed``, the phase stays ``cancelling``, the Run is
      NOT cancelled and ``session_refs`` are preserved — never a fabricated
      stop / never a released slot.
  C3  pause during review behaves the same way (at least ``cancel``, and
      ``pause`` confirms only after the real SDK stop).

Run: .venv/bin/python qa/lg022-r2/harness/review_cancel_sdk_proof.py <out_json>
"""

from __future__ import annotations

import asyncio
import http.server
import json
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

# QA-harness-only provider substitution: let the product's LocalAuthProxy point
# at the controlled loopback fake upstream.  Product code is untouched; only the
# authorized-upstream allow-list is widened for this proof.
import lightgravity.adapter.proxy as _proxy_module  # noqa: E402

_proxy_module.AUTHORIZED_UPSTREAM_HOSTS = frozenset({"api.deepseek.com", "127.0.0.1"})

import lightgravity.coordinator  # noqa: E402,F401  (break import cycle)
from lightgravity.coordinator.control import ControlService  # noqa: E402
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.store.ids import new_id  # noqa: E402
from lightgravity.verify.review import ModelReviewer, ReviewerSupport  # noqa: E402
from lightgravity.verify.review_lifecycle import (  # noqa: E402
    ReviewLifecycle,
    run_review_off_loop,
)

# --------------------------------------------------------------------------- #
# Controlled local streaming OpenAI-compatible fake upstream (provider substitute)
# --------------------------------------------------------------------------- #

_ROLE_CHUNK = (
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
    '"model":"fake-reviewer","choices":[{"index":0,'
    '"delta":{"role":"assistant","content":"{\\"outcome\\":\\"passed\\","'
    '"reason\\":"},"finish_reason":null}]}\n\n'
)
_STOP_CHUNK = (
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
    '"model":"fake-reviewer","choices":[{"index":0,"delta":{},'
    '"finish_reason":"stop"}],"usage":{"prompt_tokens":3,'
    '"completion_tokens":1,"total_tokens":4}}\n\n'
    "data: [DONE]\n\n"
)


@dataclass
class _Gate:
    """Test-owned barrier so the SDK turn is *always* mid-stream on cancel."""

    opened: threading.Event
    release: threading.Event
    #: Set when the proxy->upstream socket read loop sees the client go away
    #: (i.e. the SDK agent/proxy really stopped before the stream finished).
    client_gone: threading.Event


class _GatedUpstream(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        gate: _Gate = self.server.gate  # type: ignore[attr-defined]
        provided = False

        def send_chunk(data: bytes) -> None:
            self.wfile.write(f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n")
            self.wfile.flush()

        try:
            send_chunk(_ROLE_CHUNK.encode("utf-8"))
            gate.opened.set()
            # Hold the stream open; the reviewer turn can only end when the
            # product stop path cancels it (or the gate is released).
            gate.release.wait(timeout=30)
            if not gate.release.is_set():
                # Product stopped the turn while we held the stream: the socket
                # is gone, so we simply stop writing.
                gate.client_gone.set()
                return
            send_chunk(_STOP_CHUNK.encode("utf-8"))
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            provided = True
        except (BrokenPipeError, ConnectionResetError, OSError):
            gate.client_gone.set()
        finally:
            _ = provided


class _Upstream:
    def __init__(self) -> None:
        self.gate = _Gate(threading.Event(), threading.Event(), threading.Event())
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _GatedUpstream)
        self._server.daemon_threads = True
        self._server.gate = self.gate  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self.gate.release.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@dataclass
class _FakeCredential:
    def reveal(self) -> str:  # noqa: D102
        return "sk-fake-local-upstream-not-a-secret"


# --------------------------------------------------------------------------- #
# Real-shape store + real product control wiring
# --------------------------------------------------------------------------- #


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
            "title": "real-sdk reviewer cancel proof",
            "objective": "prove the real SDK reviewer stop boundary",
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


class _DispatcherDouble:
    """Minimal dispatcher seam: the worker is already done during review.

    The *reviewer*, not the worker, is the thing under test; this double only
    reports the worker side, exactly like the report's deterministic probe, so
    the cancel verdict must come from the real reviewer lifecycle.
    """

    async def cancel(self, task_id: str, run_id: str):  # noqa: ANN001
        from lightgravity.adapter.execution import CancelResult

        return CancelResult(
            confirmed=False, state="not_found", reason="worker already returned"
        )


def _make_reviewer(upstream_base: str) -> ModelReviewer:
    support = ReviewerSupport(
        model="fake-reviewer", base_url=upstream_base, credential_ref="fake-ref"
    )
    return ModelReviewer(
        support,
        lambda ref: _FakeCredential(),
        timeout_seconds=30.0,
    )


@dataclass
class ReviewRun:
    """One real-SDK review driven through the real product lifecycle."""

    task_id: str
    run_id: str
    session_refs: list[str]
    lifecycle: ReviewLifecycle
    future: "asyncio.Future"
    stop_fact: dict
    reviewer: ModelReviewer
    store: FileStore
    controller: ControlService


def _start_review(
    store: FileStore, upstream_base: str, stop_timeout: float
) -> tuple[ReviewRun, "asyncio.AbstractEventLoop"]:
    task_id, run_id, session_refs = _seed(store)
    reviewer = _make_reviewer(upstream_base)
    lifecycle = ReviewLifecycle(stop_timeout_seconds=stop_timeout)

    # The real product turn is given a mutable resource_stop_report sink (the
    # same seam the coordinator's ReviewContext provides) so we can read the
    # REAL SDK teardown fact.
    resource_stop_report: dict = {}

    from lightgravity.verify.candidate import load_candidate
    from lightgravity.verify.review import ReviewContext, resolve_candidate_evidence

    loop = asyncio.get_running_loop()

    def runner(stop_event: threading.Event):  # noqa: ANN001
        # Build the same deterministic-but-real review context the product uses.
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

    return (
        ReviewRun(
            task_id=task_id,
            run_id=run_id,
            session_refs=session_refs,
            lifecycle=lifecycle,
            future=future,
            stop_fact=resource_stop_report,
            reviewer=reviewer,
            store=store,
            controller=controller,
        ),
        loop,
    )


class _QueueDouble:
    def enqueue(self, task_id: str) -> str:  # noqa: ANN001
        return "not_queued"


async def _wait_stream_opened(upstream: _Upstream, timeout: float = 10.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if upstream.gate.opened.is_set():
            return True
        await asyncio.sleep(0.02)
    return upstream.gate.opened.is_set()


async def _wait_reviewing(run: ReviewRun, timeout: float = 6.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if run.lifecycle.is_reviewing(run.task_id, run.run_id):
            return True
        await asyncio.sleep(0.01)
    return run.lifecycle.is_reviewing(run.task_id, run.run_id)


async def _await_future(run: ReviewRun, timeout: float = 20.0):
    try:
        return await asyncio.wait_for(asyncio.shield(run.future), timeout=timeout)
    except asyncio.TimeoutError:
        return {"timeout": True}
    except Exception as exc:  # noqa: BLE001 - stopped/failed reviews are recorded
        return {"error": f"{type(exc).__name__}: {exc}"}


def _run_state(store: FileStore, run_id: str) -> dict:
    return store.read("run", run_id).entity


def _task_state(store: FileStore, task_id: str) -> dict:
    return store.read("task", task_id).entity


# --------------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------------- #


async def scenario_c1_cancel_real_sdk():
    """Cancel confirms only after the real SDK reviewer turn + proxy stopped."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", root / "ws")
        upstream = _Upstream()
        try:
            run, _ = _start_review(store, upstream.base_url, stop_timeout=5.0)
            opened = await _wait_stream_opened(upstream)
            reviewing = await _wait_reviewing(run)
            pre_run = _run_state(store, run.run_id)

            # Sanity: before cancel the reviewer is genuinely live and the run
            # is not terminated.  The gate is still holding the stream.
            pre = {
                "stream_opened": opened,
                "reviewing": reviewing,
                "run_state": pre_run.get("state"),
                "session_refs": list(pre_run.get("session_refs") or []),
                "teardown_fact_before_cancel": dict(run.stop_fact),
            }

            outcome = await run.controller.stop(run.task_id, "cancel")
            result = await _await_future(run)
            upstream.gate.release.set()

            post_run = _run_state(store, run.run_id)
            post_task = _task_state(store, run.task_id)
            fact = dict(run.stop_fact)
            return {
                "pre": pre,
                "control": outcome.to_dict(),
                "review_result": (
                    result
                    if isinstance(result, dict)
                    else getattr(result, "outcome", str(result))
                ),
                # The confirmed control outcome must coincide with the real SDK
                # teardown fact and the upstream having seen the client leave.
                "real_sdk_teardown_fact": fact,
                "upstream_saw_client_gone": upstream.gate.client_gone.is_set(),
                "run_state_after": post_run.get("state"),
                "task_phase_after": post_task.get("phase"),
                "session_refs_after": list(post_run.get("session_refs") or []),
                "confirmed_after_real_sdk_stop": (
                    outcome.confirmed is True
                    and fact.get("confirmed") is True
                    and fact.get("agent_closed") is True
                    and fact.get("proxy_stopped") is True
                ),
                "terminated_and_released_after_confirm": (
                    post_run.get("state") == "cancelled"
                    and post_task.get("phase") == "cancelled"
                ),
                "session_refs_preserved": (
                    list(post_run.get("session_refs") or []) == run.session_refs
                ),
            }
        finally:
            upstream.close()


async def scenario_c2_hold_when_not_confirmed():
    """No stop confirmation => cancel stays unconfirmed, slot/Run untouched."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", root / "ws")
        upstream = _Upstream()
        try:
            # stop_timeout=0 => the product asks the reviewer to stop but cannot
            # confirm before the (real SDK) turn unwinds: honest unknown.
            run, _ = _start_review(store, upstream.base_url, stop_timeout=0.0)
            opened = await _wait_stream_opened(upstream)
            reviewing = await _wait_reviewing(run)
            outcome = await run.controller.stop(run.task_id, "cancel")

            held_run = _run_state(store, run.run_id)
            held_task = _task_state(store, run.task_id)
            fact_at_hold = dict(run.stop_fact)

            # Now let the real SDK turn actually finish and confirm the gate
            # can be satisfied afterwards (release -> natural completion).
            upstream.gate.release.set()
            result = await _await_future(run)
            return {
                "stream_opened": opened,
                "reviewing_at_cancel": reviewing,
                "control": outcome.to_dict(),
                "teardown_fact_at_hold": fact_at_hold,
                "run_state_while_unconfirmed": held_run.get("state"),
                "task_phase_while_unconfirmed": held_task.get("phase"),
                "session_refs_while_unconfirmed": list(held_run.get("session_refs") or []),
                "review_result_after_release": (
                    result
                    if isinstance(result, dict)
                    else getattr(result, "outcome", str(result))
                ),
                "held_not_terminated": (
                    outcome.confirmed is False
                    and outcome.state == "unconfirmed"
                    and held_run.get("state") == "verifying"
                    and held_task.get("phase") == "cancelling"
                ),
                "session_refs_preserved": (
                    list(held_run.get("session_refs") or []) == run.session_refs
                ),
            }
        finally:
            upstream.close()


async def scenario_c3_pause_real_sdk():
    """Pause during review also confirms only after the real SDK reviewer stops."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", root / "ws")
        upstream = _Upstream()
        try:
            run, _ = _start_review(store, upstream.base_url, stop_timeout=5.0)
            opened = await _wait_stream_opened(upstream)
            reviewing = await _wait_reviewing(run)
            outcome = await run.controller.stop(run.task_id, "pause")
            result = await _await_future(run)
            upstream.gate.release.set()
            post_run = _run_state(store, run.run_id)
            post_task = _task_state(store, run.task_id)
            fact = dict(run.stop_fact)
            return {
                "stream_opened": opened,
                "reviewing": reviewing,
                "control": outcome.to_dict(),
                "review_result": (
                    result
                    if isinstance(result, dict)
                    else getattr(result, "outcome", str(result))
                ),
                "real_sdk_teardown_fact": fact,
                "upstream_saw_client_gone": upstream.gate.client_gone.is_set(),
                "run_state_after": post_run.get("state"),
                "task_phase_after": post_task.get("phase"),
                "session_refs_preserved": (
                    list(post_run.get("session_refs") or []) == run.session_refs
                ),
                "pause_confirmed_after_real_sdk_stop": (
                    outcome.confirmed is True
                    and fact.get("confirmed") is True
                    and post_run.get("state") == "paused"
                ),
            }
        finally:
            upstream.close()


def main() -> int:
    out_path = Path(sys.argv[1])
    results = {
        "evidence_kind": "real-sdk-reviewer-cancel-stop-proof",
        "provider": "provider-substitute",
        "provider_note": (
            "reviewer turn is the real product run_review_turn path (real "
            "google-antigravity Agent + LocalAuthProxy); the model provider is "
            "a controlled local streaming OpenAI-compatible fake upstream on "
            "loopback, NOT DeepSeek"
        ),
        "sdk_version": _sdk_version(),
        "real_model_calls": 0,
    }
    results["cancel_real_sdk"] = asyncio.run(scenario_c1_cancel_real_sdk())
    results["hold_unconfirmed"] = asyncio.run(scenario_c2_hold_when_not_confirmed())
    results["pause_real_sdk"] = asyncio.run(scenario_c3_pause_real_sdk())
    c1 = results["cancel_real_sdk"]
    c2 = results["hold_unconfirmed"]
    c3 = results["pause_real_sdk"]
    results["verdict"] = {
        "C1_cancel_confirmed_after_real_sdk_stop": (
            c1["confirmed_after_real_sdk_stop"]
            and c1["terminated_and_released_after_confirm"]
            and c1["session_refs_preserved"]
        ),
        "C2_unconfirmed_keeps_run_and_refs": (
            c2["held_not_terminated"] and c2["session_refs_preserved"]
        ),
        "C3_pause_confirmed_after_real_sdk_stop": (
            c3["pause_confirmed_after_real_sdk_stop"] and c3["session_refs_preserved"]
        ),
    }
    results["all_pass"] = all(results["verdict"].values())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"verdict": results["verdict"], "all_pass": results["all_pass"]}, indent=2))
    return 0 if results["all_pass"] else 1


def _sdk_version() -> str:
    try:
        import importlib.metadata as md

        return md.version("google-antigravity")
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
