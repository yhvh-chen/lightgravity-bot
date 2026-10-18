"""Loopback auth proxy: isolation, credential injection and stop confirmation."""

from __future__ import annotations

import http.server
import json
import threading
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from lightgravity.adapter import (
    CapabilityUnavailable,
    DEEPSEEK_UPSTREAM_URL,
    LocalAuthProxy,
    Secret,
    upstream_chat_completions,
)
from lightgravity.adapter.provider_matrix import execution_eligible

_FAKE_SECRET = "sk-live-proxy-test-secret-999"


class _UpstreamHandler(http.server.BaseHTTPRequestHandler):
    recorded: list[dict[str, Any]] = []
    delay: float = 0.0

    def log_message(self, *args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        type(self).recorded.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body.decode("utf-8", "replace"),
            }
        )
        if type(self).delay:
            threading.Event().wait(type(self).delay)
        payload = (
            'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
            '"model":"deepseek-flash","choices":[{"index":0,'
            '"delta":{"role":"assistant","content":"pong"},"finish_reason":null}]}\n\n'
            'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
            '"model":"deepseek-flash","choices":[{"index":0,"delta":{},'
            '"finish_reason":"stop"}],"usage":{"prompt_tokens":3,'
            '"completion_tokens":1,"total_tokens":4}}\n\n'
            "data: [DONE]\n\n"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True


@pytest.fixture
def upstream() -> Iterator[str]:
    _UpstreamHandler.recorded = []
    _UpstreamHandler.delay = 0.0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
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


def _make_proxy(upstream: str, *, max_calls: int = 8) -> LocalAuthProxy:
    proxy = LocalAuthProxy(
        credential=Secret(_FAKE_SECRET),
        upstream_url=upstream_chat_completions(upstream),
        max_calls=max_calls,
        allow_loopback_upstream=True,
        timeout=10.0,
    )
    proxy.start()
    return proxy


def test_proxy_binds_loopback_ephemeral_and_injects_bearer(upstream: str) -> None:
    proxy = _make_proxy(upstream)
    try:
        assert proxy.is_running is True
        assert proxy.base_url.startswith("http://127.0.0.1:")
        assert proxy.base_url.endswith(f"/{proxy.session_token}/v1")
        response = httpx.post(
            f"{proxy.base_url}/chat/completions",
            json={"model": "canned", "stream": True, "messages": []},
            timeout=10.0,
        )
        assert response.status_code == 200
        assert "pong" in response.text
        assert _UpstreamHandler.recorded[-1]["authorization"] == f"Bearer {_FAKE_SECRET}"
        assert proxy.call_count == 1
        assert proxy.upstream_model == "deepseek-flash"

        records = proxy.call_records()
        assert records[0]["model"] == "canned"
        assert "authorization" not in json.dumps(records).lower()
        assert _FAKE_SECRET not in json.dumps(records)
        # The proxy repr must never expose the secret.
        assert _FAKE_SECRET not in repr(proxy)
    finally:
        assert proxy.stop() is True
    assert proxy.is_running is False
    assert proxy.stop() is True  # idempotent


def test_proxy_rejects_unknown_session_token(upstream: str) -> None:
    proxy = _make_proxy(upstream)
    try:
        port = proxy.port
        assert port is not None
        response = httpx.post(
            f"http://127.0.0.1:{port}/wrong-token/v1/chat/completions",
            json={"messages": []},
            timeout=10.0,
        )
        assert response.status_code == 404
        assert _UpstreamHandler.recorded == []
    finally:
        proxy.stop()


def test_proxy_enforces_call_cap(upstream: str) -> None:
    proxy = _make_proxy(upstream, max_calls=1)
    try:
        first = httpx.post(
            f"{proxy.base_url}/chat/completions", json={"messages": []}, timeout=10.0
        )
        second = httpx.post(
            f"{proxy.base_url}/chat/completions", json={"messages": []}, timeout=10.0
        )
        assert first.status_code == 200
        assert second.status_code == 429
        assert proxy.call_count == 1
    finally:
        proxy.stop()


def test_proxy_accepts_any_absolute_upstream_but_not_a_relative_one() -> None:
    # LG-230: no host allowlist; the admin-configured endpoint is used as given.
    LocalAuthProxy(
        credential=Secret(_FAKE_SECRET),
        upstream_url="https://custom.example.com/v1/chat/completions",
    )
    with pytest.raises(CapabilityUnavailable):
        LocalAuthProxy(credential=Secret(_FAKE_SECRET), upstream_url="/v1/chat/completions")


def test_proxy_accepts_google_openai_compat_upstream() -> None:
    # LG-229: the online demo forwards to Google's OpenAI-compatible endpoint.
    url = upstream_chat_completions("https://generativelanguage.googleapis.com/v1beta/openai")
    assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    LocalAuthProxy(credential=Secret(_FAKE_SECRET), upstream_url=url)
    assert execution_eligible(
        backend="openai-compat",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )


def test_proxy_refuses_non_loopback_bind() -> None:
    with pytest.raises(CapabilityUnavailable):
        LocalAuthProxy(
            credential=Secret(_FAKE_SECRET),
            upstream_url=DEEPSEEK_UPSTREAM_URL,
            host="0.0.0.0",
        )


def test_upstream_url_derivation() -> None:
    assert upstream_chat_completions("https://api.deepseek.com/v1") == DEEPSEEK_UPSTREAM_URL
    assert upstream_chat_completions(DEEPSEEK_UPSTREAM_URL) == DEEPSEEK_UPSTREAM_URL


def test_base_url_before_start_is_capability_error() -> None:
    proxy = LocalAuthProxy(credential=Secret(_FAKE_SECRET), upstream_url=DEEPSEEK_UPSTREAM_URL)
    with pytest.raises(CapabilityUnavailable):
        _ = proxy.base_url
