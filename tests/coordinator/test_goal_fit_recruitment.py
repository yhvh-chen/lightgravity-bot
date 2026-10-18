"""LG-126 goal-fit capability inference and deterministic role applicability."""

from __future__ import annotations

from lightgravity.adapter import ResourceCompiler
from lightgravity.coordinator.planner import (
    PlanValidator,
    RuleBasedPlanner,
    infer_goal_capability,
)
from lightgravity.coordinator.recruiter import Recruiter, RoleCatalog, RoleProfile
from lightgravity.store import FileStore

from graph_helpers import build_environment, create_agent

HTML_GOAL = "制作一页活动报名静态页，含主题、时间、地点和联系入口并核验四项信息 HTML"
ANNOUNCEMENT_GOAL = "独立生成 announcement.md 发布公告，包含事项与事实核验"


def _catalog() -> RoleCatalog:
    return RoleCatalog(
        {
            "implementation": ["developer", "frontend-dev"],
            "writing": ["developer", "docs-writer"],
            "verification": ["verifier"],
        },
        profiles={
            "developer": RoleProfile(
                agent_ref="developer",
                title="Developer",
                role_category="engineering",
                capabilities=("implementation", "verification"),
                builtin_default=True,
            ),
            "frontend-dev": RoleProfile(
                agent_ref="frontend-dev",
                title="Frontend Developer",
                description="Builds web pages, HTML/CSS interfaces and responsive UI.",
                role_category="engineering",
                division="engineering",
                capabilities=("implementation",),
            ),
            "docs-writer": RoleProfile(
                agent_ref="docs-writer",
                title="Technical Writer",
                description="Writes announcements, documentation, Markdown and release copy.",
                role_category="engineering",
                division="engineering",
                capabilities=("writing",),
            ),
            "verifier": RoleProfile(
                agent_ref="verifier",
                title="Reality Checker",
                description="Independently verifies acceptance evidence and QA.",
                role_category="testing",
                capabilities=("verification",),
            ),
        },
        fallback_ref="developer",
    )


def _agents(store: FileStore) -> None:
    build_environment(store)
    create_agent(
        store,
        "frontend-dev",
        skill_refs=["implementation"],
        tool_refs=("view-file", "edit-file"),
        extra={"title": "Frontend Developer", "role_category": "engineering"},
    )
    create_agent(
        store,
        "docs-writer",
        skill_refs=["implementation"],
        tool_refs=("view-file", "edit-file"),
        extra={"title": "Technical Writer", "role_category": "engineering"},
    )


async def _team(store: FileStore, objective: str, *, preferred: str | None = None):
    from lightgravity.coordinator import DispatchContext

    catalog = _catalog()
    context = DispatchContext(
        task_id="task_01J0000000000000000000001",
        run_id="run_01J0000000000000000000001",
        attempt=1,
        objective=objective,
        acceptance_criteria=(),
        workspace_path="/tmp/ws",
    )
    proposal = await RuleBasedPlanner().plan(context)
    plan = PlanValidator(known_capabilities=catalog.capabilities).validate(
        proposal, workspace_path="/tmp/ws"
    )
    recruiter = Recruiter(catalog, compile_agent=ResourceCompiler(store).compile_agent)
    return recruiter.recruit(
        plan, goal_text=objective, preferred_agent_ref=preferred
    )


async def test_html_and_announcement_choose_justified_real_roles(
    store: FileStore,
) -> None:
    _agents(store)
    html_capability, html_signals = infer_goal_capability(HTML_GOAL)
    assert html_capability == "implementation"
    assert "frontend" in html_signals
    html_team = await _team(store, HTML_GOAL)
    html_deliver = html_team.member_for("implementation")
    assert html_deliver is not None
    assert html_deliver.role_ref == "frontend-dev"
    assert "goal-fit metadata match" in html_deliver.selection_reason

    writing_capability, writing_signals = infer_goal_capability(ANNOUNCEMENT_GOAL)
    assert writing_capability == "writing"
    assert "document" in writing_signals
    writing_team = await _team(store, ANNOUNCEMENT_GOAL)
    writing_deliver = writing_team.member_for("writing")
    assert writing_deliver is not None
    assert writing_deliver.role_ref == "docs-writer"
    # Actual role/version/config provenance is returned for the Team projection.
    assert writing_deliver.candidate.template_version
    assert writing_deliver.candidate.config_hash
    assert writing_deliver.candidate.skill_refs == ("implementation",)


async def test_generic_goal_uses_default_fallback_and_explicit_request_wins(
    store: FileStore,
) -> None:
    _agents(store)
    generic = await _team(store, "implement login")
    member = generic.member_for("implementation")
    assert member is not None and member.role_ref == "developer"

    explicit = await _team(store, HTML_GOAL, preferred="developer")
    chosen = explicit.member_for("implementation")
    assert chosen is not None
    assert chosen.role_ref == "developer"
    assert "explicit user request" in chosen.selection_reason


async def test_rule_plan_records_goal_fit_rationale() -> None:
    from lightgravity.coordinator import DispatchContext

    proposal = await RuleBasedPlanner().plan(
        DispatchContext(
            task_id="task_01J0000000000000000000001",
            run_id="run_01J0000000000000000000001",
            attempt=1,
            objective=ANNOUNCEMENT_GOAL,
            acceptance_criteria=(),
            workspace_path="/tmp/ws",
        )
    )
    assert proposal.subtasks[0].capability == "writing"
    assert any("goal-fit capability: writing" in note for note in proposal.notes)
