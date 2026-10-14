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
* :mod:`~lightgravity.coordinator.api` exposes an independent FastAPI router
  factory for LG-012 to mount (``api/app.py`` is intentionally untouched).

Scope boundary: LG-007 does not implement the full planner/recruiter/scheduler
graph (LG-008) or full pause/cancel/restore (LG-016).
"""

from .api import build_router
from .classification import (
    READ_ONLY_TOOL_CEILING,
    Classification,
    MessageIntent,
    classify_message,
)
from .dispatcher import (
    DispatchContext,
    Dispatcher,
    DispatchOutcome,
    RunController,
    SingleSlotDispatcher,
    UnavailableExecutor,
)
from .service import Coordinator, CoordinatorResult

__all__ = [
    "READ_ONLY_TOOL_CEILING",
    "Classification",
    "MessageIntent",
    "classify_message",
    "DispatchContext",
    "Dispatcher",
    "DispatchOutcome",
    "RunController",
    "SingleSlotDispatcher",
    "UnavailableExecutor",
    "Coordinator",
    "CoordinatorResult",
    "build_router",
]
