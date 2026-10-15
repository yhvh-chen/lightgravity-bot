#!/usr/bin/env python3
"""LG-037 R6 evidence-observability harness (real product path).

Purpose: make R4/R5-style evidence *recomputable* by recording, for the real
product request/response path, everything R5 dropped:

  * the exact embeddings request (no auth) + raw response + usage/prompt_tokens;
  * the query bytes / sha256 / full vector;
  * the reused R5 document vector hashes / model / dim / fragment fingerprints;
  * the FULL ranked scores (all 10 candidates, not just top-5);
  * the native product hits (``VectorSearchService.search`` output);
  * an independent cosine recompute compared against the product order.

Design (bounded, reusable, honest):

  RecordingBackend (wraps the REAL OpenAICompatEmbeddingBackend)
    -> real HTTP POST /v1/embeddings (the only real backend)
    -> real VectorSearchService.search(...)  (real product search)
    -> real VectorIndex.search over REUSED R5 document vectors

We do NOT re-embed documents (`docembedding0`); R5's vectors.jsonl is copied
read-only into this probe's private scratch and its header/hashes verified.
We do NOT fake E2E: the query embedding is a real HTTP call and the ranking is
the real product cosine index.  Because the R5 query vector was never persisted,
we make NO retrospective exact-margin claim for the historical R5 flip; we only
report this new observation.

Budget: 2 POST total (Q_IMG_ZH, Q_NEG_ZH), retry 0, serial, timeout 30s /
connect 3s, text <= 1 KiB/query, media/OCR/ASR/worker = 0.  Optional <= 1
health GET (8s).  Reservation persisted BEFORE forwarding; hard cap enforced
BEFORE HTTP.

Writes only under evidence/, http/ and private/.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.dirname(HERE)
WORKTREE = os.path.dirname(os.path.dirname(PROBE))
PRIV = os.path.join(PROBE, "private")
EVID = os.path.join(PROBE, "evidence")
HTTP = os.path.join(PROBE, "http")
SCRATCH = os.path.join(PRIV, "scratch")
LEDGER = os.path.join(EVID, "post_reservations.jsonl")
R5_VECTORS_SRC = "/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016/probes/materials-vector-r5-20261016/private/vector-data/sources-index/vectors/vectors.jsonl"

sys.path.insert(0, os.path.join(WORKTREE, "backend"))

from lightgravity.sources import SourceStore  # noqa: E402
from lightgravity.sources.content import ContentStore  # noqa: E402
from lightgravity.sources.vectors.embedder import (  # noqa: E402
    EmbedInput,
    EmbedResult,
    OpenAICompatEmbeddingBackend,
)
from lightgravity.sources.vectors.index import (  # noqa: E402
    VECTOR_CACHE_VERSION,
    VectorEntry,
    VectorIndex,
    fragment_hash,
)
from lightgravity.sources.vectors.service import (  # noqa: E402
    VectorSearchRequest,
    VectorSearchService,
)

BASE_URL = "http://192.168.8.12:11434"
MODEL = "embeddinggemma-2-Q8_0"
POST_CAP = 2
TEXT_BYTES_CAP = 1024
TIMEOUT = 30.0
CONNECT_TIMEOUT = 3.0

FROZEN_QUERIES = [
    {"q": "Q_IMG_ZH", "text": "老子 道德經 註解 學說", "type": "positive_crossmodal_image",
     "relevant": ["M_IMG_ZH"], "source": "R5 frozen corpus (verbatim)"},
    {"q": "Q_NEG_ZH", "text": "量子色動力學 膠子 強相互作用", "type": "negative_control",
     "relevant": [], "source": "R5 frozen corpus old negative"},
]

COUNTERS = {"post_used": 0, "post_attempted": 0, "retries": 0, "health_get": 0,
            "media_inputs": 0, "audio_seconds": 0.0}
POST_LOG: list[dict] = []


class BudgetExceeded(RuntimeError):
    pass


class HardCapError(RuntimeError):
    pass


def _reserve(kind: str, detail: dict) -> dict:
    """Persist a reservation BEFORE forwarding; enforce cap BEFORE HTTP."""

    if COUNTERS["post_used"] + 1 > POST_CAP:
        raise HardCapError(f"POST cap would exceed: {COUNTERS['post_used']} >= {POST_CAP}")
    rec = {"seq": COUNTERS["post_used"] + 1, "kind": kind, "ts": round(time.time(), 3), **detail}
    os.makedirs(EVID, exist_ok=True)
    with open(LEDGER, "a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return rec


class RecordingBackend:
    """Wrap the real backend, capturing exact request/response (no auth)."""

    def __init__(self, inner: OpenAICompatEmbeddingBackend) -> None:
        self._inner = inner
        self.records: list[dict] = []

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def configured(self) -> bool:
        return self._inner.configured

    def embed(self, item: EmbedInput) -> EmbedResult:
        # Build the exact request the real backend will send, so we can record
        # the literal bytes WITHOUT secrets (there is no token configured here).
        body = {
            "model": self._inner.model_id,
            "encoding_format": "float",
            "input": [_input_element(item)],
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req_view = {
            "method": "POST",
            "path": "/v1/embeddings",
            "endpoint_host": urllib.parse.urlsplit(self._inner.endpoint).netloc,
            "model": self._inner.model_id,
            "encoding_format": "float",
            "input_type": "text" if item.part_type == "text" else "media",
            "text": item.text,
            "text_bytes": len((item.text or "").encode("utf-8")),
            "text_sha256": hashlib.sha256((item.text or "").encode("utf-8")).hexdigest(),
            "request_body_bytes": len(payload),
            "auth_header_present": False,
            "media_attached": item.part_type != "text",
        }
        t0 = time.monotonic()
        try:
            result = self._inner.embed(item)
        except Exception as exc:  # noqa: BLE001  (record failures, never drop them)
            self.records.append({
                "input_kind": item.part_type,
                "request": req_view,
                "response": None,
                "error": f"{type(exc).__name__}: {str(exc)[:400]}",
                "input_sha256": hashlib.sha256((item.text or "").encode("utf-8")).hexdigest(),
                "latency_seconds": round(time.monotonic() - t0, 4),
            })
            raise
        latency = time.monotonic() - t0
        vb = json.dumps(list(result.vector)).encode()
        rec = {
            "input_kind": item.part_type,
            "request": req_view,
            "response": {
                "status": 200,
                "dim": result.dim,
                "vector_sha256": hashlib.sha256(vb).hexdigest(),
                "vector_finite": all(math.isfinite(float(x)) for x in result.vector),
                "vector_nonzero": any(abs(float(x)) > 0.0 for x in result.vector),
                "vector_l2": round(math.sqrt(sum(float(x) ** 2 for x in result.vector)), 8),
                "vector": list(result.vector),
                "input_sha256": result.input_sha256,
                "usage": _usage_of(result.raw_response),
                "raw_response": result.raw_response,
            },
            "input_sha256": result.input_sha256,
            "latency_seconds": round(latency, 4),
        }
        self.records.append(rec)
        return result


def _input_element(item: EmbedInput) -> object:
    if item.part_type == "text":
        return item.text
    raise HardCapError("media inputs are out of scope for this observation (image=0 audio=0)")


def _usage_of(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    usage = payload.get("usage") if isinstance(payload, dict) else None
    return usage if isinstance(usage, dict) else {}


def copy_r5_vectors() -> dict:
    """Copy R5 vectors.jsonl read-only into private scratch; verify header/hashes."""

    os.makedirs(SCRATCH, exist_ok=True)
    dst = os.path.join(SCRATCH, "r5-vectors", "vectors.jsonl")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    src_bytes = Path(R5_VECTORS_SRC).read_bytes()
    Path(dst).write_bytes(src_bytes)
    src_sha = hashlib.sha256(src_bytes).hexdigest()
    dst_sha = hashlib.sha256(Path(dst).read_bytes()).hexdigest()
    return {"source_path": R5_VECTORS_SRC, "source_sha256": src_sha,
            "copied_sha256": dst_sha, "byte_identical": src_sha == dst_sha,
            "copied_path": dst}


def load_r5_entries() -> tuple[dict, list[dict]]:
    header: dict = {}
    entries: list[dict] = []
    with open(R5_VECTORS_SRC) as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if i == 0 and rec.get("record") == "header":
                header = rec
                continue
            entries.append(rec)
    return header, entries


def label_map(header: dict, entries: list[dict]) -> dict[str, str]:
    """Map R5 source_id -> doc label using cached text / fragment hash."""

    corpus = json.load(open("/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016/probes/materials-vector-r5-20261016/corpus.json"))
    text_by_label = {d["id"]: d["text"] for d in corpus["text_sources"]["documents"]}
    media_hash = {
        "M_IMG_ZH": corpus["provenance"]["M_IMG_ZH"]["sha256"],
        "M_IMG_EN": corpus["provenance"]["M_IMG_EN"]["sha256"],
        "M_AUD_ZH": corpus["provenance"]["M_AUD_ZH"]["transcode"]["out_sha256"],
        "M_AUD_DIQIU": corpus["provenance"]["M_AUD_DIQIU"]["transcode"]["out_sha256"],
    }
    out: dict[str, str] = {}
    for e in entries:
        if e["kind"] == "text":
            t = e.get("text") or ""
            for lbl, txt in text_by_label.items():
                if txt and txt in t:
                    out[e["source_id"]] = lbl
                    break
        else:
            for lbl, h in media_hash.items():
                if e["fragment_hash"] == h:
                    out[e["source_id"]] = lbl
                    break
    return out


def build_store(header: dict, entries: list[dict], labels: dict[str, str]) -> SourceStore:
    """Reconstruct minimal REAL SourceStore records so 回源核对 passes.

    Vectors are NOT recomputed: the cache vectors are reused.  The records only
    carry the identity/version/formal text needed by the real product search to
    re-verify hits; content_hash mirrors the R5 cache entry.
    """

    data_dir = os.path.join(SCRATCH, "data")
    if os.path.isdir(data_dir):
        import shutil
        shutil.rmtree(data_dir)
    os.makedirs(SCRATCH, exist_ok=True)
    store = SourceStore(data_dir)
    for e in entries:
        sid = e["source_id"]
        entity = {
            "schema": "lightgravity.bot/v1", "kind": "source", "id": sid,
            "title": labels.get(sid, sid), "title_origin": "user",
            "status": "extracted", "revision": 0,
            "scope": {"task_ref": None, "project_ref": None, "inbox_ref": None},
            "origin": {"kind": "upload", "external_ref": None, "fetched": False},
            "content_hash": e.get("content_hash"),
            "stat_revision": None, "source_version": e.get("source_version", 1),
            "original": {"path": None, "media_type": None, "bytes": None, "archived_at": None},
            "derivatives": [],
            "formal": {"path": None, "revision": None, "edited_by": None},
            "index": {"lexical": "not_indexed", "lexical_hash": None,
                      "vector": "indexed", "vector_model": header.get("model")},
            "receipt_ref": None, "created_at": None, "updated_at": None,
        }
        store.create_source(sid, entity)
        if e["kind"] == "text":
            # Write the EXACT cached formal body so the reused fragment hash and
            # the verified formal body agree.
            ContentStore(source_root=store.source_dir(sid)).write_formal(
                e.get("text") or "", edited_by="r5-reuse",
                expected_revision=None,
            )
    return store


def install_reused_cache(header: dict, entries: list[dict]) -> VectorIndex:
    """Write REUSED R5 entries into this probe's private product cache."""

    idx = VectorIndex(os.path.join(SCRATCH, "data", "sources-index", "vectors"))
    vec_entries = []
    for e in entries:
        vec_entries.append(VectorEntry(
            source_id=e["source_id"], source_version=e.get("source_version", 1),
            content_hash=e.get("content_hash"), basis=e.get("basis") or "machine",
            kind=e["kind"], model=e["model"], dim=e["dim"],
            cache_version=e.get("cache_version", VECTOR_CACHE_VERSION),
            fragment_hash=e["fragment_hash"], vector=tuple(e["vector"]),
            title=e.get("title") or "", locators=tuple(e.get("locators") or []),
            text=e.get("text") or "",
        ))
    idx.replace_all(vec_entries, model=header["model"], dim=header["dim"])
    return idx


