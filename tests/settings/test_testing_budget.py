"""Budget regression with real product proxies and a loopback provider double.

No SDK/vendor/model calls; all credentials and data are temporary test values.
"""

from __future__ import annotations

import http.server
import json
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from lightgravity.adapter.credentials import Secret
from lightgravity.adapter.generation_ledger import PersistentGenerationLedger
from lightgravity.adapter.proxy import GenerationCounter, LocalAuthProxy
from lightgravity.settings import ConnectionService, ConnectionTester
from lightgravity.settings.testing import LAYER_RUNTIME_NETWORK, default_http_post


@pytest.fixture
def local_provider() -> Iterator[tuple[str, list[tuple[str, str]]]]:
    received: list[tuple[str, str]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append((body['model'], self.headers.get('Authorization', '')))
            payload = json.dumps({'choices': [{'message': {'content': 'probe'}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize('concurrent', [False, True])
@pytest.mark.parametrize('global_limit', [None, 1])
def test_invocations_keep_local_bounds_credentials_and_persistent_global_budget(
    service: ConnectionService,
    tmp_path: Path,
    local_provider: tuple[str, list[tuple[str, str]]],
    concurrent: bool,
    global_limit: int | None,
) -> None:
    upstream, received = local_provider
    for connection_id in ('alpha', 'beta'):
        service.create_connection(
            connection_id,
            model=connection_id,
            base_url=upstream,
            credential_ref=f'{connection_id}-ref',
            credential_value=f'fake-{connection_id}',
            actor='test',
            request_id=f'req-{connection_id}',
        )
    ledger = PersistentGenerationLedger(tmp_path / 'generation', limit=global_limit)
    counter = GenerationCounter(global_limit, ledger=ledger)
    proxies: list[LocalAuthProxy] = []
    rejected: list[int] = []
    first_entered = threading.Event()
    rendezvous = threading.Barrier(2)

    def factory(credential: Secret, url: str, max_calls: int) -> LocalAuthProxy:
        assert max_calls == 1
        proxy = LocalAuthProxy(
            credential=credential, upstream_url=url, max_calls=max_calls,
            allow_loopback_upstream=True, generation_budget=counter,
        )
        proxies.append(proxy)
        return proxy

    def post(url: str, body: bytes, timeout: float) -> tuple[int, dict[str, Any]]:
        # Enter only after the tester has incremented its cumulative diagnostic.
        # Start beta here so the old lifetime gate deterministically skips it.
        first_entered.set()
        if concurrent:
            rendezvous.wait(5)
        result = default_http_post(url, body, timeout)
        # Probe the same real proxy again: its one-request bound still applies.
        rejected.append(default_http_post(url, body, timeout)[0])
        return result

    tester = ConnectionTester(
        service, allow_network=True, max_network_calls=1,
        proxy_factory=factory, http_post=post, http_timeout=5,
    )
    if concurrent:
        with ThreadPoolExecutor(max_workers=2) as executor:
            alpha = executor.submit(tester.test, 'alpha')
            assert first_entered.wait(5)
            beta = executor.submit(tester.test, 'beta')
            results = [alpha.result(timeout=15), beta.result(timeout=15)]
    else:
        results = [tester.test('alpha'), tester.test('beta')]

    statuses = [result.layer(LAYER_RUNTIME_NETWORK).status for result in results]
    assert statuses.count('passed') == (2 if global_limit is None else 1)
    assert statuses.count('failed') == (0 if global_limit is None else 1)
    assert tester.network_calls == 2
    assert len(proxies) == 2 and all(not proxy.is_running for proxy in proxies)
    assert len({proxy.base_url for proxy in proxies}) == 2
    assert rejected == [429, 429]
    assert len(received) == (2 if global_limit is None else 1)
    assert all(authorization == f'Bearer fake-{model}' for model, authorization in received)
    # A new ledger reader sees the reservations; no reset or bypass per Test.
    assert PersistentGenerationLedger(tmp_path / 'generation', limit=global_limit).count() == len(received)
