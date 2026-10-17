#!/usr/bin/env python3
"""LG-112 R2 independent reference/delete concurrency probe (final candidate).

Purpose
-------
Independently re-check the defect reproduced in QA-R1 on ``ff885bf`` against the
*final* candidate whose backend tree is ``caad0343…`` (native fix ``47686ae``).

Covered
-------
* Bounded natural stress of the supported default writer vs DELETE.
* Bounded natural stress of the supported Agent writer
  (``ResourceService.update``) vs DELETE.
* Orchestrated **both winner orders** for default and Agent bindings using the
  actual supported service methods, with a QA-only pause seam. The seam is a
  runtime wrapper on an isolated QA service instance; no product source is
  edited.
* Real HTTP API interleavings (``PATCH /api/v1/settings`` and
  ``PATCH /api/v1/resources/agent/{id}`` vs ``DELETE``).
* A raw ``FileStore`` bypass case, explicitly marked **outside the supported
  guarantee** (the fix only serializes controlled services).
* Lock-contention sanity: concurrent writers must finish, and a ``LockConflict``
  must never be converted into a successful delete.
* Unpatched production host negative controls (DeepSeek-only default/proxy).

The fake upstream is never contacted here. No real vendor/key/model is used.
"""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

RESULTS: dict[str, Any] = {}
HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def service_at(root: Path) -> tuple[Any, Any]:
    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    data = root / "data"
    store = FileStore(data, data / "workspaces")
    service = ConnectionService(store, secret_store=FileSecretStore(root / "secrets"))
    return service, store


def resources_at(root: Path, store: Any, service: Any) -> Any:
    from lightgravity.resources.service import ResourceService

    return ResourceService(store, connections=service)


def create_eligible(service: Any, connection_id: str) -> None:
    service.create_connection(
        connection_id,
        title=connection_id,
        backend="openai-compat",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        auth_mode="proxy_api_key",
        credential_ref=f"{connection_id}-key",
        credential_value="sk-concurrency-dummy-not-real",
        actor="qa-probe",
        request_id=f"qa-create-{connection_id}",
    )


def fresh_root(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def outcome(result: Any) -> str:
    return result if isinstance(result, str) else f"ok:{result}"


def reset_default_none(service: Any) -> None:
    settings = service.repository.read_settings()
    if settings.default_worker_connection_ref is not None:
        service.update_settings(
            expected_revision=settings.revision,
            actor="qa",
            default_worker_connection_ref=None,
        )


def reset_agent_none(resources: Any, store: Any) -> None:
    try:
        current = store.read("agent", "race-agent")
        if current.entity.get("connection_ref") is not None:
            resources.update(
                "agent",
                "race-agent",
                patch={"connection_ref": None},
                expected_revision=current.revision,
                actor="qa",
            )
    except Exception:
        # Agent may not exist yet; (re)create it as setup only.
        try:
            current = store.read("agent", "race-agent")
            store.delete("agent", "race-agent", expected_revision=current.revision, actor="qa")
        except Exception:
            pass
        store.create(
            "agent",
            "race-agent",
            {"title": "Race agent", "enabled": True},
            actor="qa",
            request_id="qa-race-agent-setup",
        )


# --------------------------------------------------------------------------- #
# 1. bounded natural stress
# --------------------------------------------------------------------------- #
def natural_default_stress(iterations: int = 200) -> dict[str, Any]:
    root = fresh_root("lg112r2-natural-default-")
    service, _store = service_at(root)
    create_eligible(service, "race-natural")
    reset_default_none(service)
    dangling = 0
    bad_success = 0
    counts: dict[str, int] = {}
    first_dangling: dict[str, Any] | None = None

    for _ in range(iterations):
        # Setup reset: supported service methods only for the tested writers.
        reset_default_none(service)
        try:
            revision = service.repository.read_connection("race-natural").revision
            service.delete_connection("race-natural", expected_revision=revision, actor="qa")
        except Exception:
            pass
        create_eligible(service, "race-natural")
        reset_default_none(service)
        barrier = threading.Barrier(2)

        def do_delete() -> str:
            barrier.wait(5)
            try:
                revision = service.repository.read_connection("race-natural").revision
                service.delete_connection("race-natural", expected_revision=revision, actor="qa")
                return "deleted"
            except Exception as exc:  # noqa: BLE001 - outcome data
                return f"delete_error:{type(exc).__name__}"

        def do_default() -> str:
            barrier.wait(5)
            try:
                revision = service.repository.read_settings().revision
                service.update_settings(
                    expected_revision=revision,
                    actor="qa",
                    default_worker_connection_ref="race-natural",
                )
                return "default_set"
            except Exception as exc:  # noqa: BLE001 - outcome data
                return f"default_error:{type(exc).__name__}"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(do_delete), pool.submit(do_default)]
            results = [f.result(timeout=20) for f in futures]
        for item in results:
            counts[item] = counts.get(item, 0) + 1
            if item.startswith("delete_error:LockConflict"):
                bad_success += 1
        settings = service.repository.read_settings()
        connection = service.repository.get_connection_or_none("race-natural")
        if (
            settings.default_worker_connection_ref == "race-natural"
            and connection is None
        ):
            dangling += 1
            first_dangling = {
                "settings_default_worker": settings.default_worker_connection_ref,
                "connection_exists": False,
            }
            break
        if "deleted" in results and connection is not None:
            bad_success += 1

    return {
        "iterations": iterations,
        "dangling_observed": dangling,
        "delete_reported_success_but_connection_still_present": bad_success,
        "outcomes": counts,
        "first_dangling": first_dangling,
    }


