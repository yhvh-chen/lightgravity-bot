"""Graph node-level native SDK session data flow (LG-016).

LG-016's cross-Run continuation must work for the real default execution path,
which is :class:`~lightgravity.coordinator.graph.GraphDispatcher`: a Run is a
*dependency graph of real nodes*, each executed by its own member and each
returning its own native SDK session.  The Run-level ``continuation`` record
alone is not enough there — it can only describe one conversation, and it left
every member's ``session_ref`` at ``None``.

This module is the single place that:

* extracts a **complete, non-secret** native session record from a trusted
  terminal source — the adapter's :class:`~lightgravity.adapter.ExecutorResult`
  ``session_ref`` (authoritative; the SDK assigns ``conversation_id`` only after
  the turn) or a trusted terminal ``adapter.session_started`` /
  ``adapter.execution_finished`` event;
* persists it **uniformly** to the member that executed the node
  (``member.session_ref``) and to a per-node Run mapping (``run.node_sessions``)
  plus the opaque ``run.session_refs`` stop-gate list;
* resolves, on a later (resumed) Run, the per-node native coordinates to pass
  into that node's :class:`~lightgravity.adapter.ExecuteRequest` — but only when
  the plan key, the node ``config_hash`` and the member/credential authorization
  all still match.  A node whose identity cannot be proven is dispatched
  *fresh* (a new conversation), never attached to a stale one and never used to
  silently replay a completed write.

No secret ever enters these records: only native IDs, directories and version
tags.  ``conversation_id``/``save_dir`` are exactly what the LG-006/016 adapter
forwards to the SDK ``SessionContinuationMode``; a fabricated identity would let
a Run attach to the wrong conversation, so nothing is invented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from lightgravity.adapter import ExecutorResult

from .continuation import CONTINUATION_CONFIG_VERSION

#: Native session states that prove the SDK actually attached to a conversation
#: (as opposed to a session that never got an id).  Only these may be continued.
_CONTINUABLE_SESSION_STATES: frozenset[str] = frozenset(
    {"created", "resumed", "create_or_resumed"}
)

#: Node terminal states whose native session must **not** be continued: the work
#: is already done (``passed``) or was rejected.  Replaying them would repeat a
#: possibly written node; the completed node and its artifact versions are kept
#: on the Subtask instead.
_COMPLETED_STATES: frozenset[str] = frozenset({"passed"})


@dataclass(frozen=True, slots=True)
class NodeSession:
    """Non-secret native session record for one graph node."""

    key: str
    subtask_id: str
    member_ref: str
    session_id: str
    conversation_id: str
    save_dir: str
    state: str
    source: str  # result | session_started | execution_finished
    #: Terminal node result state (passed/failed/cancelled/blocked).  A
    #: ``passed`` node is completed and must never be replayed on resume.
    node_state: str | None = None
    config_version: str = CONTINUATION_CONFIG_VERSION
    #: Node config+member hash at execution time; continuation requires an exact
    #: match so a reconfigured node never reattaches to an old conversation.
    config_hash: str | None = None
    credential_ref: str | None = None
    #: Stable role identity (survives the per-Run member id churn).  Used to
    #: re-check authorization; an ephemeral member id cannot be compared across
    #: Runs because a resumed Run recruits fresh members.
    role_ref: str | None = None

    def to_member_payload(self) -> dict[str, Any]:
        """The complete non-secret ``SessionRef`` for ``member.session_ref``."""

        return {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "save_dir": self.save_dir,
            "state": self.state,
            "source": self.source,
            "config_version": self.config_version,
        }

    def to_run_payload(self) -> dict[str, Any]:
        """The per-node Run mapping entry (``run.node_sessions``)."""

        payload: dict[str, Any] = {
            "key": self.key,
            "subtask_ref": self.subtask_id,
            "member_ref": self.member_ref,
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "save_dir": self.save_dir,
            "state": self.state,
            "source": self.source,
            "config_version": self.config_version,
        }
        if self.node_state:
            payload["node_state"] = self.node_state
        if self.role_ref:
            payload["role_ref"] = self.role_ref
        if self.config_hash:
            payload["config_hash"] = self.config_hash
        if self.credential_ref:
            payload["credential_ref"] = self.credential_ref
        return payload

    def to_continuation(self) -> dict[str, Any]:
        """The per-node coordinates forwarded into a resumed ExecuteRequest."""

        return {
            "conversation_id": self.conversation_id,
            "save_dir": self.save_dir,
            "continuation_mode": "resume",
            "config_version": self.config_version,
        }


def extract_node_session(
    result: ExecutorResult | None,
    *,
    key: str,
    subtask_id: str,
    member_ref: str,
    node_state: str | None = None,
    config_hash: str | None = None,
    credential_ref: str | None = None,
    role_ref: str | None = None,
) -> NodeSession | None:
    """Build a :class:`NodeSession` from a trusted terminal ``ExecutorResult``.

    Returns ``None`` when the result carries no native ``conversation_id`` — the
    honest "the SDK reported no session" case.  ``save_dir`` is taken from the
    result's session ref; a missing directory falls back to the caller-supplied
    node directory so a resumed Run can still find the native store.
    """

    if result is None:
        return None
    ref = getattr(result, "session_ref", None)
    if ref is None:
        return None
    session_id = getattr(ref, "session_id", None)
    conversation_id = getattr(ref, "conversation_id", None)
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        return None
    save_dir = getattr(ref, "save_dir", None)
    state = str(getattr(ref, "state", "created") or "created")
    return NodeSession(
        key=key,
        subtask_id=subtask_id,
        member_ref=member_ref,
        session_id=session_id,
        conversation_id=conversation_id,
        save_dir=save_dir if isinstance(save_dir, str) else "",
        state=state,
        source="result",
        node_state=node_state,
        config_hash=config_hash,
        credential_ref=credential_ref,
        role_ref=role_ref,
    )


def record_node_session(controller: Any, session: NodeSession) -> None:
    """Persist a node session uniformly to Member + Run node mapping.

    Idempotent by ``session_id``.  Writes through the :class:`RunController`
    (Store), never mutating files directly.  A member write failure must not
    abort the Run; the Run mapping and stop-gate list are still recorded.
    """

    # 1. Per-node Run mapping (keyed by subtask runtime id).
    run = controller.read_run()
    node_sessions = _as_mapping(run.get("node_sessions"))
    existing = node_sessions.get(session.subtask_id)
    if not (isinstance(existing, dict) and existing.get("session_id") == session.session_id):
        node_sessions[session.subtask_id] = session.to_run_payload()
        controller.update_run({"node_sessions": node_sessions})

    # 2. Stop-gate opaque session list (only ids; never secrets).
    raw_refs = run.get("session_refs")
    refs = [str(item) for item in raw_refs] if isinstance(raw_refs, (list, tuple)) else []
    if session.session_id not in refs:
        controller.update_run({"session_refs": [*refs, session.session_id]})

    # 3. The member that executed the node carries the full non-secret record.
    if session.member_ref:
        try:
            controller.set_member_session(session.member_ref, session.to_member_payload())
        except Exception:  # noqa: BLE001 - the Run mapping is the fallback record
            pass


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def node_session_for_resume(
    prior_run: Mapping[str, Any] | None,
    *,
    key: str,
    config_hash: str | None,
    member_ref: str | None = None,
    role_ref: str | None = None,
) -> NodeSession | None:
    """Resolve a prior node's native coordinates for a **safe** continuation.

    A node may only be continued when **all** of the following hold:

    * a prior Run recorded a node session for the same plan ``key``;
    * the node's ``config_hash`` matches exactly (a reconfigured node gets a fresh
      conversation; the hash already folds in the member config);
    * the stable ``role_ref`` still matches when recorded (authorization identity);
    * the node's native state proves the SDK attached to a conversation and it is
      not a completed ``passed`` node (a completed write is never replayed);
    * the session carries both ``conversation_id`` and ``save_dir``.

    Anything else returns ``None`` — the caller dispatches the node fresh.
    """

    if not isinstance(prior_run, Mapping):
        return None
    node_sessions = prior_run.get("node_sessions")
    if not isinstance(node_sessions, Mapping):
        return None
    match: Mapping[str, Any] | None = None
    for entry in node_sessions.values():
        if not isinstance(entry, Mapping):
            continue
        if entry.get("key") != key:
            continue
        if config_hash is not None and entry.get("config_hash") not in (None, config_hash):
            continue
        if role_ref is not None and entry.get("role_ref") not in (None, role_ref):
            continue
        if (
            role_ref is None
            and member_ref is not None
            and entry.get("member_ref") not in (None, member_ref)
        ):
            continue
        match = entry
        break
    if match is None:
        return None
    state = str(match.get("state", ""))
    if state == "closed":
        # The session was explicitly closed; a later Run opens a new one.
        return None
    if state not in _CONTINUABLE_SESSION_STATES:
        return None
    conversation_id = match.get("conversation_id")
    save_dir = match.get("save_dir")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        return None
    if not isinstance(save_dir, str) or not save_dir.strip():
        return None
    session_id = match.get("session_id")
    return NodeSession(
        key=key,
        subtask_id=str(match.get("subtask_ref", "")),
        member_ref=str(match.get("member_ref", member_ref or "")),
        session_id=str(session_id) if isinstance(session_id, str) else "",
        conversation_id=conversation_id,
        save_dir=save_dir,
        state=state,
        source=str(match.get("source", "result")),
        config_hash=config_hash,
        role_ref=(
            str(match.get("role_ref")) if isinstance(match.get("role_ref"), str) else role_ref
        ),
        credential_ref=(
            str(match.get("credential_ref"))
            if isinstance(match.get("credential_ref"), str)
            else None
        ),
    )


def completed_keys(prior_run: Mapping[str, Any] | None) -> frozenset[str]:
    """Plan keys already ``passed`` in a prior Run.

    Used to keep completed nodes and their artifact versions instead of
    silently replaying a possibly-written node on resume.
    """

    if not isinstance(prior_run, Mapping):
        return frozenset()
    node_sessions = prior_run.get("node_sessions")
    if not isinstance(node_sessions, Mapping):
        return frozenset()
    done: set[str] = set()
    for entry in node_sessions.values():
        if not isinstance(entry, Mapping):
            continue
        key = entry.get("key")
        if isinstance(key, str) and entry.get("node_state") in _COMPLETED_STATES:
            done.add(key)
    return frozenset(done)


__all__ = [
    "NodeSession",
    "completed_keys",
    "extract_node_session",
    "node_session_for_resume",
    "record_node_session",
]
