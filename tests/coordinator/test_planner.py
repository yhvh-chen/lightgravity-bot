"""Planner proposal + program validation (LG-008).

Model calls are stubbed; no test reaches a real model.
"""

from __future__ import annotations

import pytest

from lightgravity.coordinator import DispatchContext
from lightgravity.coordinator.planner import (
    ModelPlanner,
    ModelProposalError,
    PlanInvalid,
    PlanProposal,
    PlanValidator,
    RawSubtask,
    RuleBasedPlanner,
    stable_hash,
)
from lightgravity.contracts import ErrorCode


def context(*, acceptance: tuple[str, ...] = ("it works",)) -> DispatchContext:
    return DispatchContext(
        task_id="task_01J0000000000000000000001",
        run_id="run_01J0000000000000000000001",
        attempt=1,
        objective="implement login",
        acceptance_criteria=acceptance,
        workspace_path="/tmp/ws",
    )


async def test_rule_planner_adds_verification_when_acceptance_present() -> None:
    proposal = await RuleBasedPlanner().plan(context())
    keys = [subtask.key for subtask in proposal.subtasks]
    assert keys == ["deliver", "verify"]
    deliver, verify = proposal.subtasks
    assert deliver.write is True and deliver.capability == "implementation"
    assert verify.write is False and verify.depends_on == ("deliver",)
    plan = PlanValidator(known_capabilities=["implementation", "verification"]).validate(
        proposal, workspace_path="/tmp/ws"
    )
    assert plan.order == ("deliver", "verify")
    assert [spec.order for spec in plan.subtasks] == [0, 1]
    assert plan.required_capabilities == ("implementation", "verification")


async def test_rule_planner_single_node_without_acceptance() -> None:
    proposal = await RuleBasedPlanner().plan(context(acceptance=()))
    assert [subtask.key for subtask in proposal.subtasks] == ["deliver"]
    with pytest.raises(PlanInvalid) as excinfo:
        PlanValidator().validate(proposal, workspace_path="/tmp/ws")
    assert any("acceptance" in problem for problem in excinfo.value.problems)


def test_validator_rejects_duplicate_unknown_and_cyclic_graphs() -> None:
    validator = PlanValidator(require_acceptance=True)
    duplicate = PlanProposal(
        subtasks=(
            RawSubtask(key="a", objective="x", capability="implementation", acceptance=("ok",)),
            RawSubtask(key="a", objective="y", capability="implementation", acceptance=("ok",)),
        )
    )
    with pytest.raises(PlanInvalid) as excinfo:
        validator.validate(duplicate, workspace_path="/tmp/ws")
    assert any("duplicate" in problem for problem in excinfo.value.problems)

    unknown_dep = PlanProposal(
        subtasks=(
            RawSubtask(
                key="a",
                objective="x",
                capability="implementation",
                acceptance=("ok",),
                depends_on=("missing",),
            ),
        )
    )
    with pytest.raises(PlanInvalid):
        validator.validate(unknown_dep, workspace_path="/tmp/ws")

    cycle = PlanProposal(
        subtasks=(
            RawSubtask(
                key="a",
                objective="x",
                capability="implementation",
                acceptance=("ok",),
                depends_on=("b",),
            ),
            RawSubtask(
                key="b",
                objective="y",
                capability="implementation",
                acceptance=("ok",),
                depends_on=("a",),
            ),
        )
    )
    with pytest.raises(PlanInvalid) as excinfo:
        validator.validate(cycle, workspace_path="/tmp/ws")
    assert any("cycle" in problem for problem in excinfo.value.problems)


def test_validator_rejects_unknown_capability() -> None:
    validator = PlanValidator(known_capabilities=["implementation"])
    proposal = PlanProposal(
        subtasks=(
            RawSubtask(
                key="a",
                objective="x",
                capability="deployment",
                acceptance=("ok",),
            ),
        )
    )
    with pytest.raises(PlanInvalid) as excinfo:
        validator.validate(proposal, workspace_path="/tmp/ws")
    assert any("unknown capability" in problem for problem in excinfo.value.problems)


def test_write_subtask_requires_workspace_boundary() -> None:
    proposal = PlanProposal(
        subtasks=(
            RawSubtask(
                key="a",
                objective="x",
                capability="implementation",
                acceptance=("ok",),
                write=True,
            ),
        )
    )
    with pytest.raises(PlanInvalid):
        PlanValidator().validate(proposal, workspace_path="")


async def test_model_planner_proposal_is_parsed_then_validated() -> None:
    def propose(_: DispatchContext) -> dict[str, object]:
        return {
            "subtasks": [
                {
                    "key": "deliver",
                    "objective": "implement",
                    "capability": "implementation",
                    "acceptance": ["works"],
                    "write": True,
                    # Unknown model-supplied fields must be ignored, not become authority.
                    "tools": ["run-command"],
                    "connection_ref": "attacker",
                }
            ],
            "notes": ["model"],
        }

    planner = ModelPlanner(propose)
    proposal = await planner.plan(context())
    assert proposal.source == "model"
    assert planner.calls == 1
    assert proposal.subtasks[0].depends_on == ()
    assert not hasattr(proposal.subtasks[0], "tools")
    plan = PlanValidator().validate(proposal, workspace_path="/tmp/ws")
    assert plan.order == ("deliver",)


async def test_model_planner_rejects_malformed_and_caps_calls() -> None:
    planner = ModelPlanner(lambda _: {"subtasks": "nope"})  # type: ignore[arg-type,return-value]
    with pytest.raises(ModelProposalError):
        await planner.plan(context())

    planner = ModelPlanner(lambda _: {"subtasks": []}, max_calls=1)
    empty = await planner.plan(context())
    assert empty.subtasks == ()
    with pytest.raises(PlanInvalid):
        PlanValidator().validate(empty, workspace_path="/tmp/ws")
    with pytest.raises(ModelProposalError):
        await planner.plan(context())


def test_plan_hash_is_stable_and_structure_sensitive() -> None:
    first = PlanProposal(
        subtasks=(
            RawSubtask(key="a", objective="x", capability="implementation", acceptance=("ok",)),
        )
    )
    second = PlanProposal(
        subtasks=(
            RawSubtask(key="a", objective="x", capability="implementation", acceptance=("ok",)),
        )
    )
    changed = PlanProposal(
        subtasks=(
            RawSubtask(key="a", objective="different", capability="implementation", acceptance=("ok",)),
        )
    )
    validator = PlanValidator()
    assert validator.validate(first, workspace_path="/tmp/ws").plan_hash == validator.validate(
        second, workspace_path="/tmp/ws"
    ).plan_hash
    assert validator.validate(first, workspace_path="/tmp/ws").plan_hash != validator.validate(
        changed, workspace_path="/tmp/ws"
    ).plan_hash
    assert stable_hash({"a": 1}) == stable_hash({"a": 1})
    assert ErrorCode.CONFIG_INVALID.value == "config_invalid"
