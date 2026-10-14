"""Canonical evidence artifact references (LG-010 rework; docs/08 §6.2/§6.3).

The executor's ``ArtifactSink`` returns a *transient* filesystem path (for the
first-version adapter, an absolute path under its own sink directory).  That
path is produced by the trusted adapter but is **not** a safe machine-check
input: it may point anywhere the adapter can write.

This module gives recorded evidence refs a single, explicit, Task/Run-scoped
meaning.  A trusted executor artifact is imported into the Store-owned evidence
root::

    <data_dir>/tasks/<task_id>/artifacts/<run_id>/<name>

and recorded as a self-describing reference::

    evidence:<run_id>/<name>@sha256:<hex>

Machine checks resolve only this scheme, only under the owning Task's evidence
root, only for the owning Run, and only when the content digest matches.  Raw
absolute paths are never resolved by checks, so a stray/untrusted ref cannot
make a check read an arbitrary file, and an imported artifact cannot be silently
swapped after it was recorded.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

EVIDENCE_SCHEME = "evidence:"
_DIGEST_PREFIX = "@sha256:"
#: A single safe filename component: no separators, no NUL, no ``.``/``..``.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class EvidenceRefError(ValueError):
    """A malformed, unauthorized or stale evidence reference."""


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Parsed canonical evidence reference."""

    run_id: str
    name: str
    digest: str | None
    raw: str


def evidence_root(data_dir: Path | str, task_id: str) -> Path:
    """The Store-owned evidence root for one Task."""

    return Path(data_dir) / "tasks" / task_id / "artifacts"


def canonical_evidence_ref(run_id: str, name: str, digest: str | None) -> str:
    """Build the canonical ``evidence:<run_id>/<name>@sha256:<hex>`` reference."""

    base = f"{EVIDENCE_SCHEME}{run_id}/{name}"
    return f"{base}{_DIGEST_PREFIX}{digest}" if digest else base


def parse_evidence_ref(ref: str) -> EvidenceRef | None:
    """Parse a canonical evidence ref; ``None`` when it is not one.

    Raises :class:`EvidenceRefError` when the ref uses the scheme but is
    malformed (missing run/name, unsafe name, empty digest).
    """

    if not isinstance(ref, str) or not ref.startswith(EVIDENCE_SCHEME):
        return None
    body = ref[len(EVIDENCE_SCHEME) :]
    digest: str | None = None
    if _DIGEST_PREFIX in body:
        body, _, digest = body.partition(_DIGEST_PREFIX)
        digest = digest or None
        if digest is None or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise EvidenceRefError(f"evidence ref {ref!r} has an invalid digest")
        digest = digest.lower()
    run_id, sep, name = body.partition("/")
    if not sep or not run_id or not name:
        raise EvidenceRefError(f"malformed evidence ref {ref!r}")
    if not _SAFE_NAME.match(name) or name in {".", ".."}:
        raise EvidenceRefError(f"evidence ref {ref!r} has an unsafe artifact name")
    return EvidenceRef(run_id=run_id, name=name, digest=digest, raw=ref)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_evidence_ref(
    ref: str,
    *,
    data_dir: Path | str | None,
    task_id: str,
    run_id: str,
) -> Path:
    """Resolve a canonical evidence ref under the owning Task's evidence root.

    Enforces Task ownership (root), Run ownership (``run_id`` component),
    path/symlink containment and, when recorded, the content digest.  Raises
    :class:`EvidenceRefError` on any violation.
    """

    parsed = parse_evidence_ref(ref)
    if parsed is None:
        raise EvidenceRefError(f"not a canonical evidence ref: {ref!r}")
    if data_dir is None:
        raise EvidenceRefError("evidence refs require a store with a data directory")
    if parsed.run_id != run_id:
        raise EvidenceRefError(
            f"evidence ref {ref!r} belongs to run {parsed.run_id!r}, not {run_id!r}"
        )
    root = evidence_root(data_dir, task_id)
    root_real = Path(os.path.realpath(str(root)))
    candidate = root / parsed.run_id / parsed.name
    real = Path(os.path.realpath(str(candidate)))
    if real != root_real and root_real not in real.parents:
        raise EvidenceRefError(f"evidence ref {ref!r} escapes the task evidence root")
    if not real.is_file():
        raise EvidenceRefError(f"evidence ref {ref!r} has no readable file")
    if parsed.digest is not None and _sha256_file(real) != parsed.digest:
        raise EvidenceRefError(f"evidence ref {ref!r} digest mismatch")
    return real


def import_evidence(
    data_dir: Path | str,
    task_id: str,
    run_id: str,
    source: Path | str,
    *,
    name: str | None = None,
) -> str:
    """Import a trusted executor artifact and return its canonical reference.

    The bytes are copied atomically into the Task/Run evidence root and hashed
    so later readers can detect a post-hoc change.  The source must be an
    existing regular file; a non-file (or missing) source is an error, never a
    silent skip.
    """

    src = Path(source)
    if not src.is_file():
        raise EvidenceRefError(f"executor artifact {str(source)!r} is not a readable file")
    dest_name = name or src.name
    if not dest_name or not _SAFE_NAME.match(dest_name) or dest_name in {".", ".."}:
        raise EvidenceRefError(f"executor artifact name {dest_name!r} is unsafe")
    dest_dir = evidence_root(data_dir, task_id) / run_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    handle_fd, temp_path = tempfile.mkstemp(dir=str(dest_dir), prefix=".evidence-", suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, dest_dir / dest_name)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return canonical_evidence_ref(run_id, dest_name, digest)


__all__ = [
    "EVIDENCE_SCHEME",
    "EvidenceRef",
    "EvidenceRefError",
    "canonical_evidence_ref",
    "evidence_root",
    "import_evidence",
    "parse_evidence_ref",
    "resolve_evidence_ref",
]
