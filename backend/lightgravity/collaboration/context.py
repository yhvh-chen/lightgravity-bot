"""Controlled context/summary transfer for peer collaboration (LG-030).

A collaboration request or response may carry only an **authorized summary** and
versioned artifact references - never raw source/artifact *content* and never a
control instruction.  This module defines the bounded value types and the
program-side validation that enforces that boundary before anything is persisted
or handed to another worker.

Two rules are implemented here, both from the LG-028 preparation §4.1-§4.4:

1. **Summary, not content.**  The summary is capped in length, and text that
   looks like an injected control instruction ("grant", "override", shell-like
   payloads, "ignore previous") is *stored as plain text* and explicitly flagged
   ``instruction_like`` so the coordinator treats it as data.  It is never
   interpreted as authorization or acceptance (docs/08 §4.3).  We do not censor
   the text: refusing to *execute* it is the control, silently rewriting it would
   hide the attempt from audit.
2. **Causal binding.**  Every request/response is bound to ``task``/``run``/``node``
   plus a ``message_id`` (the causing message) and a ``correlation_id``, so a
   duplicate/out-of-order peer message can be recognized and given a definite
   result instead of being replayed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Hard cap on an authorized summary.  Longer text is refused rather than
#: truncated, so a caller cannot smuggle unbounded content into the control log.
MAX_SUMMARY_CHARS = 2_000

#: Lower-cased substrings that mark text as *instruction-like*.  Such text is
#: stored verbatim but tagged; it never gains execution semantics.
_INSTRUCTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard previous",
    "system:",
    "assistant:",
    "grant permission",
    "grant me",
    "override permission",
    "escalate",
    "sudo ",
    "rm -rf",
    "chmod ",
    "curl ",
    "wget ",
    "set status",
    "mark as passed",
    "skip verification",
    "bypass",
)

#: Modes frozen for a peer request (LG-028 preparation §4.1).
COLLAB_MODES = ("summarize", "review", "execute")

#: ``collab_request`` lifecycle (source-side, not a Task phase).
REQUEST_STATES = ("requested", "resolved", "rejected", "expired")


class ContextError(ValueError):
    """An unauthorized or malformed peer context/summary."""


@dataclass(frozen=True, slots=True)
class AuthorizedSummary:
    """A bounded, non-executable summary of what a peer is asked to do.

    ``instruction_like`` is a *label for audit*, not a policy switch: the text is
    preserved either way and must be treated as data by every consumer.
    """

    text: str
    instruction_like: bool = False
    markers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "instruction_like": self.instruction_like,
            "markers": list(self.markers),
        }


def classify_summary(text: str) -> AuthorizedSummary:
    """Validate and classify an authorized summary.

    Raises :class:`ContextError` when the summary is missing or exceeds
    :data:`MAX_SUMMARY_CHARS`.  Never executes or rewrites the text.
    """

    if not isinstance(text, str) or not text.strip():
        raise ContextError("collab summary must be a non-empty string")
    if len(text) > MAX_SUMMARY_CHARS:
        raise ContextError(
            f"collab summary exceeds {MAX_SUMMARY_CHARS} characters"
        )
    lowered = text.lower()
    markers = tuple(marker for marker in _INSTRUCTION_MARKERS if marker in lowered)
    return AuthorizedSummary(text=text, instruction_like=bool(markers), markers=markers)


@dataclass(frozen=True, slots=True)
class CausalBinding:
    """Wire-level causal binding for one peer message (docs/08 §5.2).

    ``task_ref``/``run_ref``/``node_ref`` locate the message; ``message_id`` is
    the requesting message and ``correlation_id`` ties request and response into
    one chain.  ``in_reply_to`` links a response back to its request.
    """

    task_ref: str
    run_ref: str
    node_ref: str
    message_id: str
    correlation_id: str
    in_reply_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_ref": self.task_ref,
            "run_ref": self.run_ref,
            "node_ref": self.node_ref,
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "in_reply_to": self.in_reply_to,
        }


def validate_binding(
    *,
    task_ref: str,
    run_ref: str,
    node_ref: str,
    message_id: str,
    correlation_id: str,
    in_reply_to: str | None = None,
) -> CausalBinding:
    """Require the full causal binding; every identifier must be non-empty."""

    for label, value in (
        ("task_ref", task_ref),
        ("run_ref", run_ref),
        ("node_ref", node_ref),
        ("message_id", message_id),
        ("correlation_id", correlation_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ContextError(f"collab binding requires a non-empty {label}")
    if in_reply_to is not None and (not isinstance(in_reply_to, str) or not in_reply_to.strip()):
        raise ContextError("in_reply_to must be a non-empty string when present")
    return CausalBinding(
        task_ref=task_ref,
        run_ref=run_ref,
        node_ref=node_ref,
        message_id=message_id,
        correlation_id=correlation_id,
        in_reply_to=in_reply_to,
    )


def is_instruction_like(text: str) -> bool:
    """Convenience predicate used by tests and diagnostics."""

    lowered = text.lower()
    return any(marker in lowered for marker in _INSTRUCTION_MARKERS)


#: Keep the module free of accidental shell/format surprises by exposing the cap
#: for callers that build their own request bodies.
__all__ = [
    "COLLAB_MODES",
    "MAX_SUMMARY_CHARS",
    "REQUEST_STATES",
    "AuthorizedSummary",
    "CausalBinding",
    "ContextError",
    "classify_summary",
    "is_instruction_like",
    "validate_binding",
]
