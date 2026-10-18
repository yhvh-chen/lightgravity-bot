"""Rebuildable, model-versioned vector cache (LG-037).

This module implements the LG-033/docs-08 §6.6 vector rules as a **派生 cache**:

* every cached vector is tagged with the **model id**, **dimension**, a
  **content/fragment hash** (over the exact input bytes/text) and the **cache
  version**.  Those tags are the缓存 metadata, never business truth;
* a **model switch invalidates the whole cache** — cached vectors recorded under
  a different model id or dimension are never mixed with new ones.  Per-source
  indexing fails closed and leaves the file intact; an explicit full rebuild
  from the file source of truth replaces it;
* the cache is **deletable and rebuildable**: deleting the file and rebuilding
  reproduces the same entries;
* it stores **no permission/attribution/control state**: authorization and scope
  always come from ``SOURCE.md``; the query layer re-verifies every hit回源.

Media vectors are stored as vectors (*never* as fabricated text).  ``kind``
records whether the input was text/image/audio so a media hit stays distinguishable
from a text/OCR/ASR hit.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ...store.locking import LockManager

#: Cache schema version: bump to invalidate an incompatible on-disk cache.
VECTOR_CACHE_VERSION = 1

#: Default nearest-neighbour result count when the caller does not page.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

#: Vector input kinds.  Media is kept media: an image/audio vector is never
#: relabeled as text (docs/09 §7).
VECTOR_KINDS = ("text", "image", "audio")


class VectorCacheCorruptError(RuntimeError):
    """The cache exists but cannot be used; callers report ``index_unavailable``."""


class VectorModelMismatchError(RuntimeError):
    """A cached entry was recorded by another model/dim; a rebuild is required."""


@dataclass(frozen=True, slots=True)
class VectorEntry:
    """One cached vector tied to a concrete source version + input fragment."""

    source_id: str
    source_version: int
    content_hash: str | None
    basis: str
    kind: str
    model: str
    dim: int
    cache_version: int
    fragment_hash: str
    vector: tuple[float, ...]
    title: str = ""
    locators: tuple[dict[str, Any], ...] = ()
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "content_hash": self.content_hash,
            "basis": self.basis,
            "kind": self.kind,
            "model": self.model,
            "dim": self.dim,
            "cache_version": self.cache_version,
            "fragment_hash": self.fragment_hash,
            "vector": list(self.vector),
            "title": self.title,
            "locators": list(self.locators),
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "VectorEntry":
        data = value if isinstance(value, dict) else {}
        vector_raw = data.get("vector")
        if not isinstance(vector_raw, list):
            raise VectorCacheCorruptError("vector entry had no vector list")
        vector: list[float] = []
        for item in vector_raw:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise VectorCacheCorruptError("vector entry contained a non-numeric value")
            number = float(item)
            if not math.isfinite(number):
                raise VectorCacheCorruptError("vector entry contained a non-finite value")
            vector.append(number)
        locators = data.get("locators")
        return cls(
            source_id=str(data.get("source_id") or ""),
            source_version=_int_of(data.get("source_version"), default=1),
            content_hash=data.get("content_hash") if isinstance(data.get("content_hash"), str) else None,
            basis=str(data.get("basis") or "machine"),
            kind=str(data.get("kind") or "text"),
            model=str(data.get("model") or ""),
            dim=_int_of(data.get("dim"), default=len(vector)),
            cache_version=_int_of(data.get("cache_version"), default=0),
            fragment_hash=str(data.get("fragment_hash") or ""),
            vector=tuple(vector),
            title=str(data.get("title") or ""),
            locators=tuple(locators) if isinstance(locators, list) else (),
            text=str(data.get("text") or ""),
        )


@dataclass(slots=True)
class VectorBuildReport:
    """Outcome of a (re)build pass over a set of vectors."""

    indexed: list[str] = field(default_factory=list)
    not_indexed: list[str] = field(default_factory=list)
    documents: int = 0
    model: str = ""
    dim: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "indexed": list(self.indexed),
            "not_indexed": list(self.not_indexed),
            "documents": self.documents,
            "model": self.model,
            "dim": self.dim,
        }


def fragment_hash(text: str | bytes) -> str:
    """SHA-256 over the exact input fragment (text bytes or raw media bytes)."""

    data = text if isinstance(text, bytes) else text.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class VectorIndex:
    """A flat, stdlib-only JSONL vector cache (no external vector service).

    ``vectors.jsonl`` holds one :class:`VectorEntry` per line plus a header line
    recording the cache version and the model/dim it was built for.  A different
    model/dim header makes the cache *not* reusable, forcing a rebuild instead of
    silently comparing incompatible vectors.
    """

    def __init__(self, cache_dir: Path | str, *, backend_fingerprint: str | None = None) -> None:
        self._backend_fingerprint = backend_fingerprint
        self._cache_dir = Path(cache_dir)
        self._path = self._cache_dir / "vectors.jsonl"
        # Serialize read-modify-write/rebuild passes across threads and
        # processes.  Queries stay lock-free and see a complete file because
        # writes are committed with ``os.replace``.
        self._write_locks = LockManager(self._cache_dir)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.is_file()

    def delete(self) -> None:
        """Delete the whole cache; a rebuild from files restores it."""

        with self._write_locks.acquire("vectors-write"):
            self._delete_unlocked()

    def _delete_unlocked(self) -> None:
        if self._path.exists():
            try:
                self._path.unlink()
            except OSError:
                pass
        # Clean any leftover temp file from an interrupted write.
        for candidate in self._cache_dir.glob("vectors.jsonl.tmp*"):
            try:
                candidate.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------ io
    def _read_raw(self) -> tuple[dict[str, Any], list[VectorEntry]]:
        if not self._path.is_file():
            return {}, []
        try:
            text = self._path.read_text("utf-8")
        except OSError as exc:
            raise VectorCacheCorruptError(str(exc)) from exc
        header: dict[str, Any] = {}
        entries: list[VectorEntry] = []
        for index, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise VectorCacheCorruptError(f"bad line {index + 1}: {exc}") from None
            if index == 0 and isinstance(record, dict) and record.get("record") == "header":
                header = record
                continue
            entries.append(VectorEntry.from_dict(record))
        return header, entries

    def _write_raw(self, header: dict[str, Any], entries: Iterable[VectorEntry]) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(header, ensure_ascii=False, sort_keys=True)]
        for entry in entries:
            lines.append(json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True))
        payload = "\n".join(lines) + "\n"
        import os
        import tempfile

        fd, tmp_name = tempfile.mkstemp(dir=str(self._cache_dir), prefix="vectors.jsonl.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self._path)
        except OSError as exc:  # pragma: no cover - defensive
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise VectorCacheCorruptError(str(exc)) from exc

    # -------------------------------------------------------------- metadata
    def header(self) -> dict[str, Any]:
        header, _ = self._read_raw()
        return header

    def readable(self) -> bool:
        if not self._path.is_file():
            return False
        try:
            self._read_raw()
            return True
        except VectorCacheCorruptError:
            return False

    def is_compatible(self, *, model: str, dim: int | None = None) -> bool:
        """Whether the cache was built for *model* (and, if given, *dim*)."""

        header = self.header()
        if not header:
            return False
        if header.get("model") != model:
            return False
        if self._backend_fingerprint is not None and header.get("backend_fingerprint") != self._backend_fingerprint:
            return False
        if header.get("cache_version") != VECTOR_CACHE_VERSION:
            return False
        if dim is not None and header.get("dim") != dim:
            return False
        return True

    # ---------------------------------------------------------------- writes
    def replace_all(self, entries: Iterable[VectorEntry], *, model: str, dim: int) -> VectorBuildReport:
        """Rebuild the cache from scratch for one model/dim (model switch safe)."""

        with self._write_locks.acquire("vectors-write"):
            return self._replace_all_unlocked(entries, model=model, dim=dim)

    def _replace_all_unlocked(
        self, entries: Iterable[VectorEntry], *, model: str, dim: int
    ) -> VectorBuildReport:
        report = VectorBuildReport(model=model, dim=dim)
        collected: list[VectorEntry] = []
        for entry in entries:
            if entry.model != model or entry.dim != dim:
                raise VectorModelMismatchError(
                    f"entry for {entry.source_id!r} is model={entry.model!r} dim={entry.dim}, "
                    f"expected model={model!r} dim={dim}"
                )
            collected.append(entry)
            report.indexed.append(entry.source_id)
            report.documents += 1
        header = {
            "record": "header",
            "cache_version": VECTOR_CACHE_VERSION,
            "model": model,
            "dim": dim,
        }
        if self._backend_fingerprint is not None:
            header["backend_fingerprint"] = self._backend_fingerprint
        self._write_raw(header, collected)
        return report

    def upsert_entries(
        self, entries: Iterable[VectorEntry], *, model: str, dim: int
    ) -> VectorBuildReport:
        """Replace only the listed sources' entries under one cache lock.

        Per-source indexing must never drop other sources.  This keeps the
        read-modify-write atomic with respect to concurrent index/rebuild
        writers while leaving the model/dimension header untouched.
        """

        new_entries = list(entries)
        with self._write_locks.acquire("vectors-write"):
            _, existing = self._read_raw()  # fail closed before touching the file
            if self.exists() and not self.is_compatible(model=model, dim=dim):
                raise VectorModelMismatchError("cache provenance/model/dimension requires a full rebuild")
            replaced = {entry.source_id for entry in new_entries}
            kept = [entry for entry in existing if entry.source_id not in replaced]
            kept.extend(new_entries)
            return self._replace_all_unlocked(kept, model=model, dim=dim)

    def delete_and_rebuild_marker(self) -> None:
        """Remove only the cache file so a caller can rebuild from files."""

        self.delete()

    # ----------------------------------------------------------------- reads
    def all_entries(self) -> list[VectorEntry]:
        _, entries = self._read_raw()
        return entries

    def entries_for(self, source_id: str) -> list[VectorEntry]:
        return [e for e in self.all_entries() if e.source_id == source_id]

    def remove(self, source_id: str) -> None:
        with self._write_locks.acquire("vectors-write"):
            header, entries = self._read_raw()
            if not header and not entries:
                return
            kept = [e for e in entries if e.source_id != source_id]
            self._write_raw(header, kept)

    def search(
        self, query_vector: Iterable[float], *, model: str, limit: int = DEFAULT_LIMIT
    ) -> list[dict[str, Any]]:
        """Return nearest candidates (pre-authorization) for *model*.

        Mixing models is refused: a cache header for another model yields an
        empty candidate list so the caller rebuilds rather than comparing
        incompatible vectors.  Authorization and回源 re-verification happen in
        the service/query layer, never here.
        """

        header, entries = self._read_raw()
        if header.get("model") != model or header.get("cache_version") != VECTOR_CACHE_VERSION:
            return []
        if self._backend_fingerprint is not None and header.get("backend_fingerprint") != self._backend_fingerprint:
            return []
        query = tuple(float(x) for x in query_vector)
        if not query:
            return []
        results: list[dict[str, Any]] = []
        for entry in entries:
            if entry.dim != len(query):
                # Never compare vectors of different dimensions.
                continue
            score = _cosine(query, entry.vector)
            results.append(
                {
                    "source_id": entry.source_id,
                    "source_version": entry.source_version,
                    "content_hash": entry.content_hash,
                    "basis": entry.basis,
                    "kind": entry.kind,
                    "model": entry.model,
                    "dim": entry.dim,
                    "fragment_hash": entry.fragment_hash,
                    "locators": list(entry.locators),
                    "title": entry.title,
                    "text": entry.text,
                    "score": score,
                }
            )
        results.sort(key=lambda item: (-float(item["score"]), str(item["source_id"])))
        return results[: max(min(limit, MAX_LIMIT), 1)]

    def stats(self) -> dict[str, Any]:
        header, entries = self._read_raw()
        return {
            "documents": len(entries),
            "cache_version": header.get("cache_version"),
            "model": header.get("model"),
            "dim": header.get("dim"),
        }


def _cosine(left: Iterable[float], right: Iterable[float]) -> float:
    a = tuple(float(x) for x in left)
    b = tuple(float(x) for x in right)
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _int_of(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "VECTOR_CACHE_VERSION",
    "VECTOR_KINDS",
    "VectorBuildReport",
    "VectorCacheCorruptError",
    "VectorEntry",
    "VectorIndex",
    "VectorModelMismatchError",
    "fragment_hash",
]
