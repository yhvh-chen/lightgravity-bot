"""LG-027 error-branch QA: real Settings components against a controlled local upstream.

These are *real* product components (`FileStore`, `FileSecretStore`,
`ConnectionService`, `ConnectionTester`, `LocalAuthProxy`) driven over real
loopback HTTP.  The upstream is a controlled local HTTP server (not a monkeypatched
function), so the failure modes are produced by genuine HTTP responses:

* wrong credential  -> upstream ``401``;
* nonexistent model  -> upstream ``404``;
* slow upstream      -> upstream timeout (``runtime_network=failed``);
* revision conflict  -> real ``FileStore`` optimistic-concurrency rejection;
* credential rotation-> previous test result / run pin reported ``stale``;
* disabled referenced connection -> default cannot dangle.

They are local-only on purpose: the task allows local/no-network verification for
error branches and caps real DeepSeek calls.  No secret value is printed.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from lightgravity.adapter.credentials import Secret
from lightgravity.contracts import AppError
from lightgravity.settings import (
    ConnectionService,
    ConnectionTester,
    FileSecretStore,
)
from lightgravity.store import FileStore, RevisionConflict

FAKE_KEY = "lg027-local-upstream-secret"
CONN = "lg027-local-conn"
REF = "lg027-local-ref"
MODEL = "deepseek-v4-flash"


class _Handler(BaseHTTPRequestHandler):
    mode = "ok"
    hits = 0

    def log_message(self, *args: Any) -> None:  # keep the test output clean
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        type(self).hits += 1
        if type(self).mode == "auth_error":
            body = json.dumps({"error": {"message": "Authentication Fails, bad key"}}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if type(self).mode == "model_missing":
            body = json.dumps({"error": {"message": "Model Not Exist"}}).encode()
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if type(self).mode == "slow":
            time.sleep(2.0)
        body = json.dumps(
            {
                "id": "chatcmpl-test",
                "model": MODEL,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}}],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def upstream() -> Any:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Handler.mode = "ok"
    _Handler.hits = 0
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", server
    finally:
        server.shutdown()
        server.server_close()


def _service(tmp_path: Path) -> ConnectionService:
    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    secrets = FileSecretStore(tmp_path / "secrets")
    return ConnectionService(store, secret_store=secrets)


def _tester(service: ConnectionService, tmp_path: Path, **kwargs: Any) -> ConnectionTester:
    defaults: dict[str, Any] = dict(
        allow_network=True,
        allow_loopback_upstream=True,
        max_network_calls=1,
        http_timeout=0.6,
        upstream_timeout=1.0,
    )
    defaults.update(kwargs)
    return ConnectionTester(service, **defaults)


def _create(service: ConnectionService, base_url: str) -> None:
    service.create_connection(
        CONN,
        backend="openai-compat",
        model=MODEL,
        base_url=base_url,
        credential_ref=REF,
        credential_value=FAKE_KEY,
        actor="lg027-qa",
        request_id="lg027-create",
    )


def test_wrong_credential_reports_upstream_401(tmp_path: Path, upstream: Any) -> None:
    base_url, _ = upstream
    service = _service(tmp_path)
    _create(service, base_url)
    _Handler.mode = "auth_error"

    result = _tester(service, tmp_path).test(CONN)
    network = next(layer for layer in result.layers if layer.name == "runtime_network")
    assert network.status == "failed"
    assert "401" in network.detail
    assert result.overall == "failed"
    assert FAKE_KEY not in json.dumps(result.to_dict())


def test_nonexistent_model_reports_upstream_404(tmp_path: Path, upstream: Any) -> None:
    base_url, _ = upstream
    service = _service(tmp_path)
    _create(service, base_url)
    _Handler.mode = "model_missing"

    result = _tester(service, tmp_path).test(CONN)
    network = next(layer for layer in result.layers if layer.name == "runtime_network")
    assert network.status == "failed"
    assert "404" in network.detail


def test_timeout_reports_network_failure_without_hanging(tmp_path: Path, upstream: Any) -> None:
    base_url, _ = upstream
    service = _service(tmp_path)
    _create(service, base_url)
    _Handler.mode = "slow"

    started = time.monotonic()
    result = _tester(service, tmp_path, http_timeout=0.4).test(CONN)
    elapsed = time.monotonic() - started
    network = next(layer for layer in result.layers if layer.name == "runtime_network")
    assert network.status == "failed"
    assert elapsed < 1.8, elapsed  # bounded, no infinite retry
    assert "timeout" in network.detail.lower() or "timed out" in network.detail.lower()


def test_revision_conflict_on_update(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _create(service, "http://127.0.0.1:9/v1")
    with pytest.raises(RevisionConflict):
        service.update_connection(
            CONN,
            expected_revision=99,
            actor="lg027-qa",
            title="stale edit",
        )


def test_revision_conflict_on_setting_test(tmp_path: Path, upstream: Any) -> None:
    base_url, _ = upstream
    service = _service(tmp_path)
    _create(service, base_url)
    with pytest.raises(RevisionConflict):
        _tester(service, tmp_path).test(CONN, expected_revision=42)


def test_credential_rotation_marks_previous_test_stale(tmp_path: Path, upstream: Any) -> None:
    base_url, _ = upstream
    service = _service(tmp_path)
    _create(service, base_url)
    tester = _tester(service, tmp_path)
    result = tester.test(CONN)
    assert result.overall == "verified"

    # The connection revision and credential version are the staleness basis.
    before = service.get_connection(CONN)
    service.set_credential(REF, "lg027-rotated-secret")
    after = service.get_connection(CONN)

    assert result.connection_revision == before["revision"]
    stale = result.is_stale(
        after["revision"], after["credential"]["version"]
    )
    assert stale is True


def test_disabled_default_requires_clearing_reference(
    tmp_path: Path, upstream: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_url, _ = upstream
    service = _service(tmp_path)
    _create(service, base_url)
    service.update_settings(
        expected_revision=None,
        actor="lg027-qa",
        default_worker_connection_ref=CONN,
    )

    with pytest.raises(AppError) as excinfo:
        service.update_connection(
            CONN,
            expected_revision=service.get_connection(CONN)["revision"],
            actor="lg027-qa",
            enabled=False,
        )
    assert "default" in str(excinfo.value).lower()

    # Explicitly clearing the default in the same call is allowed and atomic.
    updated = service.update_connection(
        CONN,
        expected_revision=service.get_connection(CONN)["revision"],
        actor="lg027-qa",
        enabled=False,
        clear_defaults=True,
    )
    assert updated["enabled"] is False
    assert service.get_settings()["default_worker_connection_ref"] is None


def test_partial_write_failure_rolls_back_credential(tmp_path: Path) -> None:
    """A connection write failure must not silently leave an orphan secret."""

    service = _service(tmp_path)
    _create(service, "http://127.0.0.1:9/v1")

    class FailingStore:
        def __init__(self, inner: FileStore) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

        def write(self, *args: Any, **kwargs: Any) -> Any:
            raise AppError("internal_error", "injected connection write failure")

    failing = ConnectionService(
        FailingStore(service.repository._store),  # type: ignore[attr-defined]
        secret_store=service.secret_store,
    )
    with pytest.raises(AppError):
        failing.update_connection(
            CONN,
            expected_revision=service.get_connection(CONN)["revision"],
            actor="lg027-qa",
            credential_action="set",
            credential_value="lg027-orphan-candidate",
        )
    # The compensating rollback removed the secret written before the failure.
    assert service.secret_store.get(REF) is None or (
        service.secret_store.get(REF).reveal() != "lg027-orphan-candidate"  # type: ignore[attr-defined]
    )
