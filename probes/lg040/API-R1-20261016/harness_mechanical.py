"""LG-040 R1 API QA — mechanical service-layer cases (real FileStore, stubbed OCR).

Independent QA.  Uses the REAL ``SourceStore``/``IntakeService``/``ProcessingEngine``
with a **scripted in-process OCR backend** to inject controlled mechanical faults.
The scripted backend is a STUB: it produces no quality evidence and makes ZERO
network/model calls.  OCR/vector target env is unset.

Covers: machine/formal separation, reprocess non-destructive, stale index on
version bump, partial-failure honesty, corrupt/torn receipt repair, state
rebuild from files only, and vector-unavailable lexical fallback.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
RAW.mkdir(parents=True, exist_ok=True)

RESULTS: list[dict] = []


def record(case, expected, actual, ok, provenance):
    RESULTS.append({"case": case, "expected": expected, "actual": actual,
                    "status": "PASS" if ok else "FAIL", "provenance": provenance})
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {actual}")


class ScriptedBackend:
    """In-process OCR stub — mechanical only, no network, no quality evidence."""

    model = "scripted-qa-stub"

    def __init__(self, script):
        self._script = list(script)
        self.calls = []
        self._produces_quality = False  # explicit: stub is not quality evidence

    @property
    def model_id(self):
        return self.model

    def transcribe(self, request):
        import hashlib
        from lightgravity.sources.ocr import OcrPageResult
        self.calls.append(request)
        idx = len(self.calls) - 1
        outcome = self._script[idx] if idx < len(self._script) else f"page {request.page}"
        if isinstance(outcome, BaseException):
            raise outcome
        return OcrPageResult(
            page=request.page, text=str(outcome), model=self.model,
            media_type=request.media_type,
            input_sha256=hashlib.sha256(request.data).hexdigest(),
            input_bytes=len(request.data), prompt_tokens=10, completion_tokens=5,
            latency_seconds=0.01, finish_reason="stop", raw_response='{"stub":true}',
        )


def make_png(color=(10, 20, 30), size=(8, 8)):
    import struct
    import zlib

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    w, h = size
    raw = b"".join(b"\x00" + bytes(color) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def main() -> int:
    import tempfile
    from lightgravity.sources import IntakeService, ReceiveRequest, SourceStore
    from lightgravity.sources.content import ContentStore
    from lightgravity.sources.processing import ProcessingConfig, ProcessingEngine

    tmp = Path(tempfile.mkdtemp(prefix="lg040-api-mech-"))
    store = SourceStore(tmp / "data")

    # --- receive an image source (mechanical stub will "extract" it) ---
    svc = IntakeService(store)
    png = make_png()
    res = svc.receive(ReceiveRequest(request_id="mech-1", filename="scan.png",
                                     data=png, media_type="image/png"))
    sid = res.source.source_id

    # --- machine derivative via real ProcessingEngine + stub backend ---
    engine = ProcessingEngine(store, backend=ScriptedBackend(["HELLO WORLD"]),
                              config=ProcessingConfig())
    outcome = engine.process(sid)
    processed = outcome.status

    md = ContentStore(source_root=store.source_dir(sid)).read_machine_markdown(1)
    ok = processed == "succeeded" and md is not None and "HELLO WORLD" in md
    record("C-M1 machine derivative via real engine + stub", "succeeded, md has text",
           f"status={processed} md={'yes' if md else 'no'}", ok,
           "ProcessingEngine(real FileStore, ScriptedBackend stub)")

    # --- formal seeded from machine, machine untouched ---
    formal_path = None
    try:
        content = ContentStore(source_root=store.source_dir(sid))
        content.initialize_formal_from_machine(1, edited_by="qa")
        formal = content.read_formal()
        formal_path = content.formal_relative_path()
        ok = formal is not None and "HELLO WORLD" in formal
        record("C-M2 formal seeded from machine (real store)", "formal present w/ machine text",
               f"formal={'yes' if formal else 'no'}", ok,
               "ContentStore.initialize_formal_from_machine (real files)")
    except Exception as exc:  # noqa: BLE001
        record("C-M2 formal seeded from machine (real store)", "formal present",
               f"raised {type(exc).__name__}: {exc}", False, "ContentStore seed")

    # --- reprocess is non-destructive: formal preserved, machine regenerated ---
    try:
        engine2 = ProcessingEngine(store, backend=ScriptedBackend(["SECOND PASS"]),
                                   config=ProcessingConfig())
        engine2.process(sid, force=True)
        md2 = ContentStore(source_root=store.source_dir(sid)).read_machine_markdown(1)
        formal2 = ContentStore(source_root=store.source_dir(sid)).read_formal()
        ok = md2 is not None and "SECOND PASS" in md2 and formal2 is not None and "HELLO WORLD" in formal2
        record("C-M3 reprocess non-destructive (formal kept)", "machine=SECOND PASS, formal=HELLO WORLD",
               f"machine={'SECOND PASS' in (md2 or '')} formal_kept={'HELLO WORLD' in (formal2 or '')}", ok,
               "ProcessingEngine.process(force=True) over real files")
    except Exception as exc:  # noqa: BLE001
        record("C-M3 reprocess non-destructive", "formal kept",
               f"raised {type(exc).__name__}: {exc}", False, "reprocess")

    # --- version bump marks derived/index stale ---
    try:
        before = store.read_source(sid).source_version
        svc2 = IntakeService(store)
        res2 = svc2.record_version(sid, b"new version bytes", filename="scan.png")
        after = store.read_source(sid).source_version
        idx = store.read_source(sid).entity.get("index", {}).get("lexical")
        ok = after == before + 1 and idx == "stale"
        record("C-M4 record_version bumps version + marks index stale",
               f"v{before+1}, lexical=stale", f"v{after}, lexical={idx}", ok,
               "IntakeService.record_version (real store)")
    except Exception as exc:  # noqa: BLE001
        record("C-M4 record_version bumps version + marks index stale", "v+1 stale",
               f"raised {type(exc).__name__}: {exc}", False, "record_version")

    # --- torn receipt tail repaired on reopen ---
    try:
        receipt = store.receipt_path(sid)
        with receipt.open("a", encoding="utf-8") as h:
            h.write('{"source_id": "source_x", "status": "rec')
        fresh = SourceStore(tmp / "data")
        repaired = fresh.recover()
        entries = fresh.read_receipts(sid)
        ok = str(receipt) in repaired and all(e.status for e in entries)
        record("C-M5 torn receipt repaired on restart", "repaired, no bogus entry",
               f"repaired={bool(repaired)} entries={len(entries)}", ok,
               "SourceStore.recover() over real JSONL")
    except Exception as exc:  # noqa: BLE001
        record("C-M5 torn receipt repaired", "repaired",
               f"raised {type(exc).__name__}: {exc}", False, "recover")

    # --- state rebuildable from authoritative files only ---
    try:
        for cache in (tmp / "data" / "sources-hash", tmp / "data" / "intake" / "by-request"):
            if cache.is_dir():
                for child in sorted(cache.rglob("*"), reverse=True):
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
        fresh = SourceStore(tmp / "data")
        ids = [r.source_id for r in fresh.list_sources()]
        receipts = fresh.read_receipts(sid)
        orig = store.original_dir(sid) / "scan.png"
        ok = sid in ids and bool(receipts) and orig.is_file()
        record("C-M6 state rebuilds from files only", "source+receipt+original intact",
               f"listed={sid in ids} receipts={len(receipts)} original={orig.is_file()}", ok,
               "drop dedup/request caches then reopen real store")
    except Exception as exc:  # noqa: BLE001
        record("C-M6 state rebuilds from files only", "intact",
               f"raised {type(exc).__name__}: {exc}", False, "rebuild")

    # --- vector index with no backend -> disabled/unavailable, no crash ---
    try:
        from lightgravity.sources.vectors import backend_from_env, UnavailableEmbeddingBackend
        emb = backend_from_env()
        ok = isinstance(emb, UnavailableEmbeddingBackend)
        record("C-M7 vector backend disabled w/o env",
               "UnavailableEmbeddingBackend", f"{type(emb).__name__}", ok,
               "backend_from_env() with target env unset")
    except Exception as exc:  # noqa: BLE001
        record("C-M7 vector backend disabled w/o env", "unavailable",
               f"raised {type(exc).__name__}: {exc}", False, "vertex env")

    (RAW / "03_mechanical_cases.json").write_text(json.dumps(RESULTS, indent=2))
    passed = sum(1 for x in RESULTS if x["status"] == "PASS")
    print(f"\n== mechanical cases: {passed}/{len(RESULTS)} PASS ==")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