def natural_agent_stress(iterations: int = 120) -> dict[str, Any]:
    root = fresh_root("lg112r2-natural-agent-")
    service, store = service_at(root)
    resources = resources_at(root, store, service)
    create_eligible(service, "race-natural")
    reset_agent_none(resources, store)
    dangling = 0
    bad_success = 0
    counts: dict[str, int] = {}
    first_dangling: dict[str, Any] | None = None

    for _ in range(iterations):
        reset_agent_none(resources, store)
        try:
            revision = service.repository.read_connection("race-natural").revision
            service.delete_connection("race-natural", expected_revision=revision, actor="qa")
        except Exception:
            pass
        create_eligible(service, "race-natural")
        reset_agent_none(resources, store)
        barrier = threading.Barrier(2)

        def do_delete() -> str:
            barrier.wait(5)
            try:
                revision = service.repository.read_connection("race-natural").revision
                service.delete_connection("race-natural", expected_revision=revision, actor="qa")
                return "deleted"
            except Exception as exc:  # noqa: BLE001 - outcome data
                return f"delete_error:{type(exc).__name__}"

        def do_agent() -> str:
            barrier.wait(5)
            try:
                current = store.read("agent", "race-agent")
                resources.update(
                    "agent",
                    "race-agent",
                    patch={"connection_ref": "race-natural"},
                    expected_revision=current.revision,
                    actor="qa",
                )
                return "agent_bound"
            except Exception as exc:  # noqa: BLE001 - outcome data
                return f"agent_error:{type(exc).__name__}"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(do_delete), pool.submit(do_agent)]
            results = [f.result(timeout=20) for f in futures]
        for item in results:
            counts[item] = counts.get(item, 0) + 1
            if item.startswith("delete_error:LockConflict"):
                bad_success += 1
        connection = service.repository.get_connection_or_none("race-natural")
        refs = service.references_to("race-natural")
        if refs.agent_refs and connection is None:
            dangling += 1
            first_dangling = {"references": refs.to_dict(), "connection_exists": False}
            break
        if "deleted" in results and connection is not None:
            bad_success += 1

    return {
        "iterations": iterations,
        "dangling_observed": dangling,
        "delete_reported_success_but_connection_still_present": bad_success,
        "outcomes": counts,
        "first_dangling": first_dangling,
    }


