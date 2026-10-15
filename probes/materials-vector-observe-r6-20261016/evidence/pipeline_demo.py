#!/usr/bin/env python3
"""LG-037 R6 observability pipeline demonstration (OFFLINE, no network).

Why this exists
---------------
The two authorized real query POSTs to the only permitted endpoint timed out at
the 30.0 s bound (see REPORT §live-block).  No POST budget remains, so we do NOT
retry.  To still deliver the *observability mechanism* as a reusable, verifiable
artifact, this script drives the **real product code path** --

  real SourceStore (reconstructed records) + reused R5 document vectors
    -> real VectorSearchService.search -> real authorize_and_verify
    -> real VectorIndex.search (production cosine)

-- with a **documented, deterministic substitute query vector** supplied by a
stub backend.  This is EXPLICITLY a weaker path: it validates that the harness
persists query vector / full ranked scores / native product hits / prompt_tokens
and can independently recompute the product order.  It is NOT a real embedding
and MUST NOT be read as a real retrieval-quality observation for these queries.

Writes only under evidence/pipeline_demo.json (offline).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.dirname(HERE)
WORKTREE = os.path.dirname(os.path.dirname(PROBE))
sys.path.insert(0, os.path.join(WORKTREE, "backend"))
sys.path.insert(0, HERE)

import observe_harness as h  # noqa: E402

from lightgravity.sources import SourceStore  # noqa: E402
from lightgravity.sources.content import ContentStore  # noqa: E402
from lightgravity.sources.vectors.embedder import EmbedInput, EmbedResult  # noqa: E402
from lightgravity.sources.vectors.index import VectorIndex  # noqa: E402
from lightgravity.sources.vectors.service import (  # noqa: E402
    VectorSearchRequest,
    VectorSearchService,
)


class SubstituteVectorBackend:
    """Deterministic stub: returns a documented substitute query vector.

    The vector is derived from the query text sha256 so it is reproducible and
    explicitly NOT a model embedding.  ``configured`` is True so the product
    takes the vector path; the product cosine index then ranks the reused R5
    document vectors for real.
    """

    def __init__(self, model: str) -> None:
        self._model = model
        self.records: list[dict] = []

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def configured(self) -> bool:
        return True

    def embed(self, item: EmbedInput) -> EmbedResult:
        text = item.text or ""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vec = tuple((digest[i % 32] / 255.0 - 0.5) for i in range(768))
        vb = json.dumps(list(vec)).encode()
        result = EmbedResult(
            vector=vec, model=self._model, dim=768, input_kind="text",
            input_sha256=hashlib.sha256(text.encode()).hexdigest(),
            input_bytes=len(text.encode()), latency_seconds=0.0,
            prompt_tokens=None, raw_response='{"note":"substitute vector, not a model call"}',
        )
        self.records.append({
            "substitute": True,
            "text": text,
            "text_bytes": len(text.encode()),
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "dim": 768,
            "vector_sha256": hashlib.sha256(vb).hexdigest(),
            "vector_l2": round(math.sqrt(sum(x * x for x in vec)), 8),
            "vector": list(vec),
        })
        return result


def main() -> int:
    copy_info = h.copy_r5_vectors()
    header, entries = h.load_r5_entries()
    labels = h.label_map(header, entries)

    scratch = os.path.join(h.PRIV, "demo-scratch")
    if os.path.isdir(scratch):
        shutil.rmtree(scratch)
    data_dir = os.path.join(scratch, "data")
    store = SourceStore(data_dir)
    # reuse h.build_store's record construction but into demo-scratch
    for e in entries:
        sid = e["source_id"]
        entity = {
            "schema": "lightgravity.bot/v1", "kind": "source", "id": sid,
            "title": labels.get(sid, sid), "title_origin": "user",
            "status": "extracted", "revision": 0,
            "scope": {"task_ref": None, "project_ref": None, "inbox_ref": None},
            "origin": {"kind": "upload", "external_ref": None, "fetched": False},
            "content_hash": e.get("content_hash"), "stat_revision": None,
            "source_version": e.get("source_version", 1),
            "original": {"path": None, "media_type": None, "bytes": None, "archived_at": None},
            "derivatives": [], "formal": {"path": None, "revision": None, "edited_by": None},
            "index": {"lexical": "not_indexed", "lexical_hash": None,
                      "vector": "indexed", "vector_model": header.get("model")},
            "receipt_ref": None, "created_at": None, "updated_at": None,
        }
        store.create_source(sid, entity)
        if e["kind"] == "text":
            ContentStore(source_root=store.source_dir(sid)).write_formal(
                e.get("text") or "", edited_by="r5-reuse", expected_revision=None)

    # Persist the ORIGINAL media files (reused read-only from R5 fixtures) so the
    # real product 回源核对 (which requires the original for a media-only source)
    # can verify media hits.  No re-embedding, no download, no synthesis.
    media_fixtures = {
        "M_IMG_ZH": ("/home/yhvh/code/lightgravity-bot-worktrees/lg035-truth-prep/probes/lg035/TRUTH-PREP/samples/private/lg035_truth_zh_laojielao_p10.jpg", "laojielao_p10.jpg", "image/jpeg"),
        "M_IMG_EN": ("/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016/probes/lg035/fixtures/phototest-rotated-L.png", "phototest-rotated-L.png", "image/png"),
        "M_AUD_ZH": ("/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016/probes/materials-vector-r5-20261016/private/real_voice_chinese_language-1.16k.pcm.wav", "voice_zh_language_16k.wav", "audio/wav"),
        "M_AUD_DIQIU": ("/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016/probes/materials-vector-r5-20261016/private/Zh-\u5730\u7403.16k.pcm.wav", "voice_zh_diqiu_16k.wav", "audio/wav"),
    }
    for e in entries:
        lbl = labels.get(e["source_id"])
        if e["kind"] != "text" and lbl in media_fixtures:
            path, fname, mt = media_fixtures[lbl]
            data = open(path, "rb").read()
            store.persist_original(e["source_id"], fname, data)
            cur = store.read_source(e["source_id"])
            store.update_source(e["source_id"], {"original": {"path": f"original/{fname}",
                                  "media_type": mt, "bytes": len(data), "archived_at": None}},
                                  expected_revision=cur.entity["revision"])

    idx = VectorIndex(os.path.join(data_dir, "sources-index", "vectors"))
    from lightgravity.sources.vectors.index import VectorEntry, VECTOR_CACHE_VERSION
    idx.replace_all([
        VectorEntry(source_id=e["source_id"], source_version=e.get("source_version", 1),
                    content_hash=e.get("content_hash"), basis=e.get("basis") or "machine",
                    kind=e["kind"], model=e["model"], dim=e["dim"],
                    cache_version=e.get("cache_version", VECTOR_CACHE_VERSION),
                    fragment_hash=e["fragment_hash"], vector=tuple(e["vector"]),
                    title=e.get("title") or "", locators=tuple(e.get("locators") or []),
                    text=e.get("text") or "")
        for e in entries
    ], model=header["model"], dim=header["dim"])

    backend = SubstituteVectorBackend(header["model"])
    svc = VectorSearchService(store, backend=backend)
    svc._index = VectorIndex(os.path.join(data_dir, "sources-index", "vectors"))

    out = {
        "disclosure": {
            "weaker_path": True,
            "real_query_embed": False,
            "reason": "real query embed to the only authorized endpoint timed out at 30.0s "
                      "twice (POST budget exhausted, retry=0); a documented deterministic "
                      "substitute vector is used to validate the OBSERVABILITY pipeline only",
            "not_a_quality_observation": True,
            "docembedding": 0,
            "documents_are_reused_r5_vectors": True,
        },
        "r5_reuse": {"copy": copy_info, "header": header, "entry_count": len(entries),
                     "label_map": labels},
        "queries": [],
    }

    for q in h.FROZEN_QUERIES:
        text = q["text"]
        vres = svc.search(VectorSearchRequest(query=text, limit=5, include_global=True))
        rec = backend.records[-1]
        qv = rec["vector"]
        cand = svc._index.search(qv, model=header["model"], limit=10)
        full = [{"source_id": c["source_id"], "label": labels.get(c["source_id"]),
                 "kind": c["kind"], "score": round(float(c["score"]), 8),
                 "fragment_hash": c["fragment_hash"]} for c in cand]
        indep = sorted(
            [{"source_id": e["source_id"], "label": labels.get(e["source_id"]),
              "kind": e["kind"], "score": round(h.cosine(qv, e["vector"]), 8)} for e in entries],
            key=lambda x: (-x["score"], x["source_id"]),
        )
        target = q["relevant"][0] if q["relevant"] else None
        rank_info = None
        if target:
            for i, r in enumerate(full):
                if r["label"] == target:
                    rank_info = {"target": target, "rank": i + 1, "score": r["score"],
                                 "margin_to_top": round(full[0]["score"] - r["score"], 8)}
                    break
        out["queries"].append({
            "q": q["q"], "text": text, "type": q["type"], "relevant": q["relevant"],
            "substitute_query_vector": rec,
            "product_index_status": vres.get("index_status"),
            "product_hit_count": len(vres.get("hits", [])),
            "product_hit_fields": sorted(vres.get("hits", [{}])[0].keys()) if vres.get("hits") else [],
            "product_hits": vres.get("hits", []),
            "product_stale": vres.get("stale", []),
            "product_skipped": vres.get("skipped", []),
            "full_ranking": full,
            "independent_recompute": indep,
            "independent_order_matches_product": [r["source_id"] for r in full] == [r["source_id"] for r in indep],
            "target_rank_info": rank_info,
        })
        print(f"{q['q']}: status={vres.get('index_status')} hits={len(vres.get('hits', []))} "
              f"rank={rank_info} order_match={out['queries'][-1]['independent_order_matches_product']}")

    with open(os.path.join(HERE, "pipeline_demo.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
