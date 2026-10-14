"""Graph dispatcher: planner + recruiter + scheduler behind the LG-007 seam (LG-008).

:class:`GraphDispatcher` implements :class:`~lightgravity.coordinator.dispatcher.Dispatcher`.
The coordinator (LG-007) owns the Task queue, the single execution slot and the
Task/Run lifecycle; this dispatcher only decides *how* one dispatched Run turns
into a validated Subtask graph, a minimal temporary team and a dependency-ordered
execution:

1. a planner proposes nodes (rules or a bounded model proposal);
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
from typing import Any

from lightgravity.adapter import (
    CancelResult,
    CompileConstraints,
    CompiledAgentConfig,
    ExecuteRequest,
    ExecutorAdapter,
    ExecutorResult,
    ExecutionRef,
    ResourceCompiler,
)
from lightgravity.contracts import AppError, EventType, TaskPhase
from lightgravity.store import Store, new_id

from .dispatcher import DispatchContext, DispatchOutcome
from .planner import (
    Plan,
    PlanInvalid,
    Planner,
    PlanValidator,
    RuleBasedPlanner,
    SubtaskSpec,
    stable_hash,
)
from .recruiter import MemberPlan, RecruitError, Recruiter, RoleCatalog, TeamPlan
from .scheduler import (
    ArtifactHandoff,
    DependencyGraph,
    GraphNode,
    SubtaskClaimer,
    encode_handoffs,
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
    ) -> None:
        if max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")
        self._store = store
        self._executor = executor
        self._planner: Planner = planner or RuleBasedPlanner()
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
        self._inflight: dict[str, set[asyncio.Task[ExecutorResult]]] = {}
        self._active_refs: dict[str, list[ExecutionRef]] = {}
        self._explicit_cancel: set[str] = set()

    @property
    def executor(self) -> ExecutorAdapter:
        return self._executor

    # --------------------------------------------------------------- dispatch
    async def dispatch(
        self,
        context: DispatchContext,
        controller: RunController,
        emit: Callable[[dict[str, Any]], Any],
    ) -> DispatchOutcome:
        run_id = context.run_id
        self._explicit_cancel.discard(run_id)
        self._inflight[run_id] = set()
        self._active_refs[run_id] = []
        try:
            return await self._dispatch_graph(context, controller, emit)
        finally:
            self._inflight.pop(run_id, None)
            self._active_refs.pop(run_id, None)

    async def _dispatch_graph(
        self,
        context: DispatchContext,
        controller: RunController,
        emit: Callable[[dict[str, Any]], Any],
    ) -> DispatchOutcome:
        # 1. Propose + validate the plan (planning phase already entered).
        try:
            proposal = await self._planner.plan(context)
        except AppError as exc:
            return self._plan_failure(controller, "planner", exc)
        except Exception as exc:  # noqa: BLE001 - planner crash is a real failure
            return self._crash_failure(controller, "planner", exc)
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

        # 2. Recruit the minimal team.
        controller.set_task_phase(TaskPhase.RECRUITING, reason="recruit minimal team")
        controller.set_run_state("recruiting")
        try:
            recruiter = self._recruiter or self._build_recruiter(context)
            team = recruiter.recruit(plan)
        except RecruitError as exc:
            return self._plan_failure(controller, "recruit", exc)
        except AppError as exc:
            return self._plan_failure(controller, "recruit", exc)

        # 3. Freeze member entities (current members), then execute.
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
        for member in team.members:
            member_id = member_ids[member.role_ref]
            controller.create_member(
                member_id,
                {
                    "run_ref": context.run_id,
                    "role_ref": member.role_ref,
                    "state": "ready",
                    "template_version": member.candidate.template_version,
                    "connection_ref": member.candidate.connection_ref,
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
            claimer.release(node.subtask_id, self._owner)
            return self._fail_node(node, controller, code="config_invalid", message=drift)

        request = self._build_request(node, context, upstream)
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
            claimer.release(node.subtask_id, self._owner)
            return self._crash_node(node, controller, exc)
        finally:
            self._inflight.get(run_id, set()).discard(task)
        claimer.release(node.subtask_id, self._owner)
        if result.execution_ref is not None:
            self._active_refs.setdefault(run_id, []).append(result.execution_ref)
        return self._apply_result(node, controller, result)

    def _apply_result(
        self, node: _Node, controller: RunController, result: ExecutorResult
    ) -> NodeResult:
        subtask_id = node.subtask_id
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
        if result.diff_ref and result.diff_ref not in evidence:
            evidence = (*evidence, result.diff_ref)
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
        return NodeResult(
            key=node.key,
            subtask_id=subtask_id,
            state="passed",
            handoff=handoff,
            result=result,
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
        self, node: _Node, context: DispatchContext, upstream: Sequence[str]
    ) -> ExecuteRequest:
        candidate = node.member.candidate
        return ExecuteRequest(
            task_id=context.task_id,
            run_id=context.run_id,
            subtask_id=node.subtask_id,
            attempt=context.attempt,
            objective=node.spec.objective,
            acceptance_criteria=node.spec.acceptance,
            instructions=context.instructions,
            upstream_artifact_refs=tuple(upstream),
            workspace_path=context.workspace_path,
            allowed_tools=candidate.tool_refs,
            skill_refs=candidate.skill_refs,
            connection_ref=candidate.connection_ref,
            timeout_seconds=context.timeout_seconds,
            budget=dict(context.budget),
            agent_ref=node.member.role_ref,
            save_dir=context.save_dir,
            conversation_id=context.conversation_id,
        )

    def _config_drift(self, node: _Node, context: DispatchContext) -> str | None:
        constraints = CompileConstraints(
            allowed_tools=frozenset(node.member.candidate.tool_refs),
            workspace_path=context.workspace_path or None,
            conversation_id=context.conversation_id,
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
        return None

    # ---------------------------------------------------------------- helpers
    def _writer_key(self, node: _Node, context: DispatchContext) -> str:
        return context.workspace_path if node.spec.write else ""

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
    **kwargs: Any,
) -> GraphDispatcher:
    """Convenience factory mirroring the LG-007 dispatcher construction style."""

    return GraphDispatcher(
        store,
        executor,
        catalog=catalog,
        planner=planner,
        max_parallel=max_parallel,
        **kwargs,
    )


__all__ = [
    "DEFAULT_CAPABILITIES",
    "GraphDispatcher",
    "NodeResult",
    "build_graph_dispatcher",
]