# --------------------------------------------------------------------------- #
# 2. orchestrated supported-service, both winner orders
# --------------------------------------------------------------------------- #
def _delete_first(binding: str) -> dict[str, Any]:
    root = fresh_root(f"lg112r2-delete-first-{binding}-")
    service, store = service_at(root)
    other_store = type(store)(root / "data", root / "data" / "workspaces")
    other_service, _ = service_at(root)
    resources = resources_at(root, other_store, other_service)
    create_eligible(service, f"race-{binding}")
    if binding == "agent":
        other_store.create(
            "agent",
            "race-agent",
            {"title": "Race agent", "enabled": True},
            actor="qa",
            request_id="qa-race-agent-setup",
        )
    else:
        reset_default_none(service)

    entered = threading.Event()
    release = threading.Event()
    other_done = threading.Event()
    original_guard = service._guard_connection_delete

    def paused_guard(connection_id: str) -> None:
        original_guard(connection_id)
        entered.set()
        if not release.wait(10):
            raise RuntimeError("orchestrated race release timeout")

    service._guard_connection_delete = paused_guard  # type: ignore[method-assign]
    delete_result: list[dict[str, Any]] = []
    writer_result: list[dict[str, Any]] = []

    def do_delete() -> None:
        try:
            revision = service.repository.read_connection(f"race-{binding}").revision
            delete_result.append(
                service.delete_connection(
                    f"race-{binding}", expected_revision=revision, actor="qa"
                )
            )
        except Exception as exc:  # noqa: BLE001 - evidence
            delete_result.append({"error": type(exc).__name__, "message": str(exc)})

    def do_writer() -> None:
        try:
            if binding == "default":
                revision = other_service.repository.read_settings().revision
                other_service.update_settings(
                    expected_revision=revision,
                    actor="qa",
                    default_worker_connection_ref=f"race-{binding}",
                )
            else:
                current = other_store.read("agent", "race-agent")
                resources.update(
                    "agent",
                    "race-agent",
                    patch={"connection_ref": f"race-{binding}"},
                    expected_revision=current.revision,
                    actor="qa",
                )
            writer_result.append({"status": "committed"})
        except Exception as exc:  # noqa: BLE001 - evidence
            writer_result.append(
                {"status": "rejected", "error": type(exc).__name__, "message": str(exc)}
            )
        finally:
            other_done.set()

    delete_thread = threading.Thread(target=do_delete, name="r2-delete-first-delete")
    delete_thread.start()
    assert entered.wait(10), "delete guard did not run"
    writer_thread = threading.Thread(target=do_writer, name="r2-delete-first-writer")
    writer_thread.start()
    blocked_while_delete_paused = not other_done.wait(0.5)
    release.set()
    delete_thread.join(10)
    writer_thread.join(10)

    connection = service.repository.get_connection_or_none(f"race-{binding}")
    refs = service.references_to(f"race-{binding}")
    settings = service.repository.read_settings()
    dangling_default = (
        settings.default_worker_connection_ref == f"race-{binding}" and connection is None
    )
    dangling_agent = bool(refs.agent_refs) and connection is None
    return {
        "case": "delete_wins",
        "binding": binding,
        "writer_was_blocked_while_delete_held_shared_lock": blocked_while_delete_paused,
        "delete_result": delete_result,
        "writer_result": writer_result,
        "connection_exists": connection is not None,
        "references": refs.to_dict(),
        "settings_default_worker": settings.default_worker_connection_ref,
        "dangling_default": dangling_default,
        "dangling_agent": dangling_agent,
    }


