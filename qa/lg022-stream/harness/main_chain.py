"""LG-022 stream-stop QA — SECOND MAIN CHAIN (one real DeepSeek fixture).

One end-to-end real chain on the frozen candidate, under the SINGLE persistent
generation ledger/limit for this phase (never a second ledger):

  real Settings (worker + reviewer default pins) -> real Task
  -> real worker (Antigravity SDK 0.1.22 + LocalOpenAIAgentConfig + loopback
     auth proxy) writes a real artifact
  -> real asynchronous independent ModelReviewer with real teardown proof
  -> awaiting_acceptance
  -> accept bound to requirements_revision / candidate_ref / candidate_plan_hash

Regressions on the SAME fixture (no extra model calls): duplicate accept is
idempotent; stale/wrong-target accept is rejected; cancel/pause control on a
terminal task is not-applicable; duplicate task creation is idempotent; the
protected write needs a token; the connection pin survives into the Run; the
persistent ledger is the one frozen path and its count is consistent.

Budget: this phase's real-DeepSeek generation total is capped at 10 by the ONE
frozen ledger.  If the cap is reached the harness records an honest incomplete
result -- it never starts a second data_dir/ledger.

Run:
    DEEPSEEK_API_KEY=... timeout 900 .venv/bin/python \
      qa/lg022-stream/harness/main_chain.py <out_json>
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "backend"))

import unified_phase_ledger_config as cfg  # noqa: E402

# Pin the ONE ledger/limit BEFORE the runtime (and every proxy) is built, so
# worker/reviewer/retry all share the same persistent hard cap.
os.environ.update(cfg.phase_env())

import uvicorn  # noqa: E402

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.runtime.token import RuntimeToken  # noqa: E402

TOKEN = "lg022-stream-qa-token"
WORKER_CONN = "deepseek-worker-qa-stream"
REVIEWER_CONN = "deepseek-reviewer-qa-stream"
BASE_URL = "https://api.deepseek.com/v1"
MODEL = os.environ.get("LG022_MODEL", "deepseek-chat")
CREDENTIAL_REF = "deepseek-api-key"
GEN_LIMIT = cfg.PHASE_GENERATION_LIMIT
DATA_DIR = cfg.PHASE_DATA_DIR


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(method, url, *, body=None, headers=None, timeout=120.0):
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


def wait_for(predicate, timeout, interval=0.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def main() -> int:
    out_path = Path(sys.argv[1])
    workspace_root = DATA_DIR / "workspace"
    secret_store = DATA_DIR / "secrets"
    workspaces = workspace_root / "ws1"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    workspaces.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        data_dir=DATA_DIR, workspace_root=workspace_root,
        secret_store=secret_store, host="127.0.0.1", port=0,
    )
    settings.ensure_data_dir()

    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    preseed_store = FileStore(settings.data_dir, settings.workspace_root)
    preseed_conn = ConnectionService(
        preseed_store, secret_store=FileSecretStore(settings.secret_store)
    )
    from lightgravity.store import EntityNotFound

    for cid in (WORKER_CONN, REVIEWER_CONN):
        try:
            preseed_store.read("connection", cid)
            continue  # preseed is idempotent across reruns on the persistent dir
        except EntityNotFound:
            pass
        preseed_conn.create_connection(
            connection_id=cid, backend="openai-compat", model=MODEL,
            base_url=BASE_URL, credential_ref=CREDENTIAL_REF, title=cid,
            actor="qa-stream-preseed", request_id=f"preseed-{cid}",
        )
    preseed_conn.update_settings(
        expected_revision=preseed_store.read("settings", "settings").revision,
        actor="qa-stream-preseed",
        default_coordinator_connection_ref=WORKER_CONN,
        default_worker_connection_ref=WORKER_CONN,
        default_reviewer_connection_ref=REVIEWER_CONN,
    )

    state: RuntimeState = build_runtime(
        StartupOptions(
            settings=settings, token=RuntimeToken(TOKEN, "generated"),
            serve_frontend=False, max_proxy_calls=GEN_LIMIT, model_calls_cap=GEN_LIMIT,
        )
    )
    port = free_port()
    config = uvicorn.Config(state.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}/api/v1"
    results: dict = {
        "candidate_head": os.environ.get("LG022_QA_HEAD", ""),
        "phase_data_dir": str(DATA_DIR),
        "phase_limit": GEN_LIMIT,
        "steps": [], "generation_readings": [],
    }

    def gen():
        try:
            return http("GET", f"{base}/diagnostics/generation")[1].get("generation")
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}

    def note(label):
        reading = gen()
        results["generation_readings"].append({"at": label, **reading})
        return reading

    def step(name, ok, **detail):
        results["steps"].append({"name": name, "ok": bool(ok), **detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)

    try:
        if not wait_for(lambda: getattr(server, "started", False), 15):
            step("server_started", False)
            raise SystemExit("server did not start")
        step("health_ok", http("GET", f"{base}/health")[0] == 200)

        view = http("GET", f"{base}/settings")[1]
        step("worker_default_pinned", view.get("default_worker_connection_ref") == WORKER_CONN)
        step("reviewer_default_pinned", view.get("default_reviewer_connection_ref") == REVIEWER_CONN)
        step("protected_write_requires_token",
             http("PATCH", f"{base}/settings", body={"default_worker_connection_ref": WORKER_CONN})[0] == 401)

        report = state.execution_report()
        step("execution_ready", report["execution_ready"] is True, reasons=report["reasons"])
        step("reviewer_wired_model", report.get("reviewer", {}).get("reviewer") == "model",
             reviewer=report.get("reviewer"))

        if os.environ.get("LG022_DRY") == "1":
            step("dry_run_no_model_steps", True, note="wiring validated; no generation")
            results["dry"] = True
            results["ok"] = all(s["ok"] for s in results["steps"])
            results["final_generation"] = note("dry_final")
            return 0 if results["ok"] else 1

        gen0 = note("start")
        step("ledger_persistent_single_path", gen0.get("persistent") is True
             and gen0.get("limit") == GEN_LIMIT, generation=gen0)

        # ---- task created; duplicate request_id is idempotent (no new Task)
        body = {
            "request_id": "qa-stream-task-req-1", "title": "Write result file",
            "objective": ("Create a file named out/result.txt containing exactly the token "
                          "LG022_STREAM_OK on a single line. Do nothing else."),
            "acceptance_criteria": ["out/result.txt exists and contains LG022_STREAM_OK"],
            "workspace_ref": "ws1",
        }
        code, task = http("POST", f"{base}/tasks", body=body)
        task_id = task.get("task_id")
        step("task_created", code == 200 and bool(task_id), code=code, task_id=task_id)
        code2, task2 = http("POST", f"{base}/tasks", body=body)
        step("duplicate_task_idempotent", task2.get("task_id") == task_id, code=code2)

        phases_seen: set[str] = set()
        max_status_latency = 0.0
        terminal = {"awaiting_acceptance", "waiting_user", "failed", "completed",
                    "recovery_required", "cancelled"}

        def poll_until_terminal() -> str:
            nonlocal max_status_latency
            deadline = time.time() + 400
            last = ""
            while time.time() < deadline:
                t0 = time.time()
                d = http("GET", f"{base}/tasks/{task_id}")[1]
                max_status_latency = max(max_status_latency, time.time() - t0)
                last = d.get("phase", "")
                phases_seen.add(last)
                if last in terminal:
                    return last
                time.sleep(0.4)
            return last

        final_phase = poll_until_terminal()
        step("run_reached_awaiting_acceptance", final_phase == "awaiting_acceptance",
             phase=final_phase, phases_seen=sorted(phases_seen))
        step("status_query_not_blocked", max_status_latency < 2.0,
             max_status_latency=round(max_status_latency, 3))
        results["phases_seen"] = sorted(phases_seen)
        note("after_run_and_review")

        detail = http("GET", f"{base}/tasks/{task_id}")[1]
        run = detail.get("run") or {}
        run_id = run.get("id")
        results["task_after_run"] = detail
        # Real artifact on disk
        artifact = workspaces / "out" / "result.txt"
        artifact_text = artifact.read_text(errors="replace").strip() if artifact.exists() else None
        step("real_artifact_written", artifact_text is not None and "LG022_STREAM_OK" in artifact_text,
             artifact=str(artifact), content=(artifact_text or "")[:80])

        session_refs = run.get("session_refs") or []
        cleanup = run.get("cleanup") or {}
        reviewer_cleanup = run.get("reviewer_cleanup")
        step("real_session_refs_recorded", len(session_refs) >= 1, session_refs=session_refs)
        step("cleanup_not_fabricated_done", not (isinstance(cleanup, dict) and cleanup.get("status") == "done"),
             cleanup=cleanup)
        step("reviewer_real_teardown_recorded",
             isinstance(reviewer_cleanup, dict) and reviewer_cleanup.get("confirmed") is True,
             reviewer_cleanup=reviewer_cleanup)
        pin = run.get("connection_pin")
        step("worker_connection_pin_present",
             isinstance(pin, dict) and pin.get("connection_id") == WORKER_CONN
             and pin.get("role") == "worker",
             pin=pin)

        # ---- accept bound to requirements_revision / candidate_ref / plan hash
        req_rev = detail.get("requirements_revision")
        plan_hash = run.get("plan_hash")
        accept_body = {"action": "accept", "request_id": "qa-stream-accept-1",
                       "target_run_id": run_id,
                       "expected_requirements_revision": req_rev}
        acode, ares = http("POST", f"{base}/tasks/{task_id}/actions", body=accept_body,
                           headers={"X-LG-Token": TOKEN})
        acc = ares.get("acceptance") or {}
        step("accept_confirmed_bound",
             acode == 200 and ares.get("state") == "confirmed" and acc.get("status") == "accepted"
             and ares.get("candidate_ref") == run_id,
             code=acode, state=ares.get("state"), acceptance=acc,
             candidate_ref=ares.get("candidate_ref"), plan_hash=plan_hash, req_rev=req_rev)
        results["accept_response"] = ares
        results["plan_hash"] = plan_hash
        results["requirements_revision"] = req_rev

        # duplicate accept idempotent (same request_id)
        acode2, ares2 = http("POST", f"{base}/tasks/{task_id}/actions", body=accept_body,
                             headers={"X-LG-Token": TOKEN})
        step("duplicate_accept_idempotent",
             acode2 == 200 and ares2.get("candidate_ref") == run_id
             and json.dumps(ares2.get("acceptance"), sort_keys=True)
             == json.dumps(ares.get("acceptance"), sort_keys=True),
             code=acode2)

        # stale / wrong-target accept rejected (new request id, wrong run)
        scode, sres = http("POST", f"{base}/tasks/{task_id}/actions",
                           body={"action": "accept", "request_id": "qa-stream-accept-stale",
                                 "target_run_id": "run_does_not_exist"},
                           headers={"X-LG-Token": TOKEN})
        step("stale_accept_rejected", scode >= 400, code=scode, error=sres.get("error"))

        # control on a terminal task is rejected by the phase guard (illegal
        # transition); the stop gate never fabricates a stop for a task that has
        # already reached a terminal decision.
        ccode, cres = http("POST", f"{base}/tasks/{task_id}/actions",
                           body={"action": "cancel", "request_id": "qa-stream-cancel-term"},
                           headers={"X-LG-Token": TOKEN})
        cerr = cres.get("error") or {}
        step("control_on_terminal_rejected_no_fabricated_stop",
             cres.get("confirmed") is not True
             and (ccode >= 400 or cres.get("state") in {"not_applicable", "unconfirmed"}),
             code=ccode, state=cres.get("state"), error_code=cerr.get("code"))

        gen_final = note("final")
        step("ledger_persistent_final", gen_final.get("persistent") is True
             and gen_final.get("count", 0) >= 1 and gen_final.get("count", 0) <= GEN_LIMIT,
             generation=gen_final)
        ledger_history = cfg.LEDGER_HISTORY
        step("ledger_history_present_single_path", ledger_history.exists(),
             path=str(ledger_history))

        results["final_generation"] = gen_final
        results["ok"] = all(s["ok"] for s in results["steps"])
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print("WROTE", out_path, flush=True)
    return 0 if results.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
