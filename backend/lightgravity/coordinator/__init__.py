"""Resident coordinator: message routing, Task queue and Run lifecycle (LG-007).

This package is the first-version, minimal implementation of docs/08 §4.3 /
§5-§6 routing and queue ownership for the resident Bot:

* :mod:`~lightgravity.coordinator.classification` classifies an incoming
  message into a direct reply, a bounded read-only request or a delivery/Run
  path without granting extra permissions.
* :mod:`~lightgravity.coordinator.logs` persists global conversation messages
  and request-idempotency records.
* :mod:`~lightgravity.coordinator.dispatcher` is the **stable seam for LG-008**:
  the planner/recruiter/scheduler graph plugs in behind :class:`Dispatcher`.
* :class:`~lightgravity.coordinator.service.Coordinator` owns the single
  execution slot, Task/Run lifecycle and control/query handling.  All control
  state is written through the ``Store``; the executor never writes it.
* :mod:`~lightgravity.coordinator.planner` (LG-008) proposes a Subtask graph and
  validates it program-side; :mod:`~lightgravity.coordinator.recruiter` (LG-008)
  selects a minimal temporary team from an explicit capability catalog;
  :mod:`~lightgravity.coordinator.scheduler` (LG-008) validates the dependency
  graph and owns Subtask claim/lease plus artifact handoff; and
  :mod:`~lightgravity.coordinator.graph` (LG-008) composes them behind the
  :class:`Dispatcher` seam as :class:`GraphDispatcher`.
* :mod:`~lightgravity.coordinator.api` exposes an independent FastAPI router
  factory for LG-012 to mount (``api/app.py`` is intentionally untouched).

Scope boundary: LG-007 owns routing/queue/single-slot; LG-008 adds the planner,
recruiter, scheduler and graph dispatcher.  Full pause/cancel/restore (LG-016)
and artifact verification / human acceptance (LG-009) remain separate tasks.
"""

from .api import build_router
from .classification import (
    READ_ONLY_TOOL_CEILING,
    Classification,
    MessageIntent,
    classify_message,
)
from .dialogue import (
    DialogueSupport,
    ModelDialogue,
    make_sync_responder,
    resolve_dialogue_support,
    unavailable_reply,
)
from .dispatcher import (
    DispatchContext,
    Dispatcher,
    DispatchOutcome,
    RunController,
    SingleSlotDispatcher,
    UnavailableExecutor,
)
from .graph import GraphDispatcher, NodeResult, build_graph_dispatcher
from .planner import (
    ModelPlanner,
    ModelProposalError,
    Plan,
    PlanInvalid,
    PlanProposal,
    Planner,
    PlanValidator,
    RawSubtask,
    RuleBasedPlanner,
    SubtaskSpec,
)
from .planning import PlanningRequest, PlanningTrigger
from .recruiter import (
    CandidateAgent,
    MemberPlan,
    RecruitError,
    Recruiter,
    RoleCatalog,
    TeamPlan,
    member_config_hash,
)
from .control import ControlOutcome, ControlService
from .continuation import (
    CONTINUATION_CONFIG_VERSION,
    ContinuationDecision,
    NativeSessionIdentity,
    continuation_record,
    plan_continuation,
)
from .recovery import (
    DefaultProcessProbe,
    ProcessProbe,
    RecoveryDecision,
    RecoveryScanner,
)
from .session_flow import (
    NodeSession,
    completed_keys,
    extract_node_session,
    node_session_for_resume,
    record_node_session,
    reusable_completed_node,
)
from .resource_commands import (
    ResourceProposal,
    parse_resource_proposal,
    proposal_author_role,
)
from .scheduler import (
    ArtifactHandoff,
    ClaimOutcome,
    DependencyGraph,
    GraphError,
    GraphNode,
    SubtaskClaimer,
    encode_handoffs,
    parse_handoff_ref,
)
from .service import CandidateVerifier, Coordinator, CoordinatorResult

__all__ = [
    "READ_ONLY_TOOL_CEILING",
    "Classification",
    "MessageIntent",
    "classify_message",
    "DialogueSupport",
    "ModelDialogue",
    "make_sync_responder",
    "resolve_dialogue_support",
    "unavailable_reply",
    "DispatchContext",
    "Dispatcher",
    "DispatchOutcome",
    "RunController",
    "SingleSlotDispatcher",
    "UnavailableExecutor",
    "GraphDispatcher",
    "NodeResult",
    "build_graph_dispatcher",
    "ModelPlanner",
    "ModelProposalError",
    "Plan",
    "PlanInvalid",
    "PlanProposal",
    "Planner",
    "PlanValidator",
    "RawSubtask",
    "RuleBasedPlanner",
    "SubtaskSpec",
    "PlanningRequest",
    "PlanningTrigger",
    "CandidateAgent",
    "MemberPlan",
    "RecruitError",
    "Recruiter",
    "RoleCatalog",
    "TeamPlan",
    "member_config_hash",
    "ResourceProposal",
    "parse_resource_proposal",
    "proposal_author_role",
    "ArtifactHandoff",
    "ClaimOutcome",
    "DependencyGraph",
    "GraphError",
    "GraphNode",
    "SubtaskClaimer",
    "encode_handoffs",
    "parse_handoff_ref",
    "Coordinator",
    "CoordinatorResult",
    "CandidateVerifier",
    "ControlOutcome",
    "ControlService",
    "CONTINUATION_CONFIG_VERSION",
    "ContinuationDecision",
    "NativeSessionIdentity",
    "continuation_record",
    "plan_continuation",
    "DefaultProcessProbe",
    "ProcessProbe",
    "RecoveryDecision",
    "RecoveryScanner",
    "NodeSession",
    "completed_keys",
    "reusable_completed_node",
    "extract_node_session",
    "node_session_for_resume",
    "record_node_session",
    "build_router",
]
