#!/usr/bin/env python3
"""LG-040 QUALITY-R1 independent English-primary quality harness.

Drives the **real** product: real ``create_app`` (real FileStore, real routers,
real ``SourceService``/``IntakeService``/``ProcessingEngine``/``VectorSearchService``)
served over real loopback HTTP via uvicorn.  All model traffic goes through the
counting hard-cap proxy (``counting_proxy.py``).

Phases (frozen in PLAN.md / frozen/LABELS.json BEFORE any POST):
  A. intake 4 docs, set formal (human text) for D1/D2
  B. OCR mixed PDF (2 pages) via the normal product processing path   [<=2 POST]
  C. build vector index (4 vectors) + queries + negative + rebuild    [<=18 POST]

Writes raw evidence to ./evidence/.  Never fabricates vectors/hits; persists
raw embeddings, query vectors, usage, model/dim/hash/cache_version.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CORPUS = HERE / "corpus"
EVIDENCE = HERE / "evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)

PROXY_PORT = 18140
APP_PORT = 18141
BASE = f"http://127.0.0.1:{PROXY_PORT}"
APP = f"http://127.0.0.1:{APP_PORT}"

# product fixtures (read-only reuse)
NIST_PDF = ROOT / "probes/materials-fixtures-r7-20261016/sources/nist-sp811/nistspecialpublication811e2008.pdf"
MIXED_PDF = ROOT / "probes/materials-fixtures-r7-20261016/fixtures/mixed_born_digital_plus_scan.pdf"
PHOTOTEST_TIF = ROOT / "probes/lg035/fixtures/phototest.tif"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Recorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def add(self, **kw) -> None:
        kw.setdefault("ts", time.time())
        self.calls.append(kw)

    def dump(self, name: str) -> None:
        (EVIDENCE / name).write_text(json.dumps(self.calls, ensure_ascii=False, indent=2), encoding="utf-8")


def read_labels() -> dict:
    return json.loads((HERE / "frozen/LABELS.json").read_text(encoding="utf-8"))


def seed_text_machine(data_dir: Path, source_id: str, filename: str, text: str) -> dict:
    """Seed a machine derivative for a plain-text source via the PRODUCT content code.

    The product has no native-text derivative path (text/plain is not OCR-processable),
    so the trusted-text basis for D1/D2 is seeded through the product's own
    ``ContentStore.write_machine`` with an HONEST extractor label
    ``human_provided_text`` (NOT OCR, model ``none``).  This is a disclosed direct
    content-seeding step, not an OCR E2E; retrieval quality still runs the real
    product vector/search HTTP path.
    """
    from lightgravity.sources.content import ContentStore, MachineDraft, PageText
    from lightgravity.sources.store import SourceStore

    store = SourceStore(data_dir)
    record = store.read_source(source_id)
    content = ContentStore(source_root=store.source_dir(source_id))
    draft = MachineDraft(
        source_version=record.source_version,
        filename=filename,
        model="none",
        extractor="human_provided_text",
        status="succeeded",
        total_pages=1,
        pages=[PageText(page=1, text=text, input_sha256=sha256_bytes(text.encode()), model="none", status="succeeded")],
    )
    written = content.write_machine(draft)
    return {"source_id": source_id, "extractor": "human_provided_text", "written": written}


def compute_ocr_cer(data_dir: Path, source_id: str) -> dict:
    """Per-page CER of the OCR machine derivative vs human-authored truth.

    Page 1 truth = NIST SP 811 page 16 native text (human-authored, from the
    truth fixture); page 2 truth = phototest.gold.txt (human gold).  Normalized
    NFKC + collapsed whitespace + lowercased; Levenshtein edit distance.
    """
    import re
    import unicodedata

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s).lower()
        return re.sub(r"\s+", " ", s).strip()

    def levenshtein(a: str, b: str) -> int:
        if not a:
            return len(b)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            prev = cur
        return prev[-1]

    from lightgravity.sources.store import SourceStore
    store = SourceStore(data_dir)
    rec = store.read_source(source_id)
    pages_path = store.source_dir(source_id) / f"derivative/machine.v{rec.source_version}.pages.json"
    out: dict = {"source_id": source_id, "pages_path": str(pages_path)}
    if not pages_path.is_file():
        out["error"] = "no pages derivative"
        return out
    pages_doc = json.loads(pages_path.read_text(encoding="utf-8"))
    out["status"] = pages_doc.get("status")
    # page1 truth from NIST page 16 native text
    import pypdfium2 as pdfium
    p16 = pdfium.PdfDocument(str(NIST_PDF))[15].get_textpage().get_text_bounded()
    start = p16.index("Table 1 gives the seven base quantities")
    end = p16.index("4.2 SI derived units")
    truth_p1 = norm(p16[start:end])
    truth_p2 = norm((ROOT / "probes/lg035/fixtures/phototest.gold.txt").read_text(encoding="utf-8"))
    truths = {1: truth_p1, 2: truth_p2}
    for pg in pages_doc.get("pages", []):
        pno = pg.get("page")
        got = norm(pg.get("text") or "")
        t = truths.get(pno)
        entry = {"page": pno, "status": pg.get("status"), "got_chars": len(got),
                 "model": pg.get("model"), "input_sha256": pg.get("input_sha256")}
        if t is not None:
            dist = levenshtein(got, t)
            entry.update({"truth_chars": len(t), "edit_distance": dist,
                          "cer": round(dist / max(len(t), 1), 4)})
        out[f"page{pno}" if pno else "page? "] = entry
        if pno == 1:
            out["page1_cer"] = entry.get("cer")
        if pno == 2:
            out["page2_cer"] = entry.get("cer")
    return out


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/v1/health", timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    import httpx

    labels = read_labels()
    rec = Recorder()

    # ---- start app (real product) with vector+OCR backends pointed at proxy ----
    data_dir = Path(os.environ.get("LG040Q_DATA", "/tmp/lg040-quality-r1-20261016/data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "LIGHTGRAVITY_DATA_DIR": str(data_dir),
        "LIGHTGRAVITY_WORKSPACE_ROOT": str(data_dir / "workspaces"),
        "LIGHTGRAVITY_SECRET_STORE": str(data_dir / "secrets"),
        "LIGHTGRAVITY_VECTOR_BASE_URL": BASE,
        "LIGHTGRAVITY_VECTOR_MODEL": "embeddinggemma-2-Q8_0",
        "LIGHTGRAVITY_VECTOR_TIMEOUT_SECONDS": "90",
        "LIGHTGRAVITY_VECTOR_COLD_TIMEOUT_SECONDS": "90",
        "LIGHTGRAVITY_OCR_BASE_URL": BASE,
        "LIGHTGRAVITY_OCR_MODEL": "qwen3.8-27b",
        "LIGHTGRAVITY_OCR_TIMEOUT_SECONDS": "120",
        "LIGHTGRAVITY_OCR_COLD_TIMEOUT_SECONDS": "120",
        "LIGHTGRAVITY_OCR_MAX_TOKENS": "4096",
        "LG040Q_DATA": str(data_dir),
    })
    app_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "--factory", "lightgravity.api.app:create_app",
         "--host", "127.0.0.1", "--port", str(APP_PORT), "--log-level", "warning"],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    # counting hard-cap proxy in front of the authorized LAN endpoint
    proxy_proc = subprocess.Popen(
        [sys.executable, str(HERE / "counting_proxy.py"), str(PROXY_PORT)],
        cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        if not wait_for_server(APP):
            out = app_proc.stdout.read() if app_proc.stdout else ""
            log("app failed to start:\n" + out[-2000:])
            return 2
        log(f"app up on {APP}")

        # health/models GET: budget already consumed by earlier attempts (2 actual LAN GETs);
        # do NOT issue more in this run.

        client = httpx.Client(base_url=APP, timeout=180)
        rec_client = httpx.Client(base_url=APP, timeout=180)

        # ---------------- Phase A: intake ----------------
        docs = {}
        for entry in labels["corpus"]:
            doc_id = entry["doc_id"]
            rel = entry["path"]
            if rel.startswith("probes"):
                p = ROOT / rel
            else:
                p = HERE / rel
            if not p.is_file():
                p = ROOT / rel
            data = p.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            resp = client.post("/api/v1/sources", json={
                "request_id": f"lg040q-{doc_id.lower()}",
                "filename": p.name,
                "content_base64": b64,
                "title": f"LG040Q {doc_id}",
                "media_type": {"text": "text/plain", "image": "image/tiff", "audio": "audio/wav"}[entry["kind"]],
                "scope": {"task_ref": None, "project_ref": None, "inbox_ref": None},
                "origin": {"kind": "upload", "external_ref": None, "fetched": False},
                "payload_hash": None,
            })
            body = resp.json()
            sid = body["source"]["source_id"]
            docs[doc_id] = {"source_id": sid, "kind": entry["kind"], "sha256": sha256_bytes(data),
                            "intake_status": resp.status_code, "path": str(p)}
            rec.add(phase="intake", doc_id=doc_id, source_id=sid, http=resp.status_code,
                    content_hash=body["source"].get("content_hash"))
            log(f"intake {doc_id} -> {sid} ({resp.status_code})")

        # seed machine derivative (product ContentStore, honest label) then set formal human text for D1/D2
        for doc_id in ("D1", "D2"):
            sid = docs[doc_id]["source_id"]
            fname = "d1_si_units.txt" if doc_id == "D1" else "d2_phototest_gold.txt"
            text = (HERE / f"corpus/{fname}").read_text(encoding="utf-8")
            seed = seed_text_machine(data_dir, sid, fname, text)
            rec.add(phase="seed_machine_text", doc_id=doc_id, source_id=sid, extractor="human_provided_text")
            resp = client.post(f"/api/v1/sources/{sid}/formal", json={"content": text, "edited_by": "user"})
            rec.add(phase="formal", doc_id=doc_id, source_id=sid, http=resp.status_code)
            log(f"formal {doc_id} -> {resp.status_code}")
        (EVIDENCE / "docs.json").write_text(json.dumps(docs, indent=2), encoding="utf-8")

        # ---------------- Phase B: OCR mixed PDF (2 pages) via normal product path ----------------
        mixed_bytes = MIXED_PDF.read_bytes()
        resp = client.post("/api/v1/sources", json={
            "request_id": "lg040q-mixedpdf",
            "filename": MIXED_PDF.name,
            "content_base64": base64.b64encode(mixed_bytes).decode("ascii"),
            "title": "LG040Q MIXED PDF",
            "media_type": "application/pdf",
            "scope": {}, "origin": {"kind": "upload"}, "payload_hash": None,
        })
        mix = resp.json()
        mix_sid = mix["source"]["source_id"]
        log(f"intake mixed pdf -> {mix_sid} ({resp.status_code})")
        # reprocess action triggers ProcessingEngine.process -> real OCR backend
        t0 = time.monotonic()
        resp = client.post(f"/api/v1/sources/{mix_sid}/actions", json={"action": "reprocess"})
        ocr_out = resp.json()
        rec.add(phase="ocr", source_id=mix_sid, http=resp.status_code,
                wall_s=round(time.monotonic() - t0, 3), outcome=ocr_out)
        (EVIDENCE / "ocr_mixed.json").write_text(json.dumps(ocr_out, indent=2), encoding="utf-8")
        log(f"ocr mixed -> {resp.status_code} {json.dumps(ocr_out)[:300]}")
        docs["MIX"] = {"source_id": mix_sid, "kind": "pdf", "sha256": sha256_bytes(mixed_bytes)}
        (EVIDENCE / "docs.json").write_text(json.dumps(docs, indent=2), encoding="utf-8")

        # fetch machine content for CER
        try:
            content = client.get(f"/api/v1/sources/{mix_sid}/content", params={"kind": "machine"}).json()
            (EVIDENCE / "ocr_machine_content.json").write_text(json.dumps(content, indent=2), encoding="utf-8")
        except Exception as exc:
            log(f"machine content fetch failed: {exc}")

        # OCR CER per page from the persisted pages derivative vs human truth
        cer = compute_ocr_cer(data_dir, mix_sid)
        rec.add(phase="ocr_cer", **cer)
        (EVIDENCE / "ocr_cer.json").write_text(json.dumps(cer, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"ocr CER -> page1={cer.get('page1_cer')} page2={cer.get('page2_cer')}")

        # ---------------- Phase C: vector index build ----------------
        status = rec_client.get("/api/v1/vector/status").json()
        rec.add(phase="vector_status_before", body=status)
        log(f"vector status before: {json.dumps(status)[:300]}")

        t0 = time.monotonic()
        resp = client.post("/api/v1/vector/rebuild")
        build = resp.json()
        rec.add(phase="vector_build", http=resp.status_code, wall_s=round(time.monotonic() - t0, 3), body=build)
        (EVIDENCE / "vector_build.json").write_text(json.dumps(build, indent=2), encoding="utf-8")
        log(f"vector build -> {resp.status_code} {json.dumps(build)[:400]}")

        status = rec_client.get("/api/v1/vector/status").json()
        (EVIDENCE / "vector_status_after_build.json").write_text(json.dumps(status, indent=2), encoding="utf-8")

        # queries (vector)
        qresults = {}
        for q in labels["queries"]:
            t0 = time.monotonic()
            r = client.get("/api/v1/vector/search", params={"q": q["text"], "limit": 10}).json()
            r["_wall_s"] = round(time.monotonic() - t0, 3)
            qresults[q["q_id"]] = r
            rec.add(phase="vector_query", q_id=q["q_id"], body=r)
            hits = [(h.get("source_id"), round(h.get("score", 0), 4)) for h in r.get("hits", [])]
            log(f"vector {q['q_id']} -> {r.get('index_status')} hits={hits}")
        (EVIDENCE / "vector_queries.json").write_text(json.dumps(qresults, indent=2), encoding="utf-8")

        # lexical baseline on the SAME corpus
        lexresults = {}
        for q in labels["queries"]:
            r = client.get("/api/v1/search", params={"q": q["text"], "limit": 10}).json()
            lexresults[q["q_id"]] = r
            rec.add(phase="lexical_query", q_id=q["q_id"], body=r)
            hits = [(h.get("source_id")) for h in r.get("hits", [])]
            log(f"lexical {q['q_id']} -> {r.get('index_status')} hits={hits}")
        (EVIDENCE / "lexical_queries.json").write_text(json.dumps(lexresults, indent=2), encoding="utf-8")

        # rebuild reproduction: delete cache then rebuild
        cache_file = data_dir / "sources-index" / "vectors" / "vectors.jsonl"
        rec.add(phase="cache_delete", path=str(cache_file), existed=cache_file.exists())
        if cache_file.exists():
            cache_file.unlink()
        t0 = time.monotonic()
        resp = client.post("/api/v1/vector/rebuild")
        rebuild2 = resp.json()
        rec.add(phase="vector_rebuild", http=resp.status_code, wall_s=round(time.monotonic() - t0, 3), body=rebuild2)
        (EVIDENCE / "vector_rebuild.json").write_text(json.dumps(rebuild2, indent=2), encoding="utf-8")
        log(f"vector rebuild -> {resp.status_code} {json.dumps(rebuild2)[:300]}")

        # post-rebuild reproducibility query Q1'
        r = client.get("/api/v1/vector/search", params={"q": labels["queries"][0]["text"], "limit": 10}).json()
        rec.add(phase="vector_query_postrebuild", q_id="Q1prime", body=r)
        qresults["Q1prime"] = r
        (EVIDENCE / "vector_queries.json").write_text(json.dumps(qresults, indent=2), encoding="utf-8")
        log(f"vector Q1' -> {r.get('index_status')} hits={[(h.get('source_id'), round(h.get('score',0),4)) for h in r.get('hits',[])]}")

        rec.dump("call_recorder.json")
        return 0
    finally:
        for proc in (app_proc, proxy_proc):
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
