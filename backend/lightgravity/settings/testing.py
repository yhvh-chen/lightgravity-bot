"""Layered connection testing (docs/07 §5, docs/08 §8.1).

The layers are deliberately separated and never merged into one boolean:

* ``config_parse``   - static: the Connection frontmatter parses and its backend
  is registered/verified (no network).
* ``credential``     - static: the ``credential_ref`` resolves, and *where* from;
  never the value.
* ``capability``     - the SDK capability *declaration* (``adapter_capabilities``),
  reported as ``declared`` and never as a runtime pass.
* ``runtime_network``- real: a minimal OpenAI-compatible request through the
  product ``LocalAuthProxy`` (LG-006), which injects the credential in memory.
* ``tool_probe`` / ``structured_output`` - separate optional probes, reported
  ``skipped`` unless explicitly requested.

A result is bound to ``connection_revision`` + ``credential_version``; when a
connection or credential is updated the older result is detected as *stale*
(:meth:`ConnectionTestResult.is_stale`) rather than silently presented as valid.
Results are persisted as independent diagnostic records; they are never written
back into the Connection/SETTINGS authority files.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from lightgravity.adapter.capabilities import adapter_capabilities
from lightgravity.adapter.credentials import Secret
from lightgravity.adapter.proxy import LocalAuthProxy, upstream_chat_completions
from lightgravity.contracts import AppError
from lightgravity.store import RevisionConflict

from .errors import SettingsConfigInvalid
from .models import (
    DEFAULT_EXECUTABLE_BACKEND,
    Connection,
    ConnectionTestResult,
    TestLayerResult,
)
from .service import ConnectionService

#: Signature: (url, body, timeout) -> (http_status, parsed_json_or_empty).
HttpPost = Callable[[str, bytes, float], "tuple[int, dict[str, Any]]"]
#: Signature: (credential, upstream_url, max_calls) -> LocalAuthProxy.
ProxyFactory = Callable[[Secret, str, int], LocalAuthProxy]

LAYER_CONFIG_PARSE = "config_parse"
LAYER_CREDENTIAL = "credential"
LAYER_CAPABILITY = "capability"
LAYER_RUNTIME_NETWORK = "runtime_network"
LAYER_TOOL_PROBE = "tool_probe"
LAYER_STRUCTURED_OUTPUT = "structured_output"

CAPABILITY_NOTE = (
    "declared from the pinned SDK capability snapshot; a network success does not "
    "verify SDK tool/structured-output support"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_or_empty(raw: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def default_http_post(url: str, body: bytes, timeout: float) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _json_or_empty(response.read())
    except urllib.error.HTTPError as exc:
        _ = exc.read(8192)  # drain; never surface the upstream body
        return exc.code, {}


class ConnectionTestLog:
    """Persist layered test records as independent JSON diagnostics."""

    def __init__(self, directory: Path | str) -> None:
        self._dir = Path(directory)

    def record(self, result: ConnectionTestResult) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{result.test_id}.json"
        tmp = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
        payload = json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        return str(path)

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def history(self, connection_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if not self._dir.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(self._dir.glob("*.json")):
            data = self._read(path)
            if data and data.get("connection_id") == connection_id:
                rows.append(data)
        rows.sort(key=lambda item: str(item.get("finished_at", "")), reverse=True)
        return rows[:limit]

    def latest(self, connection_id: str) -> dict[str, Any] | None:
        rows = self.history(connection_id, limit=1)
        return rows[0] if rows else None


@dataclass(frozen=True, slots=True)
class _LayerOutcome:
    layer: TestLayerResult
    stop: bool = False


class ConnectionTester:
    """Run layered connection tests, reusing the LG-006 product proxy."""

    def __init__(
        self,
        service: ConnectionService,
        *,
        diagnostics: ConnectionTestLog | None = None,
        allow_network: bool = False,
        http_post: HttpPost | None = None,
        proxy_factory: ProxyFactory | None = None,
        http_timeout: float = 30.0,
        upstream_timeout: float = 60.0,
        allow_loopback_upstream: bool = False,
        max_network_calls: int = 1,
    ) -> None:
        self._service = service
        self._diagnostics = diagnostics
        self._allow_network = allow_network
        self._http_post = http_post or default_http_post
        self._proxy_factory = proxy_factory
        self._http_timeout = http_timeout
        self._upstream_timeout = upstream_timeout
        self._allow_loopback_upstream = allow_loopback_upstream
        self._max_network_calls = max_network_calls
        self._network_calls = 0
        self._network_calls_lock = Lock()

    @property
    def network_calls(self) -> int:
        """Cumulative attempted requests for diagnostics, not a shared budget."""
        with self._network_calls_lock:
            return self._network_calls

    def test(
        self,
        connection_id: str,
        *,
        expected_revision: int | None = None,
        allow_network: bool | None = None,
        probe_tools: bool = False,
        probe_structured: bool = False,
    ) -> ConnectionTestResult:
        started = _now_iso()
        test_id = f"ctest_{uuid.uuid4().hex[:16]}"
        network_allowed = self._allow_network if allow_network is None else allow_network

        connection = self._service.repository.read_connection(connection_id)
        if expected_revision is not None and connection.revision != expected_revision:
            raise RevisionConflict(
                "connection",
                connection_id,
                expected=expected_revision,
                actual=connection.revision,
            )

        layers: list[TestLayerResult] = []
        layers.append(self._config_layer(connection))
        credential = self._credential_layer(connection)
        layers.append(credential.layer)
        layers.append(self._capability_layer())
        network = self._network_layer(connection, network_allowed)
        layers.append(network.layer)
        layers.append(self._gated_layer(LAYER_TOOL_PROBE, probe_tools, network_allowed))
        layers.append(
            self._gated_layer(LAYER_STRUCTURED_OUTPUT, probe_structured, network_allowed)
        )

        credential_status = self._service.credential_status(connection.credential_ref)
        result = ConnectionTestResult(
            test_id=test_id,
            connection_id=connection.id,
            connection_revision=connection.revision,
            credential_ref=connection.credential_ref,
            credential_version=credential_status.version,
            backend=connection.backend,
            model=connection.model,
            base_url_host=_host(connection.base_url),
            started_at=started,
            finished_at=_now_iso(),
            layers=tuple(layers),
            overall=_overall(layers),
            note="static config, real network/model and SDK capability declaration are separate layers",
        )
        if self._diagnostics is not None:
            self._diagnostics.record(result)
        return result

    # ------------------------------------------------------------------ layers
    def _config_layer(self, connection: Connection) -> TestLayerResult:
        try:
            self._service.repository.validate_backend(
                connection.backend, model=connection.model, base_url=connection.base_url
            )
        except SettingsConfigInvalid as exc:
            return TestLayerResult(
                name=LAYER_CONFIG_PARSE, status="failed", detail=str(exc)
            )
        detail = f"backend={connection.backend} model={connection.model}"
        if connection.backend != DEFAULT_EXECUTABLE_BACKEND:
            detail += " (not the first-version executable backend)"
        return TestLayerResult(name=LAYER_CONFIG_PARSE, status="passed", detail=detail)

    def _credential_layer(self, connection: Connection) -> _LayerOutcome:
        status = self._service.credential_status(connection.credential_ref)
        if not connection.credential_ref:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_CREDENTIAL,
                    status="failed",
                    detail="connection declares no credential_ref",
                ),
                stop=True,
            )
        if not status.configured:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_CREDENTIAL,
                    status="failed",
                    detail=f"credential_ref {connection.credential_ref!r} is not configured",
                ),
                stop=True,
            )
        return _LayerOutcome(
            TestLayerResult(
                name=LAYER_CREDENTIAL,
                status="passed",
                detail=f"source={status.source} version={status.version}",
            )
        )

    def _capability_layer(self) -> TestLayerResult:
        capabilities = adapter_capabilities()
        detail = (
            f"sdk={capabilities.sdk_version} installed={capabilities.sdk_installed} "
            f"probe_verified={','.join(capabilities.probe_verified_backends)} "
            f"unverified={','.join(capabilities.unverified_backends)}"
        )
        return TestLayerResult(name=LAYER_CAPABILITY, status="declared", detail=detail)

    def _network_layer(
        self, connection: Connection, network_allowed: bool
    ) -> _LayerOutcome:
        if connection.backend != DEFAULT_EXECUTABLE_BACKEND:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="skipped",
                    detail=f"backend {connection.backend} is not the verified executable backend",
                )
            )
        if not network_allowed:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="skipped",
                    detail="network test not requested (allow_network=false)",
                )
            )
        # This layer makes exactly one request per explicit test invocation.
        # Each invocation gets its own allowance; the cumulative diagnostic
        # count must never gate another invocation (including concurrent ones).
        if self._max_network_calls <= 0:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="skipped",
                    detail="network call budget exhausted",
                )
            )
        if not connection.model or not connection.base_url:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="failed",
                    detail="connection is missing model or base_url",
                )
            )

        credential = self._service.credential_resolver.resolve(
            connection.credential_ref or ""
        )
        if credential is None:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="failed",
                    detail="credential could not be resolved for a real request",
                )
            )

        upstream = upstream_chat_completions(connection.base_url)
        proxy = self._make_proxy(credential, upstream)
        started = datetime.now(timezone.utc)
        try:
            proxy.start()
        except AppError as exc:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK, status="failed", detail=str(exc)
                )
            )
        with self._network_calls_lock:
            self._network_calls += 1
        try:
            body = json.dumps(
                {
                    "model": connection.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "stream": False,
                }
            ).encode("utf-8")
            status_code, payload = self._http_post(
                proxy.base_url + "/chat/completions", body, self._http_timeout
            )
            local_calls = proxy.call_count
            upstream_model = proxy.upstream_model or payload.get("model")
        except Exception as exc:  # noqa: BLE001 - network failures are test results
            status_code = 0
            local_calls = proxy.call_count
            upstream_model = None
            detail = f"{type(exc).__name__}: {exc}"
            duration = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="failed",
                    detail=detail,
                    duration_ms=duration,
                )
            )
        finally:
            stop_confirmed = proxy.stop()

        duration = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        if status_code != 200:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="failed",
                    detail=f"upstream status {status_code} (proxy stop confirmed={stop_confirmed})",
                    duration_ms=duration,
                )
            )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="failed",
                    detail=(
                        "upstream returned no choices "
                        f"(proxy stop confirmed={stop_confirmed})"
                    ),
                    duration_ms=duration,
                )
            )
        detail = (
            f"model={connection.model} upstream_model={upstream_model} "
            f"proxy_calls={local_calls} stop_confirmed={stop_confirmed}"
        )
        return _LayerOutcome(
            TestLayerResult(
                name=LAYER_RUNTIME_NETWORK,
                status="passed",
                detail=detail,
                duration_ms=duration,
            )
        )

    def _gated_layer(self, name: str, requested: bool, network_allowed: bool) -> TestLayerResult:
        if not requested:
            return TestLayerResult(name=name, status="skipped", detail="not requested")
        if not network_allowed:
            return TestLayerResult(
                name=name, status="skipped", detail="network test not enabled"
            )
        return TestLayerResult(
            name=name,
            status="skipped",
            detail=(
                "separate probe not implemented in LG-025; requires an isolated SDK "
                "session with a temp workspace and its own budget"
            ),
        )

    def _make_proxy(self, credential: Secret, upstream: str) -> LocalAuthProxy:
        if self._proxy_factory is not None:
            return self._proxy_factory(credential, upstream, 1)
        return LocalAuthProxy(
            credential=credential,
            upstream_url=upstream,
            max_calls=1,
            timeout=self._upstream_timeout,
            allow_loopback_upstream=self._allow_loopback_upstream,
        )


def _host(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).hostname


def _overall(layers: list[TestLayerResult]) -> str:
    if any(layer.status == "failed" for layer in layers):
        return "failed"
    network = next(
        (layer for layer in layers if layer.name == LAYER_RUNTIME_NETWORK), None
    )
    if network is None or network.status == "skipped":
        return "not_run"
    static = next(
        (layer for layer in layers if layer.name == LAYER_CONFIG_PARSE), None
    )
    credential = next(
        (layer for layer in layers if layer.name == LAYER_CREDENTIAL), None
    )
    if (
        network.status == "passed"
        and static is not None
        and static.status == "passed"
        and credential is not None
        and credential.status == "passed"
    ):
        return "verified"
    return "partial"


__all__ = [
    "ConnectionTester",
    "ConnectionTestLog",
    "default_http_post",
    "HttpPost",
    "ProxyFactory",
    "LAYER_CONFIG_PARSE",
    "LAYER_CREDENTIAL",
    "LAYER_CAPABILITY",
    "LAYER_RUNTIME_NETWORK",
    "LAYER_TOOL_PROBE",
    "LAYER_STRUCTURED_OUTPUT",
]
