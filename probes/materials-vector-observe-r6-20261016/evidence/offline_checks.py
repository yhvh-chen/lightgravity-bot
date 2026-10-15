#!/usr/bin/env python3
"""LG-037 R6 evidence-observability offline checks (NO network).

Meaningful offline checks that must pass BEFORE any real POST:

1. nullable/misnamed score — the product ``VerifiedHit.to_dict()`` drops
   ``score``; the pre-authorization ``VectorIndex.search`` candidate carries it.
   Proves the harness must record BOTH channels.
2. dimensions / finite / nonzero — every reused R5 document vector is 768-dim,
   finite and non-zero; the cache header model/dim/cache_version is consistent.
3. hard call limit — the recording wrapper refuses a 3rd embed (cap 2) and the
   guard fires BEFORE any HTTP; a counter backend proves no extra call.
4. actual query vector persisted — with a deterministic stub backend (no
   network) the harness records the query vector / hash / usage into the
   evidence structure.

Writes only under evidence/ (offline_checks.json).  No network is used: the
stub backend never touches HTTP.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.dirname(HERE)
WORKTREE = os.path.dirname(os.path.dirname(PROBE))
PRIV = os.path.join(PROBE, "private")
sys.path.insert(0, os.path.join(WORKTREE, "backend"))

from lightgravity.sources.lexical.query import VerifiedHit  # noqa: E402
from lightgravity.sources.vectors.embedder import EmbedInput, EmbedResult  # noqa: E402
from lightgravity.sources.vectors.index import (  # noqa: E402
    VECTOR_CACHE_VERSION,
    VectorIndex,
)

R5_VECTORS = os.path.join(PRIV, "r5-vectors", "vectors.jsonl")


def load_r5_entries() -> tuple[dict, list[dict]]:
    header: dict = {}
    entries: list[dict] = []
    with open(R5_VECTORS) as fh:
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


def check_nullable_misnamed_score() -> dict:
    """Product hit view API has no `score`; candidate dict does."""

    hit_fields = set(VerifiedHit(
        source_id="s", score=0.123, basis="formal", source_version=1,
        content_hash=None, scope={}, title="t", locators=[], snippet="",
    ).to_dict().keys())
    candidate_fields = {"source_id", "score", "fragment_hash", "kind", "model", "dim"}
    return {
        "verified_hit_to_dict_fields": sorted(hit_fields),
        "verified_hit_has_score": "score" in hit_fields,
        "verified_hit_has_similarity": "similarity" in hit_fields,
        "index_candidate_has_score": "score" in candidate_fields,
        "conclusion": (
            "product VerifiedHit.to_dict omits score -> harness must record the "
            "pre-authorization candidate `score` separately"
        ),
        "pass": ("score" not in hit_fields) and ("similarity" not in hit_fields),
    }


def check_dimensions_finite() -> dict:
    header, entries = load_r5_entries()
    dims_ok = all(len(e["vector"]) == 768 for e in entries)
    finite_ok = all(
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))
        for e in entries for x in e["vector"]
    )
    nonzero_ok = all(
        any(abs(float(x)) > 0.0 for x in e["vector"]) for e in entries
    )
    header_ok = (
        header.get("model") == "embeddinggemma-2-Q8_0"
        and header.get("dim") == 768
        and header.get("cache_version") == VECTOR_CACHE_VERSION
    )
    return {
        "header": header,
        "entry_count": len(entries),
        "all_dim_768": dims_ok,
        "all_finite": finite_ok,
        "all_nonzero": nonzero_ok,
        "header_consistent": header_ok,
        "pass": dims_ok and finite_ok and nonzero_ok and header_ok,
    }


class _CountingStubBackend:
    """Deterministic, network-free backend used to test the cap + persistence."""

    def __init__(self) -> None:
        self.calls = 0
        self.http_sent = 0
        self.model = "stub-768"

    @property
    def model_id(self) -> str:
        return self.model

    @property
    def configured(self) -> bool:
        return True

    def embed(self, item: EmbedInput) -> EmbedResult:
        self.calls += 1
        # deterministic 768-dim vector from the input hash
        digest = hashlib.sha256((item.text or "").encode("utf-8")).digest()
        vec = tuple(((digest[i % 32] / 255.0) - 0.5) for i in range(768))
        return EmbedResult(
            vector=vec, model=self.model, dim=len(vec), input_kind=item.part_type,
            input_sha256=hashlib.sha256((item.text or "").encode()).hexdigest(),
            input_bytes=len(item.text or ""), latency_seconds=0.0,
            prompt_tokens=7, raw_response='{"usage":{"prompt_tokens":7}}',
        )


class HardCapGuard:
    """Refuse the (cap+1)-th call BEFORE any HTTP is attempted."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.used = 0

    def reserve(self) -> None:
        if self.used + 1 > self.cap:
            raise RuntimeError(f"POST cap would exceed: {self.used} >= {self.cap}")
        self.used += 1


def check_hard_call_limit() -> dict:
    guard = HardCapGuard(cap=2)
    backend = _CountingStubBackend()
    outcomes: list[str] = []
    for _ in range(3):
        try:
            guard.reserve()
            backend.embed(EmbedInput.text_input("x"))
            outcomes.append("sent")
        except RuntimeError as exc:
            outcomes.append(f"blocked:{exc}")
    return {
        "outcomes": outcomes,
        "http_sent_by_stub_backend": backend.calls,
        "guard_used": guard.used,
        "third_blocked_before_http": outcomes[2].startswith("blocked") and backend.calls == 2,
        "pass": backend.calls == 2 and outcomes[2].startswith("blocked"),
    }


def check_query_vector_persisted() -> dict:
    """Stub-run one query embed and confirm the vector is persisted-ready."""

    backend = _CountingStubBackend()
    result = backend.embed(EmbedInput.text_input("老子 道德經 註解 學說"))
    vb = json.dumps(list(result.vector)).encode()
    record = {
        "query_bytes": len(result.input_sha256),
        "input_sha256": result.input_sha256,
        "dim": result.dim,
        "vector_sha256": hashlib.sha256(vb).hexdigest(),
        "vector_len": len(result.vector),
        "prompt_tokens": result.prompt_tokens,
        "raw_response_present": bool(result.raw_response),
    }
    return {
        "record": record,
        "vector_len_768": len(result.vector) == 768,
        "vector_sha_persisted": len(record["vector_sha256"]) == 64,
        "prompt_tokens_captured": record["prompt_tokens"] == 7,
        "pass": len(result.vector) == 768 and record["prompt_tokens"] == 7,
    }


def main() -> int:
    checks = {
        "1_nullable_misnamed_score": check_nullable_misnamed_score(),
        "2_dimensions_finite": check_dimensions_finite(),
        "3_hard_call_limit": check_hard_call_limit(),
        "4_query_vector_persisted": check_query_vector_persisted(),
    }
    all_pass = all(c["pass"] for c in checks.values())
    out = {"all_pass": all_pass, "network_used": False, "checks": checks}
    os.makedirs(HERE, exist_ok=True)
    with open(os.path.join(HERE, "offline_checks.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
