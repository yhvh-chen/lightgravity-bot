"""Optional multimodal vector search service (LG-037).

This is the LG-037 facade over the rebuildable :class:`VectorIndex`.  It owns:

* deciding which inputs become vectors: **trusted text** (human formal version
  preferred, trusted machine derivative next) and — separately — the **original
  media** (image/audio) embedded *as media*, never fabricated into text;
* writing the ``source.index.vector`` / ``vector_model`` state through the
  existing ``SourceStore.update_source`` so the file SoT keeps authority and the
  vector cache stays a rebuildable派生;
* a **model-change guard**: when the configured model differs from the cache's
  recorded model, the cache is rebuilt rather than mixing incompatible vectors;
* an authorized-candidate → 回源核对 search that re-reads ``SOURCE.md`` for
  every hit and reports ``index_unavailable``/``not_indexed``/``source_stale``
  honestly, degrading to lexical search and original viewing when the vector
  backend is unavailable.

It never stores permission/attribution in the cache and never writes Task/Run/
Member control state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.store.errors import EntityNotFound

from ..content import ContentStore
from ..models import SourceRecord
from ..store import SourceStore
from .embedder import (
    EmbedInput,
    EmbeddingBackend,
    EmbeddingServiceError,
    EmbeddingTimeout,
    EmbeddingUnavailable,
    UnavailableEmbeddingBackend,
)
from .index import (
    DEFAULT_LIMIT,
    VECTOR_CACHE_VERSION,
    VectorCacheCorruptError,
    VectorEntry,
    VectorIndex,
    fragment_hash,
)

#: Source statuses whose hits must be treated as invalidated (docs/08 §6.6).
_INACTIVE_STATUSES = ("archived",)
#: Trusted machine-extraction statuses (a ``failed`` extraction is never body).
_TRUSTED_MACHINE_STATUSES = ("succeeded", "partial")

#: Original media types we embed directly as media (docs/09 §7).  Text/PDF and
#: unknown originals are not force-embedded; OCR/ASR have their own paths.
_IMAGE_MEDIA_PREFIX = "image/"
_AUDIO_MEDIA_PREFIX = "audio/"


@dataclass(frozen=True, slots=True)
class VectorSearchRequest:
    """One vector search request (query text + caller authorization scope)."""

    query: str
    task_ref: str | None = None
    project_ref: str | None = None
    inbox_ref: str | None = None
    include_global: bool = False
    limit: int | None = None
    rebuild_if_missing: bool = False


class VectorSearchService:
    """Build the vector cache from files and answer re-verified queries."""

    def __init__(
        self,
        store: SourceStore,
        *,
        backend: EmbeddingBackend | None = None,
        cache_dir: Path | str | None = None,
        task_store: Any | None = None,
        events: Any | None = None,
        max_media_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._store = store
        self._backend: EmbeddingBackend = backend or UnavailableEmbeddingBackend()
        self._cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else Path(store.sources_dir().parent) / "sources-index"
        )
        self._index = VectorIndex(self._cache_dir / "vectors")
        self._tasks = task_store
        self._events = events
        self._max_media_bytes = int(max_media_bytes)
        self._lexical: Any | None = None

    @property
    def index(self) -> VectorIndex:
        return self._index

    @property
    def backend(self) -> EmbeddingBackend:
        return self._backend

    @property
    def enabled(self) -> bool:
        return bool(getattr(self._backend, "configured", False))

    # --------------------------------------------------------------- building
    def _content_store(self, source_id: str) -> ContentStore:
        return ContentStore(source_root=self._store.source_dir(source_id))

    def _trusted_text(self, record: SourceRecord) -> tuple[str | None, str | None, tuple[dict[str, Any], ...]]:
        """Return ``(text, basis, locators)`` for the trusted body, if any."""

        if record.status in _INACTIVE_STATUSES:
            return None, None, ()
        content = self._content_store(record.source_id)
        formal = content.read_formal()
        if formal is not None and formal.strip():
            return formal, "formal", ({"layer": "formal", "path": content.formal_relative_path()},)
        pages = content.read_pages(record.source_version)
        if isinstance(pages, dict) and str(pages.get("status") or "") in _TRUSTED_MACHINE_STATUSES:
            markdown = content.read_machine_markdown(record.source_version)
            if markdown is not None and markdown.strip():
                locators: list[dict[str, Any]] = []
                for page in pages.get("pages") or []:
                    if isinstance(page, dict) and str(page.get("status") or "") in _TRUSTED_MACHINE_STATUSES:
                        locators.append(
                            {
                                "layer": "machine",
                                "page": page.get("page"),
                                "input_sha256": page.get("input_sha256"),
                                "model": page.get("model"),
                            }
                        )
                return markdown, "machine", tuple(locators)
        return None, None, ()

    def _original_media(self, record: SourceRecord) -> tuple[bytes, str, dict[str, Any]] | None:
        """Return ``(bytes, media_type, locator)`` for a directly-embeddable original."""

        original = record.entity.get("original")
        original = original if isinstance(original, dict) else {}
        rel = original.get("path")
        media_type = str(original.get("media_type") or "")
        if not isinstance(rel, str) or not rel:
            return None
        name = rel.rsplit("/", 1)[-1]
        path = self._store.original_dir(record.source_id) / name
        if not path.is_file():
            return None
        if not (media_type.startswith(_IMAGE_MEDIA_PREFIX) or media_type.startswith(_AUDIO_MEDIA_PREFIX)):
            return None
        try:
            data = path.read_bytes()
        except OSError:
            return None
        if not data or len(data) > self._max_media_bytes:
            return None
        return data, media_type, {"layer": "original", "path": rel, "media_type": media_type}

    def _vector_inputs(self, record: SourceRecord) -> list[tuple[EmbedInput, str, str, tuple[dict[str, Any], ...]]]:
        """Enumerate the embeddable inputs for one source.

        Returns tuples of ``(embed_input, basis, kind, locators)``.  Trusted text
        and the original media are **separate** vectors: media is embedded as
        media and never relabeled as text.
        """

        inputs: list[tuple[EmbedInput, str, str, tuple[dict[str, Any], ...]]] = []
        text, basis, locators = self._trusted_text(record)
        if text is not None and basis is not None:
            inputs.append((EmbedInput.text_input(text), basis, "text", locators))
        media = self._original_media(record)
        if media is not None:
            data, media_type, locator = media
            kind = "image" if media_type.startswith(_IMAGE_MEDIA_PREFIX) else "audio"
            embed_input = EmbedInput.image(data, media_type) if kind == "image" else EmbedInput.audio(data, media_type)
            inputs.append((embed_input, "original", kind, (locator,)))
        return inputs

    def index_source(self, source_id: str) -> dict[str, Any]:
        """Embed and cache one source; write ``index.vector``/``vector_model``."""

        record = self._store.read_source(source_id)
        if not self.enabled:
            self._mark_disabled(record)
            return {
                "source_id": source_id,
                "indexed": False,
                "reason": "vector_backend_unavailable",
                "vector": "disabled",
            }
        inputs = self._vector_inputs(record)
        if not inputs:
            self._write_index_state(record, vector="not_indexed", vector_model=None)
            return {
                "source_id": source_id,
                "indexed": False,
                "reason": "no_embeddable_body",
                "vector": "not_indexed",
            }
        model = self._backend.model_id
        new_entries: list[VectorEntry] = []
        try:
            for embed_input, basis, kind, locators in inputs:
                result = self._backend.embed(embed_input)
                digest_source = _embed_digest_source(embed_input, kind)
                new_entries.append(
                    VectorEntry(
                        source_id=record.source_id,
                        source_version=record.source_version,
                        content_hash=record.content_digest,
                        basis=basis,
                        kind=kind,
                        model=result.model,
                        dim=result.dim,
                        cache_version=VECTOR_CACHE_VERSION,
                        fragment_hash=fragment_hash(digest_source),
                        vector=result.vector,
                        title=record.title,
                        locators=locators,
                        text=embed_input.text or "",
                    )
                )
        except (EmbeddingUnavailable, EmbeddingTimeout, EmbeddingServiceError) as exc:
            self._mark_failed(record)
            raise AppError(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "vector backend failed while indexing; lexical search and originals remain available",
                details={"source_id": source_id, "reason": getattr(exc, "detail", None) or type(exc).__name__},
            ) from None
        self._upsert_entries(model, new_entries)
        self._write_index_state(record, vector="indexed", vector_model=model)
        self._emit("source.indexed", source_id, {"vector_model": model, "kind": "vector"})
        return {
            "source_id": source_id,
            "indexed": True,
            "vector": "indexed",
            "vector_model": model,
            "dim": new_entries[0].dim if new_entries else None,
            "kinds": [e.kind for e in new_entries],
        }

    def _upsert_entries(self, model: str, entries: list[VectorEntry]) -> None:
        """Append/replace entries, rebuilding the cache header if the model changed."""

        try:
            existing = self._index.all_entries()
            header = self._index.header()
        except VectorCacheCorruptError:
            existing = []
            header = {}
        model_changed = header.get("model") not in (None, model)
        if model_changed or header.get("cache_version") != VECTOR_CACHE_VERSION:
            # Model switch ⇒ never mix vectors: drop the old cache and rebuild
            # the header/model with only the new-model entries.
            existing = []
        dim = entries[0].dim if entries else int(header.get("dim") or 0)
        keep = [e for e in existing if e.source_id not in {n.source_id for n in entries}]
        keep.extend(entries)
        self._index.replace_all(keep, model=model, dim=dim)

    def rebuild(self, *, source_ids: list[str] | None = None) -> dict[str, Any]:
        """Delete and rebuild the vector cache from files; report outcomes."""

        records = self._store.list_sources()
        if source_ids is not None:
            wanted = set(source_ids)
            records = [r for r in records if r.source_id in wanted]
        self._index.delete()
        if not self.enabled:
            disabled_states: list[dict[str, Any]] = []
            for record in records:
                self._mark_disabled(record)
                disabled_states.append(
                    {"source_id": record.source_id, "indexed": False, "reason": "vector_backend_unavailable"}
                )
            return {
                "rebuilt": False,
                "indexed": [],
                "not_indexed": [r.source_id for r in records],
                "documents": 0,
                "states": disabled_states,
                "vector": "disabled",
            }
        indexed: list[str] = []
        not_indexed: list[str] = []
        states: list[dict[str, Any]] = []
        model = self._backend.model_id
        all_entries: list[VectorEntry] = []
        for record in records:
            inputs = self._vector_inputs(record)
            if not inputs:
                not_indexed.append(record.source_id)
                states.append({"source_id": record.source_id, "indexed": False, "reason": "no_embeddable_body"})
                self._write_index_state(record, vector="not_indexed", vector_model=None)
                continue
            entry_set: list[VectorEntry] = []
            try:
                for embed_input, basis, kind, locators in inputs:
                    result = self._backend.embed(embed_input)
                    digest_source = _embed_digest_source(embed_input, kind)
                    entry_set.append(
                        VectorEntry(
                            source_id=record.source_id,
                            source_version=record.source_version,
                            content_hash=record.content_digest,
                            basis=basis,
                            kind=kind,
                            model=result.model,
                            dim=result.dim,
                            cache_version=VECTOR_CACHE_VERSION,
                            fragment_hash=fragment_hash(digest_source),
                            vector=result.vector,
                            title=record.title,
                            locators=locators,
                            text=embed_input.text or "",
                        )
                    )
            except (EmbeddingUnavailable, EmbeddingTimeout, EmbeddingServiceError):
                not_indexed.append(record.source_id)
                states.append({"source_id": record.source_id, "indexed": False, "reason": "vector_backend_failed"})
                self._mark_failed(record)
                continue
            all_entries.extend(entry_set)
            indexed.append(record.source_id)
            states.append({"source_id": record.source_id, "indexed": True})
            self._write_index_state(record, vector="indexed", vector_model=model)
        dim = all_entries[0].dim if all_entries else 0
        if all_entries:
            self._index.replace_all(all_entries, model=model, dim=dim)
        return {
            "rebuilt": True,
            "indexed": indexed,
            "not_indexed": not_indexed,
            "documents": len(all_entries),
            "model": model,
            "dim": dim or None,
            "states": states,
        }

    def remove(self, source_id: str, *, reason: str = "deleted") -> None:
        """Drop one source from the vector cache and invalidate the record."""

        try:
            self._index.remove(source_id)
        except VectorCacheCorruptError:
            pass
        try:
            record = self._store.read_source(source_id)
        except EntityNotFound:
            return
        self._write_index_state(record, vector="not_indexed", vector_model=None)
        self._emit("source.invalidated", source_id, {"reason": reason, "kind": "vector"})

    # ------------------------------------------------------------------ search
    def search(self, request: VectorSearchRequest) -> dict[str, Any]:
        """Run authorized-candidate → 回源核对 vector search, with honest fallback.

        When the vector backend is unavailable or the cache is unusable, the
        result reports ``index_status=index_unavailable`` with a reason and an
        explicit ``lexical_fallback=True`` marker; it never fabricates hits and
        never blocks original viewing.  Authorization/scope and回源 re-verification
        reuse the lexical query layer so both paths share one rule set.
        """

        from ..lexical.query import ScopeFilter, authorize_and_verify, clamp_limit, parse_query

        parsed = parse_query(request.query)
        scope_filter = ScopeFilter(
            task_ref=request.task_ref,
            project_ref=request.project_ref,
            inbox_ref=request.inbox_ref,
            include_global=request.include_global,
        )
        limit = clamp_limit(request.limit)

        if not self.enabled:
            return self._unavailable(request, parsed, scope_filter, "vector_backend_unavailable")
        if not parsed.is_empty and not self._index.exists():
            if request.rebuild_if_missing:
                self.rebuild()
            else:
                return self._unavailable(request, parsed, scope_filter, "cache_missing")
        if self._index.exists() and not self._index.readable():
            return self._unavailable(request, parsed, scope_filter, "cache_corrupt")
        if self._index.exists() and not self._index.is_compatible(model=self._backend.model_id):
            # A different model is configured: rebuild rather than compare
            # incompatible vectors.  Until rebuilt, report honestly.
            return self._unavailable(request, parsed, scope_filter, "model_mismatch_rebuild_required")

        if parsed.is_empty:
            return {
                "query": request.query,
                "kind": list(parsed.kinds),
                "hits": [],
                "stale": [],
                "skipped": [],
                "index_status": "ok",
                "vector_model": self._backend.model_id,
            }

        try:
            result = self._backend.embed(EmbedInput.text_input(request.query))
        except (EmbeddingUnavailable, EmbeddingTimeout, EmbeddingServiceError) as exc:
            return self._unavailable(
                request, parsed, scope_filter, getattr(exc, "detail", None) or type(exc).__name__
            )
        candidates = self._index.search(result.vector, model=result.model, limit=limit)
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
            "hits": [self._hit_view(h) for h in outcome.hits],
            "stale": outcome.stale,
            "skipped": outcome.skipped,
            "index_status": "ok",
            "vector_model": result.model,
            "dim": result.dim,
            "lexical_fallback": False,
            "authorized_scope": {
                "task_ref": scope_filter.task_ref,
                "project_ref": scope_filter.project_ref,
                "inbox_ref": scope_filter.inbox_ref,
                "include_global": scope_filter.include_global,
            },
        }

    def _hit_view(self, hit: Any) -> dict[str, Any]:
        data = hit.to_dict()
        # Carry the vector kind/fragment hash for a media hit so a caller can
        # tell a media vector from a text/OCR/ASR hit without it being text.
        return data

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
        media_only = self._original_media(record) is not None
        text, _, _ = self._trusted_text(record)
        if text is None and not media_only:
            return False, "no_embeddable_body"
        return True, None

    def _unavailable(
        self, request: VectorSearchRequest, parsed: Any, scope_filter: Any, reason: str
    ) -> dict[str, Any]:
        return {
            "query": request.query,
            "kind": list(parsed.kinds),
            "hits": [],
            "stale": [],
            "skipped": [],
            "index_status": "index_unavailable",
            "index_unavailable_reason": reason,
            "vector_model": self._backend.model_id if self.enabled else None,
            "lexical_fallback": True,
            "authorized_scope": {
                "task_ref": scope_filter.task_ref,
                "project_ref": scope_filter.project_ref,
                "inbox_ref": scope_filter.inbox_ref,
                "include_global": scope_filter.include_global,
            },
        }

    # ------------------------------------------------------------------ state
    def _write_index_state(self, record: SourceRecord, *, vector: str, vector_model: str | None) -> None:
        current = record.entity.get("index")
        current = current if isinstance(current, dict) else {}
        lexical = current.get("lexical") if current.get("lexical") in _LEXICAL_STATES else "not_indexed"
        lexical_hash = current.get("lexical_hash")
        try:
            self._store.update_source(
                record.source_id,
                {
                    "index": {
                        "lexical": lexical,
                        "lexical_hash": lexical_hash,
                        "vector": vector,
                        "vector_model": vector_model,
                    }
                },
                expected_revision=record.revision,
            )
        except EntityNotFound:
            return

    def _mark_disabled(self, record: SourceRecord) -> None:
        self._write_index_state(record, vector="disabled", vector_model=None)

    def _mark_failed(self, record: SourceRecord) -> None:
        self._write_index_state(record, vector="failed", vector_model=None)

    def _emit(self, event_type: str, source_id: str, payload: dict[str, Any]) -> None:
        events = self._events
        if events is None:
            return
        try:
            events.append_event(
                source_id,
                {"type": event_type, "actor": "source-vector-index", "payload": payload},
            )
        except AppError:
            return


_LEXICAL_STATES = ("not_indexed", "indexed", "stale", "failed")


def _embed_digest_source(embed_input: EmbedInput, kind: str) -> bytes:
    """Exact bytes hashed into ``fragment_hash`` for one embed input."""

    if kind == "text":
        return (embed_input.text or "").encode("utf-8")
    return embed_input.data or b""


def build_vector_service(
    *,
    data_dir: Path | str,
    task_store: Any | None = None,
    events: Any | None = None,
    backend: EmbeddingBackend | None = None,
    env: Any = None,
) -> VectorSearchService:
    """Construct a vector service from the store and (optionally) env config."""

    from ..store import SourceStore

    if backend is None:
        from .embedder import backend_from_env

        backend = backend_from_env(env)
    store = SourceStore(data_dir)
    return VectorSearchService(store, backend=backend, task_store=task_store, events=events)


__all__ = [
    "DEFAULT_LIMIT",
    "VectorSearchRequest",
    "VectorSearchService",
    "build_vector_service",
]