def health_get() -> dict | None:
    """Optional single health GET (8s), does not count as POST."""

    if COUNTERS["health_get"] >= 1:
        return None
    COUNTERS["health_get"] += 1
    url = BASE_URL + "/health"
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json",
                                                             "User-Agent": "lightgravity-bot/r6-observe"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
        result = {"status": status, "raw": raw[:4000], "latency": round(time.monotonic() - t0, 3)}
    except Exception as exc:  # noqa: BLE001
        result = {"status": None, "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                  "latency": round(time.monotonic() - t0, 3)}
    os.makedirs(HTTP, exist_ok=True)
    with open(os.path.join(HTTP, "health.raw.json"), "w") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    return result


def cosine(a, b) -> float:
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    na = math.sqrt(sum(float(x) ** 2 for x in a))
    nb = math.sqrt(sum(float(y) ** 2 for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def main() -> int:
    for p in (SCRATCH, EVID, HTTP):
        os.makedirs(p, exist_ok=True)
    if os.path.exists(LEDGER):
        os.remove(LEDGER)
    os.makedirs(os.path.join(HTTP, "queries"), exist_ok=True)

    # 1. reuse R5 vectors (read-only copy + verify)
    copy_info = copy_r5_vectors()
    header, entries = load_r5_entries()
    labels = label_map(header, entries)

    observation: dict = {
        "probe": "materials-vector-observe-r6-20261016",
        "phase": "OBSERVATION",
        "base_url": BASE_URL, "model": MODEL,
        "policy": {"post_cap": POST_CAP, "retries": 0, "concurrency": 1,
                   "timeout_seconds": TIMEOUT, "connect_timeout_seconds": CONNECT_TIMEOUT,
                   "text_bytes_cap": TEXT_BYTES_CAP, "docembedding": 0,
                   "audio": 0, "image": 0, "ocr": 0, "asr": 0, "worker": 0},
        "r5_reuse": {
            "copy": copy_info,
            "header": header,
            "entry_count": len(entries),
            "label_map": labels,
            "entries_meta": [
                {"source_id": e["source_id"], "label": labels.get(e["source_id"]),
                 "kind": e["kind"], "basis": e["basis"], "model": e["model"], "dim": e["dim"],
                 "cache_version": e["cache_version"], "fragment_hash": e["fragment_hash"],
                 "source_version": e["source_version"], "content_hash": e["content_hash"],
                 "vector_sha256": hashlib.sha256(json.dumps(e["vector"]).encode()).hexdigest()}
                for e in entries
            ],
        },
        "queries": [],
        "counters": COUNTERS,
    }

    # 2. build store + installed reused cache
    store = build_store(header, entries, labels)
    install_reused_cache(header, entries)

    # 3. real backend + recording wrapper; real VectorSearchService
    inner = OpenAICompatEmbeddingBackend(
        base_url=BASE_URL, model=MODEL,
        default_timeout_seconds=TIMEOUT, cold_timeout_seconds=TIMEOUT,
    )
    recorder = RecordingBackend(inner)
    vservice = VectorSearchService(store, backend=recorder)
    # The service's index default dir may differ; point it at our installed cache.
    vservice._index = VectorIndex(os.path.join(SCRATCH, "data", "sources-index", "vectors"))

    # 4. optional health GET
    observation["health"] = health_get()

    # 5. real 2 query POSTs (serial; reserve BEFORE forwarding)
    for q in FROZEN_QUERIES:
        text = q["text"]
        text_bytes = len(text.encode("utf-8"))
        if text_bytes > TEXT_BYTES_CAP:
            observation["queries"].append({"q": q["q"], "blocked": "text_over_cap", "text_bytes": text_bytes})
            continue
        _reserve("query", {"q": q["q"], "text_sha256": fragment_hash(text), "text_bytes": text_bytes})
        qdir = os.path.join(HTTP, "queries", q["q"])
        os.makedirs(qdir, exist_ok=True)
        t0 = time.monotonic()
        err = None
        vres = None
        try:
            COUNTERS["post_attempted"] += 1
            vres = vservice.search(VectorSearchRequest(query=text, limit=5, include_global=True))
            COUNTERS["post_used"] += 1
        except Exception as exc:  # noqa: BLE001
            COUNTERS["post_used"] += 1
            err = f"{type(exc).__name__}: {str(exc)[:300]}"
        qlat = round(time.monotonic() - t0, 4)
        rec = recorder.records[-1] if recorder.records else {}
        # full-10 ranking over reused vectors using the SAME query vector
        full_rank = []
        if rec and rec.get("response", {}).get("vector"):
            qv = rec["response"]["vector"]
            cand = vservice._index.search(qv, model=MODEL, limit=10)
            full_rank = [
                {"source_id": c["source_id"], "label": labels.get(c["source_id"]),
                 "kind": c["kind"], "fragment_hash": c["fragment_hash"],
                 "score": round(float(c["score"]), 8)}
                for c in cand
            ]
        # independent recompute
        indep = []
        if rec and rec.get("response", {}).get("vector"):
            qv = rec["response"]["vector"]
            indep = sorted(
                [{"source_id": e["source_id"], "label": labels.get(e["source_id"]),
                  "kind": e["kind"], "score": round(cosine(qv, e["vector"]), 8)}
                 for e in entries],
                key=lambda x: (-x["score"], x["source_id"]),
            )
        # target rank/margin
        target = q["relevant"][0] if q["relevant"] else None
        rank_info = None
        if target and full_rank:
            for i, r in enumerate(full_rank):
                if r["label"] == target:
                    prev = full_rank[i - 1]["score"] if i > 0 else None
                    nxt = full_rank[i + 1]["score"] if i + 1 < len(full_rank) else None
                    rank_info = {
                        "target": target, "rank": i + 1,
                        "score": r["score"],
                        "margin_to_top": round(full_rank[0]["score"] - r["score"], 8),
                        "margin_to_prev": None if prev is None else round(prev - r["score"], 8),
                        "margin_to_next": None if nxt is None else round(r["score"] - nxt, 8),
                    }
                    break
        order_match = None
        if full_rank and indep:
            order_match = [r["source_id"] for r in full_rank] == [r["source_id"] for r in indep]
        entry = {
            "q": q["q"], "text": text, "type": q["type"], "relevant": q["relevant"],
            "source": q["source"], "text_bytes": text_bytes,
            "error": err, "latency": qlat,
            "vector_index_status": (vres or {}).get("index_status"),
            "index_unavailable_reason": (vres or {}).get("index_unavailable_reason"),
            "vector_model": (vres or {}).get("vector_model"),
            "product_hits": (vres or {}).get("hits", []),
            "product_hit_fields": sorted((vres or {}).get("hits", [{}])[0].keys()) if (vres or {}).get("hits") else [],
            "product_stale": (vres or {}).get("stale", []),
            "product_skipped": (vres or {}).get("skipped", []),
            "full_ranking": full_rank,
            "independent_recompute": indep,
            "independent_order_matches_product": order_match,
            "target_rank_info": rank_info,
            "embedding_record": rec,
        }
        observation["queries"].append(entry)
        # raw per-query file (no secrets)
        with open(os.path.join(qdir, "observation.raw.json"), "w") as fh:
            json.dump(entry, fh, ensure_ascii=False, indent=2)
        # raw HTTP response body
        if rec and rec.get("response", {}).get("raw_response"):
            with open(os.path.join(qdir, "embeddings.raw.json"), "w") as fh:
                fh.write(rec["response"]["raw_response"])
        print(f"query {q['q']}: err={err} status={entry['vector_index_status']} "
              f"target_rank={rank_info} order_match={order_match}", flush=True)

    # 6. persist full observation
    observation["counters"] = COUNTERS
    observation["post_log"] = POST_LOG
    with open(os.path.join(EVID, "observation.json"), "w") as fh:
        json.dump(observation, fh, ensure_ascii=False, indent=2)
    print("counters:", COUNTERS)
    return 0


if __name__ == "__main__":
    # Best-effort connect bound: urllib's timeout covers the whole request; a
    # short global socket default additionally bounds connect.  The real backend
    # keeps its own 30s read timeout.
    socket.setdefaulttimeout(CONNECT_TIMEOUT)
    raise SystemExit(main())
