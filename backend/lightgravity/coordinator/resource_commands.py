"""Structured, bounded resource-change proposals (LG-015).

docs/05 §6.2 routes ordinary resource edits through Chat "受控对话写入".  This
module is the *program-side* contract for that path: a Task conversation
message may carry one additive ``resource_proposal`` field, and the coordinator
validates its shape before it is ever handed to
:meth:`lightgravity.resources.ResourceService.update`.

Deliberate boundaries:

* There is **no** natural-language parser and **no** extra model call here.  A
  proposal is a small, explicit structure produced by the existing Controlled
  change UI (or an equivalent client); anything else is rejected.
* The proposal never grants permissions.  It cannot name a member/worker as its
  author (only an authenticated ``user`` Task message is accepted) and cannot
  touch Connections (those go through Settings).
* Field allow-listing, adapter schema re-validation, reference resolution and
  the optimistic ``revision`` check all stay in ``ResourceService.update``;
  this module only rejects malformed/hostile shapes early with the frozen
  ``invalid_request`` code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.store.ids import is_slug

#: Roles whose messages may carry a resource proposal.  A model/worker message
#: (``assistant``/``tool``/``system``) must never write control state.
PROPOSAL_AUTHOR_ROLES: frozenset[str] = frozenset({"user"})

PROPOSAL_FIELDS: frozenset[str] = frozenset(
    {"kind", "id", "expected_revision", "patch", "body"}
)


@dataclass(frozen=True, slots=True)
class ResourceProposal:
    """A bounded request to change one resource's authoritative file."""

    kind: str
    resource_id: str
    expected_revision: int
    patch: dict[str, Any] = field(default_factory=dict)
    body: str | None = None

    @property
    def ref(self) -> str:
        return f"{self.kind}:{self.resource_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.resource_id,
            "expected_revision": self.expected_revision,
            "patch": dict(self.patch),
            "body": self.body,
        }


def _invalid(message: str, **details: Any) -> AppError:
    return AppError(ErrorCode.INVALID_REQUEST, message, details=details)


def parse_resource_proposal(raw: Any) -> ResourceProposal:
    """Validate the on-the-wire proposal shape.

    Shape errors are ``invalid_request``; semantic checks (unknown kind,
    allow-list, references, revision) are enforced by ``ResourceService``.
    """

    if not isinstance(raw, dict):
        raise _invalid(
            "resource_proposal must be a mapping",
            field="resource_proposal",
            actual=type(raw).__name__,
        )
    unknown = sorted(set(raw) - PROPOSAL_FIELDS)
    if unknown:
        raise _invalid(
            "resource_proposal has unsupported fields",
            field="resource_proposal",
            rejected=unknown,
            allowed=sorted(PROPOSAL_FIELDS),
        )

    kind = raw.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise _invalid(
            "resource_proposal.kind must be a non-empty string",
            field="resource_proposal.kind",
        )
    kind = kind.strip()

    resource_id = raw.get("id")
    if not isinstance(resource_id, str) or not is_slug(resource_id):
        raise _invalid(
            "resource_proposal.id must be a resource slug",
            field="resource_proposal.id",
            id=resource_id,
        )

    expected_revision = raw.get("expected_revision")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 0
    ):
        raise _invalid(
            "resource_proposal.expected_revision must be an int >= 0",
            field="resource_proposal.expected_revision",
            expected_revision=expected_revision,
        )

    patch = raw.get("patch", {})
    if patch is None:
        patch = {}
    if not isinstance(patch, dict):
        raise _invalid(
            "resource_proposal.patch must be a mapping",
            field="resource_proposal.patch",
        )

    body = raw.get("body")
    if body is not None and not isinstance(body, str):
        raise _invalid(
            "resource_proposal.body must be a string or null",
            field="resource_proposal.body",
        )

    return ResourceProposal(
        kind=kind,
        resource_id=resource_id,
        expected_revision=expected_revision,
        patch=dict(patch),
        body=body,
    )


def proposal_author_role(message: dict[str, Any]) -> str:
    role = message.get("role", "user")
    return role if isinstance(role, str) and role else "user"


__all__ = [
    "PROPOSAL_AUTHOR_ROLES",
    "PROPOSAL_FIELDS",
    "ResourceProposal",
    "parse_resource_proposal",
    "proposal_author_role",
]
