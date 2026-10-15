#!/usr/bin/env python3
"""LG-037 R6 — separate the two hypotheses for Q_IMG_ZH dropping out of top-5.

H1 (corpus-composition / ranking boundary): R4 and R5 indexed DIFFERENT text
   documents (and the same title's text differed). The query text was byte-identical.
   So the R4->R5 outcome change can be explained by the corpus delta, NOT by any
   change to the image or the model.

H2 (encoding defect): the product sends raw, untemplated text for both queries and
   documents (no `task: search result | query:` / `title: <t> | text: <c>` prefix).
   This is a *global* quality limiter, present in BOTH runs, so it cannot by itself
   explain the R4->R5 delta. It is verified against the official model card.

This script quantifies H1 from the preserved vectors alone (no network).
Query vectors were not preserved, so we do NOT invent query->doc scores. We report
the *document-side* structure that bounds the outcome.
"""
from __future__ import annotations
import json, math
from pathlib import Path

R4 = Path("/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-quality-r4-20261016/"
          "probes/materials-vector-quality-r4-20261016/private/vector-data/sources-index/vectors/vectors.jsonl")
R5 = Path("/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016/"
          "probes/materials-vector-r5-20261016/private/vector-data/sources-index/vectors/vectors.jsonl")
OUT = Path(__file__).resolve().parent / "ranking_boundary_results.json"

def load(p):
    out = {}
    for line in p.read_text().splitlines():
        o = json.loads(line)
        if o.get("record") == "header":
            continue
        out[o["title"]] = o
    return out

def cos(a, b):
    na = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / (na*nb)

r4, r5 = load(R4), load(R5)

# R4 ranking of Q_IMG_ZH (recorded, ordinal, from crossmodal_results.json):
r4_rank = json.load(open(Path(__file__).resolve().parents[1] /
                         "../materials-vector-quality-r4-20261016/evidence/crossmodal_results.json"
                         )) if False else None

# R4 indexed docs vs R5 indexed docs (titles)
r4_titles = set(r4); r5_titles = set(r5)
print("R4 docs:", sorted(r4_titles))
print("R5 docs:", sorted(r5_titles))
print("R4-only:", sorted(r4_titles - r5_titles))
print("R5-only:", sorted(r5_titles - r4_titles))
print()

# For Q_IMG_ZH the R4 top-5 was: D1,D2,D3,D5,M_IMG_ZH ; ranks 6,7 were D4,D7.
# R5 top-5 was: D1,D2,D3,D5,T_NORTHWIND. So the ONLY new entrant that displaced
# M_IMG_ZH is T_NORTHWIND (replacing D4), and D7 vanished.
print("=== R4 documented Q_IMG_ZH ordinal ranking ===")
print(" 1 D1  2 D2  3 D3  4 D5  5 M_IMG_ZH | 6 D4  7 D7")
print("=== R5 documented Q_IMG_ZH ordinal ranking ===")
print(" 1 D1  2 D2  3 D3  4 D5  5 T_NORTHWIND | (M_IMG_ZH >= 6)")
print()

# How attached is T_NORTHWIND to the Laozi cluster vs D4/D7? (doc-doc only)
laozi = ["D1", "D2", "D3"]
def avg_cos(doc, others, table):
    return sum(cos(table[doc]["vector"], table[o]["vector"]) for o in others) / len(others)

print("=== mean cosine to the Laozi distractors {D1,D2,D3} ===")
for d in ("D4", "D7", "T_NORTHWIND", "M_IMG_ZH"):
    tbl = r4 if d in r4 else r5
    if d in tbl:
        print(f"  {d:14s} (R4 corpus) " if d in r4 else f"  {d:14s} (R5 corpus) ", end="")
        print(f"mean_cos_to_D1D2D3 = {avg_cos(d, laozi, tbl):.6f}")
print()
print("=== the doc that M_IMG_ZH must out-score to stay in top-5 ===")
print("  R4: had to beat D4 & D7 (both wind/Northwind text, off-topic for 老子)")
print("  R5: had to beat T_NORTHWIND (Northwind), but D4/D7 slots changed")
print()
print("R4 M_IMG_ZH cos to the Laozi docs:")
for d in laozi:
    print(f"   cos(M_IMG_ZH,{d}) = {cos(r4['M_IMG_ZH']['vector'], r4[d]['vector']):.6f}")
print("R5 M_IMG_ZH cos to the Laozi docs:")
for d in laozi:
    print(f"   cos(M_IMG_ZH,{d}) = {cos(r5['M_IMG_ZH']['vector'], r5[d]['vector']):.6f}")

# Text-doc churn between runs: how much did D1..D6 move?
print()
print("=== text-doc drift R4->R5 (same title, different stored text) ===")
for t in sorted(r5_titles & r4_titles):
    if r5[t]["kind"] != "text":
        continue
    print(f"  {t:14s} cos(R4_vec,R5_vec)={cos(r4[t]['vector'], r5[t]['vector']):.6f} "
          f"fh_equal={r4[t]['fragment_hash']==r5[t]['fragment_hash']}")

json.dump({
    "r4_titles": sorted(r4_titles), "r5_titles": sorted(r5_titles),
    "r4_only": sorted(r4_titles - r5_titles), "r5_only": sorted(r5_titles - r4_titles),
    "note": "query vectors not preserved; ordinal rankings from crossmodal_results.json",
}, open(OUT, "w"), ensure_ascii=False, indent=1)
print("\nwrote", OUT)
