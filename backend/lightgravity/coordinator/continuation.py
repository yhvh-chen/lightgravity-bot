"""Native SDK session continuation for resumed Tasks (LG-016).

The product contract (docs/02 §SDK 资源, docs/04 §5/§8, docs/08 §8) says an SDK
session is *recovery reference*, not a replay log: a resumed Task must continue
the **same native conversation** when that is provably safe, and must never
silently replay the initial objective from scratch after write side effects
have already happened.

This module is the one place that decides whether a newly opened Run may
continue a previous Run's native session.  It records and consumes only
**non-secret** native identity that the installed SDK (``google-antigravity``
``0.1.22``) actually exposes and that LG-006 already plumbs through
``ExecuteRequest.save_dir`` + ``ExecuteRequest.conversation_id``:

* ``conversation_id`` — the SDK-native conversation handle,
* ``save_dir`` — the on-disk native session store for that conversation,
* ``continuation_mode`` — ``resume`` / ``create_or_resume`` / ``create_only``
  (SDK ``SessionContinuationMode``),
* a fixed ``config_version`` tag so a Run records which configuration shape
  produced its continuation decision.

Safety rules (deliberately conservative):

* Only a Run that stopped through a **confirmed user pause** may be continued.
  A Run that failed, was cancelled, was interrupted by a restart, or whose
  liveness/side effects are unknown goes to ``recovery_required`` instead and
  requires an explicit human decision — this module never auto-continues it.
* The source Run must carry a complete, clean native session record
  (``conversation_id`` **and** ``save_dir``) and a ``closed``/``done`` cleanup,
  proving the previous session stopped before we attach to it.
* A source Run whose cleanup is not ``done`` (possible unconfirmed stop / live
  session) is never continued.
* No secret value is stored: only IDs, directories and a version tag.

The planner is intentionally side-effect free until :func:`record_continuation`
is called by the coordinator after a Run opens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Fixed, non-secret configuration version of the continuation contract.  A Run
#: records this so an operator/QA can tell which continuation shape was used;
#: bump it when the persisted continuation fields or the safety rules change.
CONTINUATION_CONFIG_VERSION = "lg016.1"

#: SDK-native continuation modes (``google.antigravity.types.SessionContinuationMode``).
#: ``RESUME`` requires the conversation to exist; ``CREATE_OR_RESUME`` falls back
#: to a fresh session.  We only ever emit ``RESUME`` for a provable continuation.
MODE_RESUME = "resume"
MODE_CREATE_OR_RESUME = "create_or_resume"
MODE_CREATE_ONLY = "create_only"

#: Run states from which a native session may be continued.  Only a confirmed
#: user pause qualifies; everything else is recovery/replay territory.
CONTINUABLE_RUN_STATES: frozenset[str] = frozenset({"paused"})


@dataclass(frozen=True, slots=True)
class NativeSessionIdentity:
    """Non-secret native session coordinates persisted on a Run.

    ``conversation_id`` and ``save_dir`` are the SDK-native values that
    ``build_sdk_config`` forwards as ``conversation_id`` / ``save_dir``;
    ``continuation_mode`` is the SDK ``SessionContinuationMode`` value.
    """

    conversation_id: str
    save_dir: str
    continuation_mode: str = MODE_RESUME
    source_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "conversation_id": self.conversation_id,
            "save_dir": self.save_dir,
            "continuation_mode": self.continuation_mode,
            "config_version": CONTINUATION_CONFIG_VERSION,
        }
        if self.source_run_id:
            payload["source_run_id"] = self.source_run_id
        return payload


@dataclass(frozen=True, slots=True)
class ContinuationDecision:
    """Outcome of inspecting a Task's previous Run for native continuation."""

    kind: str  # resume | fresh | recovery_required
    reason: str
    identity: NativeSessionIdentity | None = None
    source_run_id: str | None = None
    config_version: str = CONTINUATION_CONFIG_VERSION

    @property
    def is_resume(self) -> bool:
        return self.kind == "resume"

    @property
    def is_recovery_required(self) -> bool:
        return self.kind == "recovery_required"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "reason": self.reason,
            "config_version": self.config_version,
        }
        if self.source_run_id:
            payload["source_run_id"] = self.source_run_id
        if self.identity is not None:
            payload["identity"] = self.identity.to_dict()
        return payload


def _session_identity(run: dict[str, Any], run_id: str) -> NativeSessionIdentity | None:
    """Extract the persisted native session identity from a Run entity.

    The coordinator stores it under ``continuation`` (non-secret).  Older Runs
    that only have ``session_refs`` cannot be continued because ``session_refs``
    intentionally holds only opaque session ids for the stop gate, not the
    native ``conversation_id``/``save_dir`` pair.
    """

    raw = run.get("continuation")
    if not isinstance(raw, dict):
        return None
    conversation_id = raw.get("conversation_id")
    save_dir = raw.get("save_dir")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        return None
    if not isinstance(save_dir, str) or not save_dir.strip():
        return None
    mode = raw.get("continuation_mode")
    if mode not in {MODE_RESUME, MODE_CREATE_OR_RESUME, MODE_CREATE_ONLY}:
        mode = MODE_RESUME
    source = raw.get("source_run_id")
    return NativeSessionIdentity(
        conversation_id=conversation_id,
        save_dir=save_dir,
        continuation_mode=str(mode),
        source_run_id=str(source) if isinstance(source, str) and source else run_id,
    )


