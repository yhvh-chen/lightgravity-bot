"""Graph dispatcher: planner + recruiter + scheduler behind the LG-007 seam (LG-008).

:class:`GraphDispatcher` implements :class:`~lightgravity.coordinator.dispatcher.Dispatcher`.
The coordinator (LG-007) owns the Task queue, the single execution slot and the
Task/Run lifecycle; this dispatcher only decides *how* one dispatched Run turns
into a validated Subtask graph, a minimal temporary team and a dependency-ordered
execution:

1. a plan is produced program-side (minimal legal plan for an explicit target) or, only when an explicit on-demand ``PlanningRequest`` records why, proposed by an injected bounded model planner;
2. the program validates the graph (references, acyclicity, capabilities,
   acceptance, workspace boundary);
3. the recruiter resolves required capabilities to executable ``agent``
   resources and freezes each member's config hash;
4. the scheduler claims ready nodes with an owner/lease, enforces the
   concurrency limit and same-workspace single-writer rule, hands upstream
   artifact refs + content hashes to dependents and blocks downstream work when a
   dependency fails.

All control state is written through :class:`RunController` (and thus the
``Store``); the executor adapter never writes TASK.md/RUN.md/SUBTASK.md/Member
files.  Worker success only reaches ``passed`` after a minimal machine check and
never becomes Task acceptance - the Task is handed to LG-009 in the ``verifying``
phase with the candidate artifacts.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lightgravity.adapter import (
    CancelResult,
    CompileConstraints,
    CompiledAgentConfig,
    ConnectionPin,
    DefaultConnectionResolver,
    ExecuteRequest,
    ExecutorAdapter,
    ExecutorResult,
    ExecutionRef,
    ResourceCompiler,
)
from lightgravity.contracts import AppError, EventType, TaskPhase
from lightgravity.evidence import EvidenceRefError, import_evidence
from lightgravity.store import Store, new_id
from lightgravity.workspaces import WorkspaceProvider

from .dispatcher import DispatchContext, DispatchOutcome
from .planner import (
    ModelProposalError,
    Plan,
    PlanInvalid,
    Planner,
    PlanProposal,
    PlanValidator,
    RuleBasedPlanner,
    SubtaskSpec,
    stable_hash,
)
from .planning import PlanningRequest
from .recruiter import MemberPlan, RecruitError, Recruiter, RoleCatalog, TeamPlan
from .scheduler import (
    ArtifactHandoff,
    DependencyGraph,
    GraphNode,
    SubtaskClaimer,
    encode_handoffs,
)
from .session_flow import (
    NodeSession,
    completed_keys,
    extract_node_session,
    node_session_for_resume,
    record_node_session,
    reusable_completed_node,
)
from .state import RunController, StateWriter

_BLOCKED_STATES = frozenset({"failed", "blocked", "cancelled"})
_TERMINAL_STATES = frozenset({"passed", "failed", "blocked", "cancelled"})

#: Capabilities a single default agent is assumed to cover when no catalog is
#: supplied but a concrete ``agent_ref`` is present on the Task.
DEFAULT_CAPABILITIES = ("implementation", "verification")


@dataclass(frozen=True, slots=True)
class _Node:
    """A materialized Subtask: validated spec + runtime id + assigned member."""

    subtask_id: str
    spec: SubtaskSpec
    member: MemberPlan
    depends_on: tuple[str, ...]
    member_id: str = ""

    @property
    def key(self) -> str:
        return self.spec.key


@dataclass(frozen=True, slots=True)
class NodeResult:
    """Terminal result of one scheduled Subtask."""

    key: str
    subtask_id: str
    state: str  # passed | failed | cancelled
    failure_code: str | None = None
    failure_message: str | None = None
    handoff: ArtifactHandoff | None = None
    result: ExecutorResult | None = None


@dataclass
class _RunMemory:
    """Per-run scheduling memory kept only for the dispatch call."""

    running: dict[str, asyncio.Task[NodeResult]] = field(default_factory=dict)
    writer_keys: set[str] = field(default_factory=set)
    handoffs: dict[str, ArtifactHandoff] = field(default_factory=dict)


class GraphDispatcher:
    """Planner/recruiter/scheduler dispatcher (docs/01 §4, docs/08 §8 seam)."""

    name = "graph"

    def __init__(
        self,
        store: Store,
        executor: ExecutorAdapter,
        *,
        planner: Planner | None = None,
        recruiter: Recruiter | None = None,
        catalog: RoleCatalog | None = None,
        validator: PlanValidator | None = None,
        max_parallel: int = 1,
        lease_seconds: int = 300,
        owner: str | None = None,
        cancel_timeout: float = 15.0,
        compiler: ResourceCompiler | None = None,
        connections: DefaultConnectionResolver | None = None,
        workspaces: "WorkspaceProvider | None" = None,
        collaboration: Any | None = None,
        grant_registry: Any | None = None,
        autonomous_claim: bool = False,
    ) -> None:
        if max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")
        self._store = store
        self._executor = executor
        #: Program-side minimal plan builder.  Used for every Run unless an
        #: explicit on-demand request selects the optional model planner.
        self._program_planner: Planner = RuleBasedPlanner()
        #: Optional injected model proposal interface.  ``None`` (the default)
        #: means planning is program-side only; it is never constructed by the
        #: default assembly.
        self._planner: Planner | None = planner
        self._recruiter = recruiter
        self._catalog = catalog
        self._validator = validator or PlanValidator(
            known_capabilities=(catalog.capabilities if catalog is not None else None)
        )
        self._max_parallel = max_parallel
        self._lease_seconds = lease_seconds
        self._owner = owner or f"graph-dispatcher:{os.getpid()}"
        self._cancel_timeout = cancel_timeout
        self._compiler = compiler or ResourceCompiler(store)
        self._default_connections = connections
        #: Optional real worktree isolation (LG-018).  When supplied, every
        #: ``write`` node executes in its own git worktree at a frozen base
        #: commit; ``None`` keeps the conservative single-writer behavior.
        self._workspaces = workspaces
        self._run_workspaces: dict[str, dict[str, str]] = {}
        self._run_pins: dict[str, ConnectionPin | None] = {}
        self._inflight: dict[str, set[asyncio.Task[ExecutorResult]]] = {}
        self._active_refs: dict[str, list[ExecutionRef]] = {}
        self._explicit_cancel: set[str] = set()
        #: Optional on-demand proposal attempts, keyed by run id.  The program
        #: (not a shared instance counter) owns this budget, so sharing one
        #: planner across Runs is safe and re-dispatching the same Run cannot
        #: open a new model loop.  Only Runs that carried an explicit
        #: ``PlanningRequest`` get an entry, kept for the process lifetime.
        self._on_demand_calls: dict[str, int] = {}
        #: LG-031 optional decentralized authority.  ``None`` (the default) keeps
        #: the deterministic ``SubtaskClaimer`` path exactly as before; when a
        #: ``CollaborationService`` with ``enabled=True`` is supplied the graph
        #: claims through the fenced lease authority and mints a program-frozen
        #: execution grant for each node.
        self._collaboration = collaboration
        self._grant_registry = grant_registry
        #: LG-031 R1 additive: when true (and the decentralized path is enabled)
        #: the graph does **not** pre-claim a node on the worker's behalf.  It
        #: mints a discovery-only *pool* grant and attaches the restricted
        #: discover/claim tool, so the worker itself proposes the claim and the
        #: program authenticates/validates/grants atomically.  Default ``False``
        #: keeps the exact prior behavior (program pre-claims per node).
        self._autonomous_claim = autonomous_claim
        #: node key -> (grant token, subtask id) for explicit revocation on stop.
        self._node_grants: dict[str, tuple[str, str]] = {}

    @property
    def executor(self) -> ExecutorAdapter:
        return self._executor

    @property
    def planner(self) -> Planner | None:
        """The optional injected model proposal interface (``None`` by default)."""

        return self._planner

    # --------------------------------------------------------------- dispatch
    async def dispatch(
        self,
        context: DispatchContext,
        controller: RunController,
        emit: Callable[[dict[str, Any]], Any],
    ) -> DispatchOutcome:
        run_id = context.run_id
        self._explicit_cancel.discard(run_id)
        self._run_pins[run_id] = None
        self._run_workspaces[run_id] = {}
        self._inflight[run_id] = set()
        self._active_refs[run_id] = []
        try:
            return await self._dispatch_graph(context, controller, emit)
        finally:
            self._run_pins.pop(run_id, None)
            self._run_workspaces.pop(run_id, None)
            self._inflight.pop(run_id, None)
            self._active_refs.pop(run_id, None)

    async def _dispatch_graph(
        self,
        context: DispatchContext,
        controller: RunController,
        emit: Callable[[dict[str, Any]], Any],
    ) -> DispatchOutcome:
        # 1. Produce + validate the plan.  The default is the program-side
        #    minimal plan.  An injected model planner is consulted only when an
        #    explicit on-demand request (trigger + reason) records why, and only
        #    within that request's per-Run call budget (``PlanningRequest.max_calls``).
        #    The budget is tracked per Run by the program, not by a shared
        #    instance counter, so one planner can be shared across Runs and a
        #    repeated dispatch of the same Run cannot start a new model loop.
        #    Every attempt counts, including a failed proposal call.
        planning_request = context.planning_request
        model_planner = self._planner
        on_demand = planning_request is not None and model_planner is not None
        stage = "plan_on_demand" if on_demand else "program_plan"
        if on_demand and planning_request is not None and model_planner is not None:
            used = self._on_demand_calls.get(context.run_id, 0)
            if used >= planning_request.max_calls:
                return self._plan_failure(
                    controller,
                    stage,
                    ModelProposalError(
                        "model planner call budget exhausted for this run",
                        problems=[
                            f"max_calls={planning_request.max_calls}",
                            f"attempts={used}",
                        ],
                    ),
                )
            # Count before the call so a failed attempt also consumes budget.
            self._on_demand_calls[context.run_id] = used + 1
            planner: Planner = model_planner
        else:
            planner = self._program_planner
        try:
            proposal = await planner.plan(context)
        except AppError as exc:
            return self._plan_failure(controller, stage, exc)
        except Exception as exc:  # noqa: BLE001 - planner crash is a real failure
            return self._crash_failure(controller, stage, exc)
        if on_demand and planning_request is not None:
            try:
                proposal = self._record_planning_request(proposal, planning_request)
            except Exception as exc:  # noqa: BLE001 - never let a bad request escape
                return self._crash_failure(controller, stage, exc)
        try:
            plan = self._validator.validate(proposal, workspace_path=context.workspace_path)
        except PlanInvalid as exc:
            return self._plan_failure(controller, "plan_validation", exc)

        controller.update_run(
            {
                "plan": plan.to_dict(),
                "plan_hash": plan.plan_hash,
                "plan_source": plan.source,
            }
        )

        # 2. Freeze the worker default connection for this Run (docs/07 §3).  The
        #    pin is non-secret (ref + revision + opaque credential version) and is
        #    reused for every subtask so a later default/credential edit cannot
        #    silently hot-swap an active member; a new Run re-resolves.
        try:
            run_pin = self._resolve_run_pin()
        except AppError as exc:
            return self._plan_failure(controller, "default_connection", exc)
        self._run_pins[context.run_id] = run_pin
        controller.update_run({"connection_pin": run_pin.to_dict() if run_pin else None})

        # 3. Recruit the minimal team.
        controller.set_task_phase(TaskPhase.RECRUITING, reason="recruit minimal team")
        controller.set_run_state("recruiting")
        try:
            recruiter = self._recruiter or self._build_recruiter(context)
            team = recruiter.recruit(plan)
        except RecruitError as exc:
            return self._plan_failure(controller, "recruit", exc)
        except AppError as exc:
            return self._plan_failure(controller, "recruit", exc)

        # 4. Freeze member entities (current members), then execute.
        key_to_subtask = {spec.key: new_id("subtask") for spec in plan.subtasks}
        member_ids: dict[str, str] = {}
        member_subtasks: dict[str, list[str]] = {}
        for member in team.members:
            member_ids[member.role_ref] = new_id("member")
            member_subtasks[member.role_ref] = [
                key_to_subtask[key] for key in member.subtask_keys
            ]
        members = self._materialize_members(team, member_ids, member_subtasks, context, controller)

        controller.set_task_phase(TaskPhase.EXECUTING, reason="execute subtask graph")
        controller.set_run_state("executing")
        nodes = self._materialize_subtasks(
            plan, key_to_subtask, team, member_ids, member_subtasks, context, controller
        )
        # Real write isolation (LG-018): give every ``write`` node its own real
        # git worktree at a frozen base commit *before* scheduling.  Nodes that
        # cannot be isolated (non-git / unauthorized workspace, or no provider)
        # keep the conservative same-workspace single-writer serialization.
        self.isolate_write_nodes(context, nodes)
        controller.update_run(
            {
                "team_refs": list(member_ids.values()),
                "subtask_refs": list(key_to_subtask.values()),
            }
        )

        try:
            outcome, _results = await self._run_graph(context, controller, plan, nodes, emit)
        finally:
            for member_id in members:
                try:
                    controller.release_member(member_id, reason="run scheduling finished")
                except AppError:
                    pass
        return outcome

    # ----------------------------------------------------------- materialize
    @staticmethod
    def _record_planning_request(
        proposal: PlanProposal, request: PlanningRequest
    ) -> PlanProposal:
        """Attach the on-demand trigger/reason to the validated plan snapshot.

        The reason is recorded on the plan the program validates and freezes, so
        an on-demand proposal is auditable without adding a hidden control loop
        or a new wire field.
        """

        note = (
            "on-demand planning: "
            f"trigger={request.trigger.value} reason={request.reason!r} "
            f"requested_by={request.requested_by} max_calls={request.max_calls}"
        )
        return PlanProposal(
            subtasks=proposal.subtasks,
            source=proposal.source,
            notes=(*proposal.notes, note),
        )

    def _resolve_run_pin(self) -> ConnectionPin | None:
        """Resolve the current default worker connection once per Run."""

        if self._default_connections is None:
            return None
        return self._default_connections.resolve_default("worker")

    def _build_recruiter(self, context: DispatchContext) -> Recruiter:
        catalog = self._catalog
        if catalog is None:
            agent_ref = context.agent_ref
            if not agent_ref or agent_ref == "coordinator":
                raise RecruitError(
                    "no candidate agent configured for auto-teaming",
                    problems=[
                        "GraphDispatcher needs a RoleCatalog or a concrete "
                        "context.agent_ref; 'coordinator' is not an executable agent"
                    ],
                )
            catalog = RoleCatalog.single_agent(DEFAULT_CAPABILITIES, agent_ref)
        return Recruiter(catalog, compile_agent=self._member_compiler(context, catalog))

    def _member_compiler(
        self, context: DispatchContext, catalog: RoleCatalog
    ) -> Callable[[str], CompiledAgentConfig]:
        constraints = CompileConstraints(
            allowed_tools=(
                frozenset(context.allowed_tools) if context.allowed_tools is not None else None
            ),
            workspace_path=context.workspace_path or None,
            conversation_id=context.conversation_id,
            connection_pin=self._run_pins.get(context.run_id),
        )
        return lambda agent_ref: self._compiler.compile_agent(agent_ref, constraints=constraints)

    def _materialize_members(
        self,
        team: TeamPlan,
        member_ids: Mapping[str, str],
        member_subtasks: Mapping[str, list[str]],
        context: DispatchContext,
        controller: RunController,
    ) -> list[str]:
        created: list[str] = []
        pin = self._run_pins.get(context.run_id)
        for member in team.members:
            member_id = member_ids[member.role_ref]
            member_pin = (
                pin.to_dict()
                if pin is not None and member.candidate.connection_ref == pin.connection_id
                else None
            )
            controller.create_member(
                member_id,
                {
                    "run_ref": context.run_id,
                    "role_ref": member.role_ref,
                    "state": "ready",
                    "template_version": member.candidate.template_version,
                    "connection_ref": member.candidate.connection_ref,
                    "connection_pin": member_pin,
                    "skill_refs": list(member.candidate.skill_refs),
                    "session_ref": None,
                    "tool_policy": {"allowed_tools": list(member.candidate.tool_refs)},
                    "workspace_ref": context.workspace_path or None,
                    "assigned_subtask_refs": list(member_subtasks.get(member.role_ref, [])),
                    "budget": dict(context.budget),
                    "config_hash": member.config_hash,
                    "capabilities": list(member.capabilities),
                },
                body=f"# Member {member.role_ref}\n\nRole: {member.role_ref}\n",
            )
            controller.recruit_member(
                member_id,
                {
                    "role_ref": member.role_ref,
                    "config_hash": member.config_hash,
                    "template_version": member.candidate.template_version,
                    "capabilities": list(member.capabilities),
                },
            )
            created.append(member_id)
        return created

    def _materialize_subtasks(
        self,
        plan: Plan,
        key_to_subtask: Mapping[str, str],
        team: TeamPlan,
        member_ids: Mapping[str, str],
        member_subtasks: Mapping[str, list[str]],
        context: DispatchContext,
        controller: RunController,
    ) -> tuple[_Node, ...]:
        member_by_role = {member.role_ref: member for member in team.members}
        nodes: list[_Node] = []
        for spec in plan.subtasks:
            subtask_id = key_to_subtask[spec.key]
            member_role = team.capability_to_role.get(spec.capability)
            member = member_by_role.get(member_role) if member_role else None
            if member is None:
                raise RecruitError(
                    f"no member assigned for capability {spec.capability!r}",
                    problems=[f"subtask {spec.key!r}"],
                )
            controller.create_subtask(
                subtask_id,
                {
                    "run_ref": context.run_id,
                    "state": "pending",
                    "depends_on": [key_to_subtask[dep] for dep in spec.depends_on],
                    "assignee_member_ref": member_ids[member.role_ref],
                    "upstream_artifact_refs": [],
                    "objective": spec.objective,
                    "capability": spec.capability,
                    "key": spec.key,
                    "write": spec.write,
                    "config_hash": stable_hash(
                        {
                            "key": spec.key,
                            "objective": spec.objective,
                            "capability": spec.capability,
                            "acceptance": list(spec.acceptance),
                            "depends_on": list(spec.depends_on),
                            "write": spec.write,
                            "order": spec.order,
                            "member_config_hash": member.config_hash,
                        }
                    ),
                    # Stable reuse identity (LG-016): the same plan spec + effective
                    # member role/tools/skills/connection-pin/permission/template
                    # config, deliberately **excluding** the per-Run continuation
                    # coordinates (conversation_id/save_dir).  ``config_hash`` above
                    # folds in ``conversation_id`` (CompiledAgentConfig), so it can
                    # never match across a resume; this value can, and is what the
                    # anti-replay guard compares.
                    "reuse_identity": self._reuse_identity(spec, member, context),
                    "acceptance": {
                        "status": "pending",
                        "criteria": list(spec.acceptance),
                        "evidence_refs": [],
                    },
                },
                body=f"# Subtask {spec.key}\n\n{spec.objective}\n",
            )
            nodes.append(
                _Node(
                    subtask_id=subtask_id,
                    spec=spec,
                    member=member,
                    depends_on=tuple(key_to_subtask[dep] for dep in spec.depends_on),
                    member_id=member_ids[member.role_ref],
                )
            )
        return tuple(nodes)

    # ------------------------------------------------------------- run graph
    async def _run_graph(
        self,
        context: DispatchContext,
        controller: RunController,
        plan: Plan,
        nodes: Sequence[_Node],
        emit: Callable[[dict[str, Any]], Any],
    ) -> tuple[DispatchOutcome, dict[str, NodeResult]]:
        by_key = {node.key: node for node in nodes}
        graph = DependencyGraph(
            tuple(
                GraphNode(key=node.key, depends_on=node.spec.depends_on, write=node.spec.write)
                for node in nodes
            )
        )
        states: dict[str, str] = {key: "pending" for key in graph.topological_order()}
        memory = _RunMemory()
        failures: dict[str, NodeResult] = {}
        writer = StateWriter(self._store)
        claimer = SubtaskClaimer(
            writer, task_id=context.task_id, run_id=context.run_id
        )

        # Anti-replay guard (LG-016).  On a resumed Run the prior Run may have
        # already executed and *passed* nodes with write side effects.  Such a
        # node must never be silently re-executed: it is either provably
        # reusable from a persisted checkpoint/handoff (skipped) or the resume
        # fails closed with an explicit ``recovery_required`` decision.  A fresh
        # Run (``prior_run is None``) is unaffected.
        prior_run = getattr(context, "prior_run", None)
        if prior_run is not None:
            skips, guard_failure = self._plan_resume_reuse(prior_run, nodes, controller)
            if guard_failure is not None:
                return guard_failure, failures
            for key, handoff in skips.items():
                states[key] = "passed"
                memory.handoffs[key] = handoff

        while True:
            if context.run_id in self._explicit_cancel:
                await self._drain(memory)
                return self._final_outcome(states, failures, forced_cancel=True), failures

            for key in graph.topological_order():
                if states[key] != "pending":
                    continue
                node = by_key[key]
                deps = node.spec.depends_on
                failed_deps = [
                    by_key[dep].subtask_id for dep in deps if states[dep] in _BLOCKED_STATES
                ]
                if failed_deps:
                    states[key] = "blocked"
                    failures[key] = self._block_node(node, controller, failed_deps)
                    continue
                if not all(states[dep] == "passed" for dep in deps):
                    continue
                if len(memory.running) >= self._max_parallel:
                    continue
                writer_key = self._writer_key(node, context)
                if node.spec.write and writer_key in memory.writer_keys:
                    continue  # single writer per workspace: serialize
                states[key] = "running"
                if node.spec.write and writer_key:
                    memory.writer_keys.add(writer_key)
                memory.running[key] = asyncio.ensure_future(
                    self._execute_node(node, context, controller, memory, claimer, emit)
                )

            if not memory.running:
                if all(state in _TERMINAL_STATES for state in states.values()):
                    break
                # Nothing runnable and nothing in flight: avoid an infinite loop.
                break

            done, _ = await asyncio.wait(
                set(memory.running.values()), return_when=asyncio.FIRST_COMPLETED
            )
            for key, task in list(memory.running.items()):
                if task not in done:
                    continue
                memory.running.pop(key)
                node = by_key[key]
                writer_key = self._writer_key(node, context)
                if node.spec.write and writer_key:
                    memory.writer_keys.discard(writer_key)
                try:
                    result = task.result()
                except Exception as exc:  # noqa: BLE001 - never leave a node without an outcome
                    result = self._crash_node(node, controller, exc)
                states[key] = result.state
                if result.state == "passed":
                    assert result.handoff is not None
                    memory.handoffs[key] = result.handoff
                else:
                    failures[key] = result

        return self._final_outcome(states, failures, forced_cancel=False), failures

    def _plan_resume_reuse(
        self,
        prior_run: Mapping[str, Any],
        nodes: Sequence[_Node],
        controller: RunController,
    ) -> tuple[dict[str, ArtifactHandoff], DispatchOutcome | None]:
        """Decide how a resumed Run treats the prior Run's completed nodes.

        Returns ``(skips, failure)``.  When ``failure`` is not ``None`` the Run
        must not dispatch **any** node: a completed node could neither be proven
        reusable nor safely re-executed, so the resume is blocked with an
        explicit ``recovery_required`` decision instead of replaying side
        effects (docs/08 §9, agent.md §6).

        A completed node is *reused* (skipped, its frozen artifacts handed to
        dependents) only when :func:`reusable_completed_node` proves: the same
        plan key + the same **stable reuse identity** + stable member/role
        identity and a persisted artifact handoff with a content hash and
        artifact refs.  The comparison uses the stable identity, never the raw
        ``config_hash`` (which folds in the continuation ``conversation_id`` and
        so can never match across a resume).  Any drift, a missing/closed
        session, or a plan that no longer contains the completed key fails
        closed.
        """

        done = completed_keys(prior_run)
        if not done:
            return {}, None
        by_key = {node.key: node for node in nodes}
        skips: dict[str, ArtifactHandoff] = {}
        for key in sorted(done):
            node = by_key.get(key)
            if node is None:
                reason = (
                    f"resumed plan no longer contains completed node {key!r}; "
                    "cannot prove its side effects are reusable"
                )
                return {}, self._resume_blocked(controller, key, reason)
            identity = self._subtask_reuse_identity(node)
            session, reuse_reason = reusable_completed_node(
                prior_run,
                key=key,
                reuse_identity=identity,
                role_ref=node.member.role_ref,
                member_ref=node.member_id,
            )
            if session is None or session.handoff is None:
                return {}, self._resume_blocked(controller, key, reuse_reason)
            handoff = self._handoff_from_session(node, session)
            if handoff is None:
                return {}, self._resume_blocked(
                    controller, key, f"completed node {key!r} handoff is not usable"
                )
            self._mark_node_reused(node, controller, handoff, source_run=prior_run)
            skips[key] = handoff
        return skips, None

    def _subtask_reuse_identity(self, node: _Node) -> str | None:
        """The frozen *stable* reuse identity persisted for this node."""

        try:
            value = self._store.read("subtask", node.subtask_id).entity.get("reuse_identity")
        except Exception:  # noqa: BLE001 - absent identity means "cannot prove reuse"
            return None
        return value if isinstance(value, str) and value else None

    def _reuse_identity(
        self, spec: SubtaskSpec, member: MemberPlan, context: DispatchContext
    ) -> str:
        """Compute a node's stable reuse identity (LG-016).

        The identity folds in the plan node and the *effective* member config —
        role, tools, skills, connection pin, permissions (allowed tools) and
        template version — but deliberately excludes the per-Run continuation
        coordinates (``conversation_id``/``save_dir``).  The member's compiled
        ``config_hash`` cannot be used directly: ``CompiledAgentConfig`` includes
        the session profile's ``conversation_id``, which changes on every resume
        (a resumed Run uses its own conversation coordinates), so it would make
        *every* reuse comparison fail even when nothing about the node changed.

        Recompiling with a neutral (``conversation_id=None``) session profile
        yields the same permission/connection/tool/skill/template identity the
        Run froze, independent of continuation position.  Any other drift
        (model, connection, workspace, tools, skills, template) still changes
        this value, so it cannot mask a genuine configuration change.
        """

        pin = self._run_pins.get(context.run_id)

        def neutral_hash() -> str:
            if self._compiler is None:  # pragma: no cover - compiler always set in graph
                return member.candidate.config_hash
            constraints = CompileConstraints(
                allowed_tools=frozenset(member.candidate.tool_refs),
                workspace_path=context.workspace_path or None,
                # No continuation coordinate: this is the whole point.
                conversation_id=None,
                connection_pin=pin,
            )
            try:
                compiled = self._compiler.compile_agent(member.role_ref, constraints=constraints)
            except AppError:
                # Fall back to the frozen candidate fields (still excludes the
                # continuation coordinate) rather than coupling reuse to a
                # transient compile failure.
                return member.candidate.config_hash
            return compiled.config_hash

        return stable_hash(
            {
                "key": spec.key,
                "objective": spec.objective,
                "capability": spec.capability,
                "acceptance": list(spec.acceptance),
                "depends_on": list(spec.depends_on),
                "write": spec.write,
                "order": spec.order,
                "role_ref": member.role_ref,
                "template_version": member.candidate.template_version,
                "connection_ref": member.candidate.connection_ref,
                "skill_refs": sorted(member.candidate.skill_refs),
                "tool_refs": sorted(member.candidate.tool_refs),
                "capabilities": sorted(member.capabilities),
                "neutral_member_config_hash": neutral_hash(),
            }
        )

    def _handoff_from_session(
        self, node: _Node, session: NodeSession
    ) -> ArtifactHandoff | None:
        """Rebuild a trusted handoff from a completed node's persisted record."""

        raw = session.handoff or {}
        content_hash = raw.get("content_hash")
        artifacts = raw.get("artifacts")
        revision = raw.get("revision")
        if not isinstance(content_hash, str) or not content_hash:
            return None
        if not isinstance(artifacts, (list, tuple)) or not artifacts:
            return None
        refs = tuple(str(item) for item in artifacts if isinstance(item, str) and item)
        if not refs:
            return None
        return ArtifactHandoff(
            subtask_ref=node.subtask_id,
            revision=revision if isinstance(revision, int) else 0,
            content_hash=content_hash,
            artifacts=refs,
        )

    def _mark_node_reused(
        self,
        node: _Node,
        controller: RunController,
        handoff: ArtifactHandoff,
        *,
        source_run: Mapping[str, Any],
    ) -> None:
        """Mark a resumed subtask ``passed`` from a proven prior artifact.

        No executor is invoked and no new write occurs: the subtask is recorded
        as skipped-from-checkpoint and its frozen artifact refs are preserved.
        """

        controller.transition_subtask(
            node.subtask_id,
            "passed",
            extra={"skip_reason": "reused completed node from prior Run checkpoint"},
            acceptance={
                "status": "passed",
                "criteria": list(node.spec.acceptance),
                "evidence_refs": list(handoff.artifacts),
            },
            reason="completed node reused from verified prior checkpoint",
        )
        controller.record_artifact(node.subtask_id, handoff.artifacts, handoff.to_dict())
        controller.emit(
            EventType.ARTIFACT_PRODUCED,
            {
                "mode": "resume_skip",
                "subtask_ref": node.subtask_id,
                "source_run_id": source_run.get("id") or source_run.get("run_id"),
                "content_hash": handoff.content_hash,
                "artifact_refs": list(handoff.artifacts),
            },
        )

    def _resume_blocked(
        self, controller: RunController, key: str, reason: str
    ) -> DispatchOutcome:
        """Fail closed: block the resume instead of replaying a write node."""

        message = (
            f"cannot safely reuse completed node {key!r} on resume: {reason}; "
            "refusing to re-execute a possibly-written node"
        )
        controller.emit(
            EventType.ERROR_RECORDED,
            {"mode": "resume_guard", "code": "recovery_required", "message": message},
        )
        return DispatchOutcome(
            state="recovery_required",
            summary=message,
            failure_code="recovery_required",
            failure_message=message,
        )

    def _final_outcome(
        self, states: Mapping[str, str], failures: Mapping[str, NodeResult], *, forced_cancel: bool
    ) -> DispatchOutcome:
        cancelled = [key for key, state in states.items() if state == "cancelled"]
        if forced_cancel or cancelled:
            return DispatchOutcome(
                state="cancelled",
                summary=f"run cancelled: {len(cancelled)} subtask(s) stopped",
                stop_confirmed=True,
            )
        failed = [key for key, state in states.items() if state in {"failed", "blocked"}]
        if failed:
            first = failures.get(failed[0])
            code = first.failure_code if first and first.failure_code else "internal_error"
            message = first.failure_message if first else "subtask graph did not complete"
            return DispatchOutcome(
                state="failed",
                summary=f"subtask graph failed at {failed[0]!r}: {message}",
                failure_code=code,
                failure_message=message,
            )
        return DispatchOutcome(
            state="succeeded",
            summary=f"all {len(states)} subtask(s) passed; candidate handed to verification",
        )

    async def _drain(self, memory: _RunMemory) -> None:
        if not memory.running:
            return
        await asyncio.gather(*memory.running.values(), return_exceptions=True)
        memory.running.clear()

    # ---------------------------------------------------------- node execute
    async def _execute_node(
        self,
        node: _Node,
        context: DispatchContext,
        controller: RunController,
        memory: _RunMemory,
        claimer: SubtaskClaimer,
        emit: Callable[[dict[str, Any]], Any],
    ) -> NodeResult:
        upstream = encode_handoffs(
            [memory.handoffs[dep] for dep in node.spec.depends_on if dep in memory.handoffs]
        )
        controller.transition_subtask(
            node.subtask_id,
            "ready",
            extra={"upstream_artifact_refs": list(upstream)},
            reason="dependencies satisfied",
        )
        grant_token: str | None = None
        autonomous = self._decentralized_enabled() and self._autonomous_claim
        if autonomous:
            # R1: the worker itself proposes the claim through the restricted
            # discover/claim tool; the program only freezes a discovery-only
            # pool identity here (never a node lease and never a global token).
            grant_token = self._mint_pool_grant(node, context)
        elif self._decentralized_enabled():
            acquired, grant_token, reason = self._claim_decentralized(node, context)
            if not acquired:
                return self._fail_node(
                    node,
                    controller,
                    code="lock_conflict",
                    message=f"decentralized claim refused: {reason}",
                )
        else:
            claim = claimer.claim(node.subtask_id, self._owner, lease_seconds=self._lease_seconds)
            if not claim.acquired:
                return self._fail_node(
                    node,
                    controller,
                    code="lock_conflict",
                    message=f"subtask claim refused: {claim.state} ({claim.reason})",
                )

        drift = self._config_drift(node, context)
        if drift is not None:
            self._release_node(node, claimer)
            return self._fail_node(node, controller, code="config_invalid", message=drift)

        request = self._build_request(node, context, upstream, grant_token=grant_token)
        if autonomous:
            # Autonomous workers must have actually claimed through the tool
            # before their result can be admitted; a worker that never claims
            # cannot pass (program-authority, not model self-report).
            if self._node_grants.get(node.key) is None:
                self._revoke_if_pool(node.key, grant_token)
                self._release_node(node, claimer)
                return self._fail_node(
                    node,
                    controller,
                    code="lock_conflict",
                    message="autonomous worker did not claim an authorized node",
                )
        run_id = context.run_id
        task = asyncio.ensure_future(self._executor.execute(request, emit))
        self._inflight.setdefault(run_id, set()).add(task)
        try:
            result = await task
        except asyncio.CancelledError:
            if run_id not in self._explicit_cancel:
                raise
            result = ExecutorResult(
                state="cancelled",
                summary="subtask cancelled by run control",
                stop_confirmed=True,
                execution_ref=ExecutionRef(
                    execution_id=f"exec_cancelled_{node.subtask_id}",
                    task_id=context.task_id,
                    run_id=run_id,
                    subtask_id=node.subtask_id,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - classify a crash, never fake success
            self._release_node(node, claimer)
            return self._crash_node(node, controller, exc)
        finally:
            self._inflight.get(run_id, set()).discard(task)
            # A grant is runtime authority only: revocation happens as soon as
            # the execution stops (confirmed or not), so a stale worker identity
            # can never outlive its node execution.
            if grant_token is not None:
                self._revoke_grant(node.key, grant_token)
        self._release_node(node, claimer)
        if result.execution_ref is not None:
            self._active_refs.setdefault(run_id, []).append(result.execution_ref)
        return self._apply_result(node, controller, result)

    # ---------------------------------------------------- decentralized claim
    def _decentralized_enabled(self) -> bool:
        collab = self._collaboration
        return collab is not None and bool(getattr(collab, "enabled", False))

    def _claim_decentralized(
        self, node: _Node, context: DispatchContext
    ) -> tuple[bool, str | None, str]:
        """Claim a node through the fenced lease authority and mint its grant."""

        from lightgravity.collaboration import ClaimRequest, default_registry

        collab = self._collaboration
        assert collab is not None
        decision = collab.request_claim(
            context.run_id,
            ClaimRequest(
                subtask_id=node.subtask_id,
                owner=self._owner,
                request_id=f"graph-claim-{context.run_id}-{node.key}",
                lease_seconds=self._lease_seconds,
                capability=node.spec.capability,
            ),
            allow_write=True,
            dependencies_ready=True,
            capability_ok=True,
        )
        if not decision.granted:
            return False, None, decision.reason
        granted_ids = frozenset(
            candidate.subtask_id
            for candidate in collab.discover(context.run_id, self._owner).candidates
        )
        registry = self._grant_registry or default_registry()
        token, _grant = registry.mint(
            task_id=context.task_id,
            run_id=context.run_id,
            subtask_id=node.subtask_id,
            member_ref=node.member_id,
            fence=decision.fence,
            authorized_node_refs=granted_ids,
            max_collab_calls=int(context.budget.get("max_collab_requests", 0) or 0),
            budget_remaining=decision.fence,
            ttl_seconds=max(60, int(self._lease_seconds) * 2),
        )
        self._node_grants[node.key] = (token, node.subtask_id)
        return True, token, decision.reason

    def _release_node(self, node: _Node, claimer: SubtaskClaimer) -> None:
        if self._decentralized_enabled() and self._collaboration is not None:
            try:
                self._collaboration.release(node.subtask_id, self._owner)
            except Exception:  # noqa: BLE001 - release must never mask the outcome
                return
            return
        claimer.release(node.subtask_id, self._owner)

    def _revoke_grant(self, key: str, token: str) -> None:
        registry = self._grant_registry
        if registry is None:
            from lightgravity.collaboration import default_registry

            registry = default_registry()
        registry.revoke_token(token)
        # Also revoke a node grant minted by an autonomous claim tool for this
        # node, so no worker identity outlives its execution.
        node_grant = self._node_grants.pop(key, None)
        if node_grant is not None:
            registry.revoke_token(node_grant[0])

    def _revoke_if_pool(self, key: str, token: str | None) -> None:
        if token is not None:
            self._revoke_grant(key, token)

    def _mint_pool_grant(self, node: _Node, context: DispatchContext) -> str:
        """Mint a **discovery-only** pool identity for one autonomous worker.

        It authorizes requesting a claim (never a node lease, never a global
        token) and lists the nodes this worker may see; the program upgrades it
        to a node grant at claim time.
        """

        from lightgravity.collaboration import default_registry

        registry = self._grant_registry or default_registry()
        collab = self._collaboration
        visible: frozenset[str] = frozenset()
        if collab is not None:
            view = collab.discover(context.run_id, self._owner)
            visible = frozenset(candidate.subtask_id for candidate in view.candidates)
        token, _grant = registry.mint(
            task_id=context.task_id,
            run_id=context.run_id,
            subtask_id=node.subtask_id,
            member_ref=node.member_id,
            fence=0,
            authorized_node_refs=visible,
            max_collab_calls=int(context.budget.get("max_collab_requests", 0) or 0),
            budget_remaining=None,
            ttl_seconds=max(60, int(self._lease_seconds) * 2),
            origin="graph-dispatcher:autonomous-pool",
            kind="pool",
        )
        return token

    def _claim_for_worker(
        self, node: _Node, context: DispatchContext, node_ref: str, request_id: str
    ) -> dict[str, Any]:
        """Program-side handler for an autonomous claim proposal.

        Re-authenticates by construction (this is the program, not the model),
        validates the requested node, atomically grants the lease/fence through
        the frozen authority and mints the worker's **node** grant.  A refusal is
        returned as a definite machine receipt; nothing is granted on a partial
        check.
        """

        from lightgravity.collaboration import ClaimRequest, default_registry

        collab = self._collaboration
        if collab is None:
            return {"granted": False, "reason": "feature_disabled"}
        decision = collab.request_claim(
            context.run_id,
            ClaimRequest(
                subtask_id=node_ref,
                owner=self._owner,
                request_id=request_id,
                lease_seconds=self._lease_seconds,
                capability=node.spec.capability,
            ),
            allow_write=True,
            dependencies_ready=True,
            capability_ok=True,
        )
        if not decision.granted:
            return {
                "granted": False,
                "reason": decision.reason,
                "request_id": decision.request_id,
            }
        registry = self._grant_registry or default_registry()
        granted_ids = frozenset(
            candidate.subtask_id
            for candidate in collab.discover(context.run_id, self._owner).candidates
        )
        node_token, _grant = registry.mint(
            task_id=context.task_id,
            run_id=context.run_id,
            subtask_id=node_ref,
            member_ref=node.member_id,
            fence=decision.fence,
            authorized_node_refs=granted_ids,
            max_collab_calls=int(context.budget.get("max_collab_requests", 0) or 0),
            budget_remaining=decision.fence,
            ttl_seconds=max(60, int(self._lease_seconds) * 2),
            origin="graph-dispatcher:autonomous-claim",
        )
        self._node_grants[node.key] = (node_token, node_ref)
        return {
            "granted": True,
            "reason": decision.reason,
            "fence": decision.fence,
            "lease_expires_at": decision.lease_expires_at,
            "request_id": decision.request_id,
        }

    def _claim_tools_for(
        self, node: _Node, context: DispatchContext, token: str | None
    ) -> tuple[Any, ...]:
        """Build the worker-facing discover/claim tool for autonomous mode."""

        if token is None or not self._decentralized_enabled() or not self._autonomous_claim:
            return ()
        from lightgravity.collaboration import default_registry, make_restricted_claim_tool

        collab = self._collaboration
        registry = self._grant_registry or default_registry()

        def discover() -> Any:
            assert collab is not None
            return collab.discover(context.run_id, self._owner)

        def claim_callback(node_ref: str, request_id: str) -> Any:
            return self._claim_for_worker(node, context, node_ref, request_id)

        tool = make_restricted_claim_tool(
            registry=registry,
            token=token,
            discover=discover,
            claim_callback=claim_callback,
        )
        return (tool,)

    def _peer_tools_for(self, node: _Node, context: DispatchContext, token: str | None) -> tuple[Any, ...]:
        """Build the minimal restricted peer tool bound to this node's grant.

        Only assembled when the decentralized path is enabled **and** the Run has
        a positive collaboration allowance; the deterministic path exposes no
        custom tool.
        """

        if token is None or not self._decentralized_enabled():
            return ()
        if int(context.budget.get("max_collab_requests", 0) or 0) <= 0:
            return ()
        from lightgravity.collaboration import (
            ClaimPolicyReader,
            PeerService,
            default_registry,
            make_restricted_peer_tool,
        )

        registry = self._grant_registry or default_registry()
        data_dir = getattr(self._store, "data_dir", None)

        def peer_factory() -> PeerService:
            policy = ClaimPolicyReader(self._store).read()
            return PeerService(
                self._store,
                data_dir=data_dir if data_dir is not None else ".",
                policy=policy,
            )

        tool = make_restricted_peer_tool(
            registry=registry,
            token=token,
            peer_service_factory=peer_factory,
            run_id=context.run_id,
            node_ref=node.subtask_id,
            from_member_ref=node.member_id,
        )
        return (tool,)

    def _apply_result(
        self, node: _Node, controller: RunController, result: ExecutorResult
    ) -> NodeResult:
        subtask_id = node.subtask_id
        # Collect the node's complete non-secret native session from the
        # authoritative terminal result and persist it to the Member + the Run
        # node mapping before classifying the outcome, so a confirmed pause can
        # later continue this exact node (LG-016).
        self._record_node_session(node, controller, result)
        if result.state == "cancelled":
            controller.transition_subtask(
                subtask_id,
                "cancelled",
                acceptance={"status": "blocked", "criteria": list(node.spec.acceptance), "evidence_refs": []},
                reason="executor reported a confirmed stop",
            )
            return NodeResult(
                key=node.key, subtask_id=subtask_id, state="cancelled", result=result
            )
        if result.state != "succeeded":
            code = result.failure.code if result.failure else result.state
            message = result.failure.message if result.failure else result.summary
            return self._fail_node(node, controller, code=code, message=message, result=result)

        evidence = tuple(result.artifact_refs)
        if result.diff_ref:
            try:
                canonical_diff = self._record_evidence(controller, node, result.diff_ref)
            except EvidenceRefError as exc:
                return self._fail_node(
                    node,
                    controller,
                    code="evidence_unreadable",
                    message=f"executor diff evidence could not be imported: {exc}",
                    result=result,
                )
            if canonical_diff not in evidence:
                evidence = (*evidence, canonical_diff)
        if not evidence and not result.summary.strip():
            return self._fail_node(
                node,
                controller,
                code="validation_failed",
                message="worker reported success without artifacts or a summary; refusing to pass",
                result=result,
            )
        controller.transition_subtask(subtask_id, "verifying", reason="worker returned success")
        passed = controller.transition_subtask(
            subtask_id,
            "passed",
            acceptance={
                "status": "passed",
                "criteria": list(node.spec.acceptance),
                "evidence_refs": list(evidence),
            },
            reason="minimal machine check passed",
        )
        handoff = ArtifactHandoff(
            subtask_ref=subtask_id,
            revision=passed.revision,
            content_hash=passed.content_hash,
            artifacts=evidence,
        )
        controller.record_artifact(subtask_id, evidence, handoff.to_dict())
        # Persist the frozen handoff with the node session so a later resumed Run
        # can *prove* this completed write node is reusable (anti-replay guard).
        # The recorded ``node_state`` is the authoritative subtask state.
        self._record_node_session(
            node, controller, result, handoff=handoff, node_state="passed"
        )
        return NodeResult(
            key=node.key,
            subtask_id=subtask_id,
            state="passed",
            handoff=handoff,
            result=result,
        )

    def _record_node_session(
        self,
        node: _Node,
        controller: RunController,
        result: ExecutorResult,
        handoff: ArtifactHandoff | None = None,
        *,
        node_state: str | None = None,
    ) -> None:
        """Persist a node's native session to Member + Run mapping (LG-016).

        The node's frozen **stable reuse identity** (subtask entity) is captured
        so a later resume only reattaches/reuses when the node configuration and
        member identity are unchanged — independent of the per-Run continuation
        coordinates.  The raw ``config_hash`` is still recorded for
        observability/back-compat.  Nothing is written when the SDK reported no
        conversation.  ``node_state`` overrides the default (the executor result
        state) so a completed node records the authoritative **subtask** state
        ``passed`` — the value :func:`~.session_flow.completed_keys` uses to
        detect replay.
        """

        try:
            subtask_entity = self._store.read("subtask", node.subtask_id).entity
            subtask_config_hash = subtask_entity.get("config_hash")
            subtask_reuse_identity = subtask_entity.get("reuse_identity")
        except Exception:  # noqa: BLE001 - absence must not abort the node outcome
            subtask_config_hash = None
            subtask_reuse_identity = None
        session = extract_node_session(
            result,
            key=node.key,
            subtask_id=node.subtask_id,
            member_ref=node.member_id,
            role_ref=node.member.role_ref,
            node_state=node_state or result.state,
            config_hash=(
                str(subtask_config_hash)
                if isinstance(subtask_config_hash, str) and subtask_config_hash
                else node.member.candidate.config_hash
            ),
            reuse_identity=(
                str(subtask_reuse_identity)
                if isinstance(subtask_reuse_identity, str) and subtask_reuse_identity
                else None
            ),
            handoff=handoff.to_dict() if handoff is not None else None,
        )
        if session is None:
            return
        record_node_session(controller, session)

    def _resolve_node_continuation(
        self, node: _Node, context: DispatchContext
    ) -> NodeSession | None:
        """Resolve this node's own prior native session for a resumed Run.

        Uses the Plan key + node ``config_hash`` + member identity so a node is
        only continued when the plan, frozen configuration and authorization all
        match; otherwise the node dispatches fresh (new conversation) and a
        completed write is never silently replayed.
        """

        prior_run = getattr(context, "prior_run", None)
        if prior_run is None:
            return None
        # Compare the *stable reuse identity* (node definition + effective member
        # config, excluding the per-Run continuation coordinates) with the value
        # persisted with the node session, so a reconfigured node is dispatched
        # fresh rather than reattached to a stale conversation — while a resume
        # whose only change is the conversation coordinate still reattaches.
        try:
            subtask_reuse_identity = self._store.read(
                "subtask", node.subtask_id
            ).entity.get("reuse_identity")
        except Exception:  # noqa: BLE001 - absent identity means "do not continue"
            return None
        if not isinstance(subtask_reuse_identity, str) or not subtask_reuse_identity:
            return None
        return node_session_for_resume(
            prior_run,
            key=node.key,
            reuse_identity=subtask_reuse_identity,
            member_ref=node.member_id,
            role_ref=node.member.role_ref,
        )

    def _record_evidence(self, controller: RunController, node: _Node, ref: str) -> str:
        """Import a trusted executor artifact into the Task/Run evidence root.

        A local path is copied and recorded as a canonical ``evidence:`` ref so
        machine checks never resolve a raw absolute path.  A non-path evidence
        ref (for example an opaque URL) is recorded as-is and left opaque.
        """

        if not isinstance(ref, str) or not ref or "://" in ref or not os.path.isabs(ref):
            return ref
        data_dir = getattr(self._store, "data_dir", None)
        if data_dir is None:
            raise EvidenceRefError("store does not expose a data directory for evidence import")
        name = f"{node.subtask_id}-{Path(ref).name}"
        return import_evidence(
            data_dir,
            controller.task_id,
            controller.run_id,
            ref,
            name=name,
        )

    def _fail_node(
        self,
        node: _Node,
        controller: RunController,
        *,
        code: str,
        message: str,
        result: ExecutorResult | None = None,
    ) -> NodeResult:
        controller.transition_subtask(
            node.subtask_id,
            "failed",
            extra={"fail_reason": message},
            acceptance={
                "status": "failed",
                "criteria": list(node.spec.acceptance),
                "evidence_refs": [],
            },
            reason=message,
        )
        controller.emit(
            EventType.ERROR_RECORDED,
            {"mode": "subtask", "code": code, "message": message, "subtask_ref": node.subtask_id},
        )
        return NodeResult(
            key=node.key,
            subtask_id=node.subtask_id,
            state="failed",
            failure_code=code,
            failure_message=message,
            result=result,
        )

    def _block_node(
        self, node: _Node, controller: RunController, failed_deps: Sequence[str]
    ) -> NodeResult:
        message = "upstream subtask failed: " + ", ".join(sorted(failed_deps))
        controller.transition_subtask(
            node.subtask_id,
            "failed",
            extra={"fail_reason": message, "blocked_by": list(failed_deps)},
            acceptance={
                "status": "blocked",
                "criteria": list(node.spec.acceptance),
                "evidence_refs": [],
            },
            reason=message,
        )
        return NodeResult(
            key=node.key,
            subtask_id=node.subtask_id,
            state="blocked",
            failure_code="not_ready",
            failure_message=message,
        )

    def _crash_node(
        self, node: _Node, controller: RunController, exc: BaseException
    ) -> NodeResult:
        return self._fail_node(
            node,
            controller,
            code="internal_error",
            message=f"{type(exc).__name__}: {exc}",
        )

    # ------------------------------------------------------------- request
    def _build_request(
        self,
        node: _Node,
        context: DispatchContext,
        upstream: Sequence[str],
        *,
        grant_token: str | None = None,
    ) -> ExecuteRequest:
        candidate = node.member.candidate
        # Per-node native continuation (LG-016): a node may safely reattach to
        # *its own* prior conversation when the plan key, config hash and member
        # match; otherwise fall back to the Run-level continuation decision (or a
        # fresh session).  The node coordinates override the run-level ones so a
        # multi-node graph never funnels every member into one conversation.
        node_continuation = self._resolve_node_continuation(node, context)
        save_dir: str | None
        conversation_id: str | None
        continuation_mode: str | None
        if node_continuation is not None:
            save_dir = node_continuation.save_dir
            conversation_id = node_continuation.conversation_id
            continuation_mode = node_continuation.to_continuation()["continuation_mode"]
        else:
            save_dir = context.save_dir
            conversation_id = context.conversation_id
            continuation_mode = context.continuation_mode
        # Real write isolation (LG-018): a write node runs inside its own git
        # worktree when one was provisioned; the frozen base commit is recorded
        # in the run workspace metadata.  Read-only nodes keep the shared
        # workspace path.
        node_workspace = self.workspace_for_node(context.run_id, node.key)
        effective_workspace = node_workspace or context.workspace_path
        return ExecuteRequest(
            task_id=context.task_id,
            run_id=context.run_id,
            subtask_id=node.subtask_id,
            attempt=context.attempt,
            objective=node.spec.objective,
            acceptance_criteria=node.spec.acceptance,
            instructions=context.instructions,
            upstream_artifact_refs=tuple(upstream),
            workspace_path=effective_workspace,
            allowed_tools=candidate.tool_refs,
            skill_refs=candidate.skill_refs,
            connection_ref=candidate.connection_ref,
            timeout_seconds=context.timeout_seconds,
            budget=dict(context.budget),
            agent_ref=node.member.role_ref,
            save_dir=save_dir,
            conversation_id=conversation_id,
            continuation_mode=continuation_mode,
            execution_grant=grant_token,
            custom_tools=(
                *self._claim_tools_for(node, context, grant_token),
                *self._peer_tools_for(node, context, grant_token),
            ),
        )

    def _config_drift(self, node: _Node, context: DispatchContext) -> str | None:
        pin = self._run_pins.get(context.run_id)
        constraints = CompileConstraints(
            allowed_tools=frozenset(node.member.candidate.tool_refs),
            workspace_path=(
                self.workspace_for_node(context.run_id, node.key)
                or context.workspace_path
                or None
            ),
            conversation_id=context.conversation_id,
            connection_pin=pin,
        )
        try:
            compiled = self._compiler.compile_agent(node.member.role_ref, constraints=constraints)
        except AppError as exc:
            return f"member agent {node.member.role_ref!r} no longer compiles: {exc.message}"
        if compiled.config_hash != node.member.candidate.config_hash:
            return (
                f"member agent {node.member.role_ref!r} configuration changed after "
                "recruitment; run configuration is fixed"
            )
        if (
            pin is not None
            and self._default_connections is not None
            and compiled.connection is not None
            and compiled.connection.connection_source == "pinned"
        ):
            # Credential/default edits after recruitment must not be silently
            # picked up by the next subtask of an active Run.
            try:
                current = self._default_connections.pinned_is_current(pin)
            except Exception as exc:  # noqa: BLE001 - report, never hot-swap
                return f"could not verify pinned connection {pin.connection_id!r}: {exc}"
            if not current:
                return (
                    f"pinned worker connection {pin.connection_id!r} or its credential "
                    "changed after recruitment; run configuration is fixed"
                )
        return None

    def isolate_write_nodes(
        self, context: DispatchContext, nodes: Sequence[_Node]
    ) -> dict[str, str]:
        """Give every ``write`` node its own real worktree; return node->path.

        Called before scheduling so the scheduler and the ExecuteRequest both see
        the isolated directory.  A missing provider, a non-git workspace or an
        out-of-root workspace yields no entry for a node, so that node keeps the
        conservative shared-workspace single-writer rule.
        """

        isolated: dict[str, str] = {}
        provider = self._workspaces
        if provider is None:
            return isolated
        for node in nodes:
            if not node.spec.write:
                continue
            try:
                path = provider.isolate(
                    task_id=context.task_id,
                    run_id=context.run_id,
                    node_key=node.key,
                    subtask_id=node.subtask_id,
                    base_workspace=context.workspace_path,
                )
            except Exception as exc:  # noqa: BLE001 - isolation failure is never fatal
                del exc
                path = None
            if path:
                isolated[node.key] = path
        self._run_workspaces[context.run_id] = isolated
        return isolated

    def workspace_for_node(self, run_id: str, key: str) -> str | None:
        """The isolated workspace path for a node, else ``None`` (shared)."""

        return self._run_workspaces.get(run_id, {}).get(key)

    # ---------------------------------------------------------------- helpers
    def _writer_key(self, node: _Node, context: DispatchContext) -> str:
        if not node.spec.write:
            return ""
        isolated = self.workspace_for_node(context.run_id, node.key)
        if isolated:
            # Real per-node worktree: the writer key is the node itself, so two
            # isolated write nodes may run in parallel (both were provisioned
            # before scheduling, so the map is complete).
            return f"node:{node.key}"
        return context.workspace_path

    def _plan_failure(
        self, controller: RunController, stage: str, exc: AppError
    ) -> DispatchOutcome:
        controller.emit(
            EventType.ERROR_RECORDED,
            {"mode": stage, "code": exc.code.value, "message": exc.message, "details": exc.details},
        )
        return DispatchOutcome(
            state="failed",
            summary=f"{stage} failed: {exc.message}",
            failure_code=exc.code.value,
            failure_message=exc.message,
        )

    def _crash_failure(
        self, controller: RunController, stage: str, exc: BaseException
    ) -> DispatchOutcome:
        message = f"{type(exc).__name__}: {exc}"
        controller.emit(
            EventType.ERROR_RECORDED,
            {"mode": stage, "code": "internal_error", "message": message},
        )
        return DispatchOutcome(
            state="failed",
            summary=f"{stage} crashed: {message}",
            failure_code="internal_error",
            failure_message=message,
        )

    # ---------------------------------------------------------------- cancel
    async def cancel(self, task_id: str, run_id: str) -> CancelResult:
        self._explicit_cancel.add(run_id)
        inflight = [task for task in self._inflight.get(run_id, set()) if not task.done()]
        if inflight:
            for task in inflight:
                task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.gather(*inflight, return_exceptions=True),
                    timeout=self._cancel_timeout,
                )
            except asyncio.TimeoutError:
                return CancelResult(
                    confirmed=False,
                    state="unconfirmed",
                    reason="subtask executions did not stop within the cancel timeout",
                )
            return CancelResult(
                confirmed=True, state="cancelled", reason="all in-flight subtasks stopped"
            )

        refs = list(self._active_refs.get(run_id, ()))
        if not refs:
            return CancelResult(
                confirmed=False,
                state="not_found",
                reason=f"no active subtask execution for run {run_id!r}",
            )
        for ref in refs:
            try:
                result = await self._executor.cancel(ref)
            except Exception as exc:  # noqa: BLE001 - never fake a confirmed stop
                return CancelResult(
                    confirmed=False,
                    state="unconfirmed",
                    reason=f"executor cancel raised {type(exc).__name__}",
                )
            if not result.confirmed:
                return CancelResult(
                    confirmed=False,
                    state="unconfirmed",
                    reason=result.reason or "executor did not confirm the stop",
                )
        return CancelResult(confirmed=True, state="cancelled", reason="executor confirmed stop")


def build_graph_dispatcher(
    store: Store,
    executor: ExecutorAdapter,
    *,
    catalog: RoleCatalog | None = None,
    planner: Planner | None = None,
    max_parallel: int = 1,
    workspaces: WorkspaceProvider | None = None,
    **kwargs: Any,
) -> GraphDispatcher:
    """Convenience factory mirroring the LG-007 dispatcher construction style."""

    return GraphDispatcher(
        store,
        executor,
        catalog=catalog,
        planner=planner,
        max_parallel=max_parallel,
        workspaces=workspaces,
        **kwargs,
    )


__all__ = [
    "DEFAULT_CAPABILITIES",
    "GraphDispatcher",
    "NodeResult",
    "build_graph_dispatcher",
]
