#!/usr/bin/env python3
"""Materials Vector Quality R4 — real cross-modal (text->image, text->audio) LG-037
retrieval harness over the UNMODIFIED product path.

Real product path used:
  real ``SourceStore`` -> real ``ContentStore`` formal text (distractors) -> the real
  ``VectorSearchService`` with the real ``OpenAICompatEmbeddingBackend``
  (``embeddinggemma-2-Q8_0``) and the real ``LexicalSearchService`` baseline.
Media (image/audio) is embedded **as media** (never fabricated into text).

Frozen plan: PLAN.md (commit ff6615e). Frozen labels: corpus.json.
Budget: 7 text + 2 image + 1 audio + 5 queries = 15 POST (cap 16), serial, retry 0, timeout 90s.
Writes only under evidence/ and private/.

Env: BASE_URL / MODEL may be overridden; defaults are the frozen authorized values.
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
ROOT = os.path.dirname(HERE)  # .../probes/materials-vector-quality-r4-20261016
PROBE = ROOT
WORKTREE = os.path.dirname(os.path.dirname(PROBE))  # .../materials-vector-quality-r4-20261016
PRIV = os.path.join(PROBE, "private")
DATA = os.path.join(PRIV, "vector-data")
EVID = os.path.join(PROBE, "evidence")

sys.path.insert(0, os.path.join(WORKTREE, "backend"))

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

BASE_URL = os.environ.get("LG_R4_BASE_URL", "http://192.168.8.12:11434")
MODEL = os.environ.get("LG_R4_MODEL", "embeddinggemma-2-Q8_0")
CORPUS = json.load(open(os.path.join(PROBE, "corpus.json")))

# preserved real fixtures (read-only, no download, no synthesis)
M_IMG_ZH_PATH = "/home/yhvh/code/lightgravity-bot-worktrees/lg035-truth-prep/probes/lg035/TRUTH-PREP/samples/private/lg035_truth_zh_laojielao_p10.jpg"
M_IMG_EN_PATH = os.path.join(WORKTREE, "probes/lg035/fixtures/phototest-rotated-L.png")
M_AUD_ZH_PATH = os.path.join(WORKTREE, "probes/lg039/evidence/real_voice_chinese_language-1.ogg")
# optional PCM transcode produced only if the raw container is rejected
M_AUD_ZH_WAV = os.path.join(PRIV, "real_voice_chinese_language-1.16k.pcm.wav")

POST_LOG: list[dict] = []
COUNTERS = {"post_used": 0, "post_attempted": 0, "retries": 0, "media_bytes": 0, "audio_seconds": 0.0}


class BudgetExceeded(RuntimeError):
    pass


def _ulid(label: str) -> str:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    d = hashlib.sha256(label.encode()).digest()
    v = int.from_bytes(d[:16], "big")
    chars = []
    for _ in range(26):
        chars.append(alphabet[v % 32])
        v //= 32
    return "source_" + "".join(reversed(chars))


def make_source(store: SourceStore, doc_id: str, *, text: str | None = None,
                media: tuple[str, str, str] | None = None):
    """Create a source. If ``media`` is (filename, media_type, path) persist the original.
    If ``text`` is given, write it as the formal text (so it also yields a text vector).
    """
    entity_id = _ulid(doc_id)
    digest = fragment_hash(text.encode("utf-8")) if text is not None else None
    entity = {
        "schema": "lightgravity.bot/v1", "kind": "source", "id": entity_id,
        "title": doc_id, "title_origin": "user", "status": "extracted", "revision": 0,
        "scope": {"task_ref": None, "project_ref": None, "inbox_ref": None},
        "origin": {"kind": "upload", "external_ref": None, "fetched": False},
        "content_hash": digest or fragment_hash(doc_id.encode("utf-8")),
        "stat_revision": None, "source_version": 1,
        "original": {"path": None, "media_type": None, "bytes": None, "archived_at": None},
        "derivatives": [],
        "formal": {"path": None, "revision": None, "edited_by": None},
        "index": {"lexical": "not_indexed", "lexical_hash": None, "vector": "disabled", "vector_model": None},
        "receipt_ref": None, "created_at": None, "updated_at": None,
    }
    rec = store.create_source(entity_id, entity)
    if text is not None:
        ContentStore(source_root=store.source_dir(entity_id)).write_formal(
            text, edited_by="materials-vector-quality-r4", expected_revision=None
        )
    if media is not None:
        filename, media_type, src_path = media
        data = Path(src_path).read_bytes()
        store.persist_original(entity_id, filename, data)
        cur = store.read_source(entity_id)
        store.update_source(entity_id, {"original": {"path": f"original/{filename}",
                              "media_type": media_type, "bytes": len(data), "archived_at": None}},
                              expected_revision=cur.entity["revision"])
    return store.read_source(entity_id)


def index(service: VectorSearchService, source_id: str, kind_tag: str, extra: dict) -> dict:
    if COUNTERS["post_used"] + 1 > 16:
        raise BudgetExceeded(f"POST budget would exceed: {COUNTERS['post_used']}")
    t0 = time.time()
    COUNTERS["post_attempted"] += 1
    try:
        res = service.index_source(source_id)
        COUNTERS["post_used"] += 1
        entry = {"kind": kind_tag, "source_id": source_id, "indexed": res.get("indexed"),
                 "vector": res.get("vector"), "dim": res.get("dim"),
                 "vector_model": res.get("vector_model"), "kinds": res.get("kinds"),
                 "latency": round(time.time() - t0, 3), **extra}
    except Exception as exc:  # noqa: BLE001
        COUNTERS["post_used"] += 1
        entry = {"kind": kind_tag, "source_id": source_id, "error": type(exc).__name__,
                 "msg": str(exc)[:300], "latency": round(time.time() - t0, 3), **extra}
    POST_LOG.append(entry)
    print(f"index {kind_tag} {extra.get('doc', '')}: {entry}", flush=True)
    return entry


def main() -> int:
    if os.path.isdir(DATA):
        shutil.rmtree(DATA)
    store = SourceStore(DATA)
    backend = OpenAICompatEmbeddingBackend(
        base_url=BASE_URL, model=MODEL,
        default_timeout_seconds=90.0, cold_timeout_seconds=90.0,
    )
    vservice = VectorSearchService(store, backend=backend)
    lservice = LexicalSearchService(store)

    results: dict = {"queries": [], "index": [], "counters": COUNTERS, "base_url": BASE_URL,
                     "model": MODEL, "media": {}}

    # ---------------- text distractors: 7 POSTs ----------------
    id2doc: dict[str, str] = {}
    for doc in CORPUS["text_distractors"]["documents"]:
        rec = make_source(store, doc["id"], text=doc["text"])
        id2doc[rec.source_id] = doc["id"]
        e = index(vservice, rec.source_id, "corpus_text",
                  {"doc": doc["id"], "text_sha256": fragment_hash(doc["text"])})
        results["index"].append(e)

    # ---------------- image media: 2 POSTs ----------------
    for doc_id, path, mt, fname in [
        ("M_IMG_ZH", M_IMG_ZH_PATH, "image/jpeg", "laojielao_p10.jpg"),
        ("M_IMG_EN", M_IMG_EN_PATH, "image/png", "phototest-rotated-L.png"),
    ]:
        data = Path(path).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        COUNTERS["media_bytes"] += len(data)
        rec = make_source(store, doc_id, media=(fname, mt, path))
        id2doc[rec.source_id] = doc_id
        e = index(vservice, rec.source_id, "media_image",
                  {"doc": doc_id, "input_path": path, "input_sha256": sha, "bytes": len(data), "media_type": mt})
        e["input_sha256"] = sha
        results["index"].append(e)
        results["media"][doc_id] = {"input_path": path, "input_sha256": sha, "bytes": len(data),
                                    "media_type": mt, "license_truth": CORPUS["provenance"][doc_id]}

    # ---------------- audio media: 1 POST (raw ogg first) ----------------
    aud_path = M_AUD_ZH_PATH
    aud_mt = "audio/ogg"
    aud_bytes = Path(aud_path).read_bytes()
    aud_sha = hashlib.sha256(aud_bytes).hexdigest()
    COUNTERS["media_bytes"] += len(aud_bytes)
    rec = make_source(store, "M_AUD_ZH", media=("real_voice_chinese_language-1.ogg", aud_mt, aud_path))
    id2doc[rec.source_id] = "M_AUD_ZH"
    e = index(vservice, rec.source_id, "media_audio_raw_ogg",
              {"doc": "M_AUD_ZH", "input_path": aud_path, "input_sha256": aud_sha,
               "bytes": len(aud_bytes), "media_type": aud_mt})
    e["input_sha256"] = aud_sha
    results["index"].append(e)
    results["media"]["M_AUD_ZH"] = {"input_path": aud_path, "input_sha256": aud_sha,
                                    "bytes": len(aud_bytes), "media_type": aud_mt,
                                    "license_truth": CORPUS["provenance"]["M_AUD_ZH"]}
    audio_ok = e.get("indexed") is True and e.get("kinds") == ["audio"]

    if not audio_ok:
        # Permitted transform: lossless container/PCM conversion only (no synthesis/ASR).
        import subprocess
        os.makedirs(PRIV, exist_ok=True)
        cmd = ["ffmpeg", "-y", "-i", aud_path, "-ac", "1", "-ar", "16000", "-t", "30",
               "-c:a", "pcm_s16le", M_AUD_ZH_WAV]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        results["media"]["M_AUD_ZH_transcode"] = {"cmd": cmd, "returncode": proc.returncode,
                                                   "stderr_tail": proc.stderr[-500:]}
        if proc.returncode != 0 or not os.path.isfile(M_AUD_ZH_WAV):
            results["media"]["M_AUD_ZH"]["status"] = "audio_unusable_no_synthesis"
        else:
            wav = Path(M_AUD_ZH_WAV).read_bytes()
            wsha = hashlib.sha256(wav).hexdigest()
            COUNTERS["media_bytes"] += len(wav)
            # re-index: replace the audio source original with the PCM wav, then index
            cur = store.read_source(rec.source_id)
            store.update_source(rec.source_id, {"original": {"path": "original/voice16k.wav",
                                  "media_type": "audio/wav", "bytes": len(wav), "archived_at": None}},
                                  expected_revision=cur.entity["revision"])
            store.persist_original(rec.source_id, "voice16k.wav", wav)
            e2 = index(vservice, rec.source_id, "media_audio_pcm_wav",
                       {"doc": "M_AUD_ZH", "input_path": M_AUD_ZH_WAV, "input_sha256": wsha,
                        "bytes": len(wav), "media_type": "audio/wav"})
            e2["input_sha256"] = wsha
            results["index"].append(e2)
            results["media"]["M_AUD_ZH"].update({"pcm_wav_sha256": wsha, "pcm_wav_bytes": len(wav),
                                                  "pcm_wav_path": M_AUD_ZH_WAV})

    # ---------------- queries: 5 POSTs ----------------
    lservice.rebuild()  # offline lexical index (no network)
    for q in CORPUS["queries"]:
        if COUNTERS["post_used"] + 1 > 16:
            raise BudgetExceeded("query POST budget exceeded")
        t0 = time.time()
        try:
            vres = vservice.search(VectorSearchRequest(query=q["text"], limit=5, include_global=True))
            v_err = None
        except Exception as exc:  # noqa: BLE001
            vres, v_err = None, f"{type(exc).__name__}: {str(exc)[:200]}"
        COUNTERS["post_used"] += 1
        COUNTERS["post_attempted"] += 1
        lres = lservice.search(SearchRequest(query=q["text"], limit=5, include_global=True))
        v_hits = [(h.get("source_id"), h.get("title"), h.get("kind")) for h in (vres or {}).get("hits", [])]
        l_hits = [(h.get("source_id"), h.get("title")) for h in lres.get("hits", [])]
        entry = {"q": q["q"], "text": q["text"], "type": q["type"], "relevant": q["relevant"],
                 "vector_error": v_err, "vector_index_status": (vres or {}).get("index_status"),
                 "vector_hits": v_hits, "lexical_hits": l_hits, "latency": round(time.time() - t0, 3)}
        POST_LOG.append({"kind": "query", "q": q["q"], "error": v_err,
                         "latency": entry["latency"], "status": entry["vector_index_status"]})
        results["queries"].append(entry)
        print(f"query {q['q']} [{q['type']}] v={v_hits} l={l_hits} err={v_err}", flush=True)

    # ---------------- metrics ----------------
    def metrics(hits_fn):
        out: dict = {}
        for k in CORPUS["k_values"]:
            rec_ = []
            for q in CORPUS["queries"]:
                if not q["type"].startswith("positive"):
                    continue
                hits = [id2doc.get(sid) for sid, _t, *_ in hits_fn(q["q"])[:k]]
                hits = [h for h in hits if h is not None]
                rel = set(q["relevant"])
                rec_.append(len(rel & set(hits)) / len(rel) if rel else None)
            out[f"recall@{k}"] = round(sum(x for x in rec_ if x is not None) / len(rec_), 4) if rec_ else None
        mrr, top1 = [], []
        for q in CORPUS["queries"]:
            if not q["type"].startswith("positive"):
                continue
            hits = [id2doc.get(sid) for sid, _t, *_ in hits_fn(q["q"])]
            rel = set(q["relevant"])
            rank = next((i + 1 for i, h in enumerate(hits) if h in rel), None)
            mrr.append(1 / rank if rank else 0.0)
            top1.append(1.0 if hits and hits[0] in rel else 0.0)
        out["mrr"] = round(sum(mrr) / len(mrr), 4) if mrr else None
        out["top1_accuracy"] = round(sum(top1) / len(top1), 4) if top1 else None
        neg = {}
        for q in CORPUS["queries"]:
            if q["type"] != "negative_control":
                continue
            hits = [h for h in hits_fn(q["q"]) if h is not None]
            neg[q["q"]] = {"ranked_false_hits": [id2doc.get(s, s) for s, *_ in hits], "count": len(hits)}
        out["negative_controls"] = neg
        return out

    vhits = {e["q"]: e["vector_hits"] for e in results["queries"]}
    lhits = {e["q"]: e["lexical_hits"] for e in results["queries"]}
    results["vector_metrics"] = metrics(lambda q: vhits.get(q, []))
    results["lexical_metrics"] = metrics(lambda q: lhits.get(q, []))
    results["id2doc"] = id2doc
    results["labels_authorship"] = CORPUS["labels_authorship"]
    results["post_log"] = POST_LOG

    os.makedirs(EVID, exist_ok=True)
    with open(os.path.join(EVID, "crossmodal_results.json"), "w") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print("vector_metrics:", json.dumps(results["vector_metrics"], ensure_ascii=False))
    print("lexical_metrics:", json.dumps(results["lexical_metrics"], ensure_ascii=False))
    print("counters:", COUNTERS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
