"""Resource catalog, diagnostics and controlled modification (LG-015).

docs/05 §6.1 makes Resources the home of seven categories (Connections, Session
Profiles, Hooks, MCP, Tools, Triggers, Skills); Team owns agent templates and
Member instances.  This module is the read/diagnose boundary over the LG-004
``Store`` plus a *narrow* controlled-write path:

* reads go through ``Store.read`` so Markdown stays the single authority;
* diagnostics keep **declared** (``enabled``), **parsed** (schema/field),
  **dependencies** (resolved refs) and **runtime availability** separate — live
  health is reported as ``unknown`` and never faked as success (docs/05 §6.1);
* ``PATCH`` accepts only an allow-list of top-level fields, re-parses the merged
  entity with the adapter schema, resolves every reference and writes through
  ``Store.write`` with ``expected_revision`` (atomic + optimistic concurrency).

Connections are deliberately *not* editable here: docs/05 §6.2 routes model and
credential changes through the Settings endpoints, which read and write the same
``resources/connections/<id>.md`` entity.  This module never builds a second
provider/model list and never resolves a secret value (``credential_ref`` only).
"""

from __future__ import annotations

from contextlib import nullcontext

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lightgravity.adapter import (
    AdapterConfigInvalid,
    ReferenceInvalid,
    ResourceCompiler,
    default_registry,
)
from lightgravity.adapter.registry import ImplementationRegistry
from lightgravity.adapter.schema import (
    AgentResource,
    ConnectionResource,
    HookResource,
    PassthroughResource,
    SessionProfileResource,
    SkillResource,
    ToolResource,
    parse_agent,
    parse_connection,
    parse_hook,
    parse_mcp,
    parse_session_profile,
    parse_skill,
    parse_tool,
    parse_trigger,
)
from lightgravity.contracts import AppError, ErrorCode
from lightgravity.store import ConfigInvalid, EntityNotFound, Store, Versioned
from lightgravity.store.locking import connection_reference_lock
from lightgravity.store.entities import RESOURCE_DIRS
from lightgravity.runtime.roles.catalog import CAPABILITIES, EXECUTABLE_CAPABILITIES

#: Every kind the catalog can read.  ``connection`` is included for reads and
#: diagnostics but excluded from the controlled-write path.
CATALOG_KINDS: tuple[str, ...] = (
    "agent",
    "connection",
    "conversation",
    "hook",
    "mcp",
    "tool",
    "trigger",
    "skill",
)

#: Resources navigation category -> entity kind (docs/05 §6.1).
NAV_KIND: dict[str, str] = {
    "connections": "connection",
    "session-profiles": "conversation",
    "hooks": "hook",
    "mcp": "mcp",
    "tools": "tool",
    "triggers": "trigger",
    "skills": "skill",
}

#: Top-level fields a controlled change may touch per kind.  Connections are
#: absent by design (they are edited in Settings).
UPDATABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "agent": (
        "title",
        "enabled",
        "connection_ref",
        "conversation_ref",
        "skills",
        "tool_refs",
        "hook_refs",
        "mcp_refs",
        "trigger_refs",
    ),
    "conversation": (
        "title",
        "enabled",
        "session_continuation_mode",
        "conversation_id",
        "compaction_token_threshold",
        "agent_behavior",
    ),
    "hook": ("title", "enabled", "handler", "events"),
    "mcp": ("title", "enabled", "transport"),
    "tool": ("title", "enabled", "implementation", "policy"),
    "trigger": ("title", "enabled", "type"),
    "skill": ("title",),
}

_PARSERS: dict[str, Callable[[Versioned], Any]] = {
    "agent": parse_agent,
    "connection": parse_connection,
    "conversation": parse_session_profile,
    "hook": parse_hook,
    "mcp": parse_mcp,
    "tool": parse_tool,
    "trigger": parse_trigger,
    "skill": parse_skill,
}

#: ``field -> referenced kind`` for dependency checks.
_AGENT_REF_FIELDS: tuple[tuple[str, str], ...] = (
    ("connection_ref", "connection"),
    ("conversation_ref", "conversation"),
    ("tool_refs", "tool"),
    ("hook_refs", "hook"),
    ("mcp_refs", "mcp"),
    ("trigger_refs", "trigger"),
)