def _writer_first(binding: str) -> dict[str, Any]:
    root = fresh_root(f"lg112r2-writer-first-{binding}-")
    service, store = service_at(root)
    other_store = type(store)(root / "data", root / "data" / "workspaces")
    other_service, _ = service_at(root)
    resources = resources_at(root, other_store, other_service)
    create_eligible(service, f"race-{binding}")
    if binding == "agent":
        other_store.create(
            "agent",
            "race-agent",
            {"title": "Race agent", "enabled": True},
            actor="qa",
            request_id="qa-race-agent-setup",
        )
    else:
        reset_default_none(service)

    validated = threading.Event()
    release = threading.Event()
    delete_done = threading.Event()
    delete_result: list[dict[str, Any]] = []
    writer_result: list[dict[str, Any]] = []

    if binding == "default":
        original_validate = other_service._validate_default_ref

        def paused_validate(ref: Any, *, role: str) -> None:
            original_validate(ref, role=role)
            if ref == f"race-{binding}":
                validated.set()
                if not release.wait(10):
                    raise RuntimeError("writer-first release timeout")

        other_service._validate_default_ref = paused_validate  # type: ignore[method-assign]
    else:
        original_agent_validate = resources._validate_candidate

        def paused_agent_validate(kind: str, candidate: Any) -> None:
            original_agent_validate(kind, candidate)
            validated.set()
            if not release.wait(10):
                raise RuntimeError("writer-first release timeout")

        resources._validate_candidate = paused_agent_validate  # type: ignore[method-assign]

    def do_writer() -> None:
        try:
            if binding == "default":
                revision = other_service.repository.read_settings().revision
                other_service.update_settings(
                    expected_revision=revision,
                    actor="qa",
                    default_worker_connection_ref=f"race-{binding}",
                )
            else:
                current = other_store.read("agent", "race-agent")
                resources.update(
                    "agent",
                    "race-agent",
                    patch={"connection_ref": f"race-{binding}"},
                    expected_revision=current.revision,
                    actor="qa",
                )
            writer_result.append({"status": "committed"})
        except Exception as exc:  # noqa: BLE001 - evidence
            writer_result.append(
                {"status": "error", "error": type(exc).__name__, "message": str(exc)}
            )

    def do_delete() -> None:
        try:
            revision = service.repository.read_connection(f"race-{binding}").revision
            delete_result.append(
                service.delete_connection(
                    f"race-{binding}", expected_revision=revision, actor="qa"
                )
            )
        except Exception as exc:  # noqa: BLE001 - evidence
            delete_result.append({"error": type(exc).__name__, "message": str(exc)})
        finally:
            delete_done.set()

    writer_thread = threading.Thread(target=do_writer, name="r2-writer-first-writer")
    writer_thread.start()
    assert validated.wait(10), "writer validation seam did not run"
    delete_thread = threading.Thread(target=do_delete, name="r2-writer-first-delete")
    delete_thread.start()
    # While the writer holds the shared lock in validation, DELETE must wait.
    blocked_while_writer_paused = not delete_done.wait(0.5)
    release.set()
    writer_thread.join(10)
    delete_thread.join(10)

    connection = service.repository.get_connection_or_none(f"race-{binding}")
    refs = service.references_to(f"race-{binding}")
    settings = service.repository.read_settings()
    dangling_default = (
        settings.default_worker_connection_ref == f"race-{binding}" and connection is None
    )
    dangling_agent = bool(refs.agent_refs) and connection is None
    return {
        "case": "writer_wins",
        "binding": binding,
        "delete_was_blocked_while_writer_held_shared_lock": blocked_while_writer_paused,
        "writer_result": writer_result,
        "delete_result": delete_result,
        "connection_exists": connection is not None,
        "references": refs.to_dict(),
        "settings_default_worker": settings.default_worker_connection_ref,
        "dangling_default": dangling_default,
        "dangling_agent": dangling_agent,
    }


# --------------------------------------------------------------------------- #
# 3. raw Store bypass (OUTSIDE the supported guarantee)
# --------------------------------------------------------------------------- #
def raw_store_bypass_outside_guarantee() -> dict[str, Any]:
    root = fresh_root("lg112r2-raw-bypass-")
    service, store = service_at(root)
    create_eligible(service, "race-raw")
    entered = threading.Event()
    release = threading.Event()
    original_guard = service._guard_connection_delete

    def paused_guard(connection_id: str) -> None:
        original_guard(connection_id)
        entered.set()
        if not release.wait(10):
            raise RuntimeError("raw bypass release timeout")

    service._guard_connection_delete = paused_guard  # type: ignore[method-assign]
    delete_error: list[str] = []

    def do_delete() -> None:
        try:
            revision = service.repository.read_connection("race-raw").revision
            service.delete_connection("race-raw", expected_revision=revision, actor="qa")
        except Exception as exc:  # noqa: BLE001 - evidence
            delete_error.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=do_delete, name="r2-raw-delete")
    thread.start()
    assert entered.wait(10)
    raw_result: str
    try:
        # This deliberately bypasses ResourceService/Settings and therefore the
        # shared reference lock. It is NOT a supported path and is NOT protected
        # by the native fix.
        store.create(
            "agent",
            "raw-agent",
            {"title": "Raw bypass", "enabled": True, "connection_ref": "race-raw"},
            actor="qa",
            request_id="qa-raw-agent",
        )
        raw_result = "raw_agent_created"
    except Exception as exc:  # noqa: BLE001 - evidence
        raw_result = f"error:{type(exc).__name__}: {exc}"
    release.set()
    thread.join(10)
    connection = service.repository.get_connection_or_none("race-raw")
    refs = service.references_to("race-raw")
    return {
        "label": "OUTSIDE supported guarantee: raw FileStore write bypasses the controlled services",
        "raw_store_result": raw_result,
        "delete_errors": delete_error,
        "connection_exists": connection is not None,
        "references": refs.to_dict(),
        "dangling_raw_agent": bool(refs.agent_refs) and connection is None,
        "note": (
            "A dangling reference here is expected and is not a product regression: "
            "the fix serializes supported controlled writers only."
        ),
    }


