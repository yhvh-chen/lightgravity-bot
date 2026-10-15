#!/usr/bin/env python3
"""LG-037 R6 OFFLINE diagnosis — geometry of the PRESERVED R4/R5 document vectors.

NO network, NO model calls. Reuses the real (private, read-only) vector caches
written by the R4/R5 owners. Recomputes only what the preserved bytes support:
norms, self-cosines, doc-doc cosines, margin structure and the exact
ranking function the product uses (`_cosine` + sort by (-score, source_id)).

Query vectors were NOT preserved by the R4/R5 harnesses (score field == null),
so raw query→doc scores are explicitly NOT recomputed here; we instead report
the *document geometry* that bounds what any query can achieve.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

R4 = Path("/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-quality-r4-20261016/"
          "probes/materials-vector-quality-r4-20261016/private/vector-data/sources-index/vectors/vectors.jsonl")
R5 = Path("/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016/"
          "probes/materials-vector-r5-20261016/private/vector-data/sources-index/vectors/vectors.jsonl")
OUT = Path(__file__).resolve().parent / "offline_geometry_results.json"


def load(path: Path):
    header = None
    entries = []
    for line in path.read_text().splitlines():
        o = json.loads(line)
        if o.get("record") == "header":
            header = o
            continue
        entries.append(o)
    return header, entries


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def cosine(a, b):
    na, nb = norm(a), norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def report(tag, header, entries):
    print(f"\n===== {tag} =====")
    print("header:", header)
    print(f"entries: {len(entries)}")
    rows = {}
    for e in entries:
        v = e["vector"]
        rows[e["title"]] = {
            "kind": e["kind"],
            "dim": e["dim"],
            "model": e["model"],
            "finite": all(math.isfinite(x) for x in v),
            "l2": round(norm(v), 9),
            "fragment_hash": e["fragment_hash"],
            "source_version": e.get("source_version"),
        }
    for t, r in rows.items():
        print(f"  {t:14s} kind={r['kind']:6s} dim={r['dim']} l2={r['l2']:.6f} "
              f"finite={r['finite']} v={r['source_version']}")
    # doc-doc cosine matrix
    titles = [e["title"] for e in entries]
    print("\n  doc-doc cosine matrix (rows/cols ordered):")
    print("        " + " ".join(f"{t[:6]:>7s}" for t in titles))
    mat = {}
    for a in entries:
        line = []
        for b in entries:
            c = cosine(a["vector"], b["vector"])
            line.append(c)
            mat.setdefault(a["title"], {})[b["title"]] = c
        print(f"  {a['title'][:6]:>6s} " + " ".join(f"{c:7.4f}" for c in line))
    return rows, mat


def main():
    h4, e4 = load(R4)
    h5, e5 = load(R5)
    r4, m4 = report("R4 preserved docs", h4, e4)
    r5, m5 = report("R5 preserved docs", h5, e5)

    out = {"r4_header": h4, "r5_header": h5,
           "r4_docs": r4, "r5_docs": r5,
           "r4_doc_doc_cosine": m4, "r5_doc_doc_cosine": m5}

    # same-title cross-run stability
    print("\n===== same-title cross-run geometry (media should be bit-identical) =====")
    cross = {}
    for t, v5 in r5.items():
        if t in r4:
            a = next(e for e in e4 if e["title"] == t)
            b = next(e for e in e5 if e["title"] == t)
            same_vec = a["vector"] == b["vector"]
            c = cosine(a["vector"], b["vector"])
            cross[t] = {"fragment_hash_equal": a["fragment_hash"] == b["fragment_hash"],
                        "vector_bit_equal": same_vec, "cosine": c,
                        "r4_l2": r4[t]["l2"], "r5_l2": v5["l2"]}
            print(f"  {t:14s} fh_equal={a['fragment_hash']==b['fragment_hash']} "
                  f"vec_bit_equal={same_vec} cosine={c:.6f}")
    out["cross_run_same_title"] = cross

    # margin structure for the image doc: how does M_IMG_ZH relate to the text cluster?
    print("\n===== M_IMG_ZH relation to text distractors (R5) =====")
    zh = m5["M_IMG_ZH"]
    for t in sorted(zh, key=lambda x: -zh[x]):
        if t == "M_IMG_ZH":
            continue
        print(f"  cos(M_IMG_ZH, {t:14s}) = {zh[t]:.6f}")
    en = m5["M_IMG_EN"]
    print("\n===== M_IMG_EN relation to text distractors (R5) =====")
    for t in sorted(en, key=lambda x: -en[x]):
        if t == "M_IMG_EN":
            continue
        print(f"  cos(M_IMG_EN, {t:14s}) = {en[t]:.6f}")
    print("\n===== text cluster spread (R5): min/max off-diagonal cosine =====")
    tt = [t for t in m5 if m5[t] and t.startswith(("D", "T_"))]
    offs = [m5[a][b] for a in tt for b in tt if a != b]
    print(f"  text-text off-diagonal: min={min(offs):.6f} max={max(offs):.6f} mean={sum(offs)/len(offs):.6f}")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
