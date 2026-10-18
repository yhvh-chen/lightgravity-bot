"""LG-243 worker execution history at Run planning (unit evidence).

The worker entry is a *planned/frozen connection* snapshot, not proof that a
real worker model invocation happened.  These tests use the in-process fake
executor and assert the strict allowlist + historical immutability.
"""

from __future__ import annotations

from lightgravity.adapter import ConnectionPin, ResourceCompiler
from lightgravity.coordinator import GraphDispatcher, RoleCatalog
from lightgravity.store import FileStore

from graph_helpers import (
    FakeGraphExecutor,
    build_environment,
    create_agent,
    create_resource,
    make_dispatch_setup,
)

FLEX_CATALOG = RoleCatalog({"implementation": ["flex"], "verification": ["flex"]})


class _Provider:
    def __init__(self, pin: ConnectionPin, names: dict[str, str]) -> None:
        self.pin = pin
        self.names = names
        self.current = True

    def resolve_default(self, role: str) -> ConnectionPin | None:
        return self.pin

    def pinned_is_current(self, pinned: ConnectionPin) -> bool:
        return self.current

    def connection_name(self, connection_id: str) -> str | None:
        return self.names.get(connection_id)


def _pin(store: FileStore, connection_id: str) -> ConnectionPin:
    versioned = store.read("connection", connection_id)
    entity = versioned.entity
    return ConnectionPin(
        connection_id=connection_id,
        role="worker",
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        backend=str(entity["backend"]),
        model=entity.get("model"),
        base_url=entity.get("base_url"),
        credential_ref=entity.get("credential_ref"),
        credential_version="cred_v1",
        config_hash="pin-config",
    )


def _prepare(store: FileStore) -> None:
    build_environment(store)
    create_resource(
        store,
        "connection",
        "fallback-a",
        backend="openai-compat",
        model="fallback-model-a",
        credential_ref="fallback-key-a",
        base_url="https://api.deepseek.com/v1",
        title="Worker A",
    )
    create_resource(
        store,
        "connection",
        "fallback-b",
        backend="openai-compat",
        model="fallback-model-b",
        credential_ref="fallback-key-b",
        base_url="https://api.deepseek.com/v1",
        title="Worker B",
    )
    create_agent(
        store,
        "flex",
        skill_refs=["implementation", "verification"],
        tool_refs=("view-file",),
        extra={"connection_ref": None},
    )


async def test_run_records_planned_worker_connection_and_keeps_history(
    store: FileStore,
) -> None:
    _prepare(store)
    provider = _Provider(_pin(store, "fallback-a"), {"fallback-a": "Worker A"})
    dispatcher = GraphDispatcher(
        store,
        FakeGraphExecutor(),
        catalog=FLEX_CATALOG,
        compiler=ResourceCompiler(store),
        connections=provider,
    )
    _task_id, run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, lambda _event: None)
    assert outcome.state == "succeeded"

    run = store.read("run", run_id).entity
    worker = run["execution_evidence"]["worker"]
    assert worker == {
        "role": "worker",
        "connection_id": "fallback-a",
        "name": "Worker A",
        "provider": "openai-compat",
        "model": "fallback-model-a",
        "status": "recorded",
        "source": "run_default_pin",
        "stage": "planned",
        "evidence_kind": "frozen_run_connection",
        "captured_at": worker["captured_at"],
        "reason": None,
    }
    assert isinstance(worker["captured_at"], str) and worker["captured_at"]
    # Strict allowlist: no credential ref/version, base URL or config hash.
    for forbidden in (
        "credential_ref",
        "credential_version",
        "base_url",
        "config_hash",
        "credential_value",
    ):
        assert forbidden not in worker

    # Changing the current default/title after the Run must not rewrite history.
    provider.pin = _pin(store, "fallback-b")
    provider.names["fallback-a"] = "Renamed Worker A"
    assert store.read("run", run_id).entity["execution_evidence"]["worker"] == worker


async def test_new_run_records_new_default_while_old_run_keeps_its_own(
    store: FileStore,
) -> None:
    _prepare(store)
    provider = _Provider(_pin(store, "fallback-a"), {"fallback-a": "Worker A", "fallback-b": "Worker B"})
    dispatcher = GraphDispatcher(
        store,
        FakeGraphExecutor(),
        catalog=FLEX_CATALOG,
        compiler=ResourceCompiler(store),
        connections=provider,
    )
    _task_id, first_run, controller, context = make_dispatch_setup(store)
    assert (await dispatcher.dispatch(context, controller, lambda _event: None)).state == "succeeded"
    first_worker = store.read("run", first_run).entity["execution_evidence"]["worker"]

    provider.pin = _pin(store, "fallback-b")
    _task_id2, second_run, controller2, context2 = make_dispatch_setup(store)
    assert (await dispatcher.dispatch(context2, controller2, lambda _event: None)).state == "succeeded"
    second_worker = store.read("run", second_run).entity["execution_evidence"]["worker"]

    assert first_worker["connection_id"] == "fallback-a"
    assert first_worker["name"] == "Worker A"
    assert second_worker["connection_id"] == "fallback-b"
    assert second_worker["name"] == "Worker B"
    assert store.read("run", first_run).entity["execution_evidence"]["worker"] == first_worker
