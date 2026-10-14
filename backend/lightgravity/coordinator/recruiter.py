"""Recruiter: map required capabilities to a minimal agent team (LG-008).

The first version does **not** invent organization roles.  A per-run *catalog*
maps a capability name (``implementation``, ``verification``, ...) to candidate
``agent`` resource refs; that mapping is explicit configuration (there is no
``role`` resource kind in the v1 contract).  What is automatic is the selection:
the recruiter reads the validated :class:`~lightgravity.coordinator.planner.Plan`,
resolves each candidate through the LG-005 compiler, picks the minimal set of
executable agents that covers the required capabilities and reuses one member
when a single agent covers several capabilities.

Recruitment cannot grant permissions: candidates are compiled with the run's
``CompileConstraints`` and the effective tool/budget ceiling can only shrink.
A capability with no executable candidate fails with the collected reasons and
the dispatcher records the failure instead of fabricating execution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Callable

from lightgravity.adapter import CompiledAgentConfig
from lightgravity.contracts import AppError, ErrorCode

from .planner import Plan, stable_hash

#: Compile one agent resource under the run constraints.
CompileFn = Callable[[str], CompiledAgentConfig]


class RecruitError(AppError):
    """No minimal team could be recruited; the reasons are preserved."""

    def __init__(
        self,
        message: str,
        *,
        problems: Sequence[str] = (),
        code: ErrorCode = ErrorCode.CAPABILITY_UNAVAILABLE,
    ) -> None:
        super().__init__(code, message, details={"problems": list(problems)})
        self.problems = tuple(problems)


@dataclass(frozen=True, slots=True)
class CandidateAgent:
    """A resolved, fixed agent configuration suitable for one member."""

    agent_ref: str
    executable: bool
    config_hash: str
    template_version: str
    connection_ref: str | None
    skill_refs: tuple[str, ...]
    tool_refs: tuple[str, ...]
    unavailable_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_ref": self.agent_ref,
            "executable": self.executable,
            "config_hash": self.config_hash,
            "template_version": self.template_version,
            "connection_ref": self.connection_ref,
            "skill_refs": list(self.skill_refs),
            "tool_refs": list(self.tool_refs),
            "unavailable_reasons": list(self.unavailable_reasons),
        }


@dataclass(frozen=True, slots=True)
class MemberPlan:
    """One temporary member covering one or more capabilities."""

    role_ref: str
    capabilities: tuple[str, ...]
    subtask_keys: tuple[str, ...]
    candidate: CandidateAgent
    config_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "role_ref": self.role_ref,
            "capabilities": list(self.capabilities),
            "subtask_keys": list(self.subtask_keys),
            "config_hash": self.config_hash,
            "candidate": self.candidate.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class TeamPlan:
    """Minimal team plan for one run."""

    members: tuple[MemberPlan, ...]
    capability_to_role: Mapping[str, str]

    def member_for(self, capability: str) -> MemberPlan | None:
        role_ref = self.capability_to_role.get(capability)
        if role_ref is None:
            return None
        for member in self.members:
            if member.role_ref == role_ref:
                return member
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "members": [member.to_dict() for member in self.members],
            "capability_to_role": dict(self.capability_to_role),
        }


class RoleCatalog:
    """Explicit capability -> candidate agent refs configuration.

    The catalog is the only source of "which role can do what"; it deliberately
    stays a data structure so it can come from project configuration rather than
    from a model or a hardcoded mapping inside the scheduler.
    """

    def __init__(self, capabilities: Mapping[str, Sequence[str]]) -> None:
        cleaned: dict[str, tuple[str, ...]] = {}
        for capability, refs in capabilities.items():
            name = capability.strip()
            if not name:
                raise ValueError("capability name must not be empty")
            ordered: list[str] = []
            for ref in refs:
                if not isinstance(ref, str) or not ref.strip():
                    raise ValueError(f"candidate refs for {name!r} must be non-empty strings")
                if ref not in ordered:
                    ordered.append(ref)
            cleaned[name] = tuple(ordered)
        self._capabilities = cleaned

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(self._capabilities)

    def candidate_refs(self, capability: str) -> tuple[str, ...]:
        return self._capabilities.get(capability, ())

    @classmethod
    def single_agent(cls, capabilities: Sequence[str], agent_ref: str) -> "RoleCatalog":
        return cls({capability: [agent_ref] for capability in capabilities})


def member_config_hash(
    *,
    role_ref: str,
    agent_config_hash: str,
    connection_ref: str | None,
    skill_refs: Sequence[str],
    tool_refs: Sequence[str],
    capabilities: Sequence[str],
) -> str:
    """Stable member configuration hash, fixed at recruit time."""

    return stable_hash(
        {
            "role_ref": role_ref,
            "agent_config_hash": agent_config_hash,
            "connection_ref": connection_ref,
            "skill_refs": sorted(skill_refs),
            "tool_refs": sorted(tool_refs),
            "capabilities": sorted(capabilities),
        }
    )


class Recruiter:
    """Resolve a plan's capabilities into a minimal executable team."""

    def __init__(self, catalog: RoleCatalog, *, compile_agent: CompileFn) -> None:
        self._catalog = catalog
        self._compile = compile_agent

    @property
    def catalog(self) -> RoleCatalog:
        return self._catalog

    def recruit(self, plan: Plan) -> TeamPlan:
        problems: list[str] = []
        selected: dict[str, _Selection] = {}
        capability_to_role: dict[str, str] = {}
        for capability in plan.required_capabilities:
            candidates = self._catalog.candidate_refs(capability)
            if not candidates:
                problems.append(f"capability {capability!r} has no candidate agent")
                continue
            chosen: CandidateAgent | None = None
            reasons: list[str] = []
            for ref in candidates:
                try:
                    candidate = self._resolve(ref)
                except AppError as exc:
                    reasons.append(f"{ref}: {exc.code.value}: {exc.message}")
                    continue
                if candidate.executable:
                    chosen = candidate
                    break
                reasons.append(
                    f"{ref}: " + (", ".join(candidate.unavailable_reasons) or "not executable")
                )
            if chosen is None:
                problems.append(
                    f"no executable candidate for capability {capability!r} ({'; '.join(reasons)})"
                )
                continue
            capability_to_role[capability] = chosen.agent_ref
            entry = selected.setdefault(chosen.agent_ref, _Selection(candidate=chosen))
            if capability not in entry.capabilities:
                entry.capabilities.append(capability)
            for spec in plan.subtasks:
                if spec.capability == capability and spec.key not in entry.subtasks:
                    entry.subtasks.append(spec.key)
        if problems:
            raise RecruitError("minimal team recruitment failed", problems=problems)

        members: list[MemberPlan] = []
        for agent_ref in sorted(selected):
            entry = selected[agent_ref]
            members.append(
                MemberPlan(
                    role_ref=agent_ref,
                    capabilities=tuple(entry.capabilities),
                    subtask_keys=tuple(entry.subtasks),
                    candidate=entry.candidate,
                    config_hash=member_config_hash(
                        role_ref=agent_ref,
                        agent_config_hash=entry.candidate.config_hash,
                        connection_ref=entry.candidate.connection_ref,
                        skill_refs=entry.candidate.skill_refs,
                        tool_refs=entry.candidate.tool_refs,
                        capabilities=entry.capabilities,
                    ),
                )
            )
        return TeamPlan(members=tuple(members), capability_to_role=capability_to_role)

    def _resolve(self, agent_ref: str) -> CandidateAgent:
        compiled = self._compile(agent_ref)
        return CandidateAgent(
            agent_ref=compiled.agent_id,
            executable=compiled.executable,
            config_hash=compiled.config_hash,
            template_version=str(_revision(compiled)),
            connection_ref=compiled.connection.ref if compiled.connection else None,
            skill_refs=compiled.skills.refs,
            tool_refs=tuple(tool.ref for tool in compiled.tools),
            unavailable_reasons=compiled.executable_reasons,
        )


@dataclass
class _Selection:
    """Mutable per-agent accumulator while selecting a minimal team."""

    candidate: CandidateAgent
    capabilities: list[str] = field(default_factory=list)
    subtasks: list[str] = field(default_factory=list)


def _revision(compiled: CompiledAgentConfig) -> str:
    for version in compiled.resource_versions:
        if version.kind == "agent" and version.id == compiled.agent_id:
            return str(version.revision)
    return "0"


__all__ = [
    "CandidateAgent",
    "CompileFn",
    "MemberPlan",
    "RecruitError",
    "Recruiter",
    "RoleCatalog",
    "TeamPlan",
    "member_config_hash",
]
