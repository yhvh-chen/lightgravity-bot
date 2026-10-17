"""LG-111 host policy: openai-compat enum alone is not execution eligibility."""

from __future__ import annotations

from lightgravity.adapter import ResourceCompiler
from lightgravity.store import FileStore

from helpers import build_agent, build_basic_environment


def test_custom_openai_host_compiles_but_is_not_executable(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(
        store,
        base_url="https://custom.example/v1",
        credential_ref="custom-key",
    )
    build_agent(store)
    compiled = compiler.compile_agent("developer")
    assert compiled.executable is False
    assert "endpoint_not_authorized" in compiled.executable_reasons
    assert compiled.connection is not None
    assert compiled.connection.executable is False
    assert compiled.connection.vendor_verified is False
    assert compiled.connection.verified is False


def test_deepseek_host_stays_executable(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(
        store,
        base_url="https://api.deepseek.com/v1",
        credential_ref="deepseek-key",
    )
    build_agent(store)
    compiled = compiler.compile_agent("developer")
    assert compiled.executable is True
    assert compiled.executable_reasons == ()
    assert compiled.connection is not None
    assert compiled.connection.executable is True
    assert compiled.connection.vendor_verified is True


def test_loopback_constructor_test_seam_is_preserved(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)  # loopback fake upstream used by adapter tests
    build_agent(store)
    compiled = compiler.compile_agent("developer")
    assert compiled.executable is True
    assert compiled.connection is not None
    assert compiled.connection.executable is True
