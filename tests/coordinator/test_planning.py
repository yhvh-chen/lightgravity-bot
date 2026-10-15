"""Bounded on-demand planning request contract (no model is called)."""

from __future__ import annotations

import pytest

from lightgravity.coordinator import PlanningRequest, PlanningTrigger


def test_planning_request_records_trigger_and_reason() -> None:
    request = PlanningRequest(
        trigger=PlanningTrigger.AMBIGUOUS_REQUIREMENT,
        reason="the objective has two possible interpretations",
        requested_by="user",
    )
    assert request.to_dict() == {
        "trigger": "ambiguous_requirement",
        "reason": "the objective has two possible interpretations",
        "requested_by": "user",
        "max_calls": 1,
    }


def test_all_design_triggers_are_recognized() -> None:
    assert {trigger.value for trigger in PlanningTrigger} == {
        "user_request",
        "ambiguous_requirement",
        "blocked",
        "repair_cap",
    }


@pytest.mark.parametrize("reason", ["", "   "])
def test_planning_request_requires_a_reason(reason: str) -> None:
    with pytest.raises(ValueError):
        PlanningRequest(trigger=PlanningTrigger.USER_REQUEST, reason=reason)


@pytest.mark.parametrize("max_calls", [0, -1])
def test_planning_request_is_bounded(max_calls: int) -> None:
    with pytest.raises(ValueError):
        PlanningRequest(
            trigger=PlanningTrigger.BLOCKED, reason="blocked dependency", max_calls=max_calls
        )


def test_trigger_string_is_normalized_and_to_dict_never_crashes() -> None:
    # A plain string trigger must be normalized at construction, not explode as
    # ``AttributeError: 'str' object has no attribute 'value'`` later in dispatch.
    request = PlanningRequest(trigger="user_request", reason="plain str trigger")  # type: ignore[arg-type]
    assert request.trigger is PlanningTrigger.USER_REQUEST
    assert request.to_dict()["trigger"] == "user_request"


@pytest.mark.parametrize("trigger", ["not_a_trigger", "", "USER_REQUEST", 123, None, object()])
def test_unknown_or_non_string_trigger_is_rejected(trigger: object) -> None:
    with pytest.raises(ValueError):
        PlanningRequest(trigger=trigger, reason="x")  # type: ignore[arg-type]


@pytest.mark.parametrize("requested_by", ["", "   ", 123, None, "bad\nname", "x" * 201])
def test_requested_by_must_be_a_non_empty_printable_string(requested_by: object) -> None:
    with pytest.raises(ValueError):
        PlanningRequest(  # type: ignore[arg-type]
            trigger=PlanningTrigger.USER_REQUEST, reason="x", requested_by=requested_by
        )


def test_requested_by_is_stripped() -> None:
    request = PlanningRequest(
        trigger=PlanningTrigger.USER_REQUEST, reason="x", requested_by="  user  "
    )
    assert request.requested_by == "user"
    assert request.to_dict()["requested_by"] == "user"
