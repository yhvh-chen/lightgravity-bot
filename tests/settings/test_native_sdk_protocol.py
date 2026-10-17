"""Real installed SDK against a controlled loopback fake Gemini/Vertex protocol.

This proves SDK config/auth construction and the minimal no-tools request path.
It is explicitly *not* a real-vendor verification: no external host is contacted
and only the loopback test injection is used.
"""

from __future__ import annotations

import http.server
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import pytest

from lightgravity.adapter.proxy import configure_generation_ledger
from lightgravity.settings import ConnectionService, ConnectionTester, DraftConnectionSpec

_SSE = (
    b'data: {"candidates":[{"content":{"parts":[{"text":"pong"}],"role":"model"},'
    b'"finishReason":"STOP"}]}\n\n'
)


@dataclass
class _Seen:
    paths: list[str] = field(default_factory=list)
    api_keys: list[str | None] = field(default_factory=list)
    bodies: list[bytes] = field(default_factory=list)

    def reset(self) -> None:
        self.paths.clear()
        self.api_keys.clear()
        self.bodies.clear()


class _FakeGemini(http.server.BaseHTTPRequestHandler):
    seen: _Seen

    def log_message(self, *args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        self.seen.paths.append(self.path)
        self.seen.api_keys.append(
            self.headers.get("x-goog-api-key") or self.headers.get("Authorization")
        )
        self.seen.bodies.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(_SSE)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(_SSE)
        self.close_connection = True


@pytest.fixture
def fake_gemini() -> Iterator[tuple[str, _Seen]]:
    seen = _Seen()
    handler = type("_Handler", (_FakeGemini,), {"seen": seen})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize(
    ("spec", "secret", "expected_path_fragment", "expected_key"),
    [
        (
            DraftConnectionSpec(
                backend="gemini",
                model="gemini-3.8-flash",
                auth_mode="api_key",
            ),
            "sk-dummy-gemini",
            "/v1beta/models/gemini-3.8-flash:streamGenerateContent",
            "sk-dummy-gemini",
        ),
        (
            DraftConnectionSpec(
                backend="vertex",
                model="gemini-3.8-flash",
                auth_mode="api_key",
            ),
            "sk-dummy-vertex",
            "/v1beta1/publishers/google/models/gemini-3.8-flash:streamGenerateContent",
            "sk-dummy-vertex",
        ),
        (
            DraftConnectionSpec(
                backend="vertex",
                model="gemini-3.8-flash",
                auth_mode="adc",
                project="demo-project",
                location="us-central1",
            ),
            None,
            "/v1beta1/projects/demo-project/locations/us-central1/publishers/google/models/",
            None,
        ),
    ],
)
def test_installed_sdk_reaches_controlled_loopback_protocol(
    service: ConnectionService,
    data_dir: Path,
    fake_gemini: tuple[str, _Seen],
    spec: DraftConnectionSpec,
    secret: str | None,
    expected_path_fragment: str,
    expected_key: str | None,
) -> None:
    configure_generation_ledger(data_dir, limit=None)
    endpoint, seen = fake_gemini
    tester = ConnectionTester(
        service,
        allow_network=True,
        allow_loopback_native=True,
        native_base_url=endpoint,
        native_timeout=30,
        adc_available=True,
    )
    result = tester.test_draft(spec, credential_value=secret, allow_network=True)
    network = result.layer("runtime_network")
    assert network is not None and network.status == "passed", network
    assert "stop_confirmed=True" in network.detail
    assert "tools=none" in network.detail
    assert "retries=0" in network.detail
    assert result.overall == "verified"
    assert len(seen.paths) == 1
    assert expected_path_fragment in seen.paths[0]
    assert seen.api_keys[0] == expected_key
    assert b'"tools"' not in seen.bodies[0]
    assert b'"functionCallingConfig":{"mode":"NONE"}' in seen.bodies[0]
    rendered = json.dumps(result.to_dict())
    if secret:
        assert secret not in rendered
    assert service.list_connections() == []
    assert service.secret_store.list_refs() == []
