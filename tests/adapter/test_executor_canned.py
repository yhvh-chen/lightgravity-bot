"""End-to-end executor wiring against canned local OpenAI SSE upstreams.

This exercises the real SDK session/runtime with *canned* model responses: it
proves the executor/proxy/session/emit/usage/cancel paths without any real model
call.  It is not model verification evidence (that is the LG-006 real run).
"""

from __future__ import annotations

import asyncio
import http.server
import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from lightgravity.adapter import (
    AntigravityExecutor,
    DirectoryArtifactSink,
    ExecuteRequest,
    ExecutionRef,
    InMemoryCredentialResolver,
    ResourceCompiler,
)
from lightgravity.store import FileStore

from helpers import build_agent, build_basic_environment, make_registry

_FAKE_SECRET = "sk-canned-secret-not-real"

_ROLE_CHUNK = (
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
    '"model":"deepseek-flash","choices":[{"index":0,'
    '"delta":{"role":"assistant","content":"pong"},"finish_reason":null}]}\n\n'
)
_STOP_CHUNK = (
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
    '"model":"deepseek-flash","choices":[{"index":0,"delta":{},'
    '"finish_reason":"stop"}],"usage":{"prompt_tokens":3,'
    '"completion_tokens":1,"total_tokens":4}}\n\n'
    "data: [DONE]\n\n"
)


class _CannedUpstream(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = (_ROLE_CHUNK + _STOP_CHUNK).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True


class _GatedCannedUpstream(http.server.BaseHTTPRequestHandler):
    """Streams one text chunk, then holds the stream open on a test-owned gate.

    The deterministic gate replaces the old ``time.sleep`` stall: the handler
    signals ``opened`` once a partial SSE frame is on the wire and then blocks
    on ``release``, so the test can issue a cancel that is *always* mid-stream
    instead of racing a turn that already finished.
    """

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

        def send_chunk(data: bytes) -> None:
            self.wfile.write(f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n")
            self.wfile.flush()

        gate = self.server.gate  # type: ignore[attr-defined]
        try:
            send_chunk(_ROLE_CHUNK.encode("utf-8"))
            gate.opened.set()
            gate.release.wait(timeout=30)
            send_chunk(_STOP_CHUNK.encode("utf-8"))
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


@dataclass
class _StreamGate:
    """Test-owned barrier between the canned upstream and the cancel call."""

    opened: threading.Event
    release: threading.Event


def _serve(
    handler: type[http.server.BaseHTTPRequestHandler],
    gate: _StreamGate | None = None,
) -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    if gate is not None:
        server.gate = gate
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.fixture
def canned_upstream() -> Iterator[str]:
    yield from _serve(_CannedUpstream)


@pytest.fixture
def gated_canned_upstream() -> Iterator[tuple[str, _StreamGate]]:
    gate = _StreamGate(opened=threading.Event(), release=threading.Event())
    server_gen = _serve(_GatedCannedUpstream, gate)
    url = next(server_gen)
    try:
        yield url, gate
    finally:
        gate.release.set()
        next(server_gen, None)


def _prepare(store: FileStore, tmp_path: Path, upstream: str) -> tuple[AntigravityExecutor, Path]:
    build_basic_environment(store, base_url=upstream, credential_ref="deepseek-api-key")
    store.write(
        "connection",
        "primary",
        {
            "backend": "openai-compat",
            "model": "canned",
            "credential_ref": "deepseek-api-key",
            "base_url": upstream,
        },
        expected_revision=0,
        actor="test",
    )
    build_agent(store)
    workspace = Path(store.workspace_root) / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    executor = AntigravityExecutor(
        store,
        ResourceCompiler(store, registry=make_registry()),
        credential_resolver=InMemoryCredentialResolver({"deepseek-api-key": _FAKE_SECRET}),
        artifacts=DirectoryArtifactSink(tmp_path / "artifacts"),
        allow_loopback_upstream=True,
        model_calls_cap=2,
    )
    return executor, workspace


async def test_executor_runs_canned_session_and_stops_proxy(
    store: FileStore, tmp_path: Path, canned_upstream: str
) -> None:
    executor, workspace = _prepare(store, tmp_path, canned_upstream)
    events: list[dict[str, Any]] = []

    async def emit(event: dict[str, Any]) -> None:
        events.append(event)

    result = await executor.execute(
        ExecuteRequest(
            task_id="task_canned",
            run_id="run_canned",
            subtask_id="sub_canned",
            agent_ref="developer",
            workspace_path=str(workspace),
            save_dir=str(tmp_path / "sessions"),
        ),
        emit,
    )

    assert result.state == "succeeded"
    assert result.model == "canned"
    assert result.upstream_model == "deepseek-flash"
    assert result.usage.total_tokens == 4
    assert result.session_ref is not None and result.session_ref.conversation_id
    assert any(
        event["type"] == "adapter.text" and "pong" in event.get("text", "") for event in events
    )
    assert any(event["type"] == "adapter.session_started" for event in events)
    records = {record.name: record.status for record in result.check_records}
    assert records["auth_proxy_stopped"] == "passed"
    assert records["model_identity"] == "passed"

    serialized = json.dumps(result.to_dict()) + json.dumps(events)
    assert _FAKE_SECRET not in serialized
    assert executor.model_calls_made >= 1


async def test_executor_confirms_cancel_mid_stream(
    store: FileStore, tmp_path: Path, gated_canned_upstream: tuple[str, _StreamGate]
) -> None:
    upstream, gate = gated_canned_upstream
    executor, workspace = _prepare(store, tmp_path, upstream)
    events: list[dict[str, Any]] = []
    execution_id: dict[str, str] = {}

    async def emit(event: dict[str, Any]) -> None:
        events.append(event)
        ref = event.get("execution") or {}
        if event.get("type") == "adapter.execution_started" and isinstance(
            ref.get("execution_id"), str
        ):
            execution_id["value"] = ref["execution_id"]

    request = ExecuteRequest(
        task_id="task_cancel",
        run_id="run_cancel",
        subtask_id="sub_cancel",
        agent_ref="developer",
        workspace_path=str(workspace),
        objective="Stream a long answer.",
        timeout_seconds=60,
    )
    task = asyncio.create_task(executor.execute(request, emit))
    deadline = time.monotonic() + 10
    while "value" not in execution_id and time.monotonic() < deadline:
        await asyncio.sleep(0.02)

    # Deterministic mid-stream barrier: the upstream has written a partial SSE
    # frame and is holding the connection open, so the turn cannot complete
    # before we cancel.  No timing sleep or text-buffering race is involved.
    assert await asyncio.to_thread(gate.opened.wait, 10), "upstream never streamed"
    assert not any(
        event.get("type") == "adapter.execution_finished" for event in events
    ), "execution completed before the mid-stream cancel"

    cancel_result = await executor.cancel(ExecutionRef(execution_id=execution_id["value"]))
    gate.release.set()
    result = await asyncio.wait_for(task, timeout=10)

    assert cancel_result.confirmed is True
    assert cancel_result.state == "cancelled"
    assert result.state == "cancelled"
    assert result.stop_confirmed is True
    assert result.failure is not None and result.failure.code == "cancelled"
    records = {record.name: record.status for record in result.check_records}
    assert records["auth_proxy_stopped"] == "passed"
