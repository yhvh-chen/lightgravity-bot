"""Service-level tests: formal priority, events, concurrency, rebuild stability.

These use a real ``SourceStore`` + ``LexicalSearchService`` (no HTTP) to pin the
behaviours that are awkward to trigger through the endpoint: which layer wins,
that the source frontmatter records ``index.lexical``/``lexical_hash``, that
``source.indexed``/``source.invalidated`` events are emitted, that concurrent
index writes stay consistent, and that a moved source invalidates its hit.
"""

from __future__ import annotations

import threading

from lightgravity.sources import IntakeService, ReceiveRequest, SourceStore
from lightgravity.sources.content import ContentStore, MachineDraft, PageText
from lightgravity.sources.lexical import LexicalSearchService, SearchRequest


class _Events:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict]] = []
        self._lock = threading.Lock()

    def append_event(self, stream_id: str, event: dict) -> object:
        with self._lock:
            self.records.append((stream_id, event))
        return object()


def _receive(store: SourceStore, name: str, data: bytes) -> str:
    service = IntakeService(store)
    return service.receive(
        ReceiveRequest(request_id=f"req-{name}", filename=name, data=data)
    ).source.source_id


def _machine(store: SourceStore, source_id: str, text: str) -> None:
    record = store.read_source(source_id)
    ContentStore(source_root=store.source_dir(source_id)).write_machine(
        MachineDraft(
            source_version=record.source_version,
            filename="doc.txt",
            model="scripted",
            pages=[PageText(page=1, text=text, input_sha256="0" * 64, model="scripted")],
            extractor="scripted",
            status="succeeded",
        )
    )


def test_formal_wins_over_machine_and_writes_index_state(settings) -> None:
    store = SourceStore(settings.data_dir)
    events = _Events()
    service = LexicalSearchService(store, events=events)
    source_id = _receive(store, "doc.txt", b"machine body")
    _machine(store, source_id, "机器正文 MACHINE-1")

    # Machine-only: indexed on the machine body.
    result = service.index_source(source_id)
    assert result["indexed"] is True and result["basis"] == "machine"
    record = store.read_source(source_id)
    assert record.entity["index"]["lexical"] == "indexed"
    assert record.entity["index"]["lexical_hash"] == result["lexical_hash"]
    assert any(evt[1]["type"] == "source.indexed" for evt in events.records)

    # Human formal version takes precedence: when it differs from the machine
    # body, the formal text is what the index exposes.
    content = ContentStore(source_root=store.source_dir(source_id))
    content.initialize_formal_from_machine(record.source_version, edited_by="user")
    content.write_formal("人工校订正文 FORMAL-9", edited_by="user", expected_revision=0)
    service.index_source(source_id)
    entry = service.index.entry(source_id)
    assert entry is not None and entry["basis"] == "formal"
    formal_hit = service.search(SearchRequest(query='"formal-9"', include_global=True))
    assert [h["source_id"] for h in formal_hit["hits"]] == [source_id]
    machine_gone = service.search(SearchRequest(query='"machine-1"', include_global=True))
    assert machine_gone["hits"] == []  # formal replaced the machine body in the index


def test_index_source_without_trusted_body_is_not_indexed(settings) -> None:
    store = SourceStore(settings.data_dir)
    events = _Events()
    service = LexicalSearchService(store, events=events)
    source_id = _receive(store, "scan.png", b"\x89PNG")
    result = service.index_source(source_id)
    assert result["indexed"] is False and result["lexical"] == "not_indexed"
    assert store.read_source(source_id).entity["index"]["lexical"] == "not_indexed"


def test_concurrent_index_writes_stay_consistent(settings) -> None:
    store = SourceStore(settings.data_dir)
    service = LexicalSearchService(store)
    ids = [_receive(store, f"doc-{i}.txt", f"body {i}".encode()) for i in range(8)]
    for source_id in ids:
        _machine(store, source_id, f"编号 CONC-{source_id[-4:]}")

    errors: list[BaseException] = []

    def worker(source_id: str) -> None:
        try:
            service.index_source(source_id)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(sid,)) for sid in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    for source_id in ids:
        assert service.index.entry(source_id) is not None


def test_moved_source_invalidates_hit(settings) -> None:
    store = SourceStore(settings.data_dir)
    service = LexicalSearchService(store)
    source_id = _receive(store, "doc.txt", b"body")
    _machine(store, source_id, "编号 MOVE-1")
    service.index_source(source_id)
    assert service.search(SearchRequest(query='"move-1"', include_global=True))["hits"]

    # Simulate the original/derivative being moved away: the回源核对 must drop
    # the hit rather than return a dangling result.
    content = ContentStore(source_root=store.source_dir(source_id))
    content.machine_markdown_path(1).rename(content.derivative_dir() / "moved-away.md")
    outcome = service.search(SearchRequest(query='"move-1"', include_global=True))
    assert outcome["hits"] == []
    assert any(s["reason"] in {"no_trusted_body", "source_stale"} for s in outcome["stale"])


def test_rebuild_reproduces_lexical_hash(settings) -> None:
    store = SourceStore(settings.data_dir)
    service = LexicalSearchService(store)
    source_id = _receive(store, "doc.txt", b"body")
    _machine(store, source_id, "编号 STABLE-1")
    first = service.index_source(source_id)

    rebuilt = service.rebuild()
    assert source_id in rebuilt["indexed"]
    entry = service.index.entry(source_id)
    assert entry is not None and entry["lexical_hash"] == first["lexical_hash"]


def test_rebuild_of_corrupt_cache_recovers(settings) -> None:
    store = SourceStore(settings.data_dir)
    service = LexicalSearchService(store)
    source_id = _receive(store, "doc.txt", b"body")
    _machine(store, source_id, "编号 FIX-1")
    service.index_source(source_id)
    service.index.db_path.write_bytes(b"broken")

    outcome = service.search(SearchRequest(query='"fix-1"', include_global=True))
    assert outcome["index_status"] == "index_unavailable"

    service.rebuild()
    recovered = service.search(SearchRequest(query='"fix-1"', include_global=True))
    assert recovered["index_status"] == "ok"
    assert [h["source_id"] for h in recovered["hits"]] == [source_id]