# --------------------------------------------------------------------------- #
# 4. lock contention / no fake timeout success
# --------------------------------------------------------------------------- #
def lock_contention(rounds: int = 12) -> dict[str, Any]:
    root = fresh_root("lg112r2-contention-")
    service, store = service_at(root)
    resources = resources_at(root, store, service)
    lock_errors: list[str] = []
    hangs = 0
    successes_missing_entity = 0

    for index in range(rounds):
        create_eligible(service, f"race-c{index}")
        reset_default_none(service)
        store.create(
            "agent",
            f"agent-c{index}",
            {"title": "C", "enabled": True},
            actor="qa",
            request_id=f"qa-c-{index}",
        )
        barrier = threading.Barrier(3)

        def do_delete() -> str:
            barrier.wait(5)
            try:
                revision = service.repository.read_connection(f"race-c{index}").revision
                service.delete_connection(
                    f"race-c{index}", expected_revision=revision, actor="qa"
                )
                return "deleted"
            except Exception as exc:  # noqa: BLE001
                return f"err:{type(exc).__name__}"

        def do_default() -> str:
            barrier.wait(5)
            try:
                revision = service.repository.read_settings().revision
                service.update_settings(
                    expected_revision=revision,
                    actor="qa",
                    default_worker_connection_ref=f"race-c{index}",
                )
                return "default_set"
            except Exception as exc:  # noqa: BLE001
                return f"err:{type(exc).__name__}"

        def do_agent() -> str:
            barrier.wait(5)
            try:
                current = store.read("agent", f"agent-c{index}")
                resources.update(
                    "agent",
                    f"agent-c{index}",
                    patch={"connection_ref": f"race-c{index}"},
                    expected_revision=current.revision,
                    actor="qa",
                )
                return "agent_bound"
            except Exception as exc:  # noqa: BLE001
                return f"err:{type(exc).__name__}"

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(do_delete), pool.submit(do_default), pool.submit(do_agent)]
            try:
                results = [f.result(timeout=25) for f in futures]
            except Exception:
                hangs += 1
                continue
        for item in results:
            if "LockConflict" in item:
                lock_errors.append(item)
        connection = service.repository.get_connection_or_none(f"race-c{index}")
        if results[0] == "deleted" and connection is not None:
            successes_missing_entity += 1
        refs = service.references_to(f"race-c{index}")
        if connection is None and refs.referenced:
            successes_missing_entity += 1
        reset_default_none(service)
        try:
            store.delete(
                "agent",
                f"agent-c{index}",
                expected_revision=store.read("agent", f"agent-c{index}").revision,
                actor="qa",
            )
        except Exception:
            pass

    return {
        "rounds": rounds,
        "hangs": hangs,
        "lock_conflict_errors": lock_errors,
        "success_with_missing_entity_or_dangling": successes_missing_entity,
        "note": "A LockConflict must never be reported as a successful delete.",
    }


# --------------------------------------------------------------------------- #
# 5. production host negative controls (unpatched)
# --------------------------------------------------------------------------- #
def production_host_controls() -> dict[str, Any]:
    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.proxy import LocalAuthProxy

    root = fresh_root("lg112r2-host-controls-")
    service, _store = service_at(root)
    rejected: dict[str, Any] = {}
    for index, endpoint in enumerate(
        [
            "http://127.0.0.1:9/v1",
            "https://custom.example/v1",
            "https://api.deepseek.com.evil.example/v1",
            "https://api.deepseek.com@evil.example/v1",
        ]
    ):
        connection_id = f"custom-{index}"
        view = service.create_connection(
            connection_id, base_url=endpoint, actor="qa", request_id=f"qa-host-{index}"
        )
        try:
            settings = service.repository.read_settings()
            service.update_settings(
                expected_revision=settings.revision,
                actor="qa",
                default_worker_connection_ref=connection_id,
            )
            default_error = "UNEXPECTED_SUCCESS"
        except Exception as exc:  # noqa: BLE001
            default_error = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
        try:
            LocalAuthProxy(
                credential=Secret("dummy-local-only"),
                upstream_url=endpoint + "/chat/completions",
            )
            proxy_error = "UNEXPECTED_SUCCESS"
        except Exception as exc:  # noqa: BLE001
            proxy_error = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
        rejected[endpoint] = {
            "executable_capability": view.get("capabilities", {}).get("executable"),
            "default_error": default_error,
            "proxy_error": proxy_error,
            "default_worker_after": service.repository.read_settings().default_worker_connection_ref,
        }

    # Positive control: the real DeepSeek host is still default-eligible.
    service.create_connection(
        "deepseek-positive",
        backend="openai-compat",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        auth_mode="proxy_api_key",
        credential_ref="deepseek-positive-key",
        credential_value="sk-positive-dummy-not-real",
        actor="qa",
        request_id="qa-positive",
    )
    settings = service.repository.read_settings()
    service.update_settings(
        expected_revision=settings.revision,
        actor="qa",
        default_worker_connection_ref="deepseek-positive",
    )
    positive = service.repository.read_settings().default_worker_connection_ref
    return {
        "rejected": rejected,
        "deepseek_positive_default_worker": positive,
        "note": "Production host allowlist/proxy policy is unchanged by the modal work.",
    }


