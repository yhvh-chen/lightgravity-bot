"""Reference resolution, versioning and hashing for compiled agents.

Covers docs/08 §8 (adapter boundary) and docs/02 §6 (config-to-run flow).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lightgravity.adapter import (
    AdapterConfigInvalid,
    CompiledAgentConfig,
    CompileConstraints,
    ReferenceInvalid,
    ResourceCompiler,
)
from lightgravity.store import FileStore

from helpers import build_agent, build_basic_environment, create_resource


def test_full_compile_resolves_refs_and_versions(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store)

    compiled = compiler.compile_agent("developer")

    assert isinstance(compiled, CompiledAgentConfig)
    assert compiled.agent_id == "developer"
    assert compiled.connection is not None
    assert compiled.connection.credential_ref == "worker-default"
    assert compiled.connection.verified is True
    assert compiled.session_profile is not None
    assert compiled.session_profile.continuation_mode == "create_or_resume"
    assert compiled.skills.source == "paths"
    assert compiled.skills.refs == ("implementation", "test-report")
    assert len(compiled.skills.paths) == 2
    assert all(Path(path).is_dir() for path in compiled.skills.paths)
    assert [tool.ref for tool in compiled.tools] == ["view-file", "edit-file"]
    assert [hook.handler_id for hook in compiled.hooks] == ["session-log"]
    assert compiled.executable is True
    assert compiled.executable_reasons == ()

    kinds = {version.kind for version in compiled.resource_versions}
    assert kinds == {"agent", "connection", "conversation", "skill", "tool", "hook"}
    assert all(version.revision == 0 for version in compiled.resource_versions)
    assert len(compiled.config_hash) == 64


def test_config_hash_is_stable_and_version_sensitive(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store)

    first = compiler.compile_agent("developer")
    second = compiler.compile_agent("developer")
    assert first.config_hash == second.config_hash

    store.write("agent", "developer", {"title": "renamed"}, expected_revision=0, actor="test")
    third = compiler.compile_agent("developer")
    assert third.config_hash != first.config_hash


def test_missing_connection_is_unavailable_not_fatal(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, connection_ref=None)

    compiled = compiler.compile_agent("developer")

    assert compiled.connection is None
    assert compiled.executable is False
    assert "connection_missing" in compiled.executable_reasons
    assert any(item.reason == "connection_missing" for item in compiled.unavailable)


def test_unverified_backend_blocks_execution_but_compiles(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store, backend="gemini", credential_ref="gemini-default")
    build_agent(store)

    compiled = compiler.compile_agent("developer")

    assert compiled.connection is not None
    assert compiled.connection.verified is False
    assert compiled.executable is False
    assert "backend_unverified" in compiled.executable_reasons


def test_missing_credential_ref_is_reported(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store, credential_ref=None)
    build_agent(store)

    compiled = compiler.compile_agent("developer")

    assert compiled.connection is not None
    assert compiled.connection.credential_ref is None
    assert "credential_unresolved" in compiled.executable_reasons


def test_unknown_tool_reference_is_invalid(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, tool_refs=["missing-tool"])

    with pytest.raises(ReferenceInvalid) as excinfo:
        compiler.compile_agent("developer")
    assert excinfo.value.kind == "tool"
    assert excinfo.value.ref == "missing-tool"


def test_unknown_hook_handler_is_invalid(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    create_resource(store, "hook", "broken", handler="not-registered")
    build_agent(store, hook_refs=["broken"])

    with pytest.raises(ReferenceInvalid) as excinfo:
        compiler.compile_agent("developer")
    assert excinfo.value.kind == "hook"


def test_unknown_backend_is_a_config_error(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store, backend="mystery")
    build_agent(store)

    with pytest.raises(AdapterConfigInvalid):
        compiler.compile_agent("developer")


def test_inline_skills_carry_body_content(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, skills_source="inline")

    compiled = compiler.compile_agent("developer")

    assert compiled.skills.source == "inline"
    assert compiled.skills.paths == ()
    names = {item["name"] for item in compiled.skills.inline}
    assert names == {"implementation", "test-report"}
    assert all(item["content"] for item in compiled.skills.inline)


def test_illegal_skill_source_rejected(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, skills_source="database")

    with pytest.raises(AdapterConfigInvalid) as excinfo:
        compiler.compile_agent("developer")
    assert excinfo.value.diagnostics[0]["code"] == "skills_source_invalid"


def test_parallel_skill_refs_field_rejected(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    create_resource(
        store,
        "agent",
        "legacy",
        connection_ref="primary",
        skill_refs=["implementation"],
    )

    with pytest.raises(AdapterConfigInvalid) as excinfo:
        compiler.compile_agent("legacy")
    assert excinfo.value.diagnostics[0]["code"] == "parallel_skill_field"


def test_missing_skill_reference_is_invalid(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, skill_refs=["nope"])

    with pytest.raises(ReferenceInvalid) as excinfo:
        compiler.compile_agent("developer")
    assert excinfo.value.kind == "skill"
