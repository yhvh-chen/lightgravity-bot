"""Resources only reference secrets; plaintext values are rejected/never copied.

Covers docs/08 §9 (config failure) and §10 (credential_ref boundary).
"""

from __future__ import annotations

import json

import pytest

from lightgravity.adapter import AdapterConfigInvalid, CompileConstraints, ResourceCompiler
from lightgravity.store import FileStore

from helpers import build_agent, build_basic_environment, create_resource

_FAKE_SECRET = "sk-live-should-never-appear-12345"


def test_plaintext_secret_in_connection_is_rejected(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    create_resource(
        store,
        "connection",
        "leaky",
        backend="openai-compat",
        base_url="http://127.0.0.1:1/v1",
        api_key=_FAKE_SECRET,
    )
    build_agent(store, connection_ref="leaky")

    with pytest.raises(AdapterConfigInvalid) as excinfo:
        compiler.compile_agent("developer")

    error = excinfo.value
    rendered = f"{error} {error.details!r}"
    assert _FAKE_SECRET not in rendered
    assert error.diagnostics[0]["code"] == "secret_in_resource"
    assert error.diagnostics[0]["detail"]["fields"] == ["api_key"]


def test_compiled_config_keeps_only_the_credential_ref(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store, credential_ref="worker-default")
    build_agent(store)

    compiled = compiler.compile_agent("developer")
    payload = compiled.to_dict()
    serialized = json.dumps(payload)

    assert payload["connection"]["credential_ref"] == "worker-default"
    assert _FAKE_SECRET not in serialized
    # No secret-bearing key is emitted; ``supports_api_key_field`` is a bool flag.
    assert '"api_key"' not in serialized
