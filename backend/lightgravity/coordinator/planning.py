"""Bounded on-demand planning request (docs/01 §4, default architecture).

Planning is **not** a mandatory per-Task/Run step and **not** a resident
orchestration agent.  For an explicit target the coordinator builds a minimal
legal plan program-side (see :class:`~lightgravity.coordinator.planner.RuleBasedPlanner`)
and validates it with :class:`~lightgravity.coordinator.planner.PlanValidator`.
A model-backed decomposition proposal is an *optional, bounded, on-demand*
capability: it may only be consulted when an explicit :class:`PlanningRequest`
records **why** it is needed, and it must stay inside the same Task/Run budget
and call cap.  Candidate plans are always program-validated; a request never
grants tools, connections or acceptance authority.

This module deliberately implements only the request/trigger contract.  No real
model planner is wired and no user-facing endpoint is added: the injectable
:class:`~lightgravity.coordinator.planner.ModelPlanner` proposal interface
remains the integration seam and is documented as not implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PlanningTrigger(StrEnum):
    """Why an on-demand planning proposal is being requested.

    These are the design triggers from the product decision.  Recognising a
    trigger only records the reason; it never starts a hidden planning loop and
    never calls a model on its own.
    """

    USER_REQUEST = "user_request"
    AMBIGUOUS_REQUIREMENT = "ambiguous_requirement"
    BLOCKED = "blocked"
    REPAIR_CAP = "repair_cap"


@dataclass(frozen=True, slots=True)
class PlanningRequest:
    """A bounded, reasoned, single-Run request for a model plan proposal.

    The request is validated at construction so a malformed value can never be
    carried into a Run and explode later: a valid trigger string is normalized to
    :class:`PlanningTrigger` (unknown strings and non-string values are
    rejected), ``requested_by`` must be a non-empty printable string, and
    ``reason``/``max_calls`` stay strict.
    """

    trigger: PlanningTrigger
    reason: str
    requested_by: str = "user"
    #: Maximum proposal calls **for this Run**, enforced by the program (the
    #: dispatcher); every attempt counts, including a failed proposal call.
    #: ``1`` is the default minimum plan; the dispatcher never loops.
    max_calls: int = 1

    def __post_init__(self) -> None:
        # Normalize a valid trigger string to the enum so ``to_dict`` and the
        # dispatcher's audit note can never raise ``AttributeError`` on a plain
        # ``str``.  Reject anything that is not a known trigger.
        trigger = self.trigger
        if isinstance(trigger, PlanningTrigger):
            pass
        elif isinstance(trigger, str):
            try:
                trigger = PlanningTrigger(trigger)
            except ValueError as exc:
                raise ValueError(f"unknown planning trigger {self.trigger!r}") from exc
        else:
            raise ValueError("trigger must be a PlanningTrigger or its string value")
        object.__setattr__(self, "trigger", trigger)

        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("planning reason must be a non-empty string")

        requested_by = self.requested_by
        if not isinstance(requested_by, str) or not requested_by.strip():
            raise ValueError("requested_by must be a non-empty string")
        if len(requested_by) > 200 or not requested_by.isprintable():
            raise ValueError("requested_by must be a printable string of <= 200 chars")
        object.__setattr__(self, "requested_by", requested_by.strip())

        if not isinstance(self.max_calls, int) or isinstance(self.max_calls, bool):
            raise ValueError("max_calls must be an integer")
        if self.max_calls < 1:
            raise ValueError("max_calls must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger.value,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "max_calls": self.max_calls,
        }


__all__ = ["PlanningRequest", "PlanningTrigger"]
