"""LG-037 / materials-retry-r2 embedding smoke — POST #2.

Uses the PRODUCT OpenAICompatEmbeddingBackend unchanged. Bounded: one request,
single input (real Chinese text), concurrency 1, retries 0, timeout 90 s.
Records finite / nonzero / dimension / model / input sha. Vector is NOT a
quality claim.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from lightgravity.sources.vectors.embedder import (  # noqa: E402
    EmbedInput,
    EmbeddingServiceError,
    EmbeddingTimeout,
    OpenAICompatEmbeddingBackend,
)

HERE = Path(__file__).resolve().parent
BASE = "http://192.168.8.12:11434"
MODEL = "embeddinggemma-2-Q8_0"

# Real Chinese sentence (from the Z1 human truth content domain; a real string,
# not a synthetic template). Single input batch.
TEXT = "其功也予生平篤信老氏之學說如此年來因更覃思舊業萃古今注老數十百家而遍肄之"

backend = OpenAICompatEmbeddingBackend(
    base_url=BASE,
    model=MODEL,
    default_timeout_seconds=90.0,
    cold_timeout_seconds=120.0,
)
t0 = time.monotonic()
try:
    res = backend.embed(EmbedInput.text_input(TEXT))
except (EmbeddingTimeout, EmbeddingServiceError) as exc:
    print(json.dumps({"post": 2, "outcome": "error", "type": type(exc).__name__,
                      "detail": str(exc), "elapsed_s": time.monotonic() - t0}, ensure_ascii=False))
    sys.exit(2)

vec = res.vector
finite = all(math.isfinite(x) for x in vec)
nonzero = any(x != 0.0 for x in vec)
norm = math.sqrt(sum(x * x for x in vec))
out = {
    "post": 2,
    "endpoint": backend.endpoint,
    "model": res.model,
    "dim": res.dim,
    "input_kind": res.input_kind,
    "input_sha256": res.input_sha256,
    "input_bytes": res.input_bytes,
    "latency_seconds": round(res.latency_seconds, 3),
    "prompt_tokens": res.prompt_tokens,
    "finite": finite,
    "nonzero": nonzero,
    "l2_norm": round(norm, 6),
    "first8": [round(x, 6) for x in vec[:8]],
}
(HERE / "embedding_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(json.dumps(out, ensure_ascii=False))
assert res.dim == len(vec)
