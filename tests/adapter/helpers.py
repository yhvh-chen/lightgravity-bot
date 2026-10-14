"""Shared helpers for LG-005 adapter tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lightgravity.adapter import HookRegistration, ImplementationRegistry, default_registry
from lightgravity.store import FileStore


def make_store(tmp_path: Path) -> FileStore:
    data = tmp_path / "data"
    return FileStore(data, data / "workspaces")


def create_resource(
    store: FileStore,
    kind: str,
    entity_id: str,
    *,
    body: str = "",
    **fields: Any,
) -> None:
    fields.setdefault("title", entity_id)
    fields.setdefault("enabled", True)
    store.create(
        kind,
        entity_id,
        fields,
        actor="test",
        request_id=f"req-{kind}-{entity_id}",
        body=body,
    )


def make_session_hook() -> Any:
    """Return a fresh, no-op SDK session-start hook object."""

    from google.antigravity.hooks import on_session_start

    @on_session_start
    def _noop() -> None:
        return None

    return _noop


def make_registry() -> ImplementationRegistry:
    return default_registry(
        hooks=[
            HookRegistration(
                handler_id="session-log",
                factory=make_session_hook,
                events=("session_start",),
                description="no-op session-start observer",
            ),
            HookRegistration(
                handler_id="metadata-only",
                factory=None,
                description="resolvable but not attachable",
            ),
        ]
    )


def build_basic_environment(
    store: FileStore,
    *,
    backend: str = "openai-compat",
    base_url: str = "http://127.0.0.1:11434/v1",
    credential_ref: str | None = "worker-default",
) -> None:
    """Create a connection, session profile, two skills and matching resources."""

    create_resource(
        store,
        "connection",
        "primary",
        backend=backend,
        model="worker-model",
        credential_ref=credential_ref,
        base_url=base_url,
    )
    create_resource(
        store,
        "conversation",
        "task-worker",
        session_continuation_mode="create_or_resume",
        agent_behavior="autonomous",
    )
    create_resource(store, "skill", "implementation", body="# Implementation\nDo the work.")
    create_resource(store, "skill", "test-report", body="# Tests\nReport results.")
    create_resource(store, "tool", "view-file", implementation="view-file")
    create_resource(store, "tool", "edit-file", implementation="edit-file")
    create_resource(store, "tool", "run-command", implementation="run-command")
    create_resource(
        store,
        "hook",
        "session-observer",
        handler="session-log",
        events=("session_start",),
    )


def build_agent(
    store: FileStore,
    *,
    agent_id: str = "developer",
    connection_ref: str | None = "primary",
    conversation_ref: str | None = "task-worker",
    skills_source: str = "paths",
    skill_refs: list[str] | None = None,
    tool_refs: list[str] | None = None,
    hook_refs: list[str] | None = None,
    mcp_refs: list[str] | None = None,
    trigger_refs: list[str] | None = None,
    subagents: list[str] | None = None,
    budget: dict[str, Any] | None = None,
    body: str = "# Developer\nImplement the requested change.",
    **extra: Any,
) -> None:
    skills: dict[str, Any] = {
        "source": skills_source,
        "refs": skill_refs if skill_refs is not None else ["implementation", "test-report"],
    }
    fields: dict[str, Any] = {
        "connection_ref": connection_ref,
        "conversation_ref": conversation_ref,
        "skills": skills,
        "tool_refs": tool_refs if tool_refs is not None else ["view-file", "edit-file"],
        "hook_refs": hook_refs if hook_refs is not None else ["session-observer"],
        "mcp_refs": mcp_refs or [],
        "trigger_refs": trigger_refs or [],
        "subagents": subagents or [],
    }
    if budget is not None:
        fields["budget"] = budget
    fields.update(extra)
    create_resource(store, "agent", agent_id, body=body, **fields)
