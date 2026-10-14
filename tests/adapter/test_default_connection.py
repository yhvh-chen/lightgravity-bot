"""Default-connection resolution and Run pinning in the compiler (LG-020).

No network, no real model.  These tests pin the precedence rule explicitly:

1. an explicit ``agent.connection_ref`` always wins and an invalid one never
   silently falls back to a default;
2. without an explicit ref the Run's frozen pin is used;
3. without a pin the injected role default is used;
4. a stale pin is a hard error instead of a silent connection swap.
"""

from __future__ import annotations

from lightgravity.adapter import (
    AdapterConfigInvalid,
    CompileConstraints,
    ConnectionPin,
    ReferenceInvalid,
    ResourceCompiler,
)
from lightgravity.store import FileStore

from helpers import build_agent, build_basic_environment, create_resource


def _pin(store: FileStore, connection_id: str, *, credential_version: str = "cred_v1") -> ConnectionPin:
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
        credential_version=credential_version,
        config_hash="pin-config",
    )


class _Resolver:
    def __init__(self, pin: ConnectionPin | None) -> None:
        self.pin = pin
        self.current = True
        self.calls: list[str] = []

    def resolve_default(self, role: str) -> ConnectionPin | None:
        self.calls.append(role)
        return self.pin

    def pinned_is_current(self, pinned: ConnectionPin) -> bool:
        return self.current


def test_explicit_connection_ref_wins_over_default(
    store: FileStore, registry
) -> None:
    build_basic_environment(store)
    create_resource(
        store,
        "connection",
        "fallback",
        backend="openai-compat",
        model="fallback-model",
        credential_ref="fallback-key",
        base_url="https://api.deepseek.com/v1",
    )
    resolver = _Resolver(_pin(store, "fallback"))
    compiler = ResourceCompiler(store, registry=registry, default_connections=resolver)
    build_agent(store, connection_ref="primary")

    compiled = compiler.compile_agent("developer")

    assert compiled.connection is not None
    assert compiled.connection.ref == "primary"
    assert compiled.connection.connection_source == "explicit"
    assert resolver.calls == []  # never consulted for an explicit ref


def test_invalid_explicit_connection_ref_does_not_fall_back(
    store: FileStore, registry
) -> None:
    build_basic_environment(store)
    resolver = _Resolver(_pin(store, "primary"))
    compiler = ResourceCompiler(store, registry=registry, default_connections=resolver)
    build_agent(store, connection_ref="ghost")

    try:
        compiler.compile_agent("developer")
    except ReferenceInvalid as exc:
        assert exc.kind == "connection"
        assert exc.ref == "ghost"
    else:  # pragma: no cover - must raise
        raise AssertionError("an invalid explicit connection_ref must raise")
    assert resolver.calls == []


def test_missing_ref_uses_role_default_and_records_credential_version(
    store: FileStore, registry
) -> None:
    build_basic_environment(store)
    resolver = _Resolver(_pin(store, "primary", credential_version="cred_default"))
    compiler = ResourceCompiler(store, registry=registry, default_connections=resolver)
    build_agent(store, connection_ref=None)

    compiled = compiler.compile_agent("developer")

    assert compiled.connection is not None
    assert compiled.connection.ref == "primary"
    assert compiled.connection.connection_source == "default"
    assert compiled.connection.credential_version == "cred_default"
    assert compiled.executable is True
    assert resolver.calls == ["worker"]


def test_run_pin_is_used_without_consulting_current_default(
    store: FileStore, registry
) -> None:
    build_basic_environment(store)
    create_resource(
        store,
        "connection",
        "fallback",
        backend="openai-compat",
        model="fallback-model",
        credential_ref="fallback-key",
        base_url="https://api.deepseek.com/v1",
    )
    resolver = _Resolver(_pin(store, "fallback"))
    compiler = ResourceCompiler(store, registry=registry, default_connections=resolver)
    build_agent(store, connection_ref=None)

    pin = _pin(store, "primary", credential_version="cred_run")
    compiled = compiler.compile_agent(
        "developer",
        constraints=CompileConstraints(connection_pin=pin),
    )

    assert compiled.connection is not None
    assert compiled.connection.ref == "primary"
    assert compiled.connection.connection_source == "pinned"
    assert compiled.connection.credential_version == "cred_run"
    assert resolver.calls == []


def test_stale_pin_is_a_hard_error(store: FileStore, registry) -> None:
    build_basic_environment(store)
    compiler = ResourceCompiler(store, registry=registry)
    build_agent(store, connection_ref=None)
    pin = _pin(store, "primary")
    # Mutating the connection invalidates the frozen pin.
    store.write(
        "connection",
        "primary",
        {"model": "changed-after-pin"},
        expected_revision=store.read("connection", "primary").revision,
        actor="test",
    )

    try:
        compiler.compile_agent("developer", constraints=CompileConstraints(connection_pin=pin))
    except AdapterConfigInvalid as exc:
        assert "changed after it was selected" in exc.message
    else:  # pragma: no cover - must raise
        raise AssertionError("a stale pin must not silently compile to the new connection")


def test_no_ref_no_default_is_connection_missing(store: FileStore, registry) -> None:
    build_basic_environment(store)
    compiler = ResourceCompiler(store, registry=registry)
    build_agent(store, connection_ref=None)

    compiled = compiler.compile_agent("developer")

    assert compiled.connection is None
    assert "connection_missing" in compiled.executable_reasons
