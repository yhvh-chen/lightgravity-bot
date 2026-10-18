"""Plan proposal + program-side validation (docs/01 §4, default architecture).

The **default** execution plan is program-side and model-free:
:class:`RuleBasedPlanner` deterministically derives a minimal Subtask graph from
the Task input (one write node, plus a dependent verify node when acceptance
criteria exist).  It is not a resident orchestration agent and makes no model
call.

:class:`PlanValidator` is the *program* boundary: no proposal - rule-based or
model-backed - becomes an executable :class:`Plan` until it passes graph,
reference, capability, acceptance and workspace checks.  This keeps docs/01
§4's "模型提出计划和组队建议，程序校验并实施" boundary real.

:class:`ModelPlanner` is an **optional, bounded, on-demand** model proposal
interface.  It is not wired into the default assembly and no real model backend
is implemented; a caller injects a ``propose`` callable explicitly, and the
dispatcher only consults it when an explicit
:class:`~lightgravity.coordinator.planning.PlanningRequest` records why.  Its
output is parsed structurally and validated by the same
:class:`PlanValidator`, so it can never add tools, connections, budgets or
capabilities.  The capability -> agent selection is owned by
:mod:`~lightgravity.coordinator.recruiter`.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from lightgravity.contracts import AppError, ErrorCode

from .dispatcher import DispatchContext
from .planning import PlanningRequest, PlanningTrigger
from .scheduler import DependencyGraph, GraphError, GraphNode

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: LG-126 goal-fit capability rules.  These are deterministic programme rules,
#: not a model proposal and not a fixed demo team.  They only choose *which*
#: validated capability a node needs; the recruiter still selects a real
#: executable role from metadata and the existing tool/auth gates stay intact.
_WEB_SIGNAL_RE = re.compile(
    r"\b(html|css|javascript|typescript|frontend|front-end|webpage|web[ -]?page|"
    r"responsive|react|vue|svelte|ui|ux)\b|网页|页面|静态页|前端|界面|样式|响应式",
    re.I,
)
_DESIGN_SIGNAL_RE = re.compile(
    r"\b(design|visual|brand|layout|wireframe|mockup|poster|illustration)\b|"
    r"设计|视觉|品牌|布局|线框|海报|插画",
    re.I,
)
_WRITING_SIGNAL_RE = re.compile(
    r"(?:\.md\b|\bmarkdown\b|\bdocument(?:ation)?\b|\breport\b|"
    r"\bannouncement\b|\bcopywriting\b|\bcontent\b|\barticle\b|"
    r"公告|文案|文档|报告|文章|说明文档|发布文案)",
    re.I,
)
_REVIEW_SIGNAL_RE = re.compile(
    r"\b(review|audit|inspection)\b|审查|评审|审计", re.I
)
_VERIFY_SIGNAL_RE = re.compile(
    r"\b(verify|verification|validate|validation|qa|acceptance|test)\b|"
    r"验证|核验|校验|验收|测试",
    re.I,
)
_RESEARCH_SIGNAL_RE = re.compile(
    r"\b(research|investigate|survey|compare|analysis)\b|调研|研究|分析|比较",
    re.I,
)

_SIGNAL_BY_CAPABILITY: dict[str, re.Pattern[str]] = {
    "design": _DESIGN_SIGNAL_RE,
    "implementation": _WEB_SIGNAL_RE,
    "writing": _WRITING_SIGNAL_RE,
    "review": _REVIEW_SIGNAL_RE,
    "verification": _VERIFY_SIGNAL_RE,
    "research": _RESEARCH_SIGNAL_RE,
}


def goal_role_signals(text: str) -> tuple[str, ...]:
    """Canonical role-applicability signals extracted deterministically.

    Exposed so the recruiter can rank real role metadata (title/description/
    category) against the same vocabulary instead of taking the first catalog
    entry or a hardcoded game role.  It never grants a capability.
    """

    value = text or ""
    signals: list[str] = []
    if _WEB_SIGNAL_RE.search(value):
        signals.extend(("frontend", "web", "ui"))
    if _DESIGN_SIGNAL_RE.search(value):
        signals.extend(("design", "ui", "visual", "layout"))
    if _WRITING_SIGNAL_RE.search(value):
        signals.extend(("writing", "document", "content", "copy"))
    if _REVIEW_SIGNAL_RE.search(value):
        signals.extend(("review", "audit", "quality"))
    if _VERIFY_SIGNAL_RE.search(value):
        signals.extend(("verification", "testing", "validation", "evidence"))
    if _RESEARCH_SIGNAL_RE.search(value):
        signals.extend(("research", "analysis", "investigation"))
    seen: list[str] = []
    for signal in signals:
        if signal not in seen:
            seen.append(signal)
    return tuple(seen)


def infer_goal_capability(
    objective: str, acceptance: tuple[str, ...] | list[str] = ()
) -> tuple[str, tuple[str, ...]]:
    """Choose the deliver capability for a goal plus the signals that justified it.

    Ordering is intentional: an explicit design/visual goal wins; a concrete web
    implementation goal (HTML/CSS/frontend/静态页) is implementation so the
    catalog can choose a real frontend role; document/announcement goals are
    writing; review/verification goals keep their independent capability.  An
    ordinary implementation goal stays ``implementation``.
    """

    text = "\n".join((objective or "", *[str(item) for item in acceptance]))
    if _DESIGN_SIGNAL_RE.search(text) and not _WEB_SIGNAL_RE.search(text):
        capability = "design"
    elif _WEB_SIGNAL_RE.search(text):
        capability = "implementation"
    elif _WRITING_SIGNAL_RE.search(text):
        capability = "writing"
    elif _REVIEW_SIGNAL_RE.search(text):
        capability = "review"
    elif _VERIFY_SIGNAL_RE.search(text):
        capability = "verification"
    else:
        capability = "implementation"
    return capability, goal_role_signals(text)


def stable_hash(payload: Any) -> str:
    """Deterministic SHA-256 over a JSON-serializable payload."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PlanInvalid(AppError):
    """A proposal that failed program validation (never executed as-is)."""

    def __init__(self, message: str, *, problems: Sequence[str] = ()) -> None:
        super().__init__(ErrorCode.CONFIG_INVALID, message, details={"problems": list(problems)})
        self.problems = tuple(problems)


