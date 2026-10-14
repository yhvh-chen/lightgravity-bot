"""Recruiter: minimal team selection, failure reasons and fixed config hash (LG-008)."""

from __future__ import annotations

import pytest

from lightgravity.adapter import ResourceCompiler
from lightgravity.coordinator.planner import (
    Plan,
    PlanProposal,
    PlanValidator,
    RawSubtask,
)
from lightgravity.coordinator.recruiter import (
    RecruitError,
    Recruiter,
    RoleCatalog,
    member_config_hash,
)
from lightgravity.store import FileStore

from graph_helpers import build_environment, create_agent


def make_plan(required: tuple[str, ...] = ("implementation", "verification")) -> Plan:
    subtasks = []
    for index, capability in enumerate(required):
        subtasks.append(
            RawSubtask(
                key=f"node{index}",
                objective=f"do {capability}",
                capability=capability,
                acceptance=("ok",),
                write=capability == "implementation",
            )
        )
    return PlanValidator(known_capabilities=list(required)).validate(
        PlanProposal(subtasks=tuple(subtasks)),
        workspace_path="/tmp/ws",
    )


def make_recruiter(store: FileStore, capabilities: dict[str, list[str]]) -> Recruiter:
    compiler = ResourceCompiler(store)
    return Recruiter(RoleCatalog(capabilities), compile_agent=compiler.compile_agent)


def test_selects_minimal_team_per_capability(store: FileStore) -> None:
    build_environment(store)
    recruiter = make_recruiter(
        store, {"implementation": ["developer"], "verification": ["verifier"]}
    )
    team = recruiter.recruit(make_plan())
    assert {member.role_ref for member in team.members} == {"developer", "verifier"}
    assert team.capability_to_role == {
        "implementation": "developer",
        "verification": "verifier",
    }
    developer = team.member_for("implementation")
    assert developer is not None
    assert developer.capabilities == ("implementation",)
    assert developer.candidate.executable is True
    assert developer.config_hash


def test_reuses_one_agent_for_multiple_capabilities(store: FileStore) -> None:
    build_environment(store)
    recruiter = make_recruiter(
        store, {"implementation": ["developer"], "verification": ["developer"]}
    )
    team = recruiter.recruit(make_plan())
    assert len(team.members) == 1
    member = team.members[0]
    assert member.role_ref == "developer"
    assert set(member.capabilities) == {"implementation", "verification"}
    assert member.subtask_keys == ("node0", "node1")


def test_missing_or_disabled_candidate_records_reasons(store: FileStore) -> None:
    build_environment(store)
    missing = make_recruiter(store, {"implementation": ["developer"]})
    with pytest.raises(RecruitError) as excinfo:
        missing.recruit(make_plan())
    assert any("verification" in problem for problem in excinfo.value.problems)

    create_agent(
        store,
        "disabled-dev",
        skill_refs=["implementation"],
        tool_refs=("view-file", "edit-file"),
        extra={"enabled": False},
    )
    disabled = make_recruiter(store, {"implementation": ["disabled-dev"], "verification": ["verifier"]})
    with pytest.raises(RecruitError) as excinfo:
        disabled.recruit(make_plan())
    assert any("disabled-dev" in problem for problem in excinfo.value.problems)
    assert any("agent_disabled" in problem for problem in excinfo.value.problems)


def test_member_config_hash_is_stable_and_revision_sensitive(store: FileStore) -> None:
    build_environment(store)
    recruiter = make_recruiter(store, {"implementation": ["developer"]})
    plan = make_plan(("implementation",))
    first = recruiter.recruit(plan).members[0]
    second = recruiter.recruit(plan).members[0]
    assert first.config_hash == second.config_hash

    current = store.read("agent", "developer")
    store.write(
        "agent",
        "developer",
        {"title": "developer v2"},
        expected_revision=current.revision,
        actor="test",
    )
    changed = recruiter.recruit(plan).members[0]
    assert changed.config_hash != first.config_hash
    assert changed.candidate.template_version != first.candidate.template_version


def test_member_config_hash_helper_is_order_insensitive() -> None:
    a = member_config_hash(
        role_ref="developer",
        agent_config_hash="abc",
        connection_ref="primary",
        skill_refs=["s2", "s1"],
        tool_refs=["t2", "t1"],
        capabilities=["b", "a"],
    )
    b = member_config_hash(
        role_ref="developer",
        agent_config_hash="abc",
        connection_ref="primary",
        skill_refs=["s1", "s2"],
        tool_refs=["t1", "t2"],
        capabilities=["a", "b"],
    )
    assert a == b
