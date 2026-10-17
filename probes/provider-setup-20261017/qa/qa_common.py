"""LG-112 isolated QA fixture helpers.

This is test setup only.  It starts a *real* FastAPI app (real settings/team
routers, real FileStore/secret store, real ConnectionTester) on loopback, with:

* fresh temp data/workspace/secret roots,
* fixed fake team accounts,
* a controlled loopback fake OpenAI/Gemini/Vertex protocol upstream + dummy keys.

The fake upstream is deliberately **not** a real vendor.  It is used only to
exercise the product protocol wiring in isolation; every report must label it as
such.  No product model/real credential/real vendor host is contacted.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CREDENTIAL_ENV_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|password|credential|deepseek|openai|anthropic|gemini|vertex|google_application)",
    re.IGNORECASE,
)

QA_ADMIN = "qa-admin"
QA_ADMIN_PW = "qa-admin-pw"
QA_MEMBER = "qa-member"
QA_MEMBER_PW = "qa-member-pw"

DUMMY_KEYS = {
    "qa-deepseek-key": "sk-qa-dummy-deepseek-not-real",
    "qa-custom-key": "sk-qa-dummy-custom-not-real",
    "qa-tested-key": "sk-qa-dummy-tested-not-real",
    "qa-gemini-key": "sk-qa-dummy-gemini-not-real",
    "qa-vertex-key": "sk-qa-dummy-vertex-not-real",
    "qa-replace-key": "sk-qa-dummy-replacement-not-real",
}


def sanitize_environment() -> None:
    """Prevent the QA process from inheriting any credential/budget override."""

    for key in list(os.environ):
        if CREDENTIAL_ENV_PATTERN.search(key):
            del os.environ[key]
    os.environ.pop("LIGHTGRAVITY_MAX_GENERATION_CALLS", None)
    os.environ.pop("LIGHTGRAVITY_DATA_DIR", None)
    os.environ.pop("LIGHTGRAVITY_SECRET_STORE", None)


def _jsonl_append(path: Path, payload: dict[str, Any], lock: threading.Lock) -> None:
    line = json.dumps(payload, sort_keys=True) + "\n"
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()


class FakeUpstream:
    """Controlled loopback OpenAI/Gemini/Vertex protocol double."""

    def __init__(self, port: int, log_path: Path) -> None:
        self.port = port
        self.log_path = log_path
        self.records: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: object) -> None:  # noqa: D102
                return

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                model: str | None = None
                try:
                    payload = json.loads(body.decode("utf-8"))
                    if isinstance(payload, dict) and isinstance(payload.get("model"), str):
                        model = payload["model"]
                except (UnicodeDecodeError, ValueError):
                    payload = None
                path = self.path.split("?", 1)[0]
                if model is None:
                    for token in re.findall(r"models/([^:/]+)", path):
                        model = token
                        break
                auth = (
                    self.headers.get("Authorization")
                    or self.headers.get("x-goog-api-key")
                    or ""
                )
                lowered = (model or "").lower()
                record: dict[str, Any] = {
                    "method": "POST",
                    "path": path,
                    "model": model,
                    "authorization_present": bool(auth),
                    "authorization": auth,
                    "body_sha256_len": len(body),
                    "body": body.decode("utf-8", "replace")[:8000],
                    "behavior": "success",
                }
                outer.records.append(record)
                _jsonl_append(outer.log_path, record, outer._lock)

                if "slow" in lowered:
                    time.sleep(1.6)
                if "fail" in lowered:
                    record["behavior"] = "fail"
                    payload_out = b'{"error":{"message":"qa fake upstream failure"}}'
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload_out)))
                    self.end_headers()
                    self.wfile.write(payload_out)
                    return
                if "empty" in lowered:
                    record["behavior"] = "empty"
                    payload_out = b'{"choices":[]}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload_out)))
                    self.end_headers()
                    self.wfile.write(payload_out)
                    return

                if "streamGenerateContent" in path:
                    payload_out = (
                        b'data: {"candidates":[{"content":{"parts":[{"text":"pong"}],'
                        b'"role":"model"},"finishReason":"STOP"}]}\n\n'
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(payload_out)))
                    self.end_headers()
                    self.wfile.write(payload_out)
                    return

                payload_out = json.dumps(
                    {
                        "id": "chatcmpl-qa-fake",
                        "model": model or "qa-fake",
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": "pong"},
                                "finish_reason": "stop",
                            }
                        ],
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload_out)))
                self.end_headers()
                self.wfile.write(payload_out)

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="lg112-fake-upstream", daemon=True
        )

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)


@dataclass(slots=True)
class QaRuntime:
    app: Any
    service: Any
    tester: Any
    settings: Any
    data_dir: Path
    secret_dir: Path
    log_dir: Path
    upstream: FakeUpstream
    request_log: Path
    upstream_log: Path


def build_runtime(*, data_dir: Path, log_dir: Path, upstream_port: int) -> QaRuntime:
    """Build the real app with the exact candidate product code."""

    from fastapi import FastAPI, Request

    from lightgravity.adapter.proxy import configure_generation_ledger, global_generation_counter
    from lightgravity.api.app import create_app
    from lightgravity.config import Settings
    from lightgravity.runtime.frontend import mount_frontend
    from lightgravity.settings import (
        ConnectionService,
        ConnectionTestLog,
        ConnectionTester,
        FileSecretStore,
    )
    from lightgravity.store import FileStore
    from lightgravity.team import TeamAccounts

    sanitize_environment()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    secret_dir = data_dir / "secrets"
    workspace_root = data_dir / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        data_dir=data_dir,
        workspace_root=workspace_root,
        secret_store=secret_dir,
        team_mode=True,
    )
    accounts = TeamAccounts(settings.team_accounts_path)
    if accounts.get(QA_ADMIN) is None:
        accounts.add(QA_ADMIN, QA_ADMIN_PW, "admin")
    if accounts.get(QA_MEMBER) is None:
        accounts.add(QA_MEMBER, QA_MEMBER_PW, "member")

    upstream = FakeUpstream(upstream_port, log_dir / "upstream.jsonl")
    upstream.start()

    store = FileStore(data_dir, workspace_root)
    secret_store = FileSecretStore(secret_dir)
    diagnostics = ConnectionTestLog(data_dir / "diagnostics")
    service = ConnectionService(
        store, secret_store=secret_store, test_diagnostics=diagnostics
    )
    configure_generation_ledger(data_dir, limit=None)
    tester = ConnectionTester(
        service,
        diagnostics=diagnostics,
        allow_network=False,
        allow_loopback_upstream=True,
        allow_loopback_native=True,
        native_base_url=upstream.base_url,
        native_timeout=10,
        http_timeout=10,
        upstream_timeout=10,
    )

    _seed(service, tester, store, upstream, data_dir, log_dir)

    app = create_app(
        settings,
        store=store,
        connection_service=service,
        tester=tester,
        initialize_team_accounts=False,
    )
    request_log = log_dir / "requests.jsonl"
    request_lock = threading.Lock()

    @app.middleware("http")
    async def _qa_request_log(request: Request, call_next: Any) -> Any:  # noqa: ANN401
        response = await call_next(request)
        if not request.url.path.startswith(("/assets/", "/favicon")):
            _jsonl_append(
                request_log,
                {
                    "method": request.method,
                    "path": request.url.path,
                    "query": request.url.query,
                    "status": response.status_code,
                    "origin": request.headers.get("origin"),
                    "has_cookie": bool(request.headers.get("cookie")),
                },
                request_lock,
            )
        return response

    # Expose honest, non-secret runtime facts to the browser QA driver.  These
    # are QA-only helper routes, not replacements for any product endpoint.
    @app.get("/__qa__/state")
    def _qa_state() -> dict[str, Any]:
        snapshot = global_generation_counter().snapshot()
        return {
            "generation": snapshot,
            "upstream_requests": len(upstream.records),
            "upstream_base_url": upstream.base_url,
        }

    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if not mount_frontend(app, dist, token=""):
        raise SystemExit(f"frontend dist missing: {dist}")

    qa_runtime = QaRuntime(
        app=app,
        service=service,
        tester=tester,
        settings=settings,
        data_dir=data_dir,
        secret_dir=secret_dir,
        log_dir=log_dir,
        upstream=upstream,
        request_log=request_log,
        upstream_log=log_dir / "upstream.jsonl",
    )
    return qa_runtime


def _seed(service: Any, tester: Any, store: Any, upstream: FakeUpstream, data_dir: Path, log_dir: Path) -> None:
    """Seed saved records through the real service; all secrets are dummy values."""

    from lightgravity.settings import ROLE_COORDINATOR, ROLE_WORKER

    upstream_base = upstream.base_url + "/v1"

    service.create_connection(
        "qa-deepseek",
        title="QA DeepSeek eligible",
        backend="openai-compat",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        auth_mode="proxy_api_key",
        credential_ref="qa-deepseek-key",
        credential_value=DUMMY_KEYS["qa-deepseek-key"],
        actor="qa-seed",
        request_id="qa-seed-deepseek",
    )
    service.create_connection(
        "qa-custom",
        title="QA custom loopback",
        backend="openai-compat",
        model="qa-echo",
        base_url=upstream_base,
        auth_mode="proxy_api_key",
        credential_ref="qa-custom-key",
        credential_value=DUMMY_KEYS["qa-custom-key"],
        actor="qa-seed",
        request_id="qa-seed-custom",
    )
    service.create_connection(
        "qa-tested",
        title="QA saved tested",
        backend="openai-compat",
        model="qa-echo",
        base_url=upstream_base,
        auth_mode="proxy_api_key",
        credential_ref="qa-tested-key",
        credential_value=DUMMY_KEYS["qa-tested-key"],
        actor="qa-seed",
        request_id="qa-seed-tested",
    )
    service.create_connection(
        "qa-gemini",
        title="QA Gemini API key",
        backend="gemini",
        model="gemini-3.8-flash",
        auth_mode="api_key",
        credential_ref="qa-gemini-key",
        credential_value=DUMMY_KEYS["qa-gemini-key"],
        actor="qa-seed",
        request_id="qa-seed-gemini",
    )
    service.create_connection(
        "qa-vertex-adc",
        title="QA Vertex ADC",
        backend="vertex",
        model="gemini-3.8-flash",
        auth_mode="adc",
        project="qa-project",
        location="us-central1",
        actor="qa-seed",
        request_id="qa-seed-vertex",
    )

    service.update_settings(
        expected_revision=None,
        actor="qa-seed",
        default_coordinator_connection_ref="qa-deepseek",
        default_worker_connection_ref="qa-deepseek",
        default_reviewer_connection_ref=None,
    )
    store.create(
        "agent",
        "qa-agent",
        {
            "title": "QA agent reference",
            "enabled": True,
            "connection_ref": "qa-deepseek",
        },
        actor="qa-seed",
        request_id="qa-seed-agent",
    )

    # Persist one saved-test diagnostic for qa-tested via the real tester, so
    # the list last_test is genuine persisted data.  It uses the controlled
    # loopback fake upstream, not a vendor.
    tester.test("qa-tested", allow_network=True)

    from lightgravity.adapter.proxy import global_generation_counter

    seed_meta = {
        "connections": ["qa-deepseek", "qa-custom", "qa-tested", "qa-gemini", "qa-vertex-adc"],
        "default_worker": "qa-deepseek",
        "agent_ref": "qa-agent",
        "generation_after_seed": global_generation_counter().snapshot(),
        "upstream_requests_after_seed": len(upstream.records),
        "data_dir": str(data_dir),
        "secret_dir": str(data_dir / "secrets"),
        "log_dir": str(log_dir),
    }
    (log_dir / "seed.json").write_text(json.dumps(seed_meta, indent=2) + "\n", encoding="utf-8")
    # Keep the seed diagnostics but reset the request/upstream observation logs
    # so browser assertions start from a known baseline.
    deadline = time.time() + 2
    while time.time() < deadline:
        break


def cleanup_runtime(runtime: QaRuntime) -> None:
    try:
        runtime.upstream.stop()
    finally:
        shutil.rmtree(runtime.data_dir, ignore_errors=True)