# --------------------------------------------------------------------------- #
# 6. real HTTP API interleavings
# --------------------------------------------------------------------------- #
def _http_server() -> tuple[Any, int, threading.Thread, Any]:
    import uvicorn

    from qa_common import build_runtime

    base = Path(tempfile.mkdtemp(prefix="lg112r2-http-race-"))
    runtime = build_runtime(
        data_dir=base / "data", log_dir=base / "logs", upstream_port=_free_port()
    )
    port = _free_port()
    config = uvicorn.Config(
        runtime.app, host="127.0.0.1", port=port, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="r2-http-race", daemon=True)
    thread.start()
    deadline = time.time() + 30
    import httpx

    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1).status_code == 200:
                return runtime, port, thread, server
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
    raise RuntimeError("http race app did not become healthy")


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _login(base: str) -> Any:
    import httpx

    client = httpx.Client(base_url=base, timeout=30)
    response = client.post(
        "/api/v1/auth/login", json={"username": "qa-admin", "password": "qa-admin-pw"}
    )
    assert response.status_code == 200, response.text
    return client


def _create_api_connection(client: Any, connection_id: str) -> None:
    response = client.post(
        "/api/v1/settings/connections",
        json={
            "id": connection_id,
            "title": connection_id,
            "backend": "openai-compat",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com/v1",
            "auth_mode": "proxy_api_key",
            "credential_ref": f"{connection_id}-key",
            "credential_value": "sk-api-race-dummy-not-real",
        },
    )
    assert response.status_code == 201, response.text


def _api_revision(client: Any, connection_id: str) -> int:
    return client.get(f"/api/v1/settings/connections/{connection_id}").json()["revision"]


