"""GraphDispatcher default-connection pinning for an active Run (LG-020).

Unit evidence with the in-process fake executor.  It proves that the worker
default connection is frozen at recruitment: a later Settings default change is
ignored by the active Run, and a credential rotation is reported as drift
instead of being silently used by the next subtask.
"""

from __future__ import annotations

from lightgravity.adapter import ConnectionPin, ExecuteRequest, ExecutorResult, ResourceCompiler
from lightgravity.coordinator import GraphDispatcher, RoleCatalog
from lightgravity.store import FileStore

from graph_helpers import (
    FakeGraphExecutor,
    build_environment,
    create_agent,
    create_resource,
    make_dispatch_setup,
    run_state,
)

FLEX_CATALOG = RoleCatalog({"implementation": ["flex"], "verification": ["flex"]})


class _Provider:
    """A controllable stand-in for the settings-layer pin provider."""

    def __init__(self, pin: ConnectionPin) -> None:
        self.pin = pin
        self.current = True
        self.resolved_roles: list[str] = []

    def resolve_default(self, role: str) -> ConnectionPin | None:
        self.resolved_roles.append(role)
        return self.pin

    def pinned_is_current(self, pinned: ConnectionPin) -> bool:
        return self.current


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
    )
    create_resource(
        store,
        "connection",
        "fallback-b",
        backend="openai-compat",
        model="fallback-model-b",
        credential_ref="fallback-key-b",
        base_url="https://api.deepseek.com/v1",
    )
    create_agent(
        store,
        "flex",
        skill_refs=["implementation", "verification"],
        tool_refs=("view-file",),
        extra={"connection_ref": None},
    )


async def test_active_run_ignores_new_default_connection(store: FileStore) -> None:
    _prepare(store)
    provider = _Provider(_pin(store, "fallback-a"))
    executor = FakeGraphExecutor()
    original_responder = executor._responder  # noqa: SLF001 - test harness

    def responder(request: ExecuteRequest) -> ExecutorResult:
        # Simulate the operator changing the default mid-Run.
        provider.pin = _pin(store, "fallback-b")
        return original_responder(request)

    executor._responder = responder  # noqa: SLF001
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=FLEX_CATALOG,
        compiler=ResourceCompiler(store),
        connections=provider,
    )
    _task_id, run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, lambda _event: None)

    assert outcome.state == "succeeded"
    assert len(executor.requests) == 2
    assert {request.connection_ref for request in executor.requests} == {"fallback-a"}
    assert provider.resolved_roles == ["worker"]
    run = store.read("run", run_id).entity
    assert run["connection_pin"]["connection_id"] == "fallback-a"
    assert run_state(store, run_id) == "executing"  # Coordinator writes the terminal state


async def test_credential_rotation_fails_the_next_subtask_instead_of_swapping(
    store: FileStore,
) -> None:
    _prepare(store)
    provider = _Provider(_pin(store, "fallback-a"))
    executor = FakeGraphExecutor()
    original_responder = executor._responder  # noqa: SLF001 - test harness

    def responder(request: ExecuteRequest) -> ExecutorResult:
        # Simulate a credential rotation under the same connection ref.
        provider.current = False
        return original_responder(request)

    executor._responder = responder  # noqa: SLF001
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=FLEX_CATALOG,
        compiler=ResourceCompiler(store),
        connections=provider,
    )
    _task_id, _run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, lambda _event: None)

    assert outcome.state == "failed"
    assert outcome.failure_code == "config_invalid"
    # The second subtask never reached the executor: no silent hot-swap.
    assert len(executor.requests) == 1


async def test_new_run_uses_the_new_default_connection(store: FileStore) -> None:
    _prepare(store)
    provider = _Provider(_pin(store, "fallback-a"))
    executor = FakeGraphExecutor()
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=FLEX_CATALOG,
        compiler=ResourceCompiler(store),
        connections=provider,
    )

    _task_id, _run_id, controller, context = make_dispatch_setup(store)
    first = await dispatcher.dispatch(context, controller, lambda _event: None)
    assert first.state == "succeeded"
    first_count = len(executor.requests)
    assert {request.connection_ref for request in executor.requests} == {"fallback-a"}

    # A *new* Task/Run must pick up the new default.
    provider.pin = _pin(store, "fallback-b")
    _task_id2, _run_id2, controller2, context2 = make_dispatch_setup(store)
    second = await dispatcher.dispatch(context2, controller2, lambda _event: None)
    assert second.state == "succeeded"
    new_requests = executor.requests[first_count:]
    assert new_requests
    assert {request.connection_ref for request in new_requests} == {"fallback-b"}