@dataclass(frozen=True, slots=True)
class RawSubtask:
    """Untrusted Subtask proposal (from rules or a model)."""

    key: str
    objective: str
    capability: str
    acceptance: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    write: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RawSubtask":
        key = _require_str(data.get("key"), "key")
        objective = _require_str(data.get("objective"), "objective")
        capability = _require_str(data.get("capability"), "capability")
        acceptance = _str_tuple(data.get("acceptance"), "acceptance")
        depends_on = _str_tuple(data.get("depends_on"), "depends_on")
        write = data.get("write", False)
        if not isinstance(write, bool):
            raise ValueError("write must be a boolean")
        return cls(
            key=key,
            objective=objective,
            capability=capability,
            acceptance=acceptance,
            depends_on=depends_on,
            write=write,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "objective": self.objective,
            "capability": self.capability,
            "acceptance": list(self.acceptance),
            "depends_on": list(self.depends_on),
            "write": self.write,
        }


@dataclass(frozen=True, slots=True)
class PlanProposal:
    """An untrusted plan proposal."""

    subtasks: tuple[RawSubtask, ...]
    source: str = "rules"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "notes": list(self.notes),
            "subtasks": [subtask.to_dict() for subtask in self.subtasks],
        }


@dataclass(frozen=True, slots=True)
class SubtaskSpec:
    """A validated Subtask node (keys are plan-local, not runtime ids)."""

    key: str
    objective: str
    capability: str
    acceptance: tuple[str, ...]
    depends_on: tuple[str, ...]
    write: bool
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "objective": self.objective,
            "capability": self.capability,
            "acceptance": list(self.acceptance),
            "depends_on": list(self.depends_on),
            "write": self.write,
            "order": self.order,
        }


