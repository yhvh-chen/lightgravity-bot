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
* ``peer`` — reserved, unimplemented LG-030 peer boundary.

The default path stays deterministic scheduling: every entry point is inert
unless ``decentralized_claim_enabled`` is true in ``settings/SETTINGS.md``.
"""

from .discovery import DiscoveryLimits, DiscoveryService
from .errors import ClaimRefused, StaleLease
from .lease import DEFAULT_LEASE_SECONDS, LeaseManager
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
    "DEFAULT_LEASE_SECONDS",
    "REFUSAL_REASONS",
    "TERMINAL_SUBTASK_STATES",
    "ClaimDecision",
    "ClaimPolicy",
    "ClaimPolicyReader",
    "ClaimRefused",
    "ClaimRequest",
    "CollaborationService",
    "DiscoverableCandidate",
    "DiscoveryLimits",
    "DiscoveryService",
    "DiscoveryView",
    "LeaseManager",
    "LeaseRenewal",
    "LeaseState",
    "ReclaimOutcome",
    "StaleLease",
    "fence_of",
]
