"""Permission non-expansion, budget capping and unavailable capabilities.

Covers docs/02 §6 step 3 and docs/08 §8 boundary rules.
"""

from __future__ import annotations

from lightgravity.adapter import CompileConstraints, ResourceCompiler
from lightgravity.store import FileStore

from helpers import build_agent, build_basic_environment, create_resource


def test_task_constraint_removes_tools(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, tool_refs=["view-file", "edit-file", "run-command"])

    compiled = compiler.compile_agent(
        "developer",
        constraints=CompileConstraints(allowed_tools=frozenset({"view-file", "edit-file"})),
    )

    assert [tool.ref for tool in compiled.tools] == ["view-file", "edit-file"]
    assert all(diagnostic.code == "permission_denied" for diagnostic in compiled.diagnostics)


def test_task_constraint_cannot_add_unrequested_tools(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, tool_refs=["view-file"])

    compiled = compiler.compile_agent(
        "developer",
        constraints=CompileConstraints(allowed_tools=frozenset({"view-file", "run-command"})),
    )

    assert [tool.ref for tool in compiled.tools] == ["view-file"]


def test_budget_uses_most_restrictive_value(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, budget={"max_model_calls": 10, "max_tool_calls": 20})

    compiled = compiler.compile_agent(
        "developer",
        constraints=CompileConstraints(max_model_calls=3, max_tool_calls=50),
    )

    assert compiled.budget == {"max_model_calls": 3, "max_tool_calls": 20}


def test_budget_cannot_be_expanded_by_task_constraint(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, budget={"max_model_calls": 2})

    compiled = compiler.compile_agent(
        "developer", constraints=CompileConstraints(max_model_calls=99)
    )

    assert compiled.budget == {"max_model_calls": 2}


def test_disabled_tool_is_unavailable(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    create_resource(store, "tool", "hidden", implementation="edit-file", enabled=False)
    build_agent(store, tool_refs=["hidden"])

    compiled = compiler.compile_agent("developer")

    assert compiled.tools == ()
    assert any(item.reason == "tool_disabled" for item in compiled.unavailable)


def test_unattachable_tools_are_unavailable_not_granted(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    create_resource(store, "tool", "web", implementation="search-web")
    create_resource(store, "tool", "delegate", implementation="invoke-subagent")
    build_agent(store, tool_refs=["web", "delegate"])

    compiled = compiler.compile_agent("developer")

    assert compiled.tools == ()
    reasons = {item.ref: item.reason for item in compiled.unavailable}
    assert reasons["web"] == "tool_unavailable"
    assert reasons["delegate"] == "tool_unavailable"


def test_subagent_request_is_forced_off(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    build_agent(store, subagents=["researcher"])

    compiled = compiler.compile_agent("developer")

    assert any(item.reason == "subagents_disabled" for item in compiled.unavailable)


def test_mcp_and_triggers_are_not_started(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    create_resource(store, "mcp", "context7", transport="http", url="https://example.test")
    create_resource(store, "trigger", "nightly", type="schedule", cron="0 3 * * *")
    build_agent(store, mcp_refs=["context7"], trigger_refs=["nightly"])

    compiled = compiler.compile_agent("developer")

    reasons = {item.kind: item.reason for item in compiled.unavailable}
    assert reasons["mcp"] == "mcp_not_started"
    assert reasons["trigger"] == "triggers_not_started"
    assert compiled.executable is True  # optional resources do not block the run


def test_metadata_only_hook_is_resolved_but_not_attached(
    store: FileStore, compiler: ResourceCompiler
) -> None:
    build_basic_environment(store)
    create_resource(store, "hook", "audit", handler="metadata-only")
    build_agent(store, hook_refs=["audit"])

    compiled = compiler.compile_agent("developer")

    assert compiled.hooks == ()
    assert any(item.reason == "hook_unavailable" for item in compiled.unavailable)
