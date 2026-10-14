"""Idempotent minimal resource bootstrap (LG-020, docs/07 §3, docs/08 §6.5).

The first start of a fresh data directory must not invent configuration.  This
module only writes resources when the operator supplies an **explicit** minimal
description (connection, and optionally one agent with tools/skills).  It:

* never overwrites an existing resource or SETTINGS.md revision — existing user
  configuration wins and the entry is reported as ``skipped``;
* never writes a secret value: only a ``credential_ref`` reference is stored;
* creates real resources the compiler/recruiter can resolve, so a fresh install
  can become executable after the operator stores the matching credential.

The role catalog is *derived* at startup from enabled agent resources
(:func:`lightgravity.api.bootstrap.load_role_catalog`); this module does not
keep a second catalog file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from lightgravity.store import ConfigInvalid, EntityNotFound, Store, Versioned
from lightgravity.store.entities import RESOURCE_DIRS

#: Stable id of the built-in worker seeded when no agent template exists.
DEFAULT_AGENT_ID = "lg-default-worker"

#: Bounded, workspace-scoped file tools the built-in worker may use.  They are
#: all file.read/file.write handlers backed by the SDK workspace sandbox; the
#: broader command.execute (``run-command``) and web tools are deliberately
#: excluded so the seed never opens an unbounded capability.  The task/run
#: constraint ceiling can further narrow this set, and a task with no authorized
#: workspace simply cannot attach them.
DEFAULT_WORKER_TOOL_REFS: tuple[str, ...] = (
    "view-file",
    "create-file",
    "edit-file",
)

#: Body of the built-in worker; it pins no connection.
DEFAULT_AGENT_BODY = (
    "# Built-in worker\n\n"
    "Seeded by the runtime because no agent template existed. It carries only the\n"
    "bounded, workspace-scoped file tools (view/create/edit); it has no\n"
    "command-execution or web grants and no explicit connection_ref: it runs on the\n"
    "current default worker connection configured in Settings. Extend or replace it\n"
    "from Team/Resources; deleting it and creating your own template is also\n"
    "supported.\n"
)


class _BodyCreateStore(Protocol):
    """Concrete store accepts Markdown prose; the frozen protocol does not."""

    def create(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        actor: str,
        request_id: str,
        body: str | None = None,
    ) -> Versioned: ...


@dataclass(frozen=True, slots=True)
class ConnectionInit:
    """Explicit connection description (no secret value)."""

    id: str
    model: str
    base_url: str
    credential_ref: str
    backend: str = "openai-compat"
    title: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AgentInit:
    """Explicit minimal agent description."""

    id: str
    connection_ref: str
    title: str | None = None
    body: str = "# Agent\n\nMinimal first-version agent created by LG-020 init.\n"
    skill_refs: tuple[str, ...] = ()
    tool_refs: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(slots=True)
class InitReport:
    """What the idempotent init actually did."""

    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    defaults: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": list(self.created),
            "skipped": list(self.skipped),
            "defaults": dict(self.defaults),
            "notes": list(self.notes),
        }


def _exists(store: Store, kind: str, entity_id: str) -> bool:
    try:
        store.read(kind, entity_id)
    except (EntityNotFound, ConfigInvalid):
        return False
    return True


def _ensure(
    store: Store,
    report: InitReport,
    kind: str,
    entity_id: str,
    content: Mapping[str, Any],
    *,
    body: str | None,
    actor: str,
    request_id: str,
) -> bool:
    if _exists(store, kind, entity_id):
        report.skipped.append(f"{kind}:{entity_id}")
        return False
    cast(_BodyCreateStore, store).create(
        kind,
        entity_id,
        dict(content),
        actor=actor,
        request_id=request_id,
        body=body,
    )
    report.created.append(f"{kind}:{entity_id}")
    return True


def initialize_minimal(
    store: Store,
    connections: Any,
    *,
    connection: ConnectionInit,
    agent: AgentInit | None = None,
    tools: Sequence[str] = (),
    skills: Mapping[str, str] | None = None,
    set_worker_default: bool = False,
    actor: str = "lg-init",
    request_id: str | None = None,
) -> InitReport:
    """Create the explicit minimal resources; idempotent and revision-preserving."""

    if not connection.id or not connection.credential_ref:
        raise ConfigInvalid("minimal init requires a connection id and credential_ref")
    if not connection.model or not connection.base_url:
        raise ConfigInvalid("minimal init requires connection model and base_url")

    report = InitReport()
    base_request = request_id or f"lg-init-{connection.id}"

    _ensure(
        store,
        report,
        "connection",
        connection.id,
        {
            "title": connection.title or connection.id,
            "enabled": connection.enabled,
            "backend": connection.backend,
            "model": connection.model,
            "base_url": connection.base_url,
            "credential_ref": connection.credential_ref,
        },
        body="",
        actor=actor,
        request_id=base_request,
    )

    for tool_ref in tools:
        _ensure(
            store,
            report,
            "tool",
            tool_ref,
            {"title": tool_ref, "enabled": True, "implementation": tool_ref},
            body="",
            actor=actor,
            request_id=f"{base_request}-tool-{tool_ref}",
        )

    for skill_ref, skill_body in (skills or {}).items():
        _ensure(
            store,
            report,
            "skill",
            skill_ref,
            {"title": skill_ref, "enabled": True, "description": skill_ref},
            body=skill_body,
            actor=actor,
            request_id=f"{base_request}-skill-{skill_ref}",
        )

    if agent is not None:
        if not agent.connection_ref:
            raise ConfigInvalid("minimal agent requires a connection_ref")
        if not _exists(store, "connection", agent.connection_ref):
            raise ConfigInvalid(
                f"minimal agent references missing connection {agent.connection_ref!r}"
            )
        _ensure(
            store,
            report,
            "agent",
            agent.id,
            {
                "title": agent.title or agent.id,
                "enabled": agent.enabled,
                "connection_ref": agent.connection_ref,
                "conversation_ref": None,
                "skills": {"source": "inline", "refs": list(agent.skill_refs)},
                "tool_refs": list(agent.tool_refs),
                "hook_refs": [],
                "mcp_refs": [],
                "trigger_refs": [],
                "subagents": [],
                "budget": {},
            },
            body=agent.body,
            actor=actor,
            request_id=f"{base_request}-agent-{agent.id}",
        )

    if set_worker_default:
        current = connections.get_settings()
        if current.get("default_worker_connection_ref") == connection.id:
            report.skipped.append("settings:default_worker_connection_ref")
        else:
            result = connections.update_settings(
                expected_revision=(
                    current.get("revision") if current.get("exists") else None
                ),
                default_worker_connection_ref=connection.id,
                actor=actor,
            )
            report.defaults["default_worker_connection_ref"] = connection.id
            report.defaults["revision"] = str(result.get("revision"))
            report.notes.append(
                "default worker connection set; existing revision advanced by exactly one write"
            )

    if not report.created and not report.defaults:
        report.notes.append(
            "nothing to create: all explicit minimal resources already existed; "
            "existing revisions were preserved"
        )
    return report


def _agent_template_exists(store: Store) -> bool:
    """Return whether *any* agent resource exists (enabled or not)."""

    data_dir = getattr(store, "data_dir", None)
    if data_dir is None:
        return False
    directory = Path(data_dir) / "resources" / RESOURCE_DIRS["agent"]
    if not directory.is_dir():
        return False
    return any(path.is_file() for path in directory.glob("*.md"))


def seed_default_agent(
    store: Store,
    *,
    actor: str = "lg-runtime",
    request_id: str = "lg-seed-default-agent",
) -> str | None:
    """Idempotently seed the built-in worker only when no agent template exists.

    Unlike :func:`initialize_minimal` this needs no operator input, so a fresh
    install can become executable purely through Settings (create connection,
    store credential, set default).  It never overwrites an existing template
    (including a disabled one) and grants only the bounded, workspace-scoped file
    tools; a Task still needs an authorized workspace for them to attach.
    """

    if _agent_template_exists(store):
        return None
    tool_report = InitReport()
    for tool_ref in DEFAULT_WORKER_TOOL_REFS:
        _ensure(
            store,
            tool_report,
            "tool",
            tool_ref,
            {"title": tool_ref, "enabled": True, "implementation": tool_ref},
            body="",
            actor=actor,
            request_id=f"{request_id}-tool-{tool_ref}",
        )
    cast(_BodyCreateStore, store).create(
        "agent",
        DEFAULT_AGENT_ID,
        {
            "title": "Built-in default worker",
            "enabled": True,
            "connection_ref": None,
            "conversation_ref": None,
            "skills": {"source": "inline", "refs": []},
            "tool_refs": list(DEFAULT_WORKER_TOOL_REFS),
            "hook_refs": [],
            "mcp_refs": [],
            "trigger_refs": [],
            "subagents": [],
            "budget": {},
        },
        actor=actor,
        request_id=request_id,
        body=DEFAULT_AGENT_BODY,
    )
    return DEFAULT_AGENT_ID


__all__ = [
    "DEFAULT_AGENT_BODY",
    "DEFAULT_AGENT_ID",
    "DEFAULT_WORKER_TOOL_REFS",
    "AgentInit",
    "ConnectionInit",
    "InitReport",
    "initialize_minimal",
    "seed_default_agent",
]
