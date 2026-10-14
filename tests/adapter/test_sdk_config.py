"""Concrete SDK config compilation without executing anything.

Proves the compiled plan maps onto the installed SDK types, while keeping
"config can be built" distinct from "backend is authenticated/executable".
"""

from __future__ import annotations

import pytest

from lightgravity.adapter import (
    CapabilityUnavailable,
    CompileConstraints,
    ResourceCompiler,
    SDK_PINNED_VERSION,
    build_sdk_config,
    sdk_available,
)
from lightgravity.store import FileStore

from helpers import build_agent, build_basic_environment, create_resource


def test_openai_compatible_config_compiles(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store)

    compiled = compiler.compile_agent("developer")
    result = build_sdk_config(compiled, workspaces=["/tmp/lg-test-ws"])

    from google.antigravity import LocalOpenAIAgentConfig

    assert sdk_available() is True
    assert isinstance(result.config, LocalOpenAIAgentConfig)
    assert result.kind == "openai"
    assert result.sdk_version == SDK_PINNED_VERSION
    assert result.config.base_url == "http://127.0.0.1:11434/v1"
    assert result.config.capabilities.enable_subagents is False
    enabled = {tool.value for tool in result.config.capabilities.enabled_tools}
    assert enabled == {"view_file", "edit_file", "finish"}
    assert len(result.config.hooks) == 1
    assert result.config.skills_paths


def test_gemini_config_builds_without_credentials(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store, backend="gemini", credential_ref=None)
    build_agent(store)

    compiled = compiler.compile_agent("developer")
    # Static compilation must not be blocked by missing auth ...
    assert compiled.executable is False
    assert "credential_unresolved" in compiled.executable_reasons

    result = build_sdk_config(compiled)

    from google.antigravity import LocalAgentConfig

    # ... but the config is still built, with no secret/key material attached.
    assert isinstance(result.config, LocalAgentConfig)
    assert result.config.api_key is None
    assert result.kind == "local"


def test_inline_skills_compile_to_sdk_objects(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, skills_source="inline")

    result = build_sdk_config(compiler.compile_agent("developer"))

    names = {skill.name for skill in result.config.inline_skills}
    assert names == {"implementation", "test-report"}
    assert result.config.skills_paths == []


def test_resume_without_conversation_id_is_downgraded(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    create_resource(
        store,
        "conversation",
        "resume-profile",
        session_continuation_mode="resume",
    )
    build_agent(store, conversation_ref="resume-profile")

    compiled = compiler.compile_agent("developer")
    result = build_sdk_config(compiled)

    assert compiled.session_profile is not None
    assert compiled.session_profile.conversation_id is None
    assert result.config.session_continuation_mode.value == "create_or_resume"
    assert any("RESUME" in warning for warning in result.warnings)


def test_budget_and_compaction_are_forwarded(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    create_resource(
        store,
        "conversation",
        "compact",
        session_continuation_mode="create_or_resume",
        compaction_token_threshold=4096,
    )
    build_agent(store, conversation_ref="compact", budget={"max_model_calls": 5})

    compiled = compiler.compile_agent(
        "developer", constraints=CompileConstraints(max_tool_calls=7)
    )
    result = build_sdk_config(compiled)

    assert result.config.budget_config.max_model_calls == 5
    assert result.config.budget_config.max_tool_calls == 7
    assert result.config.compaction_config.token_threshold == 4096


def test_build_without_connection_is_capability_error(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, connection_ref=None)

    compiled = compiler.compile_agent("developer")
    with pytest.raises(CapabilityUnavailable):
        build_sdk_config(compiled)
