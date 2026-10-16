"""Decentralized task discovery, atomic claims, leases and fencing (LG-029).

Implements the LG-028-frozen interface from docs/08 §4.3/§6.3 for the
*self* case: a worker may discover the Subtasks it is authorized to see and
*request* a claim; only this package (program authority) decides and persists
ownership.

Scope split inside the package keeps LG-030 independent:

* ``models`` — plain value types (no I/O);
* ``errors`` — ``claim_refused`` / ``stale_lease`` mapped onto frozen codes;
* ``discovery`` — read-only authorized projection;
* ``lease`` — atomic claim/renew/release/reclaim and the fence gate;
* ``service`` — policy (default-off), budget, request idempotency;
* ``handoff`` — versioned/hashed artifact-reference validation (LG-030);
* ``context`` — bounded authorized summaries and causal binding (LG-030);
* ``peer`` — controlled peer requests and results (LG-030).

The default path stays deterministic scheduling: every entry point is inert
unless ``decentralized_claim_enabled`` is true in ``settings/SETTINGS.md``.
"""

from .context import (
    COLLAB_MODES,
    MAX_SUMMARY_CHARS,
    AuthorizedSummary,
    CausalBinding,
    ContextError,
    classify_summary,
    validate_binding,
)
from .discovery import DiscoveryLimits, DiscoveryService
from .errors import ClaimRefused, StaleLease
from .execution_grant import (
    DEFAULT_GRANT_SECONDS,
    ExecutionGrant,
    ExecutionGrantRegistry,
    default_registry,
    make_restricted_claim_tool,
    make_restricted_peer_tool,
    reset_default_registry,
    resolve_worker_identity,
)
from .handoff import (
    ArtifactRef,
    HandoffError,
    encode_upstream_ref,
    parse_artifact_ref,
    validate_handoff_refs,
)
from .lease import DEFAULT_LEASE_SECONDS, LeaseManager
from .peer import (
    DEFAULT_COLLAB_TIMEOUT_SECONDS,
    DEFAULT_MAX_COLLAB_REQUESTS,
    CollabRefused,
    CollabRequestResult,
    HandoffRejected,
    PeerService,
)
from .models import (
    CLAIMABLE_SUBTASK_STATES,
    REFUSAL_REASONS,
    TERMINAL_SUBTASK_STATES,
    ClaimDecision,
    ClaimRequest,
    DiscoverableCandidate,
    DiscoveryView,
    LeaseRenewal,
    LeaseState,
    ReclaimOutcome,
    fence_of,
)
from .service import ClaimPolicy, ClaimPolicyReader, CollaborationService

__all__ = [
    "CLAIMABLE_SUBTASK_STATES",
    "COLLAB_MODES",
    "DEFAULT_COLLAB_TIMEOUT_SECONDS",
    "DEFAULT_GRANT_SECONDS",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MAX_COLLAB_REQUESTS",
    "MAX_SUMMARY_CHARS",
    "REFUSAL_REASONS",
    "TERMINAL_SUBTASK_STATES",
    "ArtifactRef",
    "AuthorizedSummary",
    "CausalBinding",
    "ClaimDecision",
    "ClaimPolicy",
    "ClaimPolicyReader",
    "ClaimRefused",
    "ClaimRequest",
    "CollabRefused",
    "CollabRequestResult",
    "CollaborationService",
    "ContextError",
    "DiscoverableCandidate",
    "DiscoveryLimits",
    "DiscoveryService",
    "DiscoveryView",
    "ExecutionGrant",
    "ExecutionGrantRegistry",
    "HandoffError",
    "HandoffRejected",
    "LeaseManager",
    "LeaseRenewal",
    "LeaseState",
    "PeerService",
    "ReclaimOutcome",
    "StaleLease",
    "classify_summary",
    "default_registry",
    "encode_upstream_ref",
    "fence_of",
    "make_restricted_claim_tool",
    "make_restricted_peer_tool",
    "parse_artifact_ref",
    "reset_default_registry",
    "resolve_worker_identity",
    "validate_binding",
    "validate_handoff_refs",
]
