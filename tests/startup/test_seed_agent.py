"""Runtime built-in agent seeding: idempotent, non-destructive, bounded tools.

The seed makes the Settings-only first-run path possible: after the operator
creates a connection and sets it as the worker default, a new Task has a team
candidate without having to understand ``lg init``.  It grants only the bounded,
workspace-scoped file tools (no command-execution or web grant), and a Task
still needs an authorized workspace for them to attach.
"""

from __future__ import annotations

from pathlib import Path

from lightgravity.api.bootstrap import StartupOptions, build_runtime, load_role_catalog
from lightgravity.config import Settings
from lightgravity.runtime.minimal import (
    DEFAULT_AGENT_ID,
    DEFAULT_WORKER_TOOL_REFS,
    seed_default_agent,
)
from lightgravity.runtime.token import RuntimeToken
from lightgravity.store import FileStore

from conftest import make_settings


def _store(tmp_path: Path) -> FileStore:
    settings = make_settings(tmp_path)
    settings.ensure_data_dir()
    return FileStore(settings.data_dir, settings.workspace_root)


def test_seed_creates_builtin_agent_with_bounded_tools(tmp_path: Path) -> None:
    store = _store(tmp_path)

    created = seed_default_agent(store)

    assert created == DEFAULT_AGENT_ID
    entity = store.read("agent", DEFAULT_AGENT_ID).entity
    assert entity["connection_ref"] is None  # resolves the current Settings default
    assert entity["tool_refs"] == list(DEFAULT_WORKER_TOOL_REFS)
    # Bounded file tools only: no command execution or web grant.
    assert set(entity["tool_refs"]) == {"view-file", "create-file", "edit-file"}
    assert "run-command" not in entity["tool_refs"]
    assert entity["enabled"] is True
    # Each referenced tool resolves to an enabled, registered implementation.
    for tool_ref in DEFAULT_WORKER_TOOL_REFS:
        tool = store.read("tool", tool_ref).entity
        assert tool["enabled"] is True
        assert tool["implementation"] == tool_ref


def test_seed_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = seed_default_agent(store)
    revision = store.read("agent", DEFAULT_AGENT_ID).revision

    second = seed_default_agent(store)

    assert first == DEFAULT_AGENT_ID
    assert second is None
    assert store.read("agent", DEFAULT_AGENT_ID).revision == revision


def test_seeded_worker_compiles_bounded_file_tools_when_authorized(tmp_path: Path) -> None:
    """The seeded team candidate can actually attach file tools.

    Without this the empty-tool seed could only return text and could not do an
    explicitly authorized file delivery.  The compile ceiling (task/run
    authorization) still bounds the set, and no unbounded tool is ever granted.
    """

    from lightgravity.adapter import CompileConstraints, ResourceCompiler
    from lightgravity.adapter.registry import default_registry

    settings = make_settings(tmp_path)
    settings.ensure_data_dir()
    store = FileStore(settings.data_dir, settings.workspace_root)
    seed_default_agent(store)
    store.create(
        "connection",
        "primary",
        {
            "title": "primary",
            "enabled": True,
            "backend": "openai-compat",
            "model": "worker-model",
            "base_url": "http://127.0.0.1:11434/v1",
            "credential_ref": "worker-default",
        },
        actor="test",
        request_id="req-conn-primary",
    )
    workspace = settings.workspace_root / "ws"
    workspace.mkdir(parents=True, exist_ok=True)

    compiler = ResourceCompiler(store, registry=default_registry())
    compiled = compiler.compile_agent(
        DEFAULT_AGENT_ID,
        constraints=CompileConstraints(
            allowed_tools=frozenset(DEFAULT_WORKER_TOOL_REFS),
            workspace_path=str(workspace),
        ),
    )

    assert {tool.ref for tool in compiled.tools} == set(DEFAULT_WORKER_TOOL_REFS)
    # The task/run ceiling can still narrow the set.
    narrowed = compiler.compile_agent(
        DEFAULT_AGENT_ID,
        constraints=CompileConstraints(
            allowed_tools=frozenset({"view-file"}),
            workspace_path=str(workspace),
        ),
    )
    assert {tool.ref for tool in narrowed.tools} == {"view-file"}


def test_seed_never_overwrites_a_user_agent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create(
        "agent",
        "hand-written",
        {
            "title": "mine",
            "enabled": True,
            "connection_ref": "primary",
            "conversation_ref": None,
            "skills": {"source": "inline", "refs": []},
            "tool_refs": [],
            "hook_refs": [],
            "mcp_refs": [],
            "trigger_refs": [],
            "subagents": [],
            "budget": {},
        },
        actor="user",
        request_id="req-user-agent",
    )

    created = seed_default_agent(store)

    assert created is None
    assert store.read("agent", "hand-written").revision == 0
    assert not (tmp_path / "data" / "resources" / "agents" / f"{DEFAULT_AGENT_ID}.md").exists()


def test_build_runtime_seeds_catalog_and_stays_honest(tmp_path: Path) -> None:
    settings: Settings = make_settings(tmp_path)
    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
        )
    )

    catalog = load_role_catalog(state.store, settings.data_dir)
    assert catalog is not None
    assert catalog.candidate_refs("implementation") == (DEFAULT_AGENT_ID,)

    report = state.execution_report()
    assert DEFAULT_AGENT_ID in report["agent_refs"]
    assert report["execution_ready"] is False
    assert any("default worker connection" in reason for reason in report["reasons"])


def test_operator_agent_is_preferred_over_the_seed(tmp_path: Path) -> None:
    settings: Settings = make_settings(tmp_path)
    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
        )
    )
    state.store.create(
        "agent",
        "zzz-operator",
        {
            "title": "operator",
            "enabled": True,
            "connection_ref": "primary",
            "conversation_ref": None,
            "skills": {"source": "inline", "refs": []},
            "tool_refs": [],
            "hook_refs": [],
            "mcp_refs": [],
            "trigger_refs": [],
            "subagents": [],
            "budget": {},
        },
        actor="user",
        request_id="req-operator",
    )

    catalog = load_role_catalog(state.store, settings.data_dir)
    assert catalog is not None
    candidates = catalog.candidate_refs("implementation")
    assert candidates[0] == "zzz-operator"
    assert candidates[-1] == DEFAULT_AGENT_ID