def _availability(state: str, *reasons: str) -> dict[str, Any]:
    return {"state": state, "reasons": [reason for reason in reasons if reason]}


def _role_metadata(entity: dict[str, Any]) -> dict[str, Any]:
    """Additive LG-120 role metadata; never used to grant a tool.

    Unknown frontmatter is preserved by the Store, and unknown capability words
    are retained in ``declared_capabilities`` for diagnostics but do not enter
    the controlled scheduler vocabulary.
    """

    raw_capabilities = entity.get("capabilities")
    declared = (
        [str(item) for item in raw_capabilities]
        if isinstance(raw_capabilities, (list, tuple))
        else []
    )
    capabilities = [item for item in declared if item in CAPABILITIES]
    agency_source = entity.get("agency_source")
    seed = entity.get("seed")
    upstream = entity.get("upstream")
    summary = ""
    if isinstance(upstream, dict):
        summary = str(upstream.get("description") or "")
    if not summary:
        summary = str(entity.get("description") or "")
    declared_recruitable = entity.get("recruitable")
    return {
        "role_category": str(
            entity.get("role_category")
            or ("agency" if isinstance(agency_source, dict) else "custom")
        ),
        "capabilities": capabilities,
        "declared_capabilities": declared,
        "agency_source": dict(agency_source) if isinstance(agency_source, dict) else None,
        "seed": dict(seed) if isinstance(seed, dict) else None,
        "summary": summary,
        "unsupported_reasons": [
            str(item) for item in entity.get("unsupported_reasons") or ()
        ]
        if isinstance(entity.get("unsupported_reasons"), (list, tuple))
        else [],
        "capability_notes": [
            str(item) for item in entity.get("capability_notes") or ()
        ]
        if isinstance(entity.get("capability_notes"), (list, tuple))
        else [],
        "declared_recruitable": (
            bool(declared_recruitable) if isinstance(declared_recruitable, bool) else None
        ),
    }


def _effective_recruitable(
    metadata: dict[str, Any], availability: dict[str, Any]
) -> bool:
    """Mapping-level recruitable state, excluding disabled/invalid templates.

    Actual execution still requires the compiled connection/tool refs; the
    separate ``executable`` field reports that distinct fact.
    """

    declared = metadata.pop("declared_recruitable")
    if availability["state"] in ("disabled", "invalid"):
        return False
    if declared is None:
        return availability["state"] == "unknown"
    if not declared:
        return False
    return any(item in EXECUTABLE_CAPABILITIES for item in metadata["capabilities"])


