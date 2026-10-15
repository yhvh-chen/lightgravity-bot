#!/usr/bin/env python3
"""LG-037 R6 — full 10-candidate ranking table for Q_IMG_ZH from PRESERVED data.

Honest scope:
  * The R4/R5 harnesses did NOT persist query vectors (the `score` field is null
    in crossmodal_results.json) and did not capture raw /v1/embeddings responses.
    Therefore raw query->doc cosine scores CANNOT be recomputed offline.
  * What IS preserved: the full 768-d DOCUMENT vectors (R4 and R5), the full
    ordinal top-5 rankings, the corpus, and all input hashes. We reproduce the
    ranking STRUCTURE and the document-side geometry, and we mark every unknown
    as UNKNOWN — no invented scores.

Run: python3 full_ranking_q_img_zh.py
"""
from __future__ import annotations
import json, math
from pathlib import Path

BASE = Path("/home/yhvh/code/lightgravity-bot-worktrees")
R4V = BASE / "materials-vector-quality-r4-20261016/probes/materials-vector-quality-r4-20261016/private/vector-data/sources-index/vectors/vectors.jsonl"
R5V = BASE / "materials-vector-r5-20261016/probes/materials-vector-r5-20261016/private/vector-data/sources-index/vectors/vectors.jsonl"
R4R = BASE / "materials-vector-quality-r4-20261016/probes/materials-vector-quality-r4-20261016/evidence/crossmodal_results.json"
R5R = BASE / "materials-vector-r5-20261016/probes/materials-vector-r5-20261016/evidence/crossmodal_results.json"
OUT = Path(__file__).resolve().parent / "full_ranking_q_img_zh.json"


def load_vecs(p):
    out = {}
    for line in p.read_text().splitlines():
        o = json.loads(line)
        if o.get("record") == "header":
            continue
        out[o["title"]] = o
    return out


def cos(a, b):
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def q_hits(results_path, qname):
    d = json.loads(results_path.read_text())
    q = next(x for x in d["queries"] if x["q"] == qname)
    return q


r4v, r5v = load_vecs(R4V), load_vecs(R5V)
q4 = q_hits(R4R, "Q_IMG_ZH")
q5 = q_hits(R5R, "Q_IMG_ZH")

print("Q_IMG_ZH query text:", repr(q4["text"]), "(R4 == R5:", q4["text"] == q5["text"], ")")
print("model:", json.loads(R4R.read_text())["model"])
print()
print("R4 recorded top-5 (score field is null => NOT preserved):")
for rank, h in enumerate(q4["vector_hits"], 1):
    print(f"  {rank}. {h[1]:14s} source_id={h[0]} score={h[3]!r}")
print("R5 recorded top-5:")
for rank, h in enumerate(q5["vector_hits"], 1):
    print(f"  {rank}. {h[1]:14s} source_id={h[0]} score={h[3]!r}")

print()
print("ALL 10 candidates (M_IMG_ZH is NOT in the R5 top-5; rank among all 10 is UNKNOWN").__add__("")")
print("because query vectors/scores were not preserved -> CANNOT RECOMPUTE (no invented score).")
print()
print("Document-side geometry preserved for all 10 R5 candidates (cosine to M_IMG_ZH):")
zh = r5v["M_IMG_ZH"]["vector"]
rows = []
for t, e in r5v.items():
    c = cos(zh, e["vector"])
    rows.append((t, e["kind"], c))
for t, k, c in sorted(rows, key=lambda r: -r[2]):
    tag = "  <-- TARGET" if t == "M_IMG_ZH" else ""
    print(f"  {t:14s} kind={k:6s} cos_to_M_IMG_ZH={c:.6f}{tag}")

print()
print("Distance of each R5 text candidate to the query's Laozi cluster {D1,D2,D3}:")
for t in ("D1", "D2", "D3", "T_NORTHWIND", "D5", "D6", "M_IMG_ZH"):
    e = r5v[t]["vector"]
    m = sum(cos(e, r5v[d]["vector"]) for d in ("D1", "D2", "D3")) / 3
    print(f"  {t:14s} mean_cos_to_{D1D2D3} = {m:.6f}".replace("{D1D2D3}", "Laozis"))

json.dump({
    "query_text": q4["text"],
    "query_text_identical_r4_r5": q4["text"] == q5["text"],
    "r4_top5": q4["vector_hits"], "r5_top5": q5["vector_hits"],
    "r4_scores_preserved": any(h[3] is not None for h in q4["vector_hits"]),
    "r5_scores_preserved": any(h[3] is not None for h in q5["vector_hits"]),
    "not_recomputable": "query vectors + raw /v1/embeddings responses not persisted by R4/R5 harness",
    "r5_doc_geometry_cos_to_M_IMG_ZH": {t: c for t, k, c in rows},
}, open(OUT, "w"), ensure_ascii=False, indent=1)
print("\nwrote", OUT)
