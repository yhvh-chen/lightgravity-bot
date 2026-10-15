#!/usr/bin/env python3
"""Offline dry-run: validate the R5 harness plumbing with a deterministic fake embedding
backend (NO network). Exercises corpus creation, index_source, and search paths; the
lexical baseline runs for real. Does NOT write the real evidence JSON."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.dirname(HERE)
WORKTREE = os.path.dirname(os.path.dirname(PROBE))
sys.path.insert(0, os.path.join(WORKTREE, "backend"))

spec = importlib.util.spec_from_file_location("r5h", os.path.join(HERE, "crossmodal_harness.py"))
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

from lightgravity.sources.vectors.embedder import EmbedResult  # noqa: E402
from lightgravity.sources.vectors.service import VectorSearchService  # noqa: E402


class FakeBackend:
    def __init__(self):
        self._n = 0

    @property
    def model_id(self):
        return "fake-deterministic"

    @property
    def configured(self):
        return True

    def embed(self, item):
        self._n += 1
        seed = item.text if item.text is not None else (item.data if item.data is not None else b"")
        if isinstance(seed, str):
            seed = seed.encode()
        digest = h.hashlib.sha256(h.fragment_hash(seed).encode()).digest()
        vec = tuple(((digest[i % len(digest)] / 255.0) - 0.5) for i in range(768))
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        vec = tuple(x / norm for x in vec)
        kind = "text" if item.text is not None else (item.kind if hasattr(item, "kind") else "image")
        return EmbedResult(vector=vec, model="fake-deterministic", dim=768, input_kind=kind,
                           input_sha256=h.fragment_hash(seed), input_bytes=len(seed),
                           latency_seconds=0.0, prompt_tokens=None, raw_response="")


import shutil  # noqa: E402

if os.path.isdir(h.DATA):
    shutil.rmtree(h.DATA)
store = h.SourceStore(h.DATA)
vservice = VectorSearchService(store, backend=FakeBackend())
lservice = h.LexicalSearchService(store)

for doc in h.CORPUS["text_sources"]["documents"]:
    rec = h.make_source(store, doc["id"], text=doc["text"])
    r = vservice.index_source(rec.source_id)
    assert r.get("indexed") is True, r
print("text sources indexed:", len(h.CORPUS["text_sources"]["documents"]))

for doc_id, path, mt in [("M_IMG_ZH", h.M_IMG_ZH_PATH, "image/jpeg"), ("M_IMG_EN", h.M_IMG_EN_PATH, "image/png")]:
    rec = h.make_source(store, doc_id, media=(os.path.basename(path), mt, path))
    r = vservice.index_source(rec.source_id)
    assert r.get("indexed") is True, (doc_id, r)
    assert r.get("kinds") == ["image"], r
print("images indexed: 2")

for doc_id, ogg, wav, mt in [("M_AUD_ZH", h.M_AUD_ZH_OGG, h.M_AUD_ZH_WAV, "audio/wav"),
                             ("M_AUD_DIQIU", h.M_AUD_DIQIU_OGG, h.M_AUD_DIQIU_WAV, "audio/wav")]:
    assert os.path.isfile(wav), wav
    stored = "voice_zh_language_16k.wav" if doc_id == "M_AUD_ZH" else "voice_zh_diqiu_16k.wav"
    rec = h.make_source(store, doc_id, media=(stored, mt, wav))
    r = vservice.index_source(rec.source_id)
    assert r.get("indexed") is True, (doc_id, r)
    assert r.get("kinds") == ["audio"], r
print("audio indexed: 2 (PCM WAV)")

lservice.rebuild()
for q in h.CORPUS["queries"]:
    vres = vservice.search(h.VectorSearchRequest(query=q["text"], limit=5, include_global=True))
    lhs = lres = lservice.search(h.SearchRequest(query=q["text"], limit=5, include_global=True))
    print(f"  {q['q']}: vector_hits={len(vres.get('hits', []))} lexical_hits={len(lres.get('hits', []))}")
print("OFFLINE DRY-RUN OK (no network)")