class ResourceService:
    """Read, diagnose and controlled-write resources for one data root."""

    def __init__(
        self,
        store: Store,
        *,
        data_dir: Path | str | None = None,
        connections: Any | None = None,
        registry: ImplementationRegistry | None = None,
    ) -> None:
        self._store = store
        resolved_data = data_dir if data_dir is not None else getattr(store, "data_dir", None)
        self._data_dir = Path(resolved_data) if resolved_data is not None else None
        self._connections = connections
        registry = registry or (
            connections.repository.registry if connections is not None else default_registry()
        )
        self._registry = registry
        self._compiler = ResourceCompiler(store, registry=registry)

    # ------------------------------------------------------------------ paths
    @property
    def data_dir(self) -> Path | None:
        return self._data_dir

    def _ids(self, kind: str) -> list[str]:
        if self._data_dir is None or kind not in RESOURCE_DIRS:
            return []
        directory = self._data_dir / "resources" / RESOURCE_DIRS[kind]
        if not directory.is_dir():
            return []
        if kind == "skill":
            return sorted(path.parent.name for path in directory.glob("*/SKILL.md"))
        return sorted(path.stem for path in directory.glob("*.md"))

    # ------------------------------------------------------------------ reads
    def list_resources(
        self, kind: str, *, limit: int = 100, cursor: str | None = None
    ) -> dict[str, Any]:
        self._require_kind(kind)
        ids = self._ids(kind)
        if cursor:
            ids = [item for item in ids if item > cursor]
        page = ids[:limit]
        items = [self.summary(kind, resource_id) for resource_id in page]
        next_cursor = page[-1] if len(ids) > limit and page else None
        return {"items": items, "next_cursor": next_cursor}

    def summary(self, kind: str, resource_id: str) -> dict[str, Any]:
        try:
            versioned = self._store.read(kind, resource_id)
        except ConfigInvalid as exc:
            return {
                "id": resource_id,
                "kind": kind,
                "title": resource_id,
                "enabled": False,
                "revision": None,
                "etag": None,
                "availability": _availability("invalid", "resource failed validation"),
                "diagnostics": list(exc.diagnostics),
            }
        parsed = self._safe_parse(kind, versioned)
        availability = self._availability_for(kind, versioned, parsed, full=False)
        return {
            "id": versioned.entity_id,
            "kind": kind,
            "title": str(versioned.entity.get("title") or versioned.entity_id),
            "enabled": bool(versioned.entity.get("enabled", True)),
            "revision": versioned.revision,
            "etag": versioned.etag,
            "availability": availability,
        }

    def detail(self, kind: str, resource_id: str) -> dict[str, Any]:
        self._require_kind(kind)
        versioned = self._store.read(kind, resource_id)
        return self._detail_from(kind, versioned)

    def _detail_from(self, kind: str, versioned: Versioned) -> dict[str, Any]:
        parsed = self._safe_parse(kind, versioned)
        diagnostics = list(parsed["diagnostics"]) if parsed["invalid"] else []
        references, dependency_reasons = self._references(kind, versioned, parsed["value"])
        availability = self._availability_for(
            kind, versioned, parsed, full=True, dependency_reasons=dependency_reasons
        )
        return {
            "id": versioned.entity_id,
            "kind": kind,
            "title": str(versioned.entity.get("title") or versioned.entity_id),
            "enabled": bool(versioned.entity.get("enabled", True)),
            "revision": versioned.revision,
            "etag": versioned.etag,
            "entity": dict(versioned.entity),
            "body": versioned.body,
            "declared": {"enabled": bool(versioned.entity.get("enabled", True))},
            "parsed": {"valid": not parsed["invalid"]},
            "diagnostics": diagnostics,
            "references": references,
            "inbound_refs": self._inbound_references(kind, versioned.entity_id),
            "availability": availability,
        }

    # ---------------------------------------------------------- availability
    def _safe_parse(self, kind: str, versioned: Versioned) -> dict[str, Any]:
        parser = _PARSERS.get(kind)
        if parser is None:
            return {"value": None, "invalid": False, "diagnostics": []}
        try:
            value = parser(versioned)
        except AdapterConfigInvalid as exc:
            return {
                "value": None,
                "invalid": True,
                "diagnostics": list(exc.details.get("diagnostics", [])),
            }
        return {"value": value, "invalid": False, "diagnostics": []}

    def _availability_for(
        self,
        kind: str,
        versioned: Versioned,
        parsed: dict[str, Any],
        *,
        full: bool,
        dependency_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        if parsed["invalid"]:
            return _availability("invalid", f"{kind} frontmatter failed validation")
        if not bool(versioned.entity.get("enabled", True)):
            return _availability("disabled", "declared enabled=false")
        unsupported = self._unsupported_reasons(kind, parsed["value"])
        if unsupported:
            return _availability("unsupported", *unsupported)
        if full:
            missing_dependencies = dependency_reasons or []
            if missing_dependencies:
                return _availability("missing_dependency", *missing_dependencies)
        # Parsed, enabled and (when checked) fully resolved, but no live
        # connection/session was started: the honest state is unknown.
        return _availability(
            "unknown",
            "configuration is declared and parsed; runtime health was not checked",
        )

    def _unsupported_reasons(self, kind: str, parsed: Any) -> list[str]:
        if parsed is None:
            return []
        if kind == "connection":
            assert isinstance(parsed, ConnectionResource)
            registration = self._registry.backend(parsed.backend)
            if registration is None:
                return [f"backend {parsed.backend!r} is not registered in this version"]
            if not registration.verified:
                return [f"backend {parsed.backend!r} is not verified in this environment"]
            return []
        if kind == "tool":
            assert isinstance(parsed, ToolResource)
            registration = self._registry.tool(parsed.implementation)
            if registration is None:
                return [f"tool implementation {parsed.implementation!r} is not registered"]
            if not registration.attaches or registration.sdk_tool is None:
                return [
                    registration.description
                    or f"handler {registration.handler_id} is not attachable in this version"
                ]
            return []
        if kind == "hook":
            assert isinstance(parsed, HookResource)
            registration = self._registry.hook(parsed.handler)
            if registration is None:
                return [f"hook handler {parsed.handler!r} is not registered"]
            if not registration.attaches or registration.factory is None:
                return [
                    registration.description
                    or f"handler {registration.handler_id} is not attachable in this version"
                ]
            return []
        if kind == "mcp":
            assert isinstance(parsed, PassthroughResource)
            return ["MCP servers are described but not started in this version"]
        if kind == "trigger":
            assert isinstance(parsed, PassthroughResource)
            return ["triggers are described but not started in this version"]
        return []

    # ---------------------------------------------------------- references
    def _references(
        self, kind: str, versioned: Versioned, parsed: Any
    ) -> tuple[list[dict[str, Any]], list[str]]:
        checks: list[dict[str, Any]] = []
        missing: list[str] = []
        if kind == "agent" and isinstance(parsed, AgentResource):
            for field, ref_kind in _AGENT_REF_FIELDS:
                value = getattr(parsed, field, None)
                if isinstance(value, str) and value:
                    check = self._check_reference(ref_kind, value)
                    check["field"] = field
                    checks.append(check)
                elif isinstance(value, (list, tuple)):
                    for ref in value:
                        if isinstance(ref, str) and ref:
                            check = self._check_reference(ref_kind, ref)
                            check["field"] = field
                            checks.append(check)
            for skill_ref in parsed.skills.refs:
                check = self._check_reference("skill", skill_ref)
                check["field"] = "skills.refs"
                checks.append(check)
        elif kind == "connection" and isinstance(parsed, ConnectionResource):
            if parsed.credential_ref:
                status = {"ref": "", "configured": False}
                if self._connections is not None:
                    status = self._connections.credential_status(parsed.credential_ref).to_dict()
                checks.append(
                    {
                        "field": "credential_ref",
                        "kind": "credential",
                        "ref": parsed.credential_ref,
                        "state": "resolved" if status.get("configured") else "unresolved",
                        "source": status.get("source"),
                        "configured": bool(status.get("configured")),
                    }
                )
        elif kind == "tool" and isinstance(parsed, ToolResource):
            checks.append(
                {
                    "field": "implementation",
                    "kind": "handler",
                    "ref": parsed.implementation,
                    "state": (
                        "resolved"
                        if self._registry.tool(parsed.implementation) is not None
                        else "missing"
                    ),
                }
            )
        elif kind == "hook" and isinstance(parsed, HookResource):
            checks.append(
                {
                    "field": "handler",
                    "kind": "handler",
                    "ref": parsed.handler,
                    "state": (
                        "resolved"
                        if self._registry.hook(parsed.handler) is not None
                        else "missing"
                    ),
                }
            )
        for check in checks:
            if check["state"] in ("missing", "unresolved"):
                missing.append(f"{check['kind']}:{check['ref']}")
        return checks, missing

    def _check_reference(self, ref_kind: str, ref: str) -> dict[str, Any]:
        state = "resolved"
        try:
            self._store.read(ref_kind, ref)
        except (EntityNotFound, ConfigInvalid, AdapterConfigInvalid):
            state = "missing"
        return {"field": None, "kind": ref_kind, "ref": ref, "state": state}

    def _inbound_references(self, kind: str, resource_id: str) -> list[dict[str, Any]]:
        inbound: list[dict[str, Any]] = []
        for agent_id in self._ids("agent"):
            try:
                versioned = self._store.read("agent", agent_id)
            except (EntityNotFound, ConfigInvalid):
                continue
            parsed = self._safe_parse("agent", versioned)
            if parsed["invalid"]:
                continue
            assert isinstance(parsed["value"], AgentResource)
            candidate = parsed["value"]
            fields: list[tuple[str, str, str]] = [
                ("connection_ref", "connection", candidate.connection_ref or ""),
                ("conversation_ref", "conversation", candidate.conversation_ref or ""),
            ]
            fields += [("tool_refs", "tool", ref) for ref in candidate.tool_refs]
            fields += [("hook_refs", "hook", ref) for ref in candidate.hook_refs]
            fields += [("mcp_refs", "mcp", ref) for ref in candidate.mcp_refs]
            fields += [("trigger_refs", "trigger", ref) for ref in candidate.trigger_refs]
            fields += [("skills.refs", "skill", ref) for ref in candidate.skills.refs]
            for field, ref_kind, ref in fields:
                if ref_kind == kind and ref == resource_id:
                    inbound.append(
                        {"from_kind": "agent", "from_id": agent_id, "field": field}
                    )
        for member_id in self._member_ids():
            try:
                versioned = self._store.read("member", member_id)
            except (EntityNotFound, ConfigInvalid):
                continue
            member = versioned.entity
            if kind == "connection" and member.get("connection_ref") == resource_id:
                inbound.append(
                    {"from_kind": "member", "from_id": member_id, "field": "connection_ref"}
                )
            if kind == "skill" and resource_id in _string_list(member.get("skill_refs")):
                inbound.append(
                    {"from_kind": "member", "from_id": member_id, "field": "skill_refs"}
                )
        return inbound

    # --------------------------------------------------------------- agents
    def available_agents(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for agent_id in self._ids("agent"):
            try:
                versioned = self._store.read("agent", agent_id)
            except ConfigInvalid as exc:
                items.append(
                    {
                        "id": agent_id,
                        "kind": "agent",
                        "title": agent_id,
                        "enabled": False,
                        "revision": None,
                        "availability": _availability("invalid", "resource failed validation"),
                        "diagnostics": list(exc.diagnostics),
                    }
                )
                continue
            items.append(self._agent_summary(versioned))
        return items

    def _agent_summary(self, versioned: Versioned) -> dict[str, Any]:
        parsed = self._safe_parse("agent", versioned)
        if parsed["invalid"]:
            metadata = _role_metadata(dict(versioned.entity))
            metadata["recruitable"] = False
            metadata.pop("declared_recruitable", None)
            return {
                "id": versioned.entity_id,
                "kind": "agent",
                "title": str(versioned.entity.get("title") or versioned.entity_id),
                "enabled": bool(versioned.entity.get("enabled", True)),
                "revision": versioned.revision,
                "availability": _availability("invalid", "agent frontmatter failed validation"),
                "diagnostics": list(parsed["diagnostics"]),
                "skill_refs": [],
                "connection_ref": None,
                "config_hash": None,
                **metadata,
            }
        assert isinstance(parsed["value"], AgentResource)
        agent = parsed["value"]
        availability = self._compile_availability(versioned.entity_id, agent)
        metadata = _role_metadata(dict(versioned.entity))
        metadata["recruitable"] = _effective_recruitable(metadata, availability)
        return {
            "id": versioned.entity_id,
            "kind": "agent",
            "title": agent.title,
            "enabled": agent.enabled,
            "revision": versioned.revision,
            "revision_etag": versioned.etag,
            "template_version": str(versioned.entity.get("template_version") or "1"),
            "connection_ref": agent.connection_ref,
            "conversation_ref": agent.conversation_ref,
            "skill_refs": list(agent.skills.refs),
            "skills_source": agent.skills.source,
            "tool_refs": list(agent.tool_refs),
            "hook_refs": list(agent.hook_refs),
            "mcp_refs": list(agent.mcp_refs),
            "trigger_refs": list(agent.trigger_refs),
            "availability": availability,
            "executable": availability["state"] == "unknown",
            "body": versioned.body,
            **metadata,
        }

    def _compile_availability(self, agent_id: str, agent: AgentResource) -> dict[str, Any]:
        if not agent.enabled:
            return _availability("disabled", "declared enabled=false")
        try:
            compiled = self._compiler.compile_agent(agent_id)
        except AdapterConfigInvalid as exc:
            return _availability("invalid", *self._diagnostic_reasons(exc))
        except ReferenceInvalid as exc:
            state = "unsupported" if "not registered" in exc.message else "missing_dependency"
            return _availability(state, exc.message)
        except AppError as exc:  # unexpected contract error: never a fake success
            return _availability("invalid", exc.message)
        if not compiled.executable:
            reasons = [
                f"{item.kind}:{item.ref} ({item.reason})" for item in compiled.unavailable
            ]
            state = "unsupported" if any(
                item.reason in _UNSUPPORTED_REASONS for item in compiled.unavailable
            ) else "missing_dependency"
            return _availability(state, *reasons)
        return _availability(
            "unknown",
            "agent configuration is executable; no live session was started",
        )

    @staticmethod
    def _diagnostic_reasons(exc: AdapterConfigInvalid) -> list[str]:
        entries = exc.details.get("diagnostics", [])
        reasons = [entry.get("message") for entry in entries if entry.get("message")]
        return reasons or [exc.message]

    # -------------------------------------------------------------- members
    def members(
        self,
        *,
        task_ref: str | None = None,
        run_ref: str | None = None,
        include_released: bool = True,
    ) -> list[dict[str, Any]]:
        run_task = self._run_task_map()
        items: list[dict[str, Any]] = []
        for member_id in self._member_ids():
            try:
                versioned = self._store.read("member", member_id)
            except ConfigInvalid as exc:
                items.append(
                    {
                        "id": member_id,
                        "kind": "member",
                        "state": None,
                        "availability": _availability("invalid", "resource failed validation"),
                        "diagnostics": list(exc.diagnostics),
                    }
                )
                continue
            member = versioned.entity
            member_run = member.get("run_ref")
            if run_ref is not None and member_run != run_ref:
                continue
            if task_ref is not None and run_task.get(str(member_run)) != task_ref:
                continue
            state = str(member.get("state"))
            if state == "released" and not include_released:
                continue
            items.append(self._member_summary(versioned))
        return items

    def _member_summary(self, versioned: Versioned) -> dict[str, Any]:
        member = versioned.entity
        state = str(member.get("state"))
        if state == "released":
            availability = _availability("unknown", "released; retained as history")
        elif state == "failed":
            availability = _availability("invalid", str(member.get("fail_reason") or "failed"))
        else:
            availability = _availability("unknown", "no live session check performed")
        return {
            "id": versioned.entity_id,
            "kind": "member",
            "title": str(member.get("role_ref") or versioned.entity_id),
            "state": state,
            "released": state == "released",
            "revision": versioned.revision,
            "run_ref": member.get("run_ref"),
            "role_ref": member.get("role_ref"),
            "template_version": member.get("template_version"),
            "connection_ref": member.get("connection_ref"),
            "skill_refs": _string_list(member.get("skill_refs")),
            "tool_policy": member.get("tool_policy") if isinstance(member.get("tool_policy"), dict) else {},
            "assigned_subtask_refs": _string_list(member.get("assigned_subtask_refs")),
            "session_ref": member.get("session_ref"),
            "config_hash": member.get("config_hash"),
            "budget": member.get("budget") if isinstance(member.get("budget"), dict) else {},
            "fail_reason": member.get("fail_reason"),
            "availability": availability,
            "body": versioned.body,
        }

    def _member_ids(self) -> list[str]:
        if self._data_dir is None:
            return []
        directory = self._data_dir / "members"
        if not directory.is_dir():
            return []
        return sorted(path.stem for path in directory.glob("*.md"))

    def _run_task_map(self) -> dict[str, str]:
        if self._data_dir is None:
            return {}
        result: dict[str, str] = {}
        runs_dir = self._data_dir / "runs"
        if not runs_dir.is_dir():
            return result
        for path in sorted(runs_dir.glob("*/RUN.md")):
            run_id = path.parent.name
            try:
                versioned = self._store.read("run", run_id)
            except (EntityNotFound, ConfigInvalid):
                continue
            task_ref = versioned.entity.get("task_ref")
            if isinstance(task_ref, str) and task_ref:
                result[run_id] = task_ref
        return result

    # --------------------------------------------------------------- update
    def update(
        self,
        kind: str,
        resource_id: str,
        *,
        patch: dict[str, Any],
        expected_revision: int,
        actor: str,
        body: str | None = None,
    ) -> dict[str, Any]:
        with connection_reference_lock(self._store) if kind == "agent" else nullcontext():
            self._require_kind(kind)
            if kind == "connection":
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "connections are edited through the Settings endpoints; there is one "
                    "Connection authority and no second model list",
                    details={
                        "kind": kind,
                        "id": resource_id,
                        "use": f"/api/v1/settings/connections/{resource_id}",
                    },
                )
            allowed = set(UPDATABLE_FIELDS.get(kind, ()))
            unknown = sorted(set(patch) - allowed)
            if unknown:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    f"fields not editable through this controlled path: {', '.join(unknown)}",
                    details={"kind": kind, "allowed": sorted(allowed), "rejected": unknown},
                )
            if not patch and body is None:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "nothing to update: provide at least one allowed field or a body",
                    details={"kind": kind, "allowed": sorted(allowed)},
                )
            current = self._store.read(kind, resource_id)
            merged = dict(current.entity)
            merged.update(patch)
            candidate = Versioned(
                kind=kind,
                entity_id=resource_id,
                entity=merged,
                revision=current.revision,
                content_hash=current.content_hash,
                body=current.body if body is None else body,
                path=current.path,
            )
            # Program validation before the Store write: adapter schema/field
            # combinations, then every reference must resolve.  A model proposal is
            # therefore checked, never trusted.
            self._validate_candidate(kind, candidate)
            written = self._write(kind, resource_id, patch, body, expected_revision, actor)
            return self._detail_from(kind, written)

    def _write(
        self,
        kind: str,
        resource_id: str,
        patch: dict[str, Any],
        body: str | None,
        expected_revision: int,
        actor: str,
    ) -> Versioned:
        write = getattr(self._store, "write")
        try:
            return write(
                kind,
                resource_id,
                patch,
                expected_revision=expected_revision,
                actor=actor,
                body=body,
            )
        except TypeError:
            # Protocol-shaped stores without the Markdown ``body`` extension.
            return write(
                kind,
                resource_id,
                patch,
                expected_revision=expected_revision,
                actor=actor,
            )

    def _validate_candidate(self, kind: str, candidate: Versioned) -> None:
        parsed = self._safe_parse(kind, candidate)
        if parsed["invalid"]:
            raise AppError(
                ErrorCode.CONFIG_INVALID,
                f"{kind} {candidate.entity_id!r} update failed validation",
                details={"diagnostics": parsed["diagnostics"]},
            )
        _references, missing = self._references(kind, candidate, parsed["value"])
        if missing:
            raise AppError(
                ErrorCode.REFERENCE_INVALID,
                f"{kind} {candidate.entity_id!r} references resources that do not resolve",
                details={"missing": missing},
            )

    # ---------------------------------------------------------------- helper
    def _require_kind(self, kind: str) -> None:
        if kind not in CATALOG_KINDS:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                f"unknown resource kind {kind!r}",
                details={"kind": kind, "allowed": sorted(CATALOG_KINDS)},
            )


#: Reasons from the compiler that mean "not supported in this version" rather
#: than "a dependency is missing".
_UNSUPPORTED_REASONS = frozenset(
    {
        "backend_unverified",
        "tool_unavailable",
        "hook_unavailable",
        "mcp_not_started",
        "triggers_not_started",
        "subagents_disabled",
        "session_profile_disabled",
    }
)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str) and item]


__all__ = ["ResourceService", "CATALOG_KINDS", "NAV_KIND", "UPDATABLE_FIELDS"]
