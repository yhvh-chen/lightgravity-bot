"""Rebuildable lexical index over the file source of truth (LG-036).

This module implements the docs/08 §6.6 / docs/09 §5/§7 lexical-index rules and
docs/contracts/LG-033-preparation.md §8.1:

* the index is a **derived, rebuildable cache** built from the file source of
  truth (source metadata + human formal content preferred, trusted machine
  derivative next);
* it stores **no独有的 permission / attribution / control state** — scope and
  authorization always come from the ``SOURCE.md`` frontmatter, and every hit is
  re-verified against the file SoT before it is returned;
* it can be **deleted and rebuilt** to the same content (stable ``lexical_hash``)
  and the same query results;
* it uses the standard library ``sqlite3`` FTS5 module as a **local, in-process
  cache file** — no separate database service (docs/09 §7).

Only text that a trusted path produced is indexed.  A source with no formal
version and no trusted machine derivative is honestly ``not_indexed``: we never
fabricate body text, and low-quality/unverified OCR output is never promoted to
a Chinese/image retrieval quality claim (docs/09 §9, docs/08 §6.6).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from ...store.locking import LockManager

#: Cache schema version: bump to invalidate an incompatible on-disk cache.
CACHE_SCHEMA_VERSION = 1

#: Default number of hits returned when the caller does not page.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

#: Longest excerpt returned for one hit (characters, unicode-safe).
SNIPPET_CHARS = 320


class IndexCorruptError(RuntimeError):
    """The cache file exists but cannot be used; callers report ``index_unavailable``."""


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    """One indexable body of text tied to a concrete source version.

    ``text`` is the *trusted* body text (formal version when present, otherwise
    a trusted machine derivative).  ``basis`` records which layer produced it so
    a hit can be traced and so callers can distinguish human-edited content from
    machine transcription.  ``locators`` carry page/line anchors for回源.
    """

    source_id: str
    source_version: int
    content_hash: str | None
    basis: str  # "formal" | "machine"
    title: str
    text: str
    media_type: str | None = None
    locators: tuple[dict[str, Any], ...] = ()

    def lexical_hash(self) -> str:
        """Stable digest over the indexed material (not over the query)."""

        payload = json.dumps(
            {
                "cache_schema": CACHE_SCHEMA_VERSION,
                "source_id": self.source_id,
                "source_version": self.source_version,
                "content_hash": self.content_hash,
                "basis": self.basis,
                "title": self.title,
                "text": self.text,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class IndexBuildReport:
    """Outcome of a (re)build pass over a set of documents."""

    indexed: list[str] = field(default_factory=list)
    not_indexed: list[str] = field(default_factory=list)
    documents: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "indexed": list(self.indexed),
            "not_indexed": list(self.not_indexed),
            "documents": self.documents,
        }


def tokenize(text: str) -> list[str]:
    """Split text into FTS tokens the **same way FTS5 ``unicode61`` will**.

    We index a pre-tokenized, space-joined copy of the text, and FTS5 then
    re-tokenizes it with ``unicode61``.  For phrase matching to work exactly, our
    tokenizer must agree with ``unicode61``: a token is a run of alphanumerics or
    ``_`` (so ``-``, ``.``, ``/``, ``,`` are separators).  CJK ideographs are
    emitted one per token, which lets a CJK phrase become an ordered token
    sequence that an FTS5 phrase query matches precisely.

    Dates (``2026-10-16``), amounts (``1,234.56``) and identifiers
    (``HT-2024-001``) therefore index as adjacent token runs and remain findable
    as exact phrases/spans.  ``test_tokenize_matches_fts5_unicode61`` pins this
    agreement against the real FTS5 tokenizer.
    """

    tokens: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            tokens.append("".join(buf).lower())
            buf.clear()

    for ch in text:
        if _is_cjk(ch):
            flush()
            tokens.append(ch)
        elif _is_word(ch):
            buf.append(ch)
        else:
            flush()
    flush()
    return tokens


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x3040 <= code <= 0x30FF
    )


def _is_word(ch: str) -> bool:
    # Match FTS5 ``unicode61`` exactly: it treats ``_``/``-``/``.``/``/`` and all
    # non-alphanumerics as separators, so only alphanumerics are word chars.
    return ch.isalnum()


def _tokenized_text(text: str) -> str:
    return " ".join(tokenize(text))


class LexicalIndex:
    """A stdlib-sqlite FTS5 cache over the file source of truth."""

    def __init__(self, cache_dir: Path | str) -> None:
        self._cache_dir = Path(cache_dir)
        self._db_path = self._cache_dir / "lexical.sqlite3"
        self._connection_locks = LockManager(self._cache_dir)

    @property
    def db_path(self) -> Path:
        return self._db_path

    # ------------------------------------------------------------------ paths
    def exists(self) -> bool:
        return self._db_path.is_file()

    def delete(self) -> None:
        """Delete the whole cache.  Files remain the SoT; a rebuild restores it."""

        for suffix in ("", "-wal", "-shm"):
            candidate = self._db_path.with_name(self._db_path.name + suffix)
            if candidate.exists():
                try:
                    candidate.unlink()
                except OSError:
                    pass

    # --------------------------------------------------------------- connection
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # SQLite serializes transactions, but competing first connections can
        # fail immediately while switching an empty database to WAL. Serialize
        # setup across cache instances/processes, leaving transactions to SQLite.
        with self._connection_locks.acquire("lexical-initialize"):
            if self._db_path.is_file():
                with self._db_path.open("rb") as handle:
                    header = handle.read(16)
                if header and header != b"SQLite format 3\x00":
                    raise IndexCorruptError(f"not a sqlite database: {self._db_path}")
            conn = sqlite3.connect(str(self._db_path), timeout=5.0)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            except BaseException:
                conn.close()
                raise
        # sqlite3.Connection's context manager commits/rolls back, but does not
        # close. Close deterministically so late GC cannot checkpoint an old WAL
        # over a subsequently modified cache file or retain unused descriptors.
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5("
                "source_id UNINDEXED, source_version UNINDEXED, "
                "content_hash UNINDEXED, basis UNINDEXED, title, "
                "body, tokens, locators UNINDEXED, lexical_hash UNINDEXED, "
                "tokenize='unicode61')"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO cache_meta(key, value) VALUES ('schema_version', ?)",
                (str(CACHE_SCHEMA_VERSION),),
            )
        except sqlite3.DatabaseError as exc:  # pragma: no cover - defensive
            raise IndexCorruptError(str(exc)) from exc

    def readable(self) -> bool:
        """Return whether the cache can currently be opened and queried.

        A missing WAL sidecar is fine, but a file whose SQLite header is not a
        valid database (or whose schema is wrong) is reported as unreadable so
        callers can return an honest ``index_unavailable`` instead of an empty
        success.
        """

        if not self._db_path.is_file():
            return False
        try:
            # Read the 16-byte header directly first: this catches an overwritten
            # file even when a stale WAL would otherwise postpone the error.
            with self._db_path.open("rb") as handle:
                header = handle.read(16)
            if header != b"SQLite format 3\x00":
                return False
            with self._connect() as conn:
                conn.execute("SELECT count(*) FROM docs").fetchone()
            return True
        except (sqlite3.DatabaseError, OSError, IndexCorruptError):
            return False

    # ------------------------------------------------------------------- writes
    def upsert(self, doc: IndexedDocument) -> str:
        """Index/replace one document; return its stable ``lexical_hash``."""

        lexical_hash = doc.lexical_hash()
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute("DELETE FROM docs WHERE source_id = ?", (doc.source_id,))
                conn.execute(
                    "INSERT INTO docs("
                    "source_id, source_version, content_hash, basis, title, body, "
                    "tokens, locators, lexical_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        doc.source_id,
                        doc.source_version,
                        doc.content_hash,
                        doc.basis,
                        doc.title,
                        doc.text,
                        _tokenized_text(f"{doc.title}\n{doc.text}"),
                        json.dumps(list(doc.locators), ensure_ascii=False),
                        lexical_hash,
                    ),
                )
                conn.commit()
        except sqlite3.DatabaseError as exc:
            raise IndexCorruptError(str(exc)) from exc
        return lexical_hash

    def remove(self, source_id: str) -> None:
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute("DELETE FROM docs WHERE source_id = ?", (source_id,))
                conn.commit()
        except sqlite3.DatabaseError as exc:
            raise IndexCorruptError(str(exc)) from exc

    def clear(self) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute("DELETE FROM docs")
            conn.commit()

    def replace_all(self, docs: Iterable[IndexedDocument]) -> IndexBuildReport:
        """Rebuild the index from scratch (used by delete-and-rebuild)."""

        report = IndexBuildReport()
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute("DELETE FROM docs")
            for doc in docs:
                lexical_hash = doc.lexical_hash()
                conn.execute(
                    "INSERT INTO docs("
                    "source_id, source_version, content_hash, basis, title, body, "
                    "tokens, locators, lexical_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        doc.source_id,
                        doc.source_version,
                        doc.content_hash,
                        doc.basis,
                        doc.title,
                        doc.text,
                        _tokenized_text(f"{doc.title}\n{doc.text}"),
                        json.dumps(list(doc.locators), ensure_ascii=False),
                        lexical_hash,
                    ),
                )
                report.indexed.append(doc.source_id)
                report.documents += 1
            conn.commit()
        return report

    # -------------------------------------------------------------------- reads
    def entry(self, source_id: str) -> dict[str, Any] | None:
        """Return the cached index entry for one source, or ``None``."""

        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT source_id, source_version, content_hash, basis, lexical_hash, "
                    "locators FROM docs WHERE source_id = ?",
                    (source_id,),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise IndexCorruptError(str(exc)) from exc
        if row is None:
            return None
        return self._row_to_entry(row)

    def all_entries(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT source_id, source_version, content_hash, basis, lexical_hash, "
                "locators FROM docs ORDER BY source_id"
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    @staticmethod
    def _row_to_entry(row: tuple[Any, ...]) -> dict[str, Any]:
        locators_raw = row[5]
        try:
            locators = json.loads(locators_raw) if locators_raw else []
        except (TypeError, json.JSONDecodeError):
            locators = []
        return {
            "source_id": row[0],
            "source_version": row[1],
            "content_hash": row[2],
            "basis": row[3],
            "lexical_hash": row[4],
            "locators": locators if isinstance(locators, list) else [],
        }

    def search(
        self, match_expr: str, *, limit: int = DEFAULT_LIMIT
    ) -> list[dict[str, Any]]:
        """Run an FTS ``MATCH`` expression and return candidate rows (pre-auth).

        ``match_expr`` is always built internally from parsed tokens (never a
        raw user string), so it cannot inject FTS operators.  Authorization and
        source-of-truth re-verification happen in the query layer, not here.
        """

        if not match_expr.strip():
            return []
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                rows = conn.execute(
                    "SELECT source_id, source_version, content_hash, basis, lexical_hash, "
                    "locators, title, body FROM docs WHERE docs MATCH ? "
                    "ORDER BY bm25(docs, 0.0, 0.0, 0.0, 0.0, 2.0, 1.0, 0.0), source_id "
                    "LIMIT ?",
                    (match_expr, max(min(limit, MAX_LIMIT), 1)),
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise IndexCorruptError(str(exc)) from exc
        results: list[dict[str, Any]] = []
        for row in rows:
            entry = self._row_to_entry(row[:6])
            entry["title"] = row[6]
            entry["body"] = row[7]
            results.append(entry)
        return results

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            self._ensure_schema(conn)
            count = conn.execute("SELECT count(*) FROM docs").fetchone()[0]
            row = conn.execute("SELECT value FROM cache_meta WHERE key='schema_version'").fetchone()
        return {"documents": int(count), "cache_schema_version": row[0] if row else None}


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "SNIPPET_CHARS",
    "IndexBuildReport",
    "IndexCorruptError",
    "IndexedDocument",
    "LexicalIndex",
    "tokenize",
]
