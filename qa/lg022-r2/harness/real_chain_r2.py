"""LG-022 reverify R2 — real end-to-end chain on the batch7 integrated candidate.

Drives the REAL product runtime behind a REAL uvicorn loopback server over REAL
HTTP, with the real executor (Antigravity SDK 0.1.22 + LocalOpenAIAgentConfig +
loopback auth proxy) and the real independent ModelReviewer, connected to the
real DeepSeek upstream.  NOT an in-process ASGI transport, NOT a mock executor.

R2 focus (on top of R1):
  * the shared generation ledger is PERSISTENT at <data_dir>/generation/ and the
    diagnostics endpoint reports persistent=true;
  * a successful session-bearing Run reaches awaiting_acceptance via the R2
    authoritative adapter stop-confirmation, WITH session_refs PRESERVED and
    cleanup NOT fabricated to done;
  * the reviewer's real teardown fact is recorded on run.reviewer_cleanup.

Run:
    DEEPSEEK_API_KEY=... uv run python \
      qa/lg022-r2/harness/real_chain_r2.py <data_dir> <workspace_dir> <out_json>
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

# Hard-cap the shared global counter for THIS process before the runtime is
# built, so every worker/reviewer/retry proxy shares one real limit.
GEN_LIMIT = int(os.environ.get("LG022_GEN_LIMIT", "10"))
os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(GEN_LIMIT)

import uvicorn  # noqa: E402

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.runtime.token import RuntimeToken  # noqa: E402

TOKEN = os.environ.get("LG022_QA_TOKEN", "lg022-reverify-token")
WORKER_CONN = "deepseek-worker-reverify"
REVIEWER_CONN = "deepseek-reviewer-reverify"
BASE_URL = "https://api.deepseek.com/v1"
MODEL = os.environ.get("LG022_MODEL", "deepseek-chat")
CREDENTIAL_REF = "deepseek-api-key"


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
    data_dir = Path(sys.argv[1])
    workspace_root = Path(sys.argv[2])
    out_path = Path(sys.argv[3])
    data_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "ws1").mkdir(parents=True, exist_ok=True)
    secret_store = data_dir / "secrets"

    settings = Settings(
        data_dir=data_dir, workspace_root=workspace_root,
        secret_store=secret_store, host="127.0.0.1", port=0,
    )
    settings.ensure_data_dir()

    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    preseed_store = FileStore(settings.data_dir, settings.workspace_root)
    preseed_conn = ConnectionService(
        preseed_store, secret_store=FileSecretStore(settings.secret_store)
    )
    for cid in (WORKER_CONN, REVIEWER_CONN):
        preseed_conn.create_connection(
            connection_id=cid, backend="openai-compat", model=MODEL,
            base_url=BASE_URL, credential_ref=CREDENTIAL_REF, title=cid,
            actor="reverify-preseed", request_id=f"preseed-{cid}",
        )
    preseed_conn.update_settings(
        expected_revision=None, actor="reverify-preseed",
        default_coordinator_connection_ref=WORKER_CONN,
        default_worker_connection_ref=WORKER_CONN,
        default_reviewer_connection_ref=REVIEWER_CONN,
    )

    state: RuntimeState = build_runtime(
        StartupOptions(
            settings=settings, token=RuntimeToken(TOKEN, "generated"),
            serve_frontend=False, max_proxy_calls=GEN_LIMIT,
            model_calls_cap=GEN_LIMIT,
        )
    )
    port = free_port()
    config = uvicorn.Config(state.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}/api/v1"
    results: dict = {"steps": [], "generation_readings": [], "gen_limit": GEN_LIMIT}

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

        code, _ = http("GET", f"{base}/health")
        step("health_ok", code == 200, code=code)
        note("after_health")

        view = http("GET", f"{base}/settings")[1]
        step("worker_default_pinned", view.get("default_worker_connection_ref") == WORKER_CONN)
        step("reviewer_default_pinned", view.get("default_reviewer_connection_ref") == REVIEWER_CONN)

        code, _ = http("PATCH", f"{base}/settings",
                       body={"default_worker_connection_ref": WORKER_CONN})
        step("protected_write_requires_token", code == 401, code=code)

        report = state.execution_report()
        step("execution_ready", report["execution_ready"] is True, reasons=report["reasons"])
        step("reviewer_wired_model", report.get("reviewer", {}).get("reviewer") == "model",
             reviewer=report.get("reviewer"))

        # -------- light Q&A must NOT create a Task (real DeepSeek direct answer)
        if os.environ.get("LG022_DRY") == "1":
            step("dry_run_skip_model_steps", True, note="no real generation requests")
            results["dry"] = True
            results["ok"] = all(s["ok"] for s in results["steps"])
            results["final_generation"] = note("dry_final")
            return 0 if results["ok"] else 1
        before = len(http("GET", f"{base}/tasks")[1].get("items", []))
        code, ans = http(
            "POST", f"{base}/conversations/global/messages",
            body={"conversation_id": "global", "message_id": "reverify-msg-1",
                  "content": "用一个短句说明什么是幂等。", "role": "user"},
        )
        after = len(http("GET", f"{base}/tasks")[1].get("items", []))
        step("light_qa_no_task_created", code == 200 and after == before,
             code=code, before=before, after=after, kind=ans.get("kind"),
             reply=(ans.get("reply") or "")[:120], raw_error=ans.get("error"))
        note("after_light_qa")

        # -------------------- real task -> real worker -> real artifact -> review
        code, task = http(
            "POST", f"{base}/tasks",
            body={"request_id": "reverify-task-req-1", "title": "Write result file",
                  "objective": "Create a file named out/result.txt containing exactly the token LG022_REVERIFY_OK on a single line.",
                  "acceptance_criteria": ["out/result.txt exists and contains LG022_REVERIFY_OK"],
                  "workspace_ref": "ws1"},
        )
        task_id = task.get("task_id")
        step("task_created", code == 200 and bool(task_id), code=code, task_id=task_id)

        # During the run+review, repeatedly poll status and measure latency to
        # prove the loop is NOT blocked (D2).  Also capture phases seen.
        phases_seen = set()
        max_status_latency = 0.0
        review_seen = False

        def poll_until_terminal() -> str:
            nonlocal max_status_latency, review_seen
            terminal = {"awaiting_acceptance", "waiting_user", "failed", "completed",
                        "recovery_required", "cancelled"}
            deadline = time.time() + 200
            last = ""
            while time.time() < deadline:
                t0 = time.time()
                d = http("GET", f"{base}/tasks/{task_id}")[1]
                lat = time.time() - t0
                max_status_latency = max(max_status_latency, lat)
                last = d.get("phase", "")
                phases_seen.add(last)
                if last in {"reviewing", "verifying"}:
                    review_seen = True
                if last in terminal:
                    return last
                time.sleep(0.4)
            return last

        final_phase = poll_until_terminal()
        step("run_reached_awaiting_acceptance", final_phase == "awaiting_acceptance",
             phase=final_phase, phases_seen=sorted(phases_seen))
        step("status_query_not_blocked_during_run", max_status_latency < 2.0,
             max_status_latency=round(max_status_latency, 3),
             review_phase_observed=review_seen)
        results["phases_seen"] = sorted(phases_seen)
        results["max_status_latency_s"] = round(max_status_latency, 3)
        note("after_run_and_review")

        detail = http("GET", f"{base}/tasks/{task_id}")[1]
        run = detail.get("run") or {}
        run_id = run.get("id") if isinstance(run, dict) else None
        results["task_after_run"] = {"phase": final_phase, "run": run,
                                     "acceptance": detail.get("acceptance")}
        results["requirements_revision"] = detail.get("requirements_revision")
        results["executor_model_calls"] = getattr(state.executor, "model_calls_made", None)

        # ---- D3: success Run must have no fail_reason; failure history kept
        run_md = data_dir / "runs" / str(run_id) / "RUN.md" if run_id else None
        fail_reason = None
        if run_md and run_md.exists():
            for line in run_md.read_text().splitlines():
                if line.startswith("fail_reason:"):
                    fail_reason = line.split(":", 1)[1].strip()
        step("d3_success_run_no_fail_reason", fail_reason in (None, "", "null", "None"),
             fail_reason=fail_reason)
        results["run_md_fail_reason"] = fail_reason

        # ---- R2 stop gate: session_refs preserved, cleanup NOT fabricated done,
        #      reviewer real teardown fact recorded on run.reviewer_cleanup.
        run_entity = run if isinstance(run, dict) else {}
        session_refs = run_entity.get("session_refs") or []
        cleanup = run_entity.get("cleanup") or {}
        reviewer_cleanup = run_entity.get("reviewer_cleanup")
        results["stop_gate"] = {
            "session_refs": session_refs,
            "cleanup": cleanup,
            "reviewer_cleanup": reviewer_cleanup,
        }
        step("r2_session_refs_preserved_nonempty", len(session_refs) >= 1,
             session_refs=session_refs)
        step("r2_cleanup_not_fabricated_done",
             not (isinstance(cleanup, dict) and cleanup.get("status") == "done"),
             cleanup=cleanup)
        step("r2_reviewer_stop_fact_recorded",
             isinstance(reviewer_cleanup, dict) and bool(reviewer_cleanup),
             reviewer_cleanup=reviewer_cleanup)

        # persistent ledger must be reported by the diagnostics endpoint
        gen_final_preview = note("before_accept")
        step("r2_generation_persistent", gen_final_preview.get("persistent") is True,
             generation=gen_final_preview)
        ledger_dir = data_dir / "generation"
        step("r2_ledger_files_present",
             (ledger_dir / "generation.jsonl").exists(),
             ledger_files=sorted(p.name for p in ledger_dir.glob("*")) if ledger_dir.exists() else [])

        # ------------------------------------------------ accept bound to version
        accept_body = {"action": "accept", "request_id": "reverify-accept-1",
                       "target_run_id": run_id}
        acode, ares = http("POST", f"{base}/tasks/{task_id}/actions", body=accept_body,
                           headers={"X-LG-Token": TOKEN})
        acc = ares.get("acceptance") or {}
        step("accept_bound_exact_run",
             acode == 200 and ares.get("state") == "confirmed"
             and acc.get("status") == "accepted" and ares.get("candidate_ref") == run_id,
             code=acode, state=ares.get("state"), acceptance=acc,
             candidate_ref=ares.get("candidate_ref"), target_run_id=run_id)
        results["accept_response"] = ares

        acode2, ares2 = http("POST", f"{base}/tasks/{task_id}/actions", body=accept_body,
                             headers={"X-LG-Token": TOKEN})
        step("duplicate_accept_idempotent",
             acode2 == 200 and ares2.get("candidate_ref") == run_id
             and ares2.get("state") == ares.get("state")
             and json.dumps(ares2.get("acceptance"), sort_keys=True)
             == json.dumps(ares.get("acceptance"), sort_keys=True),
             code=acode2, candidate_ref=ares2.get("candidate_ref"))

        # stale accept: wrong target run with a NEW request_id must be rejected
        scode, sres = http("POST", f"{base}/tasks/{task_id}/actions",
                           body={"action": "accept", "request_id": "reverify-accept-stale",
                                 "target_run_id": "run_does_not_exist"},
                           headers={"X-LG-Token": TOKEN})
        step("stale_accept_rejected", scode >= 400,
             code=scode, state=sres.get("state"), error=sres.get("error"))

        results["final_generation"] = note("final")
        results["ok"] = all(s["ok"] for s in results["steps"])
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print("WROTE", out_path, flush=True)
    return 0 if results.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
