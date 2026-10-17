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

from .planner import Plan, goal_role_signals, stable_hash

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
class RoleProfile:
    """Non-secret role metadata used only for deterministic applicability ranking."""

    agent_ref: str
    title: str = ""
    description: str = ""
    role_category: str = ""
    division: str = ""
    capabilities: tuple[str, ...] = ()
    instructions: str = ""
    builtin_default: bool = False


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
    role_category: str = ""

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
            "role_category": self.role_category,
        }


@dataclass(frozen=True, slots=True)
class MemberPlan:
    """One temporary member covering one or more capabilities."""

    role_ref: str
    capabilities: tuple[str, ...]
    subtask_keys: tuple[str, ...]
    candidate: CandidateAgent
    config_hash: str
    selection_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "role_ref": self.role_ref,
            "capabilities": list(self.capabilities),
            "subtask_keys": list(self.subtask_keys),
            "config_hash": self.config_hash,
            "selection_reason": self.selection_reason,
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

    def __init__(
        self,
        capabilities: Mapping[str, Sequence[str]],
        *,
        profiles: Mapping[str, RoleProfile] | None = None,
        fallback_ref: str | None = None,
    ) -> None:
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
        self._profiles = dict(profiles or {})
        self._fallback_ref = fallback_ref

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(self._capabilities)

    def candidate_refs(self, capability: str) -> tuple[str, ...]:
        return self._capabilities.get(capability, ())

    def profile(self, agent_ref: str) -> RoleProfile | None:
        return self._profiles.get(agent_ref)

    def ranked_candidates(self, capability: str, goal_text: str = "") -> tuple[str, ...]:
        """Deterministically rank real roles by goal applicability metadata.

        With no meaningful goal signal the generic built-in worker (when it is
        part of this catalog) is the fallback rather than the first agency role.
        Custom/operator templates keep their catalog order; no role text grants
        a capability or a tool.
        """

        refs = list(self._capabilities.get(capability, ()))
        if not refs or not self._profiles:
            return tuple(refs)
        signals = goal_role_signals(goal_text)
        if not signals:
            fallback = self._fallback_ref
            if fallback and fallback in refs:
                return (fallback, *(ref for ref in refs if ref != fallback))
            return tuple(refs)
        scored: list[tuple[int, int, str]] = []
        for index, ref in enumerate(refs):
            profile = self._profiles.get(ref)
            score = _profile_score(profile, signals) if profile is not None else 0
            scored.append((score, -index, ref))
        scored.sort(reverse=True)
        return tuple(ref for _score, _index, ref in scored)

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

    def recruit(
        self,
        plan: Plan,
        *,
        goal_text: str = "",
        preferred_agent_ref: str | None = None,
    ) -> TeamPlan:
        problems: list[str] = []
        selected: dict[str, _Selection] = {}
        capability_to_role: dict[str, str] = {}
        for capability in plan.required_capabilities:
            candidates = list(self._catalog.ranked_candidates(capability, goal_text))
            if not candidates:
                problems.append(f"capability {capability!r} has no candidate agent")
                continue
            chosen: CandidateAgent | None = None
            selection_reason = ""
            reasons: list[str] = []
            # An explicit user/custom template request is honoured for delivery
            # capabilities.  Verification/review stays independent so a user
            # cannot turn the same worker into its own verifier by naming it.
            known_preferred = bool(
                preferred_agent_ref
                and any(
                    preferred_agent_ref in self._catalog.candidate_refs(item)
                    for item in self._catalog.capabilities
                )
            )
            preferred = (
                preferred_agent_ref
                if preferred_agent_ref
                and known_preferred
                and capability not in {"verification", "review"}
                else None
            )
            ordered: list[tuple[str, str]] = [
                (ref, "goal-fit metadata match") for ref in candidates
            ]
            if preferred is not None:
                ordered = [
                    (preferred, "explicit user request"),
                    *(
                        (ref, reason)
                        for ref, reason in ordered
                        if ref != preferred
                    ),
                ]
            for ref, reason in ordered:
                try:
                    candidate = self._resolve(ref)
                except AppError as exc:
                    reasons.append(f"{ref}: {exc.code.value}: {exc.message}")
                    continue
                if candidate.executable:
                    chosen = candidate
                    selection_reason = (
                        f"{reason}; capability={capability}; "
                        f"catalog={len(candidates)} candidate(s)"
                        + (f"; signals={goal_text[:160]}" if goal_text else "")
                    )
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
            entry = selected.setdefault(
                chosen.agent_ref,
                _Selection(candidate=chosen, selection_reason=selection_reason),
            )
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
                    selection_reason=entry.selection_reason,
                )
            )
        return TeamPlan(members=tuple(members), capability_to_role=capability_to_role)

    def _resolve(self, agent_ref: str) -> CandidateAgent:
        compiled = self._compile(agent_ref)
        profile = self._catalog.profile(agent_ref)
        return CandidateAgent(
            agent_ref=compiled.agent_id,
            executable=compiled.executable,
            config_hash=compiled.config_hash,
            template_version=str(_revision(compiled)),
            connection_ref=compiled.connection.ref if compiled.connection else None,
            skill_refs=compiled.skills.refs,
            tool_refs=tuple(tool.ref for tool in compiled.tools),
            unavailable_reasons=compiled.executable_reasons,
            role_category=profile.role_category if profile is not None else "",
        )


