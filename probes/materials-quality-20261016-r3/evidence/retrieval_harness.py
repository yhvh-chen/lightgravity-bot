#!/usr/bin/env python3
"""Materials Quality R3 — LG-037 retrieval quality harness (REAL service).

Uses the UNMODIFIED product path: real ``SourceStore`` -> real ``ContentStore``
formal docs -> ``VectorSearchService`` with the real ``OpenAICompatEmbeddingBackend``
(``embeddinggemma-2-Q8_0``) and the real ``LexicalSearchService`` baseline.

POST budget: corpus 7 (text) + media 1 + queries 7 = 15 (PLAN cap 16 total incl OCR).
Each ``embed`` = exactly 1 POST (product sends one input element per request).
Serial, retry 0, timeout 120s. Writes only under evidence/ and private/.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EVID = HERE
PRIV = os.path.join(ROOT, "private")
DATA = os.path.join(PRIV, "vector-data")

sys.path.insert(0, os.path.join(ROOT, "backend"))

from lightgravity.sources import SourceStore  # noqa: E402
from lightgravity.sources.content import ContentStore  # noqa: E402
from lightgravity.sources.vectors import (  # noqa: E402
    EmbedInput,
    OpenAICompatEmbeddingBackend,
    VectorSearchService,
    VectorSearchRequest,
)
from lightgravity.sources.vectors.index import fragment_hash  # noqa: E402
from lightgravity.sources.lexical.service import LexicalSearchService, SearchRequest  # noqa: E402

BASE_URL = "http://192.168.8.12:11434"
MODEL = "embeddinggemma-2-Q8_0"
CORPUS = json.load(open(os.path.join(ROOT, "corpus.json")))
Z1_IMG = "/home/yhvh/code/lightgravity-bot-worktrees/lg035-truth-prep/probes/lg035/TRUTH-PREP/samples/private/lg035_truth_zh_laojielao_p10.jpg"

POST_LOG: list[dict] = []


def _ulid(label: str) -> str:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    d = hashlib.sha256(label.encode()).digest()
    v = int.from_bytes(d[:16], "big")
    chars = []
    for _ in range(26):
        chars.append(alphabet[v % 32])
        v //= 32
    return "source_" + "".join(reversed(chars))


def make_source(store: SourceStore, doc_id: str, text: str):
    entity_id = _ulid(doc_id)
    entity = {
        "schema": "lightgravity.bot/v1", "kind": "source", "id": entity_id,
        "title": doc_id, "title_origin": "user", "status": "extracted", "revision": 0,
        "scope": {"task_ref": None, "project_ref": None, "inbox_ref": None},
        "origin": {"kind": "upload", "external_ref": None, "fetched": False},
        "content_hash": fragment_hash(text), "stat_revision": None, "source_version": 1,
        "original": {"path": None, "media_type": None, "bytes": None, "archived_at": None},
        "derivatives": [],
        "formal": {"path": None, "revision": None, "edited_by": None},
        "index": {"lexical": "not_indexed", "lexical_hash": None, "vector": "disabled", "vector_model": None},
        "receipt_ref": None, "created_at": None, "updated_at": None,
    }
    rec = store.create_source(entity_id, entity)
    ContentStore(source_root=store.source_dir(entity_id)).write_formal(
        text, edited_by="materials-quality-r3", expected_revision=None
    )
    return rec


def main() -> int:
    if os.path.isdir(DATA):
        shutil.rmtree(DATA)
    store = SourceStore(DATA)
    backend = OpenAICompatEmbeddingBackend(
        base_url=BASE_URL, model=MODEL,
        default_timeout_seconds=120.0, cold_timeout_seconds=120.0,
    )
    vservice = VectorSearchService(store, backend=backend)
    lservice = LexicalSearchService(store)

    budget = {"limit": 16, "used": 1}  # 1 OCR already spent

    # ---------------- corpus indexing: 7 text POSTs ----------------
    corpus_ids: dict[str, str] = {}
    for doc in CORPUS["documents"]:
        rec = make_source(store, doc["id"], doc["text"])
        corpus_ids[doc["id"]] = rec.source_id
        t0 = time.time()
        try:
            res = vservice.index_source(rec.source_id)
        except Exception as exc:  # noqa: BLE001
            POST_LOG.append({"kind": "corpus_text", "doc": doc["id"], "error": type(exc).__name__,
                             "msg": str(exc)[:200], "latency": round(time.time() - t0, 3)})
            budget["used"] += 1
            print(f"corpus {doc['id']} FAILED {type(exc).__name__}: {str(exc)[:120]}")
            continue
        budget["used"] += 1
        POST_LOG.append({"kind": "corpus_text", "doc": doc["id"], "indexed": res.get("indexed"),
                         "dim": res.get("dim"), "model": res.get("vector_model"),
                         "text_sha256": fragment_hash(doc["text"]), "latency": round(time.time() - t0, 3)})
        print(f"corpus {doc['id']} indexed={res.get('indexed')} dim={res.get('dim')} model={res.get('vector_model')}")

    # ---------------- media image: 1 POST ----------------
    with open(Z1_IMG, "rb") as fh:
        img = fh.read()
    img_sha = hashlib.sha256(img).hexdigest()
    img_rec = make_source(store, "D_IMG_Z1", "image-only-source")
    store.persist_original(img_rec.source_id, "page10.jpg", img)
    # update original pointer so _original_media finds it
    cur = store.read_source(img_rec.source_id)
    rec2 = store.update_source(img_rec.source_id, {"original": {"path": "original/page10.jpg",
                              "media_type": "image/jpeg", "bytes": len(img), "archived_at": None}},
                              expected_revision=cur.entity["revision"])
    t0 = time.time()
    media_err = None
    try:
        embed_res = backend.embed(EmbedInput.image(img, "image/jpeg"))
        budget["used"] += 1
        POST_LOG.append({"kind": "media_image", "doc": "D_IMG_Z1", "dim": embed_res.dim,
                         "model": embed_res.model, "input_sha256": embed_res.input_sha256,
                         "finite": all(isinstance(x, float) for x in embed_res.vector),
                         "latency": round(embed_res.latency_seconds, 3)})
        print(f"media image dim={embed_res.dim} model={embed_res.model} sha={img_sha[:12]}",
              flush=True)
    except Exception as exc:  # noqa: BLE001
        media_err = f"{type(exc).__name__}: {str(exc)[:200]}"
        budget["used"] += 1
        POST_LOG.append({"kind": "media_image", "doc": "D_IMG_Z1", "error": type(exc).__name__,
                         "msg": str(exc)[:300], "latency": round(time.time() - t0, 3)})
        print("media image FAILED:", media_err)

    # ---------------- queries: 7 POSTs ----------------
    # Build lexical index over the docs (no network). Vector entries were already
    # upserted by index_source(); do NOT call vservice.rebuild() — it would re-embed
    # every document and exceed the frozen POST budget.
    lex_state = lservice.rebuild()

    results = {"queries": [], "corpus_ids": corpus_ids, "budget": budget}
    for q in CORPUS["queries"]:
        t0 = time.time()
        try:
            vres = vservice.search(VectorSearchRequest(query=q["text"], limit=5, include_global=True))
            v_err = None
        except Exception as exc:  # noqa: BLE001
            vres, v_err = None, f"{type(exc).__name__}: {str(exc)[:200]}"
        budget["used"] += 1
        lres = lservice.search(SearchRequest(query=q["text"], limit=5, include_global=True))
        v_hits = [(h.get("source_id"), h.get("title")) for h in (vres or {}).get("hits", [])]
        l_hits = [(h.get("source_id"), h.get("title")) for h in lres.get("hits", [])]
        entry = {
            "q": q["q"], "text": q["text"], "type": q["type"], "relevant": q["relevant"],
            "vector_error": v_err,
            "vector_index_status": (vres or {}).get("index_status"),
            "vector_hits": v_hits, "lexical_hits": l_hits,
            "latency": round(time.time() - t0, 3),
        }
        POST_LOG.append({"kind": "query", "q": q["q"], "error": v_err,
                         "latency": round(time.time() - t0, 3), "index_status": entry["vector_index_status"]})
        results["queries"].append(entry)
        print(f"{q['q']} [{q['type']}] v={v_hits} l={l_hits} err={v_err}")

    # ---------------- metrics ----------------
    # map source_id -> doc id
    id2doc = {sid: did for did, sid in corpus_ids.items()}
    k_values = CORPUS["k_values"]

    def metrics(hits_fn):
        out: dict = {}
        for k in k_values:
            rec = []
            for q in CORPUS["queries"]:
                if q["type"] != "positive":
                    continue
                hits = [id2doc.get(sid) for sid, _ in hits_fn(q["q"])[:k]]
                hits = [h for h in hits if h is not None]
                rel = set(q["relevant"])
                got = len(rel & set(hits))
                rec.append(got / len(rel))
            out[f"recall@{k}"] = round(sum(rec) / len(rec), 4) if rec else None
        # MRR + top1
        mrr = []
        top1 = []
        for q in CORPUS["queries"]:
            if q["type"] != "positive":
                continue
            hits = [id2doc.get(sid) for sid, _ in hits_fn(q["q"])]
            rel = set(q["relevant"])
            rank = next((i + 1 for i, h in enumerate(hits) if h in rel), None)
            mrr.append(1 / rank if rank else 0.0)
            top1.append(1.0 if hits and hits[0] in rel else 0.0)
        out["mrr"] = round(sum(mrr) / len(mrr), 4) if mrr else None
        out["top1_accuracy"] = round(sum(top1) / len(top1), 4) if top1 else None
        # negative controls
        neg = {}
        for q in CORPUS["queries"]:
            if q["type"] != "negative_control":
                continue
            hits = [h for h in hits_fn(q["q"]) if h is not None]
            neg[q["q"]] = {"hits": hits, "leakage": len(hits)}
        out["negative_controls"] = neg
        return out

    vhits_by_q = {e["q"]: e["vector_hits"] for e in results["queries"]}
    lhits_by_q = {e["q"]: e["lexical_hits"] for e in results["queries"]}
    results["vector_metrics"] = metrics(lambda q: vhits_by_q.get(q, []))
    results["lexical_metrics"] = metrics(lambda q: lhits_by_q.get(q, []))

    results["corpus_provenance"] = CORPUS["provenance"]
    results["labels_authorship"] = CORPUS["labels_authorship"]
    results["post_log"] = POST_LOG
    results["media_image_sha256"] = img_sha

    with open(os.path.join(EVID, "retrieval_results.json"), "w") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print("POST used total (incl 1 OCR):", budget["used"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
