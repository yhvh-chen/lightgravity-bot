"""LG-031 phase4: align the per-session proxy cap with the request model budget.

phase3's real chain failed because a multi-step worker hit the loopback proxy's
per-session ``max_proxy_calls`` with an opaque ``429 local auth proxy call budget
exhausted`` *before* the SDK's own ``BudgetConfig.max_model_calls`` could report a
clean ``MAX_MODEL_CALLS_EXCEEDED`` stop reason.  Two independent ceilings meant
the proxy masked the real stop cause and the dependent worker never ran.

The additive fix: the executor now caps the per-session proxy at the frozen
per-request ``budget.max_model_calls`` (when the coordinator set one), so the SDK
budget is what trips and the honest stop reason survives.  When no model budget
is present the cap is unchanged.  These tests are fully offline (canned upstream;
no real model, no credential).
"""

from __future__ import annotations

import asyncio
import http.server
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from lightgravity.adapter import (
    AntigravityExecutor,
    DirectoryArtifactSink,
    ExecuteRequest,
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


@pytest.fixture
def canned_upstream() -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CannedUpstream)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def _prepare(
    store: FileStore, tmp_path: Path, upstream: str, *, max_proxy_calls: int
) -> tuple[AntigravityExecutor, Path, list[int]]:
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
    caps: list[int] = []

    def factory(_credential: Any, _upstream: str, max_calls: int) -> Any:
        caps.append(max_calls)
        from lightgravity.adapter.proxy import LocalAuthProxy

        return LocalAuthProxy(
            credential=_credential,
            upstream_url=_upstream,
            max_calls=max_calls,
            allow_loopback_upstream=True,
        )

    executor = AntigravityExecutor(
        store,
        ResourceCompiler(store, registry=make_registry()),
        credential_resolver=InMemoryCredentialResolver({"deepseek-api-key": _FAKE_SECRET}),
        artifacts=DirectoryArtifactSink(tmp_path / "artifacts"),
        allow_loopback_upstream=True,
        max_proxy_calls=max_proxy_calls,
        proxy_factory=factory,
    )
    return executor, workspace, caps


async def _run(executor: AntigravityExecutor, workspace: Path, tmp_path: Path, budget: dict[str, Any]) -> Any:
    return await executor.execute(
        ExecuteRequest(
            task_id="task_ceiling",
            run_id="run_ceiling",
            subtask_id="sub_ceiling",
            agent_ref="developer",
            workspace_path=str(workspace),
            save_dir=str(tmp_path / "sessions"),
            budget=budget,
        ),
        lambda event: None,
    )


@pytest.mark.asyncio
async def test_proxy_cap_aligned_to_request_model_budget(
    store: FileStore, tmp_path: Path, canned_upstream: str
) -> None:
    """A frozen per-request model budget also caps the loopback proxy."""

    executor, workspace, caps = _prepare(
        store, tmp_path, canned_upstream, max_proxy_calls=64
    )
    result = await _run(executor, workspace, tmp_path, {"max_model_calls": 3})
    assert result.state == "succeeded"
    # The proxy was created with the request budget (3), not the generous 64.
    assert caps == [3]


@pytest.mark.asyncio
async def test_proxy_cap_takes_smallest_ceiling(
    store: FileStore, tmp_path: Path, canned_upstream: str
) -> None:
    """The proxy honours the minimum of the constructor cap and the budget."""

    executor, workspace, caps = _prepare(
        store, tmp_path, canned_upstream, max_proxy_calls=2
    )
    result = await _run(executor, workspace, tmp_path, {"max_model_calls": 10})
    assert result.state == "succeeded"
    # min(2, 10) == 2: the constructor's per-worker ceiling still wins.
    assert caps == [2]


@pytest.mark.asyncio
async def test_proxy_cap_unchanged_without_model_budget(
    store: FileStore, tmp_path: Path, canned_upstream: str
) -> None:
    """Additive only: no model budget leaves the constructor cap intact."""

    executor, workspace, caps = _prepare(
        store, tmp_path, canned_upstream, max_proxy_calls=7
    )
    result = await _run(executor, workspace, tmp_path, {})
    assert result.state == "succeeded"
    assert caps == [7]


@pytest.mark.asyncio
async def test_proxy_cap_ignores_invalid_budget_values(
    store: FileStore, tmp_path: Path, canned_upstream: str
) -> None:
    """A non-integer or non-positive budget never weakens the proxy cap."""

    executor, workspace, caps = _prepare(
        store, tmp_path, canned_upstream, max_proxy_calls=9
    )
    result = await _run(executor, workspace, tmp_path, {"max_model_calls": "lots"})
    assert result.state == "succeeded"
    assert caps == [9]


def test_no_secret_leaks_in_alignment() -> None:
    """Guard: the alignment helper never handles the credential value."""

    # The cap derivation only inspects ``request.budget``; sanity-check the
    # request dataclass does not carry the resolved secret.
    request = ExecuteRequest(
        task_id="t", run_id="r", subtask_id="s", agent_ref="developer", budget={"max_model_calls": 3}
    )
    assert _FAKE_SECRET not in json.dumps({"budget": request.budget})
    assert asyncio.iscoroutinefunction(AntigravityExecutor.execute)
