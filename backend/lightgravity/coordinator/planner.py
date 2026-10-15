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
    ) -> None:
        self._implementation = implementation_capability
        self._verification = verification_capability

    async def plan(self, context: DispatchContext) -> PlanProposal:
        acceptance = tuple(context.acceptance_criteria)
        subtasks: list[RawSubtask] = [
            RawSubtask(
                key="deliver",
                objective=context.objective,
                capability=self._implementation,
                acceptance=acceptance,
                write=True,
            )
        ]
        if acceptance:
            subtasks.append(
                RawSubtask(
                    key="verify",
                    objective=f"独立验证：{context.objective}",
                    capability=self._verification,
                    acceptance=acceptance,
                    depends_on=("deliver",),
                    write=False,
                )
            )
        return PlanProposal(
            subtasks=tuple(subtasks),
            source="rules",
            notes=("minimal rule plan: deliver + optional verify",),
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
    "stable_hash",
]