def plan_continuation(
    task_entity: dict[str, Any],
    source_run: dict[str, Any] | None,
    source_run_id: str | None,
) -> ContinuationDecision:
    """Decide how a newly opened Run should attach to a previous native session.

    ``source_run``/``source_run_id`` describe the Task's most recent stopped Run
    (usually ``task_entity['active_run']`` before it is cleared).  The decision
    is one of:

    * ``resume`` — provably safe: a confirmed *paused* Run with a clean native
      session record and ``done`` cleanup.  The new Run continues the same
      conversation with ``session_continuation_mode=resume``.
    * ``recovery_required`` — the previous Run did not stop cleanly (interrupted
      / unknown side effects / missing cleanup).  The caller must **not** open a
      replay Run; a human decides.
    * ``fresh`` — no previous native session to continue (first attempt, or the
      source Run is a clean terminal state we do not continue, e.g. failed).
    """

    if source_run is None or not isinstance(source_run_id, str) or not source_run_id:
        return ContinuationDecision(
            kind="fresh", reason="no previous Run to continue"
        )

    state = str(source_run.get("state", ""))
    phase = str(task_entity.get("phase", ""))

    # An interrupted Run whose result is unknown must never be auto-continued.
    if phase == "recovery_required" or state == "recovery_required":
        return ContinuationDecision(
            kind="recovery_required",
            reason="previous Run requires a human recovery decision; not auto-continuing",
            source_run_id=source_run_id,
        )

    cleanup = source_run.get("cleanup")
    cleanup_status = (
        str(cleanup.get("status")) if isinstance(cleanup, dict) else "pending"
    )

    if state not in CONTINUABLE_RUN_STATES:
        # Terminal non-pause states are not silently continued: a failed Run may
        # have left unknown side effects, a cancelled Run was deliberately
        # abandoned.  These stay fresh (a *new* Run) unless a human reopens them.
        return ContinuationDecision(
            kind="fresh",
            reason=f"previous Run state {state!r} is not a confirmed pause",
            source_run_id=source_run_id,
        )

    if cleanup_status != "done":
        # The previous session may still be live or its stop was unconfirmed.
        # Attaching now could double-writer the native store; require recovery.
        return ContinuationDecision(
            kind="recovery_required",
            reason=(
                f"previous paused Run cleanup is {cleanup_status!r}, not 'done'; "
                "stop not proven, not auto-continuing"
            ),
            source_run_id=source_run_id,
        )

    identity = _session_identity(source_run, source_run_id)
    if identity is None:
        # A clean pause but no native session coordinates (e.g. the adapter
        # reported no session, or an older Run): continue the Task, but create a
        # fresh session rather than pretend we resumed.
        return ContinuationDecision(
            kind="fresh",
            reason="previous Run has no persisted native conversation identity",
            source_run_id=source_run_id,
        )

    return ContinuationDecision(
        kind="resume",
        reason="continuing native session from confirmed paused Run",
        identity=identity,
        source_run_id=source_run_id,
    )


def continuation_record(
    *,
    conversation_id: str | None,
    save_dir: str | None,
    continuation_mode: str = MODE_CREATE_ONLY,
    source_run_id: str | None = None,
    resumed: bool = False,
) -> dict[str, Any] | None:
    """Build the non-secret ``continuation`` payload recorded on a new Run.

    Returns ``None`` when the adapter reported no native conversation id, so the
    Run honestly records "no native session" instead of a fabricated identity.
    """

    if not isinstance(conversation_id, str) or not conversation_id.strip():
        return None
    if not isinstance(save_dir, str) or not save_dir.strip():
        return None
    mode = continuation_mode if resumed else MODE_CREATE_ONLY
    payload: dict[str, Any] = {
        "conversation_id": conversation_id,
        "save_dir": save_dir,
        "continuation_mode": mode,
        "config_version": CONTINUATION_CONFIG_VERSION,
    }
    if source_run_id:
        payload["source_run_id"] = source_run_id
    return payload


__all__ = [
    "CONTINUABLE_RUN_STATES",
    "CONTINUATION_CONFIG_VERSION",
    "MODE_CREATE_ONLY",
    "MODE_CREATE_OR_RESUME",
    "MODE_RESUME",
    "ContinuationDecision",
    "NativeSessionIdentity",
    "continuation_record",
    "plan_continuation",
]
