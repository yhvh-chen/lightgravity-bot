#!/usr/bin/env python3
"""LG-037 R7 offline meaningful checks (NO network).

Verifies the recording wrapper BEFORE any real call:

  1. failure-path recording: an injected stub backend that raises records the
     error (fixes R6's first-run "only success recorded" defect);
  2. hard cap enforced BEFORE HTTP: 3rd reserve() raises, stub sees only 2 calls;
  3. actual query vector / sha256 / dim / prompt_tokens persisted on success;
  4. two-layer score separation: product ``VerifiedHit.to_dict()`` has no
     ``score``; ``VectorIndex.search()`` candidate dict DOES carry ``score``;
  5. R5 reused document vectors: 10 entries / 768-dim / finite / nonzero and
     header (model/dim/cache_version) consistent.

Writes only under evidence/.  No socket is opened.
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
EVID = os.path.join(PROBE, "evidence")
R5_VECTORS_SRC = (
    "/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016"
    "/probes/materials-vector-r5-20261016/private/vector-data/sources-index/vectors/vectors.jsonl"
)

sys.path.insert(0, os.path.join(WORKTREE, "backend"))

from lightgravity.sources.vectors.embedder import (  # noqa: E402
    EmbedInput,
    EmbedResult,
)
from lightgravity.sources.vectors.index import VectorIndex  # noqa: E402

RESULTS: dict = {"checks": [], "all_pass": True}


def check(name: str, passed: bool, detail: object) -> None:
    RESULTS["checks"].append({"name": name, "passed": bool(passed), "detail": detail})
    if not passed:
        RESULTS["all_pass"] = False
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {json.dumps(detail, ensure_ascii=False)[:300]}")


# --- reuse the R7 harness guard/reserve logic (import-free of network) ---------
sys.path.insert(0, HERE)
import r7_harness as H  # noqa: E402


class StubBackend:
    """Deterministic offline backend; raises on demand, counts calls."""

    def __init__(self, *, raise_on: int | None = None) -> None:
        self.calls = 0
        self._raise_on = raise_on

    @property
    def model_id(self) -> str:
        return "stub-model"

    @property
    def configured(self) -> bool:
        return True

    def embed(self, item: EmbedInput) -> EmbedResult:
        self.calls += 1
        if self._raise_on is not None and self.calls == self._raise_on:
            raise RuntimeError("stub deliberate failure")
        vec = tuple([0.5] * 768)
        return EmbedResult(
            vector=vec, model="stub-model", dim=768, input_kind=item.part_type,
            input_sha256=hashlib.sha256((item.text or "").encode()).hexdigest(),
            input_bytes=len((item.text or "").encode()),
            latency_seconds=0.001, prompt_tokens=7,
            raw_response=json.dumps({"data": [{"embedding": list(vec)}],
                                     "usage": {"prompt_tokens": 7, "total_tokens": 7}}),
        )


def main() -> int:
    os.makedirs(EVID, exist_ok=True)

    # ---- 1. failure-path recording -------------------------------------------
    stub = StubBackend(raise_on=1)
    recorder = H.RecordingBackend(stub)
    try:
        recorder.embed(EmbedInput.text_input("fail path"))
    except RuntimeError:
        pass
    rec = recorder.records[-1] if recorder.records else {}
    check("failure_path_recorded", bool(rec) and rec.get("response") is None
          and rec.get("error_class") == "RuntimeError",
          {"records": len(recorder.records), "error_class": (rec or {}).get("error_class"),
           "error": (rec or {}).get("error")})

    # ---- 2. hard cap before HTTP ---------------------------------------------
    H.COUNTERS.update({"post_used": 0, "post_attempted": 0})
    H.LEDGER = os.path.join(EVID, "offline_cap_probe.jsonl")
    if os.path.exists(H.LEDGER):
        os.remove(H.LEDGER)
    stub2 = StubBackend()
    rec2 = H.RecordingBackend(stub2)
    # emulate the harness reserve+call loop with cap=2
    emitted = 0
    cap_error = False
    for i in range(3):
        try:
            H._reserve("offline", {"i": i})
            rec2.embed(EmbedInput.text_input(f"q{i}"))
            H.COUNTERS["post_used"] += 1
            emitted += 1
        except H.HardCapError:
            cap_error = True
            break
    check("hard_cap_before_http", cap_error and emitted == 2 and stub2.calls == 2,
          {"cap_error": cap_error, "emitted": emitted, "stub_calls": stub2.calls})

    # ---- 3. query vector persisted on success --------------------------------
    stub3 = StubBackend()
    rec3 = H.RecordingBackend(stub3)
    res = rec3.embed(EmbedInput.text_input("persist me"))
    r = rec3.records[-1]
    check("query_vector_persisted",
          r["response"]["dim"] == 768 and len(r["response"]["vector"]) == 768
          and r["response"]["usage"] and res.prompt_tokens == 7,
          {"dim": r["response"]["dim"], "len": len(r["response"]["vector"]),
           "usage": r["response"]["usage"]})

    # ---- 4. two-layer score separation ---------------------------------------
    from lightgravity.sources.lexical.query import VerifiedHit  # noqa: E402
    fields = set(VerifiedHit(
        source_id="s", score=0.0, basis="formal", source_version=1,
        content_hash=None, scope={}, title="t", locators=[], snippet="x",
        verified=True, stale=False, reason=None,
    ).to_dict().keys())
    check("verified_hit_has_no_score", "score" not in fields and "similarity" not in fields,
          {"fields": sorted(fields)})
    cand_fields = _candidate_fields()
    check("candidate_has_score", "score" in cand_fields, {"candidate_fields": sorted(cand_fields)})

    # ---- 5. reused R5 vectors dims/finite ------------------------------------
    header, entries = H.load_r5_entries()
    ok = header.get("model") == "embeddinggemma-2-Q8_0" and header.get("dim") == 768 \
        and header.get("cache_version") == 1 and len(entries) == 10
    finite = all(len(e["vector"]) == 768 and all(math.isfinite(float(x)) for x in e["vector"])
                 and any(abs(float(x)) > 0 for x in e["vector"]) for e in entries)
    check("r5_vectors_header_and_dims", ok and finite,
          {"header": header, "entries": len(entries), "all_finite_nonzero": finite})

    with open(os.path.join(EVID, "offline_checks.json"), "w") as fh:
        json.dump(RESULTS, fh, ensure_ascii=False, indent=2)
    print("all_pass:", RESULTS["all_pass"])
    return 0 if RESULTS["all_pass"] else 1


def _candidate_fields() -> set:
    """Probe VectorIndex.search candidate dict keys with a tiny in-memory index."""
    import tempfile
    from lightgravity.sources.vectors.index import VectorEntry, VECTOR_CACHE_VERSION
    with tempfile.TemporaryDirectory() as td:
        idx = VectorIndex(os.path.join(td, "vectors"))
        e = VectorEntry(source_id="s", source_version=1, content_hash=None, basis="formal",
                        kind="text", model="embeddinggemma-2-Q8_0", dim=3,
                        cache_version=VECTOR_CACHE_VERSION, fragment_hash="f", vector=(1.0, 0.0, 0.0),
                        title="t", locators=(), text="x")
        idx.replace_all([e], model="embeddinggemma-2-Q8_0", dim=3)
        cands = idx.search((1.0, 0.0, 0.0), model="embeddinggemma-2-Q8_0", limit=1)
        return set(cands[0].keys()) if cands else set()


if __name__ == "__main__":
    raise SystemExit(main())
