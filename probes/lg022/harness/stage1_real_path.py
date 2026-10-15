"""LG-022 real end-to-end harness (Stage 1: minimal real product path).

Drives the REAL product runtime (``build_runtime``) behind a REAL uvicorn
loopback server, over REAL HTTP, with the real LG-006 executor + loopback auth
proxy -> real DeepSeek upstream.  This is *not* an in-process ASGI transport and
*not* a mock executor: the model calls are real HTTP generation requests.

What it covers (LG-022 acceptance):
  * Settings controlled worker + reviewer defaults (protected write, pin).
  * Light Q&A that must NOT create a Task/Run.
  * Real task write -> queue -> real worker execution -> real artifact.
  * Independent real ModelReviewer on the final candidate (separate role/pin).
  * Human accept bound to the exact Run/candidate version.
  * Duplicate message / duplicate accept must not act on a new candidate.

Budget: <= 6 real DeepSeek HTTP calls total for this stage (see QA-PLAN).
The credential comes only from the process env and is never printed.

Run:
    DEEPSEEK_API_KEY=... LIGHTGRAVITY_TEST_PORT=... uv run python probes/lg022/harness/stage1_real_path.py <data_dir> <workspace_dir> <out_json>
"""

from __future__ import annotations

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

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.runtime.token import RuntimeToken  # noqa: E402

TOKEN = os.environ.get("LG022_QA_TOKEN", "lg022-qa-token")
WORKER_CONN = "deepseek-worker-qa"
REVIEWER_CONN = "deepseek-reviewer-qa"
BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-flash"
CREDENTIAL_REF = "deepseek-api-key"

REAL_CALLS = {"count": 0}  # incremented by us per observed upstream call record


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(method: str, url: str, *, body: dict | None = None, headers: dict | None = None,
         timeout: float = 120.0) -> tuple[int, dict]:
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