@dataclass(frozen=True, slots=True)
class Plan:
    """A validated, executable Subtask graph."""

    subtasks: tuple[SubtaskSpec, ...]
    source: str = "rules"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "notes": list(self.notes),
            "subtasks": [subtask.to_dict() for subtask in self.subtasks],
        }

    @property
    def plan_hash(self) -> str:
        return stable_hash(self.to_dict())

    @property
    def order(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.subtasks)

    def by_key(self) -> dict[str, SubtaskSpec]:
        return {spec.key: spec for spec in self.subtasks}

    @property
    def required_capabilities(self) -> tuple[str, ...]:
        seen: list[str] = []
        for spec in self.subtasks:
            if spec.capability not in seen:
                seen.append(spec.capability)
        return tuple(seen)


class PlanValidator:
    """Program-side validation of a :class:`PlanProposal`."""

    def __init__(
        self,
        *,
        known_capabilities: Sequence[str] | None = None,
        require_acceptance: bool = True,
        require_workspace_for_write: bool = True,
    ) -> None:
        self._known_capabilities = (
            frozenset(known_capabilities) if known_capabilities is not None else None
        )
        self._require_acceptance = require_acceptance
        self._require_workspace_for_write = require_workspace_for_write

    def validate(
        self,
        proposal: PlanProposal,
        *,
        workspace_path: str = "",
    ) -> Plan:
        problems: list[str] = []
        if not proposal.subtasks:
            problems.append("plan has no subtasks")
        seen: dict[str, RawSubtask] = {}
        for spec in proposal.subtasks:
            if not _KEY_RE.match(spec.key):
                problems.append(f"subtask key {spec.key!r} is not a valid slug")
            elif spec.key in seen:
                problems.append(f"duplicate subtask key {spec.key!r}")
            else:
                seen[spec.key] = spec
            if not spec.objective.strip():
                problems.append(f"subtask {spec.key!r} has an empty objective")
            if not spec.capability.strip():
                problems.append(f"subtask {spec.key!r} has an empty capability")
            elif (
                self._known_capabilities is not None
                and spec.capability not in self._known_capabilities
            ):
                problems.append(
                    f"subtask {spec.key!r} requires unknown capability {spec.capability!r}"
                )
            if self._require_acceptance and not spec.acceptance:
                problems.append(f"subtask {spec.key!r} has no acceptance criteria")
            if (
                self._require_workspace_for_write
                and spec.write
                and not workspace_path.strip()
            ):
                problems.append(
                    f"write subtask {spec.key!r} has no authorized workspace boundary"
                )
        if problems:
            raise PlanInvalid("plan failed program validation", problems=problems)

        try:
            graph = DependencyGraph(
                tuple(
                    GraphNode(key=spec.key, depends_on=spec.depends_on, write=spec.write)
                    for spec in proposal.subtasks
                )
            )
        except GraphError as exc:
            raise PlanInvalid("plan graph failed program validation", problems=exc.problems) from exc

        ordered = tuple(
            SubtaskSpec(
                key=seen[key].key,
                objective=seen[key].objective,
                capability=seen[key].capability,
                acceptance=seen[key].acceptance,
                depends_on=seen[key].depends_on,
                write=seen[key].write,
                order=index,
            )
            for index, key in enumerate(graph.topological_order())
        )
        return Plan(subtasks=ordered, source=proposal.source, notes=proposal.notes)


@runtime_checkable
class Planner(Protocol):
    """Proposal boundary; never grants permissions."""

    name: str

    async def plan(self, context: DispatchContext) -> PlanProposal: ...


class ModelProposalError(AppError):
    """A model proposal that could not be parsed into a plan proposal."""

    def __init__(self, message: str, *, problems: Sequence[str] = ()) -> None:
        super().__init__(
            ErrorCode.VALIDATION_FAILED, message, details={"problems": list(problems)}
        )
        self.problems = tuple(problems)


