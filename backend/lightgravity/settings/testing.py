"""Layered connection testing (docs/07 §5, docs/08 §8.1, LG-104/LG-109).

The layers are deliberately separated and never merged into one boolean:

* ``config_parse``   - static: the complete provider configuration validates and
  the installed SDK config class can be constructed without a secret/network.
* ``credential``     - static: a transient draft secret, the saved
  ``credential_ref`` source, ADC prerequisite presence, or "not required".
  The value is never returned.
* ``capability``     - the SDK capability *declaration*, reported as
  ``declared`` and never as a runtime pass.
* ``runtime_network``- one explicit minimal request, either through the existing
  product loopback proxy (OpenAI-compatible) or the real installed SDK config
  (Gemini/Vertex API key).  It reserves the same persistent global generation
  ledger before forwarding and honours a cap of 0/corruption fail-closed.
* ``tool_probe`` / ``structured_output`` - separate optional probes, reported
  ``skipped`` unless explicitly requested.

A saved result is bound to ``connection_revision`` + ``credential_version`` and
may be persisted as an independent diagnostic.  A draft result is transient: the
draft endpoint never writes a Connection, secret, default, diagnostic, Task/Run
or SDK config.  A draft result carries ``draft=true`` and ``None`` identity when
it was never saved.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import tempfile
import threading
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
from lightgravity.adapter.provider_matrix import (
    auth_requires_credential,
    credential_recipient_identity,
    effective_auth_mode,
)
from lightgravity.adapter.proxy import (
    LocalAuthProxy,
    global_generation_counter,
    upstream_chat_completions,
)
from lightgravity.adapter.sdk_config import (
    ConnectionSdkSpec,
    build_connection_sdk_config,
)
from lightgravity.contracts import AppError
from lightgravity.store import RevisionConflict

from .errors import SettingsConfigInvalid
from .models import (
    Connection,
    ConnectionTestResult,
    TestLayerResult,
)
from .service import ConnectionService

#: Signature: (url, body, timeout) -> (http_status, parsed_json_or_empty).
HttpPost = Callable[[str, bytes, float], "tuple[int, dict[str, Any]]"]
#: Signature: (credential, upstream_url, max_calls) -> LocalAuthProxy.
ProxyFactory = Callable[[Secret, str, int], LocalAuthProxy]
#: Signature: (spec, credential, endpoint_base_url, timeout) -> (ok, detail).
NativeRunner = Callable[
    [ConnectionSdkSpec, Secret | None, str | None, float], "tuple[bool, str]"
]

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

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


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
class DraftConnectionSpec:
    """Non-secret provider fields accepted by the draft test endpoint."""

    backend: str
    model: str | None = None
    base_url: str | None = None
    auth_mode: str | None = None
    project: str | None = None
    location: str | None = None
    model_path: str | None = None
    litert_backend: str | None = None

    def sdk_spec(self) -> ConnectionSdkSpec:
        return ConnectionSdkSpec(
            backend=self.backend,
            model=self.model,
            auth_mode=self.auth_mode,
            base_url=self.base_url,
            project=self.project,
            location=self.location,
            model_path=self.model_path,
            litert_backend=self.litert_backend,
        )


@dataclass(frozen=True, slots=True)
class _TestConnection:
    id: str | None
    revision: int | None
    backend: str
    model: str | None
    base_url: str | None
    credential_ref: str | None
    auth_mode: str | None = None
    project: str | None = None
    location: str | None = None
    model_path: str | None = None
    litert_backend: str | None = None

    @classmethod
    def from_saved(cls, connection: Connection) -> "_TestConnection":
        return cls(
            id=connection.id,
            revision=connection.revision,
            backend=connection.backend,
            model=connection.model,
            base_url=connection.base_url,
            credential_ref=connection.credential_ref,
            auth_mode=connection.auth_mode,
            project=connection.project,
            location=connection.location,
            model_path=connection.model_path,
            litert_backend=connection.litert_backend,
        )


@dataclass(frozen=True, slots=True)
class _LayerOutcome:
    layer: TestLayerResult
    stop: bool = False


def _host(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).hostname


def _is_loopback_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in _LOOPBACK_HOSTS


def _adc_prerequisite() -> tuple[bool, str]:
    """Check ADC presence statically; never run gcloud or request metadata."""

    explicit = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if explicit and Path(explicit).is_file():
        return True, "GOOGLE_APPLICATION_CREDENTIALS file present"
    default = (
        Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    )
    if default.is_file():
        return True, "gcloud ADC file present"
    return False, "ADC credential file not detected"


def _run_coroutine_sync(factory: Callable[[], Any], timeout: float) -> Any:
    """Run one coroutine in a private thread with a finite wall-clock bound."""

    box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            box["value"] = asyncio.run(asyncio.wait_for(factory(), timeout=timeout))
        except BaseException as exc:  # noqa: BLE001 - caller maps to test result
            box["error"] = exc

    thread = threading.Thread(target=_runner, name="lg-provider-test", daemon=True)
    thread.start()
    thread.join(timeout + 5.0)
    if thread.is_alive():
        raise TimeoutError(f"provider probe exceeded {timeout + 5.0:.0f}s runtime bound")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _call_callable_sync(
    call: Callable[[], tuple[bool, str]], timeout: float
) -> tuple[bool, str]:
    """Bound an injected/real native probe with a finite wall-clock wait."""

    box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            box["value"] = call()
        except BaseException as exc:  # noqa: BLE001 - caller maps to test result
            box["error"] = exc

    thread = threading.Thread(target=_runner, name="lg-provider-probe-call", daemon=True)
    thread.start()
    thread.join(timeout + 5.0)
    if thread.is_alive():
        raise TimeoutError(f"provider probe exceeded {timeout + 5.0:.0f}s runtime bound")
    if "error" in box:
        raise box["error"]
    return box.get("value", (False, "provider probe returned no result"))


def _default_native_probe(
    spec: ConnectionSdkSpec,
    credential: Secret | None,
    endpoint_base_url: str | None,
    timeout: float,
) -> tuple[bool, str]:
    """Run one minimal real-SDK turn with no tools, retries or subagents."""

    from google.antigravity import Agent, types as types_mod

    save_dir = tempfile.mkdtemp(prefix="lg-provider-probe-")
    stop_state = {"confirmed": False}

    async def _probe() -> str:
        config = build_connection_sdk_config(
            spec,
            credential=credential,
            endpoint_base_url=endpoint_base_url,
            common_kwargs={
                "capabilities": types_mod.CapabilitiesConfig(
                    enabled_tools=[], enable_subagents=False
                ),
                "retry_config": types_mod.RetryConfig(
                    api_retry=types_mod.ModelAPIRetryConfig(max_retries=0),
                    model_output_retry=types_mod.ModelOutputRetryConfig(max_retries=0),
                ),
                "budget_config": types_mod.BudgetConfig(max_model_calls=1),
                "save_dir": save_dir,
                "workspaces": [],
                "system_instructions": "Reply briefly to the probe.",
            },
        )
        agent = Agent(config)
        await agent.__aenter__()
        try:
            response = await agent.chat("ping")
            return await response.text()
        finally:
            try:
                await agent.__aexit__(None, None, None)
                stop_state["confirmed"] = True
            except Exception:  # noqa: BLE001 - report unconfirmed stop honestly
                stop_state["confirmed"] = False

    try:
        text = _run_coroutine_sync(_probe, timeout)
        if not isinstance(text, str) or not text.strip():
            return (
                False,
                f"sdk probe returned no text (stop_confirmed={stop_state['confirmed']})",
            )
        return (
            True,
            f"model_response=received stop_confirmed={stop_state['confirmed']} "
            f"max_model_calls=1 tools=none retries=0",
        )
    except Exception as exc:  # noqa: BLE001 - network failures are test results
        return (
            False,
            f"{type(exc).__name__}: {exc} "
            f"(stop_confirmed={stop_state['confirmed']})",
        )
    finally:
        shutil.rmtree(save_dir, ignore_errors=True)


class ConnectionTester:
    """Run layered connection tests without treating save/test as execution."""

    def __init__(
        self,
        service: ConnectionService,
        *,
        diagnostics: ConnectionTestLog | None = None,
        allow_network: bool = False,
        http_post: HttpPost | None = None,
        proxy_factory: ProxyFactory | None = None,
        native_runner: NativeRunner | None = None,
        http_timeout: float = 30.0,
        upstream_timeout: float = 60.0,
        native_timeout: float = 30.0,
        allow_loopback_upstream: bool = False,
        allow_loopback_native: bool = False,
        native_base_url: str | None = None,
        adc_available: bool | None = None,
        generation_counter: Any | None = None,
        max_network_calls: int = 1,
    ) -> None:
        if native_base_url is not None:
            if not allow_loopback_native or not _is_loopback_url(native_base_url):
                raise ValueError(
                    "native_base_url is a test-only loopback injection and requires "
                    "allow_loopback_native=True"
                )
        self._service = service
        self._diagnostics = diagnostics
        self._allow_network = allow_network
        self._http_post = http_post or default_http_post
        self._proxy_factory = proxy_factory
        self._native_runner = native_runner or _default_native_probe
        self._http_timeout = http_timeout
        self._upstream_timeout = upstream_timeout
        self._native_timeout = native_timeout
        self._allow_loopback_upstream = allow_loopback_upstream
        self._allow_loopback_native = allow_loopback_native
        self._native_base_url = native_base_url
        self._adc_available = adc_available
        self._generation_counter = generation_counter
        self._max_network_calls = max_network_calls
        self._network_calls = 0
        self._network_calls_lock = Lock()

    @property
    def network_calls(self) -> int:
        """Cumulative attempted requests for diagnostics, not a shared budget."""
        with self._network_calls_lock:
            return self._network_calls

    # ------------------------------------------------------------- saved test
    def test(
        self,
        connection_id: str,
        *,
        expected_revision: int | None = None,
        allow_network: bool | None = None,
        probe_tools: bool = False,
        probe_structured: bool = False,
    ) -> ConnectionTestResult:
        network_allowed = self._allow_network if allow_network is None else allow_network
        connection = self._service.repository.read_connection(connection_id)
        if expected_revision is not None and connection.revision != expected_revision:
            raise RevisionConflict(
                "connection",
                connection_id,
                expected=expected_revision,
                actual=connection.revision,
            )
        return self._run(
            _TestConnection.from_saved(connection),
            network_allowed=network_allowed,
            probe_tools=probe_tools,
            probe_structured=probe_structured,
            draft=False,
            persist=True,
        )

    # ------------------------------------------------------------- draft test
    def test_draft(
        self,
        connection: DraftConnectionSpec,
        *,
        credential_value: str | None = None,
        existing_connection_id: str | None = None,
        expected_revision: int | None = None,
        allow_network: bool | None = None,
        probe_tools: bool = False,
        probe_structured: bool = False,
    ) -> ConnectionTestResult:
        """Test an unsaved/changed draft entirely in request memory.

        No Connection, secret, default, diagnostic, Task/Run or SDK config is
        written.  An existing saved credential can only be reused when the draft
        has the same backend/auth mode/endpoint recipient and the caller supplied
        the saved id + current revision.
        """

        network_allowed = self._allow_network if allow_network is None else allow_network
        effective = self._service.validate_connection_spec(
            backend=connection.backend,
            model=connection.model,
            base_url=connection.base_url,
            auth_mode=connection.auth_mode,
            project=connection.project,
            location=connection.location,
            model_path=connection.model_path,
            litert_backend=connection.litert_backend,
        )
        supplied = (
            Secret(credential_value)
            if isinstance(credential_value, str) and credential_value.strip()
            else None
        )
        saved: Connection | None = None
        transient = supplied
        credential_source: str | None = "transient_request_memory" if supplied else None
        credential_version: str | None = None

        if existing_connection_id is not None:
            saved = self._service.repository.read_connection(existing_connection_id)
            if expected_revision is None:
                raise SettingsConfigInvalid(
                    "expected_revision is required when a draft reuses a saved connection",
                    diagnostics=[
                        {
                            "code": "expected_revision_missing",
                            "location": "expected_revision",
                        }
                    ],
                )
            if saved.revision != expected_revision:
                raise RevisionConflict(
                    "connection",
                    existing_connection_id,
                    expected=expected_revision,
                    actual=saved.revision,
                )
            old_identity = credential_recipient_identity(
                backend=saved.backend,
                auth_mode=saved.auth_mode,
                base_url=saved.base_url,
                project=saved.project,
                location=saved.location,
                credential_ref=saved.credential_ref,
            )
            new_identity = credential_recipient_identity(
                backend=connection.backend,
                auth_mode=connection.auth_mode,
                base_url=connection.base_url,
                project=connection.project,
                location=connection.location,
                credential_ref=saved.credential_ref,
            )
            if (
                old_identity != new_identity
                and supplied is None
                and auth_requires_credential(connection.backend, effective)
            ):
                raise SettingsConfigInvalid(
                    "changing provider, auth mode or credential-recipient endpoint "
                    "requires a fresh credential_value for a draft test",
                    diagnostics=[
                        {
                            "code": "credential_recipient_changed",
                            "location": "credential_value",
                        }
                    ],
                )
            if old_identity == new_identity and supplied is None:
                if auth_requires_credential(connection.backend, effective):
                    transient = self._service.credential_resolver.resolve(
                        saved.credential_ref or ""
                    )
                    status = self._service.credential_status(saved.credential_ref)
                    credential_source = status.source
                    credential_version = status.version

        test_connection = _TestConnection(
            id=saved.id if saved is not None else None,
            revision=saved.revision if saved is not None else None,
            backend=connection.backend,
            model=connection.model,
            base_url=connection.base_url,
            credential_ref=saved.credential_ref if saved is not None else None,
            auth_mode=connection.auth_mode,
            project=connection.project,
            location=connection.location,
            model_path=connection.model_path,
            litert_backend=connection.litert_backend,
        )
        return self._run(
            test_connection,
            network_allowed=network_allowed,
            probe_tools=probe_tools,
            probe_structured=probe_structured,
            draft=True,
            persist=False,
            credential_override=transient,
            credential_source=credential_source,
            credential_version=credential_version,
        )

    # ------------------------------------------------------------------ runner
    def _run(
        self,
        connection: _TestConnection,
        *,
        network_allowed: bool,
        probe_tools: bool,
        probe_structured: bool,
        draft: bool,
        persist: bool,
        credential_override: Secret | None = None,
        credential_source: str | None = None,
        credential_version: str | None = None,
    ) -> ConnectionTestResult:
        started = _now_iso()
        test_id = f"ctest_{uuid.uuid4().hex[:16]}"
        effective = effective_auth_mode(
            connection.backend,
            connection.auth_mode,
            project=connection.project,
            location=connection.location,
            credential_ref=connection.credential_ref,
        )
        layers: list[TestLayerResult] = []
        layers.append(self._config_layer(connection, effective))
        credential = self._credential_layer(
            connection,
            effective,
            credential_override=credential_override,
            credential_source=credential_source,
            credential_version=credential_version,
        )
        layers.append(credential.layer)
        layers.append(self._capability_layer())
        network = self._network_layer(
            connection,
            effective,
            network_allowed,
            credential_override=credential_override,
        )
        layers.append(network.layer)
        layers.append(self._gated_layer(LAYER_TOOL_PROBE, probe_tools, network_allowed))
        layers.append(
            self._gated_layer(LAYER_STRUCTURED_OUTPUT, probe_structured, network_allowed)
        )

        if credential_version is None and connection.credential_ref and not draft:
            credential_version = self._service.credential_status(
                connection.credential_ref
            ).version
        result = ConnectionTestResult(
            test_id=test_id,
            connection_id=connection.id,
            connection_revision=connection.revision,
            credential_ref=connection.credential_ref,
            credential_version=credential_version,
            backend=connection.backend,
            model=connection.model,
            base_url_host=_host(connection.base_url),
            started_at=started,
            finished_at=_now_iso(),
            layers=tuple(layers),
            overall=_overall(layers),
            note=(
                "draft test is transient; no connection/secret/diagnostic was written"
                if draft
                else "static config, real network/model and SDK capability declaration are separate layers"
            ),
            draft=draft,
        )
        if persist and self._diagnostics is not None:
            self._diagnostics.record(result)
        return result

    # ------------------------------------------------------------------ layers
    def _config_layer(
        self, connection: _TestConnection, effective: str
    ) -> TestLayerResult:
        try:
            self._service.validate_connection_spec(
                backend=connection.backend,
                model=connection.model,
                base_url=connection.base_url,
                auth_mode=connection.auth_mode,
                project=connection.project,
                location=connection.location,
                model_path=connection.model_path,
                litert_backend=connection.litert_backend,
                credential_ref=connection.credential_ref,
            )
            build_connection_sdk_config(
                ConnectionSdkSpec(
                    backend=connection.backend,
                    model=connection.model,
                    auth_mode=connection.auth_mode,
                    base_url=connection.base_url,
                    project=connection.project,
                    location=connection.location,
                    model_path=connection.model_path,
                    litert_backend=connection.litert_backend,
                )
            )
        except Exception as exc:  # noqa: BLE001 - static failures are test results
            return TestLayerResult(
                name=LAYER_CONFIG_PARSE,
                status="failed",
                detail=f"{type(exc).__name__}: {exc}",
            )
        detail = (
            f"backend={connection.backend} auth_mode={effective} "
            f"model={connection.model} sdk_config=constructed(unauthenticated)"
        )
        if connection.backend == "litert":
            package_present = importlib.util.find_spec("litert_lm") is not None
            file_present = bool(
                connection.model_path and Path(connection.model_path).is_file()
            )
            detail += (
                f" litert_package={package_present} model_file={file_present} "
                "static_only=true"
            )
        if connection.backend != "openai-compat":
            detail += " (not the first-version executable task backend)"
        return TestLayerResult(name=LAYER_CONFIG_PARSE, status="passed", detail=detail)

    def _credential_layer(
        self,
        connection: _TestConnection,
        effective: str,
        *,
        credential_override: Secret | None,
        credential_source: str | None,
        credential_version: str | None,
    ) -> _LayerOutcome:
        if not auth_requires_credential(connection.backend, effective):
            if effective == "adc":
                available, reason = (
                    (self._adc_available, "injected ADC prerequisite state")
                    if self._adc_available is not None
                    else _adc_prerequisite()
                )
                return _LayerOutcome(
                    TestLayerResult(
                        name=LAYER_CREDENTIAL,
                        status="declared",
                        detail=(
                            f"ADC is environment-owned; static prerequisite="
                            f"{available} ({reason}); no gcloud/metadata request made"
                        ),
                    )
                )
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_CREDENTIAL,
                    status="skipped",
                    detail="no cloud credential is required for this provider",
                )
            )

        if credential_override is not None:
            source = credential_source or "transient_request_memory"
            version = f" version={credential_version}" if credential_version else ""
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_CREDENTIAL,
                    status="passed",
                    detail=f"source={source}{version}",
                ),
                stop=False,
            )
        if not connection.credential_ref:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_CREDENTIAL,
                    status="failed",
                    detail="connection declares no credential_ref and no draft value was supplied",
                ),
                stop=True,
            )
        status = self._service.credential_status(connection.credential_ref)
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
        self,
        connection: _TestConnection,
        effective: str,
        network_allowed: bool,
        *,
        credential_override: Secret | None,
    ) -> _LayerOutcome:
        if not network_allowed:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="skipped",
                    detail="network test not requested (allow_network=false)",
                )
            )
        # LG-108: one request per explicit test invocation; the cumulative
        # diagnostic count never gates a later click.
        if self._max_network_calls <= 0:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="skipped",
                    detail="network call budget exhausted",
                )
            )
        if connection.backend == "litert":
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="skipped",
                    detail=(
                        "LiteRT is static-only in this build; no install, download "
                        "or inference was attempted"
                    ),
                )
            )
        if connection.backend == "openai-compat":
            return self._openai_network_layer(
                connection, credential_override=credential_override
            )
        if connection.backend in ("gemini", "vertex"):
            return self._native_network_layer(
                connection, effective, credential_override=credential_override
            )
        return _LayerOutcome(
            TestLayerResult(
                name=LAYER_RUNTIME_NETWORK,
                status="skipped",
                detail=f"backend {connection.backend} has no network probe",
            )
        )

    def _openai_network_layer(
        self, connection: _TestConnection, *, credential_override: Secret | None
    ) -> _LayerOutcome:
        if not connection.model or not connection.base_url:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="failed",
                    detail="connection is missing model or base_url",
                )
            )
        credential = credential_override or self._service.credential_resolver.resolve(
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

    def _native_network_layer(
        self,
        connection: _TestConnection,
        effective: str,
        *,
        credential_override: Secret | None,
    ) -> _LayerOutcome:
        if effective == "adc":
            available, reason = (
                (self._adc_available, "injected ADC prerequisite state")
                if self._adc_available is not None
                else _adc_prerequisite()
            )
            if not available:
                return _LayerOutcome(
                    TestLayerResult(
                        name=LAYER_RUNTIME_NETWORK,
                        status="skipped",
                        detail=(
                            "ADC prerequisite not detected; no gcloud or metadata "
                            f"request was made ({reason})"
                        ),
                    )
                )
            credential = None
        else:
            credential = (
                credential_override
                or self._service.credential_resolver.resolve(connection.credential_ref or "")
            )
            if credential is None:
                return _LayerOutcome(
                    TestLayerResult(
                        name=LAYER_RUNTIME_NETWORK,
                        status="failed",
                        detail="credential could not be resolved for a real request",
                    )
                )
        if not connection.model:
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK,
                    status="failed",
                    detail="connection is missing model",
                )
            )

        counter = self._generation_counter or global_generation_counter()
        snapshot = counter.snapshot()
        if not counter.reserve():
            if snapshot.get("corrupt"):
                detail = (
                    "global generation ledger is corrupt; refusing the network "
                    "request (fail closed)"
                )
            else:
                detail = (
                    "global generation budget exhausted "
                    f"(count={snapshot.get('count')} limit={snapshot.get('limit')})"
                )
            return _LayerOutcome(
                TestLayerResult(
                    name=LAYER_RUNTIME_NETWORK, status="skipped", detail=detail
                )
            )

        with self._network_calls_lock:
            self._network_calls += 1
        started = datetime.now(timezone.utc)
        spec = ConnectionSdkSpec(
            backend=connection.backend,
            model=connection.model,
            auth_mode=connection.auth_mode,
            base_url=connection.base_url,
            project=connection.project,
            location=connection.location,
            model_path=connection.model_path,
            litert_backend=connection.litert_backend,
        )
        endpoint = self._native_base_url
        try:
            ok, detail = _call_callable_sync(
                lambda: self._native_runner(
                    spec, credential, endpoint, self._native_timeout
                ),
                self._native_timeout,
            )
        except Exception as exc:  # noqa: BLE001 - network failures are test results
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        duration = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        prefix = f"model={connection.model} budget_reserved=true "
        if endpoint:
            prefix += "endpoint=loopback_test_fake "
        return _LayerOutcome(
            TestLayerResult(
                name=LAYER_RUNTIME_NETWORK,
                status="passed" if ok else "failed",
                detail=prefix + detail,
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
        and credential.status in ("passed", "declared")
    ):
        return "verified"
    return "partial"


__all__ = [
    "ConnectionTester",
    "ConnectionTestLog",
    "DraftConnectionSpec",
    "default_http_post",
    "HttpPost",
    "ProxyFactory",
    "NativeRunner",
    "LAYER_CONFIG_PARSE",
    "LAYER_CREDENTIAL",
    "LAYER_CAPABILITY",
    "LAYER_RUNTIME_NETWORK",
    "LAYER_TOOL_PROBE",
    "LAYER_STRUCTURED_OUTPUT",
]
