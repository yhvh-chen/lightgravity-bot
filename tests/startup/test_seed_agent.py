"""Runtime built-in agent seeding: idempotent, non-destructive, no permissions.

The seed makes the Settings-only first-run path possible: after the operator
creates a connection and sets it as the worker default, a new Task has a team
candidate without having to understand ``lg init``.
"""

from __future__ import annotations

from pathlib import Path

from lightgravity.api.bootstrap import StartupOptions, build_runtime, load_role_catalog
from lightgravity.config import Settings
from lightgravity.runtime.minimal import DEFAULT_AGENT_ID, seed_default_agent
from lightgravity.runtime.token import RuntimeToken
from lightgravity.store import FileStore

from conftest import make_settings


def _store(tmp_path: Path) -> FileStore:
    settings = make_settings(tmp_path)
    settings.ensure_data_dir()
    return FileStore(settings.data_dir, settings.workspace_root)


def test_seed_creates_builtin_agent_without_permissions(tmp_path: Path) -> None:
    store = _store(tmp_path)

    created = seed_default_agent(store)

    assert created == DEFAULT_AGENT_ID
    entity = store.read("agent", DEFAULT_AGENT_ID).entity
    assert entity["connection_ref"] is None  # resolves the current Settings default
    assert entity["tool_refs"] == []
    assert entity["enabled"] is True


def test_seed_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = seed_default_agent(store)
    revision = store.read("agent", DEFAULT_AGENT_ID).revision

    second = seed_default_agent(store)

    assert first == DEFAULT_AGENT_ID
    assert second is None
    assert store.read("agent", DEFAULT_AGENT_ID).revision == revision


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
