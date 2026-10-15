"""LG-022 reverify R2 — focused real light-Q&A probe (≤1 real DeepSeek call).

Re-runs ONLY the light Q&A acceptance step with the correct request schema
(batch7 forbids the extra ``conversation_id`` field that the R1 harness sent).
Asserts a real direct answer returns 200, NO Task is created, and the persistent
ledger records the forward.

Run: DEEPSEEK_API_KEY=... .venv/bin/python qa/lg022-r2/harness/light_qa_probe.py <data_dir> <ws> <out_json>
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

GEN_LIMIT = int(os.environ.get("LG022_GEN_LIMIT", "3"))
os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(GEN_LIMIT)

import uvicorn  # noqa: E402

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.runtime.token import RuntimeToken  # noqa: E402

TOKEN = os.environ.get("LG022_QA_TOKEN", "lg022-reverify-token")
CONN = "deepseek-worker-r2"
BASE_URL = "https://api.deepseek.com/v1"
MODEL = os.environ.get("LG022_MODEL", "deepseek-chat")


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


def main() -> int:
    data_dir = Path(sys.argv[1]); workspace_root = Path(sys.argv[2]); out_path = Path(sys.argv[3])
    data_dir.mkdir(parents=True, exist_ok=True)
    (workspace_root / "ws1").mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=data_dir, workspace_root=workspace_root,
                        secret_store=data_dir / "secrets", host="127.0.0.1", port=0)
    settings.ensure_data_dir()
    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore
    store = FileStore(settings.data_dir, settings.workspace_root)
    conn = ConnectionService(store, secret_store=FileSecretStore(settings.secret_store))
    conn.create_connection(connection_id=CONN, backend="openai-compat", model=MODEL,
                           base_url=BASE_URL, credential_ref="deepseek-api-key", title=CONN,
                           actor="qa", request_id="qa-conn")
    conn.update_settings(expected_revision=None, actor="qa",
                         default_coordinator_connection_ref=CONN,
                         default_worker_connection_ref=CONN,
                         default_reviewer_connection_ref=CONN)
    state: RuntimeState = build_runtime(StartupOptions(
        settings=settings, token=RuntimeToken(TOKEN, "generated"),
        serve_frontend=False, max_proxy_calls=GEN_LIMIT, model_calls_cap=GEN_LIMIT))
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(state.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}/api/v1"
    results: dict = {"steps": [], "kind": "real-light-qa"}
    try:
        for _ in range(30):
            if getattr(server, "started", False):
                break
            time.sleep(0.3)
        before = http("GET", f"{base}/tasks")[1].get("items", [])
        code, ans = http("POST", f"{base}/conversations/global/messages",
                         body={"message_id": "r2-light-qa-1",
                               "content": "用一个短句说明什么是幂等。", "role": "user"})
        after = http("GET", f"{base}/tasks")[1].get("items", [])
        gen = http("GET", f"{base}/diagnostics/generation")[1].get("generation")
        results["response"] = {"code": code, "kind": ans.get("kind"),
                               "reply": (ans.get("reply") or "")[:200], "error": ans.get("error")}
        results["generation"] = gen
        results["light_qa_no_task_created"] = code == 200 and len(after) == len(before)
        results["real_answer_returned"] = code == 200 and bool((ans.get("reply") or "").strip())
        results["steps"] = [
            {"name": "light_qa_no_task_created", "ok": results["light_qa_no_task_created"],
             "code": code, "before": len(before), "after": len(after)},
            {"name": "real_answer_returned", "ok": results["real_answer_returned"]},
        ]
        results["ok"] = all(s["ok"] for s in results["steps"])
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"ok": results["ok"], "code": results["response"]["code"],
                          "kind": results["response"]["kind"], "generation": results["generation"],
                          "reply": results["response"]["reply"]}, ensure_ascii=False))
    return 0 if results.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
