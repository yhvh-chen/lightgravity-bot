"""Peer handoff boundary reserved for LG-030 (NOT implemented here).

LG-029 owns discovery, claim, lease and fencing for the *self* case.  LG-030
owns controlled peer requests and context/artifact handoff (the frozen
``collab_requests`` endpoints, ``collab.*``/``handoff.*`` events).  This module
exists only to reserve an independent, non-overlapping peer surface so LG-030 can
implement without editing the claim/lease modules in this package.

Nothing here is wired or functional yet.  The marker is explicit so callers and
the integration owner do not mistake the presence of this module for
implementation: :data:`PEER_MODULE_IMPLEMENTED` is ``False`` and every entry
point raises :class:`NotImplementedError` with an honest owner pointer, matching
the docs/08 §4.3 note that the collaboration endpoints are frozen interfaces
only until their owning task implements them.
"""

from __future__ import annotations

from typing import NoReturn

#: LG-030 owns the peer/collab implementation; flip only from that task.
PEER_MODULE_IMPLEMENTED = False

PEER_OWNER_TASK = "LG-030"


def _not_implemented(operation: str) -> NoReturn:
    raise NotImplementedError(
        f"{operation} is owned by {PEER_OWNER_TASK} (docs/08 §4.3 collab_requests); "
        "not implemented by LG-029"
    )


def request_peer(*args: object, **kwargs: object) -> NoReturn:
    """Placeholder for the LG-030 controlled peer request."""

    del args, kwargs
    _not_implemented("request_peer")


def read_peer_requests(*args: object, **kwargs: object) -> NoReturn:
    """Placeholder for the LG-030 read-only peer request projection."""

    del args, kwargs
    _not_implemented("read_peer_requests")


def handoff_artifact(*args: object, **kwargs: object) -> NoReturn:
    """Placeholder for the LG-030 versioned artifact handoff."""

    del args, kwargs
    _not_implemented("handoff_artifact")


__all__ = [
    "PEER_MODULE_IMPLEMENTED",
    "PEER_OWNER_TASK",
    "handoff_artifact",
    "read_peer_requests",
    "request_peer",
]
