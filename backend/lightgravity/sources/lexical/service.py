"""Lexical search service: build/rebuild the cache and serve verified hits.

This is the LG-036 facade that the API layer calls.  It owns:

* deciding **which** trusted text is indexable per source (human formal version
  preferred; trusted machine derivative next; otherwise honest ``not_indexed``);
* writing the ``source.index`` block (``lexical``/``lexical_hash``) through the
  existing ``SourceStore.update_source`` — that frontmatter + the source files
  remain the source of truth, the SQLite cache is a rebuildable派生;
* rebuilding the whole cache from files and reproducing stable hashes;
* running a query through the two-phase authorized-candidate → 回源核对 path and
  reporting honest ``index_unavailable``/``not_indexed``/``source_stale`` states.

It never stores permission or attribution in the cache: authorization always
re-reads ``SOURCE.md``.  It never writes Task/Run/Member control state and never
executes content.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.store.errors import EntityNotFound, RevisionConflict

from ..content import ContentStore
from ..models import SourceRecord
from ..store import SourceStore
from .index import (
    DEFAULT_LIMIT,
    SNIPPET_CHARS,
    IndexBuildReport,
    IndexCorruptError,
    IndexedDocument,
    LexicalIndex,
)
from .query import (
    ScopeFilter,
    SearchOutcome,
    authorize_and_verify,
    clamp_limit,
    parse_query,
)

#: Source statuses whose hits must be treated as invalidated (docs/08 §6.6).
_INACTIVE_STATUSES = ("archived",)
#: Trusted machine-extraction statuses (a ``failed`` extraction is never body).
_TRUSTED_MACHINE_STATUSES = ("succeeded", "partial")


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """One search request (query text + caller authorization scope)."""

    query: str
    task_ref: str | None = None
    project_ref: str | None = None
    inbox_ref: str | None = None
    include_global: bool = False
    limit: int | None = None
    rebuild_if_missing: bool = False


class LexicalSearchService:
    """Build the lexical cache from files and answer re-verified queries."""

    def __init__(
        self,
        store: SourceStore,
        *,
        cache_dir: Path | str | None = None,
        task_store: Any | None = None,
        events: Any | None = None,
    ) -> None:
        self._store = store
        self._cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else Path(store.sources_dir().parent) / "sources-index"
        )
        self._index = LexicalIndex(self._cache_dir / "lexical")
        self._tasks = task_store
        self._events = events

    @property
    def index(self) -> LexicalIndex:
        return self._index

    # --------------------------------------------------------------- building
    def _content_store(self, source_id: str) -> ContentStore:
        return ContentStore(source_root=self._store.source_dir(source_id))

    def document_for(self, record: SourceRecord) -> tuple[IndexedDocument | None, str | None]:
        """Return the indexable document for a source, or ``(None, reason)``.

        Formal content wins over the machine derivative.  A source with neither
        is honestly not indexed; a source whose only body is untrusted/absent is
        never fabricated.
        """

        if record.status in _INACTIVE_STATUSES:
            return None, "archived"
        content = self._content_store(record.source_id)
        formal = content.read_formal()
        if formal is not None and formal.strip():
            return (
                IndexedDocument(
                    source_id=record.source_id,
                    source_version=record.source_version,
                    content_hash=record.content_digest,
                    basis="formal",
                    title=record.title,
                    text=formal,
                    media_type="text/markdown; charset=utf-8",
                    locators=({"layer": "formal", "path": content.formal_relative_path()},),
                ),
                None,
            )
        machine = self._read_trusted_machine(record, content)
        if machine is not None:
            text, locators = machine
            return (
                IndexedDocument(
                    source_id=record.source_id,
                    source_version=record.source_version,
                    content_hash=record.content_digest,
                    basis="machine",
                    title=record.title,
                    text=text,
                    media_type="text/markdown; charset=utf-8",
                    locators=locators,
                ),
                None,
            )
        return None, "no_trusted_body"

    def _read_trusted_machine(
        self, record: SourceRecord, content: ContentStore
    ) -> tuple[str, tuple[dict[str, Any], ...]] | None:
        pages = content.read_pages(record.source_version)
        if not isinstance(pages, dict):
            return None
        status = str(pages.get("status") or "")
        if status not in _TRUSTED_MACHINE_STATUSES:
            return None
        markdown = content.read_machine_markdown(record.source_version)
        if markdown is None or not markdown.strip():
            return None
        locators: list[dict[str, Any]] = []
        for page in pages.get("pages") or []:
            if not isinstance(page, dict):
                continue
            if str(page.get("status") or "") not in _TRUSTED_MACHINE_STATUSES:
                continue
            locators.append(
                {
                    "layer": "machine",
                    "page": page.get("page"),
                    "input_sha256": page.get("input_sha256"),
                    "model": page.get("model"),
                }
            )
        return markdown, tuple(locators)

    def index_source(self, source_id: str) -> dict[str, Any]:
        """Index one source; write ``index.lexical``/``lexical_hash`` honestly."""

        record = self._store.read_source(source_id)
        doc, reason = self.document_for(record)
        if doc is None:
            self._mark_not_indexed(record, reason or "no_trusted_body")
            return {
                "source_id": source_id,
                "indexed": False,
                "reason": reason or "no_trusted_body",
                "lexical": "not_indexed",
            }
        try:
            lexical_hash = self._index.upsert(doc)
        except IndexCorruptError:
            self._mark_failed(record)
            raise AppError(
                ErrorCode.INDEX_UNAVAILABLE,
                "lexical index cache is corrupt; rebuild required",
                details={"source_id": source_id},
            ) from None
        self._write_index_state(
            record,
            lexical="indexed",
            lexical_hash=lexical_hash,
        )
        self._emit("source.indexed", source_id, {"source_version": record.source_version})
        return {
            "source_id": source_id,
            "indexed": True,
            "basis": doc.basis,
            "lexical_hash": lexical_hash,
            "lexical": "indexed",
        }

    def rebuild(self, *, source_ids: list[str] | None = None) -> dict[str, Any]:
        """Delete and rebuild the cache from files; report per-source outcomes."""

        records = self._store.list_sources()
        if source_ids is not None:
            wanted = set(source_ids)
            records = [r for r in records if r.source_id in wanted]
        report = IndexBuildReport()
        docs: list[IndexedDocument] = []
        states: list[dict[str, Any]] = []
        for record in records:
            doc, reason = self.document_for(record)
            if doc is None:
                report.not_indexed.append(record.source_id)
                states.append(
                    {"source_id": record.source_id, "indexed": False, "reason": reason or "no_trusted_body"}
                )
                self._mark_not_indexed(record, reason or "no_trusted_body")
                continue
            docs.append(doc)
        self._index.delete()
        try:
            build = self._index.replace_all(docs)
        except IndexCorruptError:
            raise AppError(
                ErrorCode.INDEX_UNAVAILABLE,
                "lexical index cache could not be rebuilt",
                details={"cache": str(self._index.db_path)},
            ) from None
        report.indexed.extend(build.indexed)
        report.documents = build.documents
        for record in records:
            entry = self._index.entry(record.source_id)
            if entry is not None:
                states.append(
                    {"source_id": record.source_id, "indexed": True, "lexical_hash": entry["lexical_hash"]}
                )
        return {
            "rebuilt": True,
            "indexed": report.indexed,
            "not_indexed": report.not_indexed,
            "documents": report.documents,
            "states": states,
        }

    def remove(self, source_id: str, *, reason: str = "deleted") -> None:
        """Drop one source from the cache and invalidate the record."""

        try:
            self._index.remove(source_id)
        except IndexCorruptError:
            pass
        try:
            record = self._store.read_source(source_id)
        except EntityNotFound:
            return
        self._write_index_state(record, lexical="not_indexed", lexical_hash=None)
        self._emit("source.invalidated", source_id, {"reason": reason})

    # ------------------------------------------------------------------ search
    def search(self, request: SearchRequest) -> dict[str, Any]:
        """Run the two-phase authorized-candidate → 回源核对 search."""

        parsed = parse_query(request.query)
        scope_filter = ScopeFilter(
            task_ref=request.task_ref,
            project_ref=request.project_ref,
            inbox_ref=request.inbox_ref,
            include_global=request.include_global,
        )
        limit = clamp_limit(request.limit)

        if parsed.is_empty:
            return {
                "query": request.query,
                "kind": list(parsed.kinds),
                "hits": [],
                "stale": [],
                "skipped": [],
                "index_status": "ok",
                "authorized_scope": scope_filter.__dict__ if hasattr(scope_filter, "__dict__") else {},
            }

        if not self._index.exists():
            if request.rebuild_if_missing:
                self.rebuild()
            else:
                # A missing cache is reported honestly; the caller may rebuild.
                return self._unavailable(request, parsed, scope_filter, "cache_missing")

        if not self._index.readable():
            return self._unavailable(request, parsed, scope_filter, "cache_corrupt")

        try:
            candidates = self._index.search(parsed.match_expr, limit=limit)
        except IndexCorruptError:
            return self._unavailable(request, parsed, scope_filter, "cache_corrupt")

        outcome = authorize_and_verify(
            candidates,
            scope_filter=scope_filter,
            read_source=self._store.read_source,
            verify_source=self._verify_source,
            query_tokens=parsed.tokens,
        )
        return {
            "query": request.query,
            "kind": list(parsed.kinds),
            "hits": [h.to_dict() for h in outcome.hits],
            "stale": outcome.stale,
            "skipped": outcome.skipped,
            "index_status": "ok",
            "authorized_scope": {
                "task_ref": scope_filter.task_ref,
                "project_ref": scope_filter.project_ref,
                "inbox_ref": scope_filter.inbox_ref,
                "include_global": scope_filter.include_global,
            },
        }

    def _verify_source(self, record: SourceRecord) -> tuple[bool, str | None]:
        """Re-verify one candidate against the current file SoT (回源核对)."""

        if record.status in _INACTIVE_STATUSES:
            return False, "source_revoked"
        original = record.entity.get("original")
        original = original if isinstance(original, dict) else {}
        rel = original.get("path")
        if isinstance(rel, str) and rel:
            name = rel.rsplit("/", 1)[-1]
            if not (self._store.original_dir(record.source_id) / name).is_file():
                return False, "original_missing"
        # The indexed body must still be present in *some* trusted layer.
        doc, reason = self.document_for(record)
        if doc is None:
            return False, reason or "no_trusted_body"
        return True, None

    def _unavailable(
        self, request: SearchRequest, parsed: Any, scope_filter: ScopeFilter, reason: str
    ) -> dict[str, Any]:
        return {
            "query": request.query,
            "kind": list(parsed.kinds),
            "hits": [],
            "stale": [],
            "skipped": [],
            "index_status": "index_unavailable",
            "index_unavailable_reason": reason,
            "authorized_scope": {
                "task_ref": scope_filter.task_ref,
                "project_ref": scope_filter.project_ref,
                "inbox_ref": scope_filter.inbox_ref,
                "include_global": scope_filter.include_global,
            },
        }

    # ------------------------------------------------------------------ helpers
    def _write_index_state(
        self, record: SourceRecord, *, lexical: str, lexical_hash: str | None
    ) -> None:
        """Merge lexical fields at the current revision (vector may write too)."""

        source_id = record.source_id
        for _ in range(3):
            try:
                current_record = self._store.read_source(source_id)
            except EntityNotFound:
                return
            current = current_record.entity.get("index")
            current = current if isinstance(current, dict) else {}
            vector = current.get("vector") if current.get("vector") in _VECTOR_STATES else "disabled"
            vector_model = current.get("vector_model")
            try:
                self._store.update_source(
                    source_id,
                    {
                        "index": {
                            "lexical": lexical,
                            "lexical_hash": lexical_hash,
                            "vector": vector,
                            "vector_model": vector_model,
                        }
                    },
                    expected_revision=current_record.revision,
                )
                return
            except RevisionConflict:
                continue
            except EntityNotFound:
                return

    def _mark_not_indexed(self, record: SourceRecord, reason: str) -> None:
        current = record.entity.get("index")
        current = current if isinstance(current, dict) else {}
        if current.get("lexical") == "not_indexed" and current.get("lexical_hash") is None:
            return
        self._write_index_state(record, lexical="not_indexed", lexical_hash=None)
        self._emit("source.invalidated", record.source_id, {"reason": reason})

    def _mark_failed(self, record: SourceRecord) -> None:
        self._write_index_state(record, lexical="failed", lexical_hash=None)

    def _emit(self, event_type: str, source_id: str, payload: dict[str, Any]) -> None:
        events = self._events
        if events is None:
            return
        try:
            events.append_event(
                source_id,
                {"type": event_type, "actor": "source-lexical-index", "payload": payload},
            )
        except AppError:
            return


_VECTOR_STATES = ("disabled", "not_indexed", "indexed", "stale", "failed")


def lexical_hash_for(text: str) -> str:
    """Stable helper used by tests/tools to fingerprint indexed material."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "DEFAULT_LIMIT",
    "SNIPPET_CHARS",
    "LexicalSearchService",
    "SearchRequest",
    "lexical_hash_for",
]
