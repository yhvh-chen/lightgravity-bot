#!/usr/bin/env python3
"""LG-112 reference/delete concurrency probe.

The product's DELETE guard runs under the *connection* entity lock while the
default/agent writers use the *settings/agent* entity locks.  This probe:

1. attempts a natural concurrent schedule many times, and
2. uses a QA-only widened schedule (pause after the guard read, then commit the
   reference, then unlink) to deterministically demonstrate whether that ordering
   is possible in the candidate code.

It never edits product source; the pause is a runtime wrapper on one service
instance inside this isolated QA process.
"""

from __future__ import annotations

import json
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.settings.models import ROLE_WORKER
from lightgravity.store import EntityNotFound, FileStore

RESULTS: dict[str, Any] = {}


def service_at(root: Path) -> tuple[ConnectionService, FileStore]:
    data = root / "data"
    store = FileStore(data, data / "workspaces")
    service = ConnectionService(
        store, secret_store=FileSecretStore(root / "secrets")
    )
    return service, store


def create_eligible(service: ConnectionService, connection_id: str) -> None:
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


def natural_attempt(iterations: int = 200) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="lg112-natural-race-"))
    service, store = service_at(root)
    create_eligible(service, "race-natural")
    service.update_settings(
        expected_revision=None,
        actor="qa",
        default_worker_connection_ref=None,
    )
    dangling = 0
    outcome_counts: dict[str, int] = {}
    for index in range(iterations):
        # Reset to a clean, existing, unreferenced connection each iteration.
        try:
            service.repository.delete_connection(
                "race-natural", expected_revision=service.repository.read_connection("race-natural").revision, actor="qa"
            )
        except Exception:
            pass
        create_eligible(service, "race-natural")
        settings = service.repository.read_settings()
        service._repo.write_settings(
            {"default_worker_connection_ref": None},
            expected_revision=settings.revision,
            actor="qa",
        )
        barrier = threading.Barrier(2)

        def do_delete() -> str:
            barrier.wait(5)
            try:
                service.delete_connection(
                    "race-natural",
                    expected_revision=service.repository.read_connection("race-natural").revision,
                    actor="qa",
                )
                return "deleted"
            except Exception as exc:  # noqa: BLE001 - outcome data
                return f"delete_error:{type(exc).__name__}"

        def do_default() -> str:
            barrier.wait(5)
            try:
                service.update_settings(
                    expected_revision=service.repository.read_settings().revision,
                    actor="qa",
                    default_worker_connection_ref="race-natural",
                )
                return "default_set"
            except Exception as exc:  # noqa: BLE001 - outcome data
                return f"default_error:{type(exc).__name__}"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [pool.submit(do_delete), pool.submit(do_default)]
            results = [f.result(timeout=20) for f in outcomes]
        for item in results:
            outcome_counts[item] = outcome_counts.get(item, 0) + 1
        settings = service.repository.read_settings()
        connection = service.repository.get_connection_or_none("race-natural")
        if settings.default_worker_connection_ref == "race-natural" and connection is None:
            dangling += 1
            break
    return {
        "iterations": iterations,
        "dangling_observed": dangling,
        "outcomes": outcome_counts,
    }


def orchestrated_default_race() -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="lg112-orchestrated-default-"))
    service, store = service_at(root)
    create_eligible(service, "race-default")
    service.update_settings(
        expected_revision=None,
        actor="qa",
        default_worker_connection_ref=None,
    )
    settings_revision = service.repository.read_settings().revision

    entered = threading.Event()
    release = threading.Event()
    original_guard = service._guard_connection_delete

    def paused_guard(connection_id: str) -> None:
        # Product guard reads the current references...
        original_guard(connection_id)
        # ...then this QA-only seam pauses before the unlink, widening the
        # window in which another entity's writer can commit a new reference.
        entered.set()
        if not release.wait(10):
            raise RuntimeError("orchestrated race release timeout")

    service._guard_connection_delete = paused_guard  # type: ignore[method-assign]
    delete_error: list[str] = []

    def do_delete() -> None:
        try:
            service.delete_connection(
                "race-default",
                expected_revision=service.repository.read_connection("race-default").revision,
                actor="qa",
            )
        except Exception as exc:  # noqa: BLE001 - outcome data
            delete_error.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=do_delete, name="lg112-delete-race")
    thread.start()
    assert entered.wait(10), "delete guard did not run"
    default_result: dict[str, Any]
    try:
        service.update_settings(
            expected_revision=settings_revision,
            actor="qa",
            default_worker_connection_ref="race-default",
        )
        default_result = {"status": "default_set"}
    except Exception as exc:  # noqa: BLE001 - outcome data
        default_result = {"status": f"error:{type(exc).__name__}: {exc}"}
    release.set()
    thread.join(10)
    settings = service.repository.read_settings()
    connection = service.repository.get_connection_or_none("race-default")
    refs = service.references_to("race-default")
    resolve_error: str | None = None
    try:
        service.resolve_default(ROLE_WORKER)
    except Exception as exc:  # noqa: BLE001 - evidence
        resolve_error = f"{type(exc).__name__}: {exc}"
    return {
        "delete_thread_errors": delete_error,
        "default_update": default_result,
        "settings_default_worker": settings.default_worker_connection_ref,
        "connection_exists": connection is not None,
        "references_after": refs.to_dict(),
        "resolve_default_error": resolve_error,
        "dangling_default": (
            settings.default_worker_connection_ref == "race-default"
            and connection is None
        ),
    }


def orchestrated_agent_race() -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="lg112-orchestrated-agent-"))
    service, store = service_at(root)
    create_eligible(service, "race-agent")
    entered = threading.Event()
    release = threading.Event()
    original_guard = service._guard_connection_delete

    def paused_guard(connection_id: str) -> None:
        original_guard(connection_id)
        entered.set()
        if not release.wait(10):
            raise RuntimeError("orchestrated race release timeout")

    service._guard_connection_delete = paused_guard  # type: ignore[method-assign]
    delete_error: list[str] = []

    def do_delete() -> None:
        try:
            service.delete_connection(
                "race-agent",
                expected_revision=service.repository.read_connection("race-agent").revision,
                actor="qa",
            )
        except Exception as exc:  # noqa: BLE001 - outcome data
            delete_error.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=do_delete, name="lg112-delete-agent-race")
    thread.start()
    assert entered.wait(10), "delete guard did not run"
    agent_result: dict[str, Any]
    try:
        store.create(
            "agent",
            "race-agent-ref",
            {
                "title": "Race agent",
                "enabled": True,
                "connection_ref": "race-agent",
            },
            actor="qa",
            request_id="qa-race-agent",
        )
        agent_result = {"status": "agent_created"}
    except Exception as exc:  # noqa: BLE001 - outcome data
        agent_result = {"status": f"error:{type(exc).__name__}: {exc}"}
    release.set()
    thread.join(10)
    connection = service.repository.get_connection_or_none("race-agent")
    refs = service.references_to("race-agent")
    return {
        "delete_thread_errors": delete_error,
        "agent_creation": agent_result,
        "connection_exists": connection is not None,
        "references_after": refs.to_dict(),
        "dangling_agent_ref": bool(refs.agent_refs) and connection is None,
    }


def main() -> int:
    RESULTS["natural"] = natural_attempt(iterations=150)
    RESULTS["orchestrated_default"] = orchestrated_default_race()
    RESULTS["orchestrated_agent"] = orchestrated_agent_race()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        out = Path(__file__).resolve().parent / "logs" / "concurrency-probe.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(RESULTS, indent=2, sort_keys=True) + "\n", encoding="utf-8")
