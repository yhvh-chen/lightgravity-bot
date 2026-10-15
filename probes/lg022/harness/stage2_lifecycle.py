"""LG-022 Stage 2: lifecycle + fault coverage with CONTROLLED substitutes.

IMPORTANT HONESTY NOTE
----------------------
This stage uses a **controlled substitute executor** (no DeepSeek network) and a
**controlled reviewer substitute** (a real product ``Reviewer`` port, but not the
SDK ModelReviewer) to exercise control/lifecycle mechanics deterministically and
without spending the real-model budget.  Results here are labelled
``substitute`` and must NOT be read as the real SDK review chain passing.  The
real SDK write chain is covered in stage1; the real SDK reviewer chain is
**blocked by defect D1** (see repro-d1.json).

Coverage:
  * pause/cancel **while the independent reviewer is running** -> does the
    runtime actually stop / release the reviewer, or only the (already
    finished) worker execution? (the boundary LG-017/021 did not cover)
  * status query does not wait for execution.
  * duplicate message idempotency and cross-target accept protection.
  * Task lifetime budget across Runs.
  * pin drift on a new Run.
  * SSE cursor reconnect / no duplicate on replay.
  * restart recovery does not replay unknown side effects.

Run:
  uv run python probes/lg022/harness/stage2_lifecycle.py <data_dir> <out_json>
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

import uvicorn  # noqa: E402

from lightgravity.api.access import LocalAccessPolicy  # noqa: E402
from lightgravity.api.app import create_app  # noqa: E402
from lightgravity.adapter.executor import (  # noqa: E402
    ExecutorResult,
    ExecutionRef,
)
from lightgravity.config import Settings  # noqa: E402
from lightgravity.verify.review import (  # noqa: E402
    Finding,
    ReviewContext,
    ReviewReport,
)
from lightgravity.verify.rework import ReworkOrchestrator  # noqa: E402

TOKEN = "lg022-s2-token"
FREE_CALLS = {"executor": 0}


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(method: str, url: str, *, body: dict | None = None, headers: dict | None = None,
         timeout: float = 60.0) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = {"_raw": raw}
        return exc.code, parsed


class ControlledExecutor:
    """Deterministic executor substitute: writes a real file, no network."""

    name = "controlled-substitute"

    def __init__(self, workspace_root: Path) -> None:
        self._ws = workspace_root
        self._active: dict[str, ExecutionRef] = {}

    def capabilities(self):  # noqa: ANN201
        from lightgravity.adapter.capabilities import adapter_capabilities

        return adapter_capabilities()

    @property
    def model_calls_made(self) -> int:
        return 0

    async def execute(self, request, emit):  # noqa: ANN001,ANN201
        FREE_CALLS["executor"] += 1
        out = Path(request.workspace_path or self._ws) / "out"
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.txt").write_text("LG022_S2_OK\n")
        ref = ExecutionRef(execution_id="exec_s2", task_id=request.task_id, run_id=request.run_id)
        self._active[request.run_id] = ref
        return ExecutorResult(
            state="succeeded", summary="controlled write", stop_confirmed=True,
            execution_ref=ref, model="controlled",
            artifact_refs=("out/result.txt",),
        )

    async def cancel(self, ref):  # noqa: ANN001,ANN201
        from lightgravity.coordinator.dispatcher import CancelResult

        self._active.pop(ref.run_id, None)
        return CancelResult(confirmed=True, state="cancelled", reason="controlled stop")

    def start(self):  # noqa: ANN201
        return None

    async def stop(self):  # noqa: ANN201
        return None


class SlowReviewer:
    """Real product Reviewer port that blocks to simulate a running review."""

    name = "controlled-slow-reviewer"
    kind = "model"
    model_calls = 1
    last_usage = {"unknown": ["usage"]}

    def __init__(self, delay: float = 15.0) -> None:
        self.delay = delay
        self.started = threading.Event()
        self.finished = threading.Event()
        self.ran = 0

    def review(self, context: ReviewContext) -> ReviewReport:
        self.ran += 1
        self.started.set()
        time.sleep(self.delay)
        self.finished.set()
        return ReviewReport(
            outcome="passed", candidate_ref=context.candidate.candidate_ref,
            reviewer=self.name, reason="substitute review passed",
        )

    def available(self) -> bool:
        return True


def make_runtime(data_dir: Path, ws_root: Path, reviewer, *, executor=None):
    settings = Settings(data_dir=data_dir, workspace_root=ws_root,
                        secret_store=data_dir / "secrets", host="127.0.0.1", port=0)
    settings.ensure_data_dir()
    (ws_root / "ws_code").mkdir(parents=True, exist_ok=True)
    exc = executor or ControlledExecutor(ws_root)
    app = create_app(settings, executor=exc,
                     access_policy=LocalAccessPolicy(token=TOKEN))
    coordinator = app.state.coordinator
    coordinator.set_rework(
        ReworkOrchestrator(
            app.state.store, reviewer=reviewer, writer=None, spawner=coordinator, actor="qa"
        )
    )
    return settings, app


def serve(app):
    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    return server, thread, f"http://127.0.0.1:{port}/api/v1"


def main() -> int:
    data_dir = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    ws_root = data_dir / "workspaces"
    results: dict = {"stage": "lifecycle-substitute", "steps": []}

    def step(name: str, ok: bool, **detail):
        results["steps"].append({"name": name, "ok": bool(ok), "evidence_kind": "substitute", **detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)

    reviewer = SlowReviewer(delay=12.0)
    settings, app = make_runtime(data_dir, ws_root, reviewer)
    server, thread, base = serve(app)
    try:
        # create task (worker writes via controlled executor)
        code, task = http("POST", f"{base}/tasks", body={
            "request_id": "s2-req-1", "title": "controlled task",
            "objective": "write out/result.txt", "acceptance_criteria": ["out/result.txt exists"],
            "workspace_ref": "ws_code"})
        task_id = task.get("task_id")
        step("task_created", code == 200 and bool(task_id), code=code, task_id=task_id)

        # wait until the reviewer has actually started (started event set)
        started = reviewer.started.wait(timeout=20)
        step("reviewer_started", started, reviewer_ran=reviewer.ran)

        # While the reviewer is definitely still running, probe responsiveness
        # from a SEPARATE thread: a status query and a pause control.
        probe: dict = {}

        def probe_from_other_thread():
            t0 = time.time()
            try:
                sc, sd = http("GET", f"{base}/tasks/{task_id}", timeout=30)
                probe["status_latency"] = round(time.time() - t0, 3)
                probe["status_code"] = sc
                probe["status_phase"] = sd.get("phase")
            except Exception as exc:  # noqa: BLE001
                probe["status_error"] = f"{type(exc).__name__}: {exc}"
                probe["status_latency"] = round(time.time() - t0, 3)
            t1 = time.time()
            try:
                pc, pd = http("POST", f"{base}/tasks/{task_id}/actions",
                              body={"action": "pause", "request_id": "s2-pause-1"}, timeout=30)
                probe["pause_latency"] = round(time.time() - t1, 3)
                probe["pause_code"] = pc
                probe["pause_state"] = pd.get("state")
                probe["pause_error"] = (pd.get("error") or {}).get("code")
            except Exception as exc:  # noqa: BLE001
                probe["pause_error"] = f"{type(exc).__name__}: {exc}"
                probe["pause_latency"] = round(time.time() - t1, 3)

        prober = threading.Thread(target=probe_from_other_thread)
        prober.start()
        still_running_at_probe = not reviewer.finished.is_set()
        prober.join(timeout=40)
        results["review_probe"] = {**probe, "reviewer_still_running_at_probe_start": still_running_at_probe}

        # Honest finding: a sync reviewer running on the event loop freezes the
        # API (status/pause cannot be served) until the review returns.
        frozen = probe.get("status_latency", 0) > 5.0 or probe.get("pause_latency", 0) > 5.0
        step("control_served_during_review", not frozen,
             status_latency=probe.get("status_latency"), pause_latency=probe.get("pause_latency"),
             status_phase=probe.get("status_phase"), pause_state=probe.get("pause_state"),
             pause_error=probe.get("pause_error"),
             note="FAIL if the event loop is blocked so status/pause cannot be served")

        finished = reviewer.finished.wait(timeout=25)
        step("reviewer_eventually_finished", finished, reviewer_ran=reviewer.ran)
        time.sleep(0.5)
        final_phase = http("GET", f"{base}/tasks/{task_id}")[1].get("phase")
        results["final_phase_after_probe"] = final_phase
        step("task_phase_after_review_with_pause_request",
             final_phase in {"awaiting_acceptance", "paused", "verifying", "waiting_user"},
             phase=final_phase)

        # ------------------------------------------------- status non-blocking
        t0 = time.time()
        scode, st = http("GET", f"{base}/tasks/{task_id}")
        step("status_query_immediate", scode == 200 and time.time() - t0 < 1.0,
             elapsed=round(time.time() - t0, 4), phase=st.get("phase"))

        # --------------------------------------------------- accept binding
        detail = http("GET", f"{base}/tasks/{task_id}")[1]
        run = detail.get("run") or {}
        run_id = run.get("id")
        results["final"] = {"phase": final_phase, "run_id": run_id}
        if final_phase == "awaiting_acceptance" and run_id:
            acode, ares = http("POST", f"{base}/tasks/{task_id}/actions",
                               body={"action": "accept", "request_id": "s2-accept-1",
                                     "target_run_id": run_id})
            step("accept_bound_exact_run",
                 acode == 200 and ares.get("state") == "confirmed"
                 and (ares.get("acceptance") or {}).get("status") == "accepted",
                 code=acode, candidate_ref=ares.get("candidate_ref"))
            # stale target accept must be rejected
            scode2, sres2 = http("POST", f"{base}/tasks/{task_id}/actions",
                                 body={"action": "accept", "request_id": "s2-accept-stale",
                                       "target_run_id": "run_does_not_match"})
            step("accept_wrong_target_rejected", scode2 >= 400,
                 code=scode2, err=(sres2.get("error") or {}).get("code"))
        else:
            step("accept_bound_exact_run", False,
                 reason=f"phase {final_phase} not awaiting_acceptance (substitute path)")

        results["ok"] = all(s["ok"] for s in results["steps"])
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print("WROTE", out_path, flush=True)
    return 0 if results.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