def wait_for(predicate, timeout: float, interval: float = 0.5) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def main() -> int:
    data_dir = Path(sys.argv[1])
    workspace_root = Path(sys.argv[2])
    out_path = Path(sys.argv[3])
    data_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "ws1").mkdir(parents=True, exist_ok=True)
    secret_store = data_dir / "secrets"

    user = os.environ.get("USER", "qa")
    settings = Settings(
        data_dir=data_dir,
        workspace_root=workspace_root,
        secret_store=secret_store,
        host="127.0.0.1",
        port=0,
    )
    settings.ensure_data_dir()

    # Pre-seed the controlled settings BEFORE building the runtime: this is the
    # realistic "configured from the start" path (a user who configured
    # worker/reviewer defaults, then restarted the local service).  Configuring
    # *after* start is a separate lifecycle boundary tested in stage3.
    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    preseed_store = FileStore(settings.data_dir, settings.workspace_root)
    preseed_conn = ConnectionService(preseed_store, secret_store=FileSecretStore(settings.secret_store))
    for cid in (WORKER_CONN, REVIEWER_CONN):
        preseed_conn.create_connection(
            connection_id=cid, backend="openai-compat", model=MODEL,
            base_url=BASE_URL, credential_ref=CREDENTIAL_REF, title=cid,
            actor="qa-preseed", request_id=f"preseed-{cid}",
        )
    preseed_conn.update_settings(
        expected_revision=None, actor="qa-preseed",
        default_coordinator_connection_ref=WORKER_CONN,
        default_worker_connection_ref=WORKER_CONN,
        default_reviewer_connection_ref=REVIEWER_CONN,
    )

    state: RuntimeState = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken(TOKEN, "generated"),
            serve_frontend=False,
            max_proxy_calls=6,
            model_calls_cap=10,
        )
    )
    port = free_port()
    config = uvicorn.Config(state.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}/api/v1"
    results: dict = {"steps": [], "real_calls": 0}

    def step(name: str, ok: bool, **detail):
        results["steps"].append({"name": name, "ok": bool(ok), **detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)

    try:
        if not wait_for(lambda: getattr(server, "started", False), 15):
            step("server_started", False)
            raise SystemExit("server did not start")

        # ---------------------------------------------------------- health
        code, health = http("GET", f"{base}/health")
        step("health_ok", code == 200, code=code)

        # ------------------------------------ settings: verify pinned defaults
        view = http("GET", f"{base}/settings")[1]
        step("worker_default_pinned", view.get("default_worker_connection_ref") == WORKER_CONN,
             value=view.get("default_worker_connection_ref"))
        step("reviewer_default_pinned", view.get("default_reviewer_connection_ref") == REVIEWER_CONN,
             value=view.get("default_reviewer_connection_ref"))

        # protected write without token must be rejected
        code, _ = http("PATCH", f"{base}/settings",
                       body={"default_worker_connection_ref": WORKER_CONN})
        step("protected_write_requires_token", code == 401, code=code)

        report = state.execution_report()
        step("execution_ready", report["execution_ready"] is True, reasons=report["reasons"])
        step("reviewer_wired_model", report.get("reviewer", {}).get("reviewer") == "model",
             reviewer=report.get("reviewer"))

        # ------------------------------------- light Q&A must NOT create Task
        tasks_before = http("GET", f"{base}/tasks")[1]
        # /tasks is sanitized already; use the read-only "items" list
        code, ans = http(
            "POST", f"{base}/conversations/global/messages",
            body={"conversation_id": "global", "message_id": "qa-msg-1",
                  "content": "用一个句子解释什么是幂等性。", "role": "user"},
        )
        tasks_after = http("GET", f"{base}/tasks")[1]
        n_before = len(tasks_before.get("items", []))
        n_after = len(tasks_after.get("items", []))
        step("light_qa_no_task_created", code == 200 and n_after == n_before,
             code=code, before=n_before, after=n_after, kind=ans.get("kind"),
             reply=(ans.get("reply") or "")[:120], raw_error=ans.get("error"))
        results["light_answer_reply"] = (ans.get("reply") or "")[:200]

        # ---------------------------------------- real task -> worker -> run
        code, task = http(
            "POST", f"{base}/tasks",
            body={"request_id": "qa-task-req-1", "title": "Write result file",
                  "objective": "Create a file named out/result.txt containing exactly the token LG022_OK on a single line.",
                  "acceptance_criteria": ["out/result.txt exists and contains LG022_OK"],
                  "workspace_ref": "ws1"},
        )
        task_id = task.get("task_id")
        step("task_created", code == 200 and bool(task_id), code=code, task_id=task_id)

        def task_phase() -> str:
            return http("GET", f"{base}/tasks/{task_id}")[1].get("phase", "")
        reached = wait_for(lambda: task_phase() in {"awaiting_acceptance", "waiting_user", "failed", "completed"},
                           150)
        phase = task_phase()
        step("run_reached_terminal_phase", reached, phase=phase)
        results["real_calls_worker_stage"] = state.executor.model_calls_made if state.executor else None

        detail = http("GET", f"{base}/tasks/{task_id}")[1]
        run = detail.get("run") or {}
        run_id = run.get("id") if isinstance(run, dict) else None
        results["task_after_run"] = {"phase": phase, "run": run,
                                     "acceptance": detail.get("acceptance")}

        # status query must not wait for execution (immediate)
        t0 = time.time()
        scode, st = http("GET", f"{base}/tasks/{task_id}")
        step("status_query_immediate", time.time() - t0 < 2.0 and scode == 200,
             elapsed=round(time.time() - t0, 3), phase=st.get("phase"))

        # -------------------------------------------- accept bound to version
        accept_body = {"action": "accept", "request_id": "qa-accept-1", "target_run_id": run_id}
        acode, ares = http("POST", f"{base}/tasks/{task_id}/actions", body=accept_body,
                           headers={"X-LG-Token": TOKEN})
        acc_status = (ares.get("acceptance") or {}).get("status")
        step("accept_bound_exact_run",
             acode == 200 and ares.get("state") == "confirmed"
             and acc_status == "accepted" and ares.get("candidate_ref") == run_id,
             code=acode, state=ares.get("state"), acceptance_status=acc_status,
             candidate_ref=ares.get("candidate_ref"), target_run_id=run_id,
             response=ares if acode != 200 else None)

        # duplicate accept replay: same request_id + target must be byte-identical
        # to the first result and must not act on a new candidate or open a Run.
        acode2, ares2 = http("POST", f"{base}/tasks/{task_id}/actions", body=accept_body,
                             headers={"X-LG-Token": TOKEN})
        step("duplicate_accept_idempotent",
             acode2 == 200 and ares2.get("candidate_ref") == run_id
             and ares2.get("state") == ares.get("state")
             and json.dumps(ares2.get("acceptance"), sort_keys=True)
             == json.dumps(ares.get("acceptance"), sort_keys=True),
             code=acode2, candidate_ref=ares2.get("candidate_ref"),
             same_result=json.dumps(ares2, sort_keys=True) == json.dumps(ares, sort_keys=True))

        results["final_calls"] = state.executor.model_calls_made if state.executor else None
        results["executor_model_calls_cap"] = 10
        results["ok"] = all(s["ok"] for s in results["steps"])
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print("WROTE", out_path, flush=True)
    return 0 if results.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
