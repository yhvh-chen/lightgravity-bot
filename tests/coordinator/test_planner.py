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


def context(
    *, acceptance: tuple[str, ...] = ("it works",), objective: str = "implement login"
) -> DispatchContext:
    return DispatchContext(
        task_id="task_01J0000000000000000000001",
        run_id="run_01J0000000000000000000001",
        attempt=1,
        objective=objective,
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


async def test_rule_planner_single_node_derives_acceptance_without_declared() -> None:
    """LG-047 QA-R1: an ordinary Chat delivery request declares no criteria.

    The program-side rule plan must still be a *valid* minimal single-worker
    plan: the deliver node carries a deterministic derived acceptance criterion,
    no independent verify node is added, and the unchanged validator accepts it.
    """

    proposal = await RuleBasedPlanner().plan(
        context(acceptance=(), objective="Create a Markdown file named report.md")
    )
    assert [subtask.key for subtask in proposal.subtasks] == ["deliver"]
    deliver = proposal.subtasks[0]
    assert deliver.acceptance and "report.md" in deliver.acceptance[0]
    plan = PlanValidator(known_capabilities=["implementation"]).validate(
        proposal, workspace_path="/tmp/ws"
    )
    assert plan.order == ("deliver",)


def test_validator_still_requires_acceptance_and_workspace() -> None:
    """The program checks are not waived: an arbitrary proposal missing
    acceptance criteria or a write workspace boundary is still rejected."""

    no_acceptance = PlanProposal(
        subtasks=(RawSubtask(key="a", objective="x", capability="implementation", write=True),)
    )
    with pytest.raises(PlanInvalid) as excinfo:
        PlanValidator().validate(no_acceptance, workspace_path="/tmp/ws")
    assert any("acceptance" in problem for problem in excinfo.value.problems)

    no_workspace = PlanProposal(
        subtasks=(
            RawSubtask(
                key="a", objective="x", capability="implementation",
                acceptance=("ok",), write=True,
            ),
        )
    )
    with pytest.raises(PlanInvalid) as excinfo:
        PlanValidator().validate(no_workspace, workspace_path="")
    assert any("workspace" in problem for problem in excinfo.value.problems)


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


async def test_model_planner_rejects_malformed_and_honors_optional_instance_ceiling() -> None:
    planner = ModelPlanner(lambda _: {"subtasks": "nope"})  # type: ignore[arg-type,return-value]
    with pytest.raises(ModelProposalError):
        await planner.plan(context())

    # ``max_calls`` is an optional defensive instance-lifetime ceiling for
    # direct callers; the per-Run budget is ``PlanningRequest.max_calls`` and is
    # enforced by the dispatcher (see test_graph_dispatcher.py).
    planner = ModelPlanner(lambda _: {"subtasks": []}, max_calls=1)
    empty = await planner.plan(context())
    assert empty.subtasks == ()
    with pytest.raises(PlanInvalid):
        PlanValidator().validate(empty, workspace_path="/tmp/ws")
    with pytest.raises(ModelProposalError):
        await planner.plan(context())


async def test_model_planner_default_has_no_instance_ceiling() -> None:
    """QA-1: a default ``ModelPlanner`` is not globally capped across contexts."""

    planner = ModelPlanner(lambda _: {"subtasks": []})
    first = DispatchContext(
        task_id="task_a", run_id="run_a", attempt=1, objective="x", workspace_path="/tmp/ws"
    )
    second = DispatchContext(
        task_id="task_b", run_id="run_b", attempt=1, objective="x", workspace_path="/tmp/ws"
    )
    assert (await planner.plan(first)).subtasks == ()
    assert (await planner.plan(second)).subtasks == ()
    assert planner.calls == 2
    assert planner.max_calls is None


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
