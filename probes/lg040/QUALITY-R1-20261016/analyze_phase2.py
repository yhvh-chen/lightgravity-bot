#!/usr/bin/env python3
"""LG-040 QUALITY-R1 phase-2 scoring (OFFLINE ONLY — no network, no model calls).

Scores the already-captured phase-2 evidence:
* the PNG image embed that finally succeeded (the phase-1 TIFF image embed failed),
* the real cache DELETE + rebuild reproduction (5 sources incl. image vector),
* the post-rebuild Q3' (image) and Q1'' (reproducibility) service orders, and
* independent cosine recomputation from the raw wire vectors.

Adds NO model calls; reads only persisted evidence + the product cache under
``/tmp/lg040-quality-r1-20261016/data``.  Writes ``evidence/phase2_analysis.json``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
DATA = Path("/tmp/lg040-quality-r1-20261016/data")


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def load_cache():
    entries = []
    for vf in sorted((DATA / "sources-index").glob("**/vectors.jsonl")):
        for line in vf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("record") == "header":
                continue
            if "vector" in obj:
                entries.append(obj)
    return entries


def main() -> int:
    labels = json.loads((HERE / "frozen/LABELS.json").read_text(encoding="utf-8"))
    docs = json.loads((EVIDENCE / "docs.json").read_text(encoding="utf-8"))
    p2 = json.loads((EVIDENCE / "phase2.json").read_text(encoding="utf-8"))
    cache = load_cache()
    docid_by_sid = {v["source_id"]: k for k, v in docs.items() if "source_id" in v}
    # phase-2 introduced a *new* PNG source id (replaces the failed TIFF)
    png_sid = p2["d3b_source_id"]
    docid_by_sid[png_sid] = "D3"

    cache_vectors = {e["source_id"]: e["vector"] for e in cache if isinstance(e.get("vector"), list)}

    raws = []
    for fp in sorted((EVIDENCE / "raw_responses").glob("*.json")):
        b = json.loads(fp.read_text(encoding="utf-8"))
        try:
            raws.append((fp.name, b["data"][0]["embedding"], b.get("usage")))
        except Exception:
            pass
    # phase-2 wire order: 01..04 = build D1,D2,D4,MIX; 05 = build D3png; 06 = Q3'; 07 = Q1''
    wire_names = ["D1_build", "D2_build", "D4_build", "MIX_build", "D3png_build", "Q3_rebuilt", "Q1_rebuilt"]

    scores_by_name = {}
    for i, (fn, vec, usage) in enumerate(raws):
        nm = wire_names[i] if i < len(wire_names) else fn
        sc = [(docid_by_sid.get(sid, sid), cosine(vec, cv)) for sid, cv in cache_vectors.items()]
        sc.sort(key=lambda x: (-x[1], x[0]))
        scores_by_name[nm] = {
            "raw_file": fn, "usage": usage,
            "recomputed_order": [s[0] for s in sc],
            "recomputed_scores": [round(s[1], 6) for s in sc],
        }

    # service-returned orders (phase-2)
    def order(block):
        return [docid_by_sid.get(h.get("source_id"), h.get("source_id")) for h in block.get("hits", [])]

    q3_svc = order(p2["Q3_rebuilt"])
    q1_svc = order(p2["Q1_rebuilt"])
    qpos = {q["q_id"]: q.get("positive") for q in labels["queries"]}

    def metrics(order_, pos):
        if pos is None:
            return {"recall@1": None, "recall@3": None, "recall@5": None, "mrr": 0.0, "top1_correct": None}
        rr = 0.0
        for i, d in enumerate(order_, 1):
            if d == pos:
                rr = 1.0 / i
                break
        return {
            "recall@1": 1.0 if order_[:1] == [pos] else 0.0,
            "recall@3": 1.0 if pos in order_[:3] else 0.0,
            "recall@5": 1.0 if pos in order_[:5] else 0.0,
            "mrr": rr,
            "top1_correct": order_[:1] == [pos],
        }

    out = {
        "offline_only": True,
        "new_model_calls": 0,
        "cache": {
            "documents": len(cache),
            "model": cache[0].get("model") if cache else None,
            "dim": cache[0].get("dim") if cache else None,
            "kinds": {docid_by_sid.get(e["source_id"], e["source_id"]): e.get("kind") for e in cache},
        },
        "png_image_vector_present": any(e.get("kind") == "image" for e in cache),
        "cache_delete_rebuild": {
            "cache_deleted": p2.get("cache_deleted"),
            "rebuilt": p2["rebuild"].get("rebuilt"),
            "documents": p2["rebuild"].get("documents"),
            "indexed": len(p2["rebuild"].get("indexed", [])),
            "not_indexed": p2["rebuild"].get("not_indexed"),
            "rebuild_wall_s": p2.get("rebuild_wall_s"),
        },
        "phase2_raw_order": scores_by_name,
        "Q3_rebuilt_service_order": q3_svc,
        "Q1_rebuilt_service_order": q1_svc,
        "Q3_rebuilt_metrics": metrics(q3_svc, qpos["Q3"]),
        "Q1_rebuilt_metrics": metrics(q1_svc, qpos["Q1"]),
    }

    # independent agreement: did Q3'/Q1'' raw vectors reproduce the service order?
    out["independent_agreement"] = {
        "Q3_rebuilt": scores_by_name.get("Q3_rebuilt", {}).get("recomputed_order") == q3_svc,
        "Q1_rebuilt": scores_by_name.get("Q1_rebuilt", {}).get("recomputed_order") == q1_svc,
        "recomputed_Q3": scores_by_name.get("Q3_rebuilt", {}).get("recomputed_order"),
        "recomputed_Q1": scores_by_name.get("Q1_rebuilt", {}).get("recomputed_order"),
    }

    # gate updates (frozen definitions)
    out["gates_phase2"] = {
        "G2_image_rebuilt": "PASS" if out["Q3_rebuilt_metrics"]["top1_correct"] else "FAIL",
        "G2_note": "image source ranked at position %d (1-based) among rebuilt 5-doc index"
                   % (q3_svc.index("D3") + 1 if "D3" in q3_svc else -1),
        "G1_reproducibility_rebuilt": "PASS" if out["Q1_rebuilt_metrics"]["top1_correct"] else "FAIL",
    }

    (EVIDENCE / "phase2_analysis.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("png_image_vector_present", "cache_delete_rebuild", "Q3_rebuilt_service_order", "Q1_rebuilt_service_order", "gates_phase2", "independent_agreement")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