def http_api_interleavings() -> dict[str, Any]:
    runtime, port, thread, server = _http_server()
    base = f"http://127.0.0.1:{port}"
    origin = {"Origin": base}
    client = _login(base)
    results: dict[str, Any] = {}
    try:
        # ---------------- default: delete wins
        cid = "api-default-delete-first"
        _create_api_connection(client, cid)
        settings = client.get("/api/v1/settings").json()
        client.patch(
            "/api/v1/settings",
            json={
                "expected_revision": settings["revision"],
                "default_worker_connection_ref": None,
            },
            headers=origin,
        )
        entered = threading.Event()
        release = threading.Event()
        original_guard = runtime.service._guard_connection_delete

        def paused_guard(connection_id: str) -> None:
            original_guard(connection_id)
            entered.set()
            release.wait(10)

        runtime.service._guard_connection_delete = paused_guard  # type: ignore[method-assign]
        delete_outcome: list[Any] = []
        patch_outcome: list[Any] = []

        def del_call() -> None:
            response = client.request(
                "DELETE",
                f"/api/v1/settings/connections/{cid}",
                json={"expected_revision": _api_revision(client, cid)},
                headers=origin,
            )
            delete_outcome.append({"status": response.status_code, "body": response.text[:400]})

        def patch_call() -> None:
            settings = client.get("/api/v1/settings").json()
            response = client.patch(
                "/api/v1/settings",
                json={
                    "expected_revision": settings["revision"],
                    "default_worker_connection_ref": cid,
                },
                headers=origin,
            )
            patch_outcome.append({"status": response.status_code, "body": response.text[:400]})

        d = threading.Thread(target=del_call)
        d.start()
        assert entered.wait(10)
        p = threading.Thread(target=patch_call)
        p.start()
        time.sleep(0.4)
        patch_blocked = p.is_alive()
        release.set()
        d.join(10)
        p.join(10)
        runtime.service._guard_connection_delete = original_guard  # type: ignore[method-assign]
        final_settings = client.get("/api/v1/settings").json()
        final_view = client.get(f"/api/v1/settings/connections/{cid}")
        results["http_default_delete_first"] = {
            "delete": delete_outcome,
            "patch": patch_outcome,
            "patch_blocked_while_delete_paused": patch_blocked,
            "connection_exists": final_view.status_code == 200,
            "default_worker": final_settings.get("default_worker_connection_ref"),
            "dangling": (
                final_settings.get("default_worker_connection_ref") == cid
                and final_view.status_code != 200
            ),
        }

        # ---------------- default: writer wins
        cid2 = "api-default-writer-first"
        _create_api_connection(client, cid2)
        settings = client.get("/api/v1/settings").json()
        client.patch(
            "/api/v1/settings",
            json={
                "expected_revision": settings["revision"],
                "default_worker_connection_ref": None,
            },
            headers=origin,
        )
        validated = threading.Event()
        release2 = threading.Event()
        original_validate = runtime.service._validate_default_ref

        def paused_validate(ref: Any, *, role: str) -> None:
            original_validate(ref, role=role)
            if ref == cid2:
                validated.set()
                release2.wait(10)

        runtime.service._validate_default_ref = paused_validate  # type: ignore[method-assign]
        delete_outcome = []
        patch_outcome = []

        def patch_call2() -> None:
            settings = client.get("/api/v1/settings").json()
            response = client.patch(
                "/api/v1/settings",
                json={
                    "expected_revision": settings["revision"],
                    "default_worker_connection_ref": cid2,
                },
                headers=origin,
            )
            patch_outcome.append({"status": response.status_code, "body": response.text[:400]})

        def del_call2() -> None:
            response = client.request(
                "DELETE",
                f"/api/v1/settings/connections/{cid2}",
                json={"expected_revision": _api_revision(client, cid2)},
                headers=origin,
            )
            delete_outcome.append({"status": response.status_code, "body": response.text[:400]})

        p2 = threading.Thread(target=patch_call2)
        p2.start()
        assert validated.wait(10)
        d2 = threading.Thread(target=del_call2)
        d2.start()
        time.sleep(0.4)
        delete_blocked = d2.is_alive()
        release2.set()
        p2.join(10)
        d2.join(10)
        runtime.service._validate_default_ref = original_validate  # type: ignore[method-assign]
        final_settings = client.get("/api/v1/settings").json()
        final_view = client.get(f"/api/v1/settings/connections/{cid2}")
        results["http_default_writer_first"] = {
            "patch": patch_outcome,
            "delete": delete_outcome,
            "delete_blocked_while_writer_paused": delete_blocked,
            "connection_exists": final_view.status_code == 200,
            "default_worker": final_settings.get("default_worker_connection_ref"),
            "dangling": (
                final_settings.get("default_worker_connection_ref") == cid2
                and final_view.status_code != 200
            ),
        }

        # ---------------- agent: delete wins
        cid3 = "api-agent-delete-first"
        _create_api_connection(client, cid3)
        # The QA seed creates agent "qa-agent"; use the real controlled PATCH.
        agent_id = "qa-agent"
        entered = threading.Event()
        release3 = threading.Event()
        original_guard = runtime.service._guard_connection_delete

        def paused_guard3(connection_id: str) -> None:
            original_guard(connection_id)
            entered.set()
            release3.wait(10)

        runtime.service._guard_connection_delete = paused_guard3  # type: ignore[method-assign]
        delete_outcome = []
        patch_outcome = []

        def del_call3() -> None:
            response = client.request(
                "DELETE",
                f"/api/v1/settings/connections/{cid3}",
                json={"expected_revision": _api_revision(client, cid3)},
                headers=origin,
            )
            delete_outcome.append({"status": response.status_code, "body": response.text[:400]})

        def patch_agent() -> None:
            revision = client.get(f"/api/v1/resources/agent/{agent_id}").json()["revision"]
            response = client.patch(
                f"/api/v1/resources/agent/{agent_id}",
                json={"expected_revision": revision, "patch": {"connection_ref": cid3}},
                headers=origin,
            )
            patch_outcome.append({"status": response.status_code, "body": response.text[:400]})

        d3 = threading.Thread(target=del_call3)
        d3.start()
        assert entered.wait(10)
        pa = threading.Thread(target=patch_agent)
        pa.start()
        time.sleep(0.4)
        agent_blocked = pa.is_alive()
        release3.set()
        d3.join(10)
        pa.join(10)
        runtime.service._guard_connection_delete = original_guard  # type: ignore[method-assign]
        final_view = client.get(f"/api/v1/settings/connections/{cid3}")
        agent_view = client.get(f"/api/v1/resources/agent/{agent_id}").json()
        results["http_agent_delete_first"] = {
            "delete": delete_outcome,
            "patch": patch_outcome,
            "patch_blocked_while_delete_paused": agent_blocked,
            "connection_exists": final_view.status_code == 200,
            "agent_connection_ref": agent_view.get("connection_ref"),
            "dangling": (
                agent_view.get("connection_ref") == cid3 and final_view.status_code != 200
            ),
        }
    finally:
        client.close()
        server.should_exit = True
        thread.join(10)
        try:
            runtime.upstream.stop()
        except Exception:  # noqa: BLE001
            pass
    return results


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    RESULTS["source_head"] = _git_head()
    RESULTS["natural_default"] = natural_default_stress(200)
    RESULTS["natural_agent"] = natural_agent_stress(120)
    RESULTS["service_default_delete_first"] = _delete_first("default")
    RESULTS["service_default_writer_first"] = _writer_first("default")
    RESULTS["service_agent_delete_first"] = _delete_first("agent")
    RESULTS["service_agent_writer_first"] = _writer_first("agent")
    RESULTS["raw_store_bypass"] = raw_store_bypass_outside_guarantee()
    RESULTS["lock_contention"] = lock_contention(12)
    RESULTS["production_host_controls"] = production_host_controls()
    RESULTS["http_api"] = http_api_interleavings()

    # ---- assertions (supported paths only) ----
    assert RESULTS["natural_default"]["dangling_observed"] == 0
    assert RESULTS["natural_agent"]["dangling_observed"] == 0
    for name in (
        "service_default_delete_first",
        "service_default_writer_first",
        "service_agent_delete_first",
        "service_agent_writer_first",
    ):
        case = RESULTS[name]
        assert case["dangling_default"] is False, case
        assert case["dangling_agent"] is False, case
        assert case["writer_was_blocked_while_delete_held_shared_lock"] if name.endswith(
            "delete_first"
        ) else True
    # both winner orders really produce different, honest outcomes
    assert RESULTS["service_default_delete_first"]["connection_exists"] is False
    assert RESULTS["service_default_writer_first"]["connection_exists"] is True
    assert RESULTS["service_agent_delete_first"]["connection_exists"] is False
    assert RESULTS["service_agent_writer_first"]["connection_exists"] is True
    assert RESULTS["service_default_delete_first"]["writer_result"][0]["status"] == "rejected"
    assert RESULTS["service_default_writer_first"]["writer_result"][0]["status"] == "committed"
    assert RESULTS["service_agent_delete_first"]["writer_result"][0]["status"] == "rejected"
    assert RESULTS["service_agent_writer_first"]["writer_result"][0]["status"] == "committed"
    # writer-first must make DELETE refuse, not delete a referenced record
    assert RESULTS["service_default_writer_first"]["delete_result"][0].get("error")
    assert RESULTS["service_agent_writer_first"]["delete_result"][0].get("error")

    assert RESULTS["lock_contention"]["hangs"] == 0
    assert RESULTS["lock_contention"]["lock_conflict_errors"] == []
    assert RESULTS["lock_contention"]["success_with_missing_entity_or_dangling"] == 0

    for endpoint, record in RESULTS["production_host_controls"]["rejected"].items():
        assert record["executable_capability"] is False, (endpoint, record)
        assert record["default_error"] != "UNEXPECTED_SUCCESS", (endpoint, record)
        assert record["proxy_error"] != "UNEXPECTED_SUCCESS", (endpoint, record)
        assert record["default_worker_after"] is None, (endpoint, record)
    assert (
        RESULTS["production_host_controls"]["deepseek_positive_default_worker"]
        == "deepseek-positive"
    )

    for name in ("http_default_delete_first", "http_default_writer_first", "http_agent_delete_first"):
        case = RESULTS["http_api"][name]
        assert case["dangling"] is False, case
    assert RESULTS["http_api"]["http_default_delete_first"]["patch_blocked_while_delete_paused"] is True
    assert RESULTS["http_api"]["http_default_writer_first"]["delete_blocked_while_writer_paused"] is True
    assert RESULTS["http_api"]["http_agent_delete_first"]["patch_blocked_while_delete_paused"] is True

    return 0


def _git_head() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "-C", str(HERE.parents[2]), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    import sys
    import traceback

    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001
        RESULTS["assertion_error"] = traceback.format_exc()
        traceback.print_exc()
        raise
    finally:
        out = HERE / "logs" / "concurrency-r2-probe.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(RESULTS, indent=2, sort_keys=True, default=str) + "\n")
