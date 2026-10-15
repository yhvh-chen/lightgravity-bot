"""Versioned artifact handoff references for peer collaboration (LG-030).

The frozen contract requires that a peer hand off only *authorized summaries*
plus *versioned/hashed artifact references* (docs/08 §6.3 ``upstream_artifact_refs``
and the LG-028 preparation §4.1-§4.2).  A reference must therefore never be a raw
path, and it must self-describe the producing Subtask version and content digest
so the downstream side can verify existence, ownership and digest before use.

Two accepted reference shapes:

* ``evidence:<run_id>/<name>@sha256:<hex>`` — the canonical evidence namespace
  produced by :mod:`lightgravity.evidence` (LG-010/LG-014).  Resolved only under
  the owning Task's evidence root and only for the owning Run.
* ``<subtask_ref>@<content_hash>:<artifact>`` — the existing
  :class:`~lightgravity.coordinator.scheduler.ArtifactHandoff` encoding, kept so
  an in-Run upstream artifact (a workspace-relative path with a producer digest)
  can be referenced without inventing a second vocabulary.

This module is pure validation/parsing: it performs no I/O beyond reading the
digest of an already-resolved file, and it never grants execution semantics to
the *content* of an artifact.  A handoff carries data; it is never a control
instruction (docs/08 §4.3 note on source text).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lightgravity.evidence import (
    EvidenceRefError,
    parse_evidence_ref,
    resolve_evidence_ref,
)

#: A workspace-relative artifact path: no absolute/`..`/empty segments.
_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
#: ``<subtask_ref>@<content_hash>:<artifact>`` (see scheduler.parse_handoff_ref).
_HANDOFF_REF = re.compile(r"^(?P<subtask>[^@]+)@(?P<hash>[0-9a-fA-F]{64}):(?P<artifact>.+)$")


class HandoffError(ValueError):
    """A malformed, unauthorized or stale artifact reference."""


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """A parsed, versioned artifact reference ready for authorization.

    ``kind`` is ``"evidence"`` or ``"upstream"``; ``digest`` is always a
    lowercase sha256 hex when the reference carries one.  ``origin_ref`` is the
    Subtask that produced the artifact when the caller supplied it (upstream
    shape); ``None`` for canonical evidence refs, whose producing Run is implied.
    """

    raw: str
    kind: str
    artifact: str
    digest: str | None
    origin_ref: str | None = None
    run_ref: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ref": self.raw,
            "kind": self.kind,
            "artifact": self.artifact,
            "digest": self.digest,
            "origin_ref": self.origin_ref,
            "run_ref": self.run_ref,
        }


def parse_artifact_ref(ref: str) -> ArtifactRef:
    """Parse and structurally validate one artifact reference.

    Raises :class:`HandoffError` for raw absolute paths, ``..`` escapes, empty
    references and malformed shapes.  Digest presence is not required for a
    workspace-relative upstream path, but when a digest is present it must be a
    valid sha256 hex.
    """

    if not isinstance(ref, str) or not ref.strip():
        raise HandoffError("artifact reference must be a non-empty string")
    value = ref.strip()

    # Canonical evidence namespace: delegate to the LG-010 parser so the two
    # lines cannot drift.
    if value.startswith("evidence:"):
        try:
            parsed = parse_evidence_ref(value)
        except EvidenceRefError as exc:
            raise HandoffError(str(exc)) from exc
        if parsed is None:  # pragma: no cover - startswith guarantees a parse
            raise HandoffError(f"not a canonical evidence ref: {value!r}")
        return ArtifactRef(
            raw=value,
            kind="evidence",
            artifact=parsed.name,
            digest=parsed.digest,
            run_ref=parsed.run_id,
        )

    if value.startswith("/") or value.startswith("~") or "\\" in value:
        raise HandoffError(f"raw/absolute artifact ref is not allowed: {value!r}")

    upstream = _HANDOFF_REF.match(value)
    if upstream is not None:
        return ArtifactRef(
            raw=value,
            kind="upstream",
            artifact=upstream.group("artifact"),
            digest=upstream.group("hash").lower(),
            origin_ref=upstream.group("subtask"),
        )

    # A bare workspace-relative path.  Reject traversal and absolute-ish forms.
    if not _SAFE_RELATIVE.match(value) or ".." in value.split("/"):
        raise HandoffError(f"unsafe or malformed artifact ref: {value!r}")
    return ArtifactRef(raw=value, kind="workspace", artifact=value, digest=None)


def validate_handoff_refs(
    refs: list[str] | tuple[str, ...],
    *,
    data_dir: Path | str | None,
    task_id: str,
    run_id: str,
    workspace_root: Path | str | None = None,
    known_subtask_refs: set[str] | None = None,
) -> tuple[ArtifactRef, ...]:
    """Authorize a batch of handoff refs for one Task/Run.

    Every ref must be structurally valid and, when it is an ``evidence:`` ref,
    must resolve under the **owning Task's** evidence root and the **owning
    Run** only.  A ref that names another Task/Run is rejected (no cross-Task
    leakage).  When ``known_subtask_refs`` is supplied, an upstream ref whose
    producer Subtask is not part of this Run is rejected too.

    The digest is verified for evidence refs (via the resolver).  For upstream
    refs the digest is carried through for the caller's own content check; this
    function does not read workspace files, so it cannot be tricked into reading
    an unauthorized path.
    """

    parsed: list[ArtifactRef] = []
    for ref in refs:
        artifact = parse_artifact_ref(ref)
        if artifact.kind == "evidence":
            try:
                resolve_evidence_ref(
                    artifact.raw, data_dir=data_dir, task_id=task_id, run_id=run_id
                )
            except EvidenceRefError as exc:
                raise HandoffError(str(exc)) from exc
        elif artifact.kind == "upstream":
            if (
                known_subtask_refs is not None
                and artifact.origin_ref not in known_subtask_refs
            ):
                raise HandoffError(
                    f"handoff ref {ref!r} names unknown/foreign producer "
                    f"{artifact.origin_ref!r}"
                )
        else:  # workspace-relative
            if workspace_root is None:
                raise HandoffError(
                    f"workspace artifact ref {ref!r} requires an authorized workspace root"
                )
        parsed.append(artifact)
    return tuple(parsed)


def encode_upstream_ref(subtask_ref: str, digest: str, artifact: str) -> str:
    """Re-encode an upstream handoff in the frozen ``<subtask>@<hash>:<artifact>`` form."""

    if not _HEX64.match(digest):
        raise HandoffError(f"digest must be a sha256 hex: {digest!r}")
    if artifact.startswith("/") or ".." in artifact.split("/"):
        raise HandoffError(f"unsafe artifact path: {artifact!r}")
    return f"{subtask_ref}@{digest.lower()}:{artifact}"


__all__ = [
    "ArtifactRef",
    "HandoffError",
    "encode_upstream_ref",
    "parse_artifact_ref",
    "validate_handoff_refs",
]
