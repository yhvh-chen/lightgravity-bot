"""LG-034 durability tests: concurrent writes, atomic replace, JSONL repair.

These assert the same-store durability discipline the rest of the project uses
(LG-004 atomic writes + ``flock``): concurrent receives never corrupt a source
record, a torn receipt tail is repaired on restart, and the authoritative files
alone reproduce the state.
"""

from __future__ import annotations

import threading
from pathlib import Path

from lightgravity.sources import IntakeService, ReceiveRequest, SourceStore


def _receive(store: SourceStore, index: int) -> str:
    service = IntakeService(store)
    result = service.receive(
        ReceiveRequest(
            request_id=f"req-concurrent-{index}",
            filename=f"file-{index}.txt",
            data=f"payload-{index}".encode(),
        )
    )
    return result.source.source_id


def test_concurrent_receives_are_all_persisted(settings) -> None:
    store = SourceStore(settings.data_dir)
    sources: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        try:
            source_id = _receive(store, index)
            with lock:
                sources.append(source_id)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(sources) == 12
    assert len(set(sources)) == 12
    # Every source is independently readable from its own authoritative file.
    for source_id in sources:
        assert store.read_source(source_id).source_version == 1


def test_torn_receipt_tail_is_repaired_on_restart(settings) -> None:
    store = SourceStore(settings.data_dir)
    service = IntakeService(store)
    result = service.receive(
        ReceiveRequest(request_id="req-torn", filename="t.txt", data=b"torn")
    )
    receipt = store.receipt_path(result.source.source_id)

    # Simulate a crash mid-append: a partial JSON line with no newline.
    with receipt.open("a", encoding="utf-8") as handle:
        handle.write('{"source_id": "source_x", "status": "rec')

    fresh = SourceStore(settings.data_dir)
    repaired = fresh.recover()
    assert str(receipt) in repaired
    entries = fresh.read_receipts(result.source.source_id)
    assert all(entry.status == "received" for entry in entries)
    # The partial line was dropped rather than yielding a bogus record.
    assert len(entries) == 1


def test_state_is_rebuildable_from_files_only(settings) -> None:
    store = SourceStore(settings.data_dir)
    service = IntakeService(store)
    result = service.receive(
        ReceiveRequest(request_id="req-rebuild", filename="rb.txt", data=b"rebuild")
    )

    # Drop the derived caches (dedup + request maps); the authoritative files
    # still list the source and its receipt unchanged.
    for cache in (settings.data_dir / "sources-hash", settings.data_dir / "intake" / "by-request"):
        if cache.is_dir():
            for child in sorted(cache.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()

    fresh = SourceStore(settings.data_dir)
    records = fresh.list_sources()
    assert [record.source_id for record in records] == [result.source.source_id]
    receipts = fresh.read_receipts(result.source.source_id)
    assert receipts and receipts[0].content_hash == store.read_source(result.source.source_id).content_digest
    assert Path(fresh.original_dir(result.source.source_id) / "rb.txt").is_file()