@dataclass
class _Selection:
    """Mutable per-agent accumulator while selecting a minimal team."""

    candidate: CandidateAgent
    capabilities: list[str] = field(default_factory=list)
    subtasks: list[str] = field(default_factory=list)
    selection_reason: str = ""


_SIGNAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "frontend": ("frontend", "front-end", "front end", "web", "ui", "page"),
    "web": ("web", "frontend", "front-end", "interface", "page"),
    "ui": ("ui", "ux", "interface", "design"),
    "design": ("design", "visual", "brand", "layout", "ux"),
    "visual": ("visual", "design", "brand", "illustration"),
    "layout": ("layout", "design", "responsive"),
    "writing": ("writer", "writing", "content", "copy", "editorial"),
    "document": ("document", "documentation", "writer", "report"),
    "content": ("content", "copy", "writer", "editorial"),
    "copy": ("copy", "copywriter", "content", "writer"),
    "review": ("review", "reviewer", "audit", "compliance"),
    "audit": ("audit", "review", "compliance"),
    "quality": ("quality", "qa", "review", "verification"),
    "verification": ("verification", "verify", "validator", "test", "qa"),
    "testing": ("test", "tester", "testing", "qa", "validation"),
    "validation": ("validation", "validator", "verification", "acceptance"),
    "evidence": ("evidence", "verification", "qa", "readiness"),
    "research": ("research", "analyst", "analysis", "researcher"),
    "analysis": ("analysis", "analyst", "research"),
    "investigation": ("investigation", "research", "analyst"),
}


def _profile_score(profile: RoleProfile, signals: Sequence[str]) -> int:
    """Score role metadata against canonical goal signals (deterministic)."""

    title = profile.title.lower()
    category = f"{profile.role_category} {profile.division}".lower()
    description = profile.description.lower()
    body = profile.instructions[:6000].lower()
    score = 0
    for signal in signals:
        for keyword in _SIGNAL_KEYWORDS.get(signal, (signal,)):
            if keyword in title:
                score += 60
            elif keyword in category:
                score += 25
            elif keyword in description:
                score += 15
            elif keyword in body:
                score += 1
    if profile.builtin_default:
        # Generic worker remains a real fallback, never a blanket winner.
        score -= 1
    return score


def _revision(compiled: CompiledAgentConfig) -> str:
    for version in compiled.resource_versions:
        if version.kind == "agent" and version.id == compiled.agent_id:
            return str(version.revision)
    return "0"


__all__ = [
    "CandidateAgent",
    "RoleProfile",
    "CompileFn",
    "MemberPlan",
    "RecruitError",
    "Recruiter",
    "RoleCatalog",
    "TeamPlan",
    "member_config_hash",
]
