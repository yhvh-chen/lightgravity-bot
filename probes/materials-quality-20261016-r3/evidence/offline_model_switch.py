#!/usr/bin/env python3
"""Materials Quality R3 — OFFLINE model-switch / dimension / rebuild checks.

Uses the FROZEN real embedding responses already on disk (768-dim, model
`embeddinggemma-2-Q8_0`) in private/vector-data/sources-index/vectors/vectors.jsonl.
**No network. No model-switch POST is made.** This only verifies the product
cache's compatibility guards against the frozen real vectors — it does NOT feign
an actual alternate-model validation (which would need a real second model).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "private", "vector-data")
sys.path.insert(0, os.path.join(ROOT, "backend"))

from lightgravity.sources.vectors.index import VectorIndex, VECTOR_CACHE_VERSION  # noqa: E402

idx = VectorIndex(os.path.join(DATA, "sources-index", "vectors"))
header = idx.header()
stats = idx.stats()
entries = idx.all_entries()
real = entries[0] if entries else None
query = list(real.vector) if real else []

checks = {
    "cache_header": header,
    "stats": stats,
    "canonical_model": header.get("model"),
    "canonical_dim": header.get("dim"),
    "is_compatible_same_model": idx.is_compatible(model="embeddinggemma-2-Q8_0"),
    "is_compatible_other_model": idx.is_compatible(model="some-other-model-v9"),
    "same_model_search_returns": len(idx.search(query, model="embeddinggemma-2-Q8_0", limit=5)),
    "other_model_search_returns": len(idx.search(query, model="some-other-model-v9", limit=5)),
    "cache_version_matches": header.get("cache_version") == VECTOR_CACHE_VERSION,
    "self_query_top1": idx.search(query, model="embeddinggemma-2-Q8_0", limit=1)[0]["source_id"] if query and idx.search(query, model="embeddinggemma-2-Q8_0", limit=1) else None,
    "real_entry_source_id": real.source_id if real else None,
}
with open(os.path.join(HERE, "offline_model_switch.json"), "w") as fh:
    json.dump(checks, fh, ensure_ascii=False, indent=2)
print(json.dumps(checks, ensure_ascii=False, indent=2))
