"""LG-022 R1: process-global generation-request counter tests (no network)."""

from __future__ import annotations

import threading

from lightgravity.adapter.proxy import GenerationCounter


def test_counter_counts_and_enforces_global_limit() -> None:
    counter = GenerationCounter(limit=3)
    assert [counter.reserve() for _ in range(4)] == [True, True, True, False]
    assert counter.count == 3
    # LG-022 R2: snapshot carries an additive ``persistent`` flag; an in-memory
    # counter is honestly non-persistent.
    assert counter.snapshot() == {
        "count": 3,
        "limit": 3,
        "remaining": 0,
        "persistent": False,
    }


def test_counter_none_limit_counts_without_capping() -> None:
    counter = GenerationCounter(limit=None)
    for _ in range(10):
        assert counter.reserve() is True
    assert counter.snapshot()["remaining"] is None
    assert counter.count == 10


def test_counter_thread_safe_under_concurrency() -> None:
    counter = GenerationCounter(limit=50)
    granted: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(10):
            ok = counter.reserve()
            with lock:
                granted.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(1 for value in granted if value) == 50
    assert counter.count == 50


def test_global_counter_is_shared_by_default() -> None:
    from lightgravity.adapter.proxy import global_generation_counter

    assert global_generation_counter() is global_generation_counter()


# ---------------------------------------------------------------------------
# LG-031 R2: the executor must plumb one *shared* counter into every worker
# proxy, so a real hard cap cannot reset between workers/sessions.  These tests
# are fully offline (a local canned upstream; no real model, no credential).
# ---------------------------------------------------------------------------


def test_executor_reuses_injected_shared_generation_counter() -> None:
    """Two executors given the same counter pass it to their proxies."""

    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.executor import AntigravityExecutor
    from lightgravity.adapter.proxy import LocalAuthProxy
    from lightgravity.store import FileStore
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    store = FileStore(tmp / "data", tmp / "data" / "workspaces")
    counter = GenerationCounter(limit=2)
    executors = [
        AntigravityExecutor(
            store,
            workspace_root=tmp / "ws",
            generation_budget=counter,
            allow_loopback_upstream=True,
        )
        for _ in range(2)
    ]
    observed = []
    for executor in executors:
        proxy = executor._make_proxy(  # noqa: SLF001 - explicit wiring seam
            Secret("sk-not-real"),
            "http://127.0.0.1:9/v1/chat/completions",
            8,
        )
        assert isinstance(proxy, LocalAuthProxy)
        observed.append(proxy._state.generator_budget)  # noqa: SLF001
    # Both proxies consume one and the same counter object.
    assert observed[0] is counter and observed[1] is counter
    # The cap is genuinely shared: two reservations leave nothing for a third.
    assert counter.reserve() is True
    assert counter.reserve() is True
    assert counter.reserve() is False
    assert counter.count == 2


def test_executor_without_injection_still_uses_global_counter() -> None:
    """Default (no explicit budget) keeps the process-global counter."""

    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.executor import AntigravityExecutor
    from lightgravity.adapter.proxy import global_generation_counter
    from lightgravity.store import FileStore
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    store = FileStore(tmp / "data", tmp / "data" / "workspaces")
    executor = AntigravityExecutor(
        store, workspace_root=tmp / "ws", allow_loopback_upstream=True
    )
    proxy = executor._make_proxy(  # noqa: SLF001 - explicit wiring seam
        Secret("sk-not-real"),
        "http://127.0.0.1:9/v1/chat/completions",
        8,
    )
    assert proxy._state.generator_budget is global_generation_counter()  # noqa: SLF001


def test_shared_counter_blocks_second_worker_forward() -> None:
    """A limit of 1 shared by two proxies forwards exactly one real request."""

    import http.server
    import json as _json
    import threading
    import urllib.request

    from lightgravity.adapter.proxy import LocalAuthProxy
    from lightgravity.adapter.credentials import Secret

    forwarded: list[int] = []

    class _Upstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # noqa: D102
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            forwarded.append(1)
            payload = _json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    upstream = f"http://{host}:{port}/v1/chat/completions"
    counter = GenerationCounter(limit=1)
    proxies = [
        LocalAuthProxy(
            credential=Secret("sk-not-real"),
            upstream_url=upstream,
            max_calls=8,
            allow_loopback_upstream=True,
            timeout=10.0,
            generation_budget=counter,
        )
        for _ in range(2)
    ]

    def call(proxy: LocalAuthProxy) -> int:
        request = urllib.request.Request(
            f"{proxy.base_url}/chat/completions",
            data=_json.dumps({"model": "canned", "messages": []}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:  # noqa: PERF203
            return int(exc.code)

    try:
        for proxy in proxies:
            proxy.start()
        assert call(proxies[0]) == 200
        assert call(proxies[1]) == 429  # shared cap already consumed
        assert counter.count == 1
        assert forwarded == [1]
    finally:
        for proxy in proxies:
            proxy.stop()
        server.shutdown()
        server.server_close()
        thread.join(5)