class RuleBasedPlanner:
    """Program-side minimal plan builder for an explicit target (default).

    It is deterministic and model-free: it always emits one implementation node,
    and when the Task declares acceptance criteria it adds a dependent
    verification node so the first-version minimum team is "developer +
    verifier"; otherwise a single developer node runs.  This is a rule, not a
    hardcoded fixed plan: the node set changes with the Task input, and the
    recruiter selects the actual agents.  It is **not** an orchestration agent
    and makes no model call.
    """

    name = "rules"

    def __init__(
        self,
        *,
        implementation_capability: str = "implementation",
        verification_capability: str = "verification",
        available_capabilities: Sequence[str] | None = None,
    ) -> None:
        self._implementation = implementation_capability
        self._verification = verification_capability
        #: Optional scheduler catalog vocabulary.  When supplied, goal-fit only
        #: selects a capability that the catalog can actually recruit; a legacy
        #: implementation-only catalog keeps working instead of failing a
        #: writing/design goal whose roles are not installed.
        self._available_capabilities = (
            frozenset(available_capabilities)
            if available_capabilities is not None
            else None
        )

    async def plan(self, context: DispatchContext) -> PlanProposal:
        declared = tuple(context.acceptance_criteria)
        # LG-047 QA-R1: the deliver node must always carry a real acceptance
        # boundary.  When the Task declares none (an ordinary Chat delivery
        # request such as "create a Markdown file ..."), the program derives a
        # deterministic, checkable criterion from the objective rather than
        # emitting a node that the validator must reject.  This supplies a
        # requirement to verify; it never asserts success.
        acceptance = declared or default_acceptance_criteria(context.objective)
        goal_capability, signals = infer_goal_capability(
            context.objective, acceptance
        )
        # A configured single implementation/verification planner may be used by
        # tests/older assemblies.  Goal-fit only substitutes capabilities that
        # this planner's contract can express; verification remains independent.
        deliver_capability = (
            goal_capability
            if self._implementation == "implementation"
            else self._implementation
        )
        if (
            self._available_capabilities is not None
            and deliver_capability not in self._available_capabilities
        ):
            deliver_capability = self._implementation
        subtasks: list[RawSubtask] = [
            RawSubtask(
                key="deliver",
                objective=context.objective,
                capability=deliver_capability,
                acceptance=acceptance,
                write=True,
            )
        ]
        # An independent verification node is added only when the Task itself
        # declares acceptance criteria.  A derived default keeps the prototype's
        # minimal single-worker plan (docs/10 §7) while still satisfying the
        # required acceptance boundary.
        if declared:
            subtasks.append(
                RawSubtask(
                    key="verify",
                    objective=f"Independent verification: {context.objective}",
                    capability=self._verification,
                    acceptance=declared,
                    depends_on=("deliver",),
                    write=False,
                )
            )
        rationale = (
            "goal-fit capability: "
            f"{deliver_capability} (signals={','.join(signals) or 'generic'})"
        )
        return PlanProposal(
            subtasks=tuple(subtasks),
            source="rules",
            notes=(
                "minimal rule plan: deliver + optional verify",
                rationale,
            ),
        )


ProposeFn = Callable[[DispatchContext], "Mapping[str, Any] | Awaitable[Mapping[str, Any]]"]


class ModelPlanner:
    """Optional, bounded, on-demand model plan proposal interface (not wired).

    No real model backend is implemented by this package and no default
    assembly constructs a ``ModelPlanner``.  A caller may inject a ``propose``
    callable explicitly; the dispatcher consults it only when an explicit
    :class:`~lightgravity.coordinator.planning.PlanningRequest` is present, so
    planning is never a per-Task/Run prerequisite.  ``propose`` returns a
    ``{"subtasks": [...]}`` mapping in the same shape as :class:`RawSubtask`.
    The mapping is parsed structurally and then validated by
    :class:`PlanValidator`; the model cannot add tools, connections, budgets or
    capabilities beyond what the recruiter's agent catalog exposes.

    The authoritative **per-Run** call budget is
    :attr:`~lightgravity.coordinator.planning.PlanningRequest.max_calls`, and it
    is enforced by :class:`~lightgravity.coordinator.graph.GraphDispatcher`
    (failed attempts count).  This class does **not** cap calls per instance by
    default, so one instance may be shared safely across Runs.  The optional
    ``max_calls`` constructor argument is a defensive *instance-lifetime ceiling*
    for direct callers only (default ``None`` = no ceiling); it must not be used
    as the per-Run budget.
    """

    name = "model"

    def __init__(self, propose: ProposeFn, *, max_calls: int | None = None) -> None:
        if max_calls is not None and max_calls <= 0:
            raise ValueError("max_calls must be > 0 when set")
        self._propose = propose
        #: Optional instance-lifetime ceiling (``None`` = uncapped); the per-Run
        #: budget lives on ``PlanningRequest`` and is enforced by the dispatcher.
        self._max_calls = max_calls
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def max_calls(self) -> int | None:
        return self._max_calls

    async def plan(self, context: DispatchContext) -> PlanProposal:
        if self._max_calls is not None and self._calls >= self._max_calls:
            raise ModelProposalError(
                "model planner instance call ceiling reached",
                problems=[f"max_calls={self._max_calls}"],
            )
        self._calls += 1
        raw = self._propose(context)
        if inspect.isawaitable(raw):
            raw = await raw
        if not isinstance(raw, Mapping):
            raise ModelProposalError("model proposal must be a mapping")
        subtasks_raw = raw.get("subtasks")
        if not isinstance(subtasks_raw, Sequence) or isinstance(subtasks_raw, (str, bytes)):
            raise ModelProposalError("model proposal must contain a subtasks list")
        subtasks: list[RawSubtask] = []
        problems: list[str] = []
        for index, item in enumerate(subtasks_raw):
            if not isinstance(item, Mapping):
                problems.append(f"subtask #{index} is not a mapping")
                continue
            try:
                subtasks.append(RawSubtask.from_mapping(item))
            except ValueError as exc:
                problems.append(f"subtask #{index}: {exc}")
        if problems:
            raise ModelProposalError("model proposal is malformed", problems=problems)
        notes_raw = raw.get("notes", [])
        notes = (
            tuple(str(item) for item in notes_raw)
            if isinstance(notes_raw, Sequence) and not isinstance(notes_raw, (str, bytes))
            else ()
        )
        return PlanProposal(subtasks=tuple(subtasks), source="model", notes=notes)


#: A filename-like token in the objective (used to derive a concrete, checkable
#: acceptance criterion for a generic Chat file-delivery request).
_ARTIFACT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.[A-Za-z0-9]{1,8}")


def default_acceptance_criteria(objective: str) -> tuple[str, ...]:
    """Deterministically derive a minimal, checkable acceptance criterion.

    Used only when a Task declares no criteria (an ordinary Chat delivery).  If
    the objective names a concrete artifact, the criterion requires that file in
    the task workspace; otherwise it requires a produced deliverable that
    matches the objective.  This is a *requirement*, not a success claim: the
    existing machine check and independent review still decide the outcome.
    """

    text = (objective or "").strip()
    match = _ARTIFACT_RE.search(text)
    if match is not None:
        name = match.group(0)
        return (
            f"The requested deliverable file {name!r} exists in the task "
            f"workspace and satisfies the objective: {text}",
        )
    return (f"A deliverable matching the objective is produced: {text}",)


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _str_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be a list of strings")
    result: list[str] = []
    for item in value:
        result.append(_require_str(item, field))
    return tuple(result)


__all__ = [
    "ModelPlanner",
    "goal_role_signals",
    "infer_goal_capability",
    "ModelProposalError",
    "Plan",
    "PlanInvalid",
    "PlanProposal",
    "PlanValidator",
    "Planner",
    "PlanningRequest",
    "PlanningTrigger",
    "ProposeFn",
    "RawSubtask",
    "RuleBasedPlanner",
    "SubtaskSpec",
    "default_acceptance_criteria",
    "stable_hash",
]
