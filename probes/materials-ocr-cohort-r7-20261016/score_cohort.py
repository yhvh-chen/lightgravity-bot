#!/usr/bin/env python3
"""LG-035 R7 cohort — SCORE stage (offline, reads persisted raw before scoring).

Reads `evidence/raw/*_text.txt` + the frozen truth + gold text, computes the table
hardgate and per-page CER gates, and writes `evidence/scores.json`.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIX = "/home/yhvh/code/lightgravity-bot-worktrees/materials-fixtures-r7-20261016/probes/materials-fixtures-r7-20261016"
EVID = os.path.join(HERE, "evidence")
RAW = os.path.join(EVID, "raw")
sys.path.insert(0, HERE)

from table_score import cer, norm, score_table  # noqa: E402


def read_text(name: str) -> str:
    p = os.path.join(RAW, name)
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def native_p16_text() -> str:
    """Native text layer of NIST SP 811 p.16 (page-1 born-digital truth)."""
    import pypdfium2 as pdfium
    src = os.path.join(FIX, "sources/nist-sp811/nistspecialpublication811e2008.pdf")
    doc = pdfium.PdfDocument(open(src, "rb").read())
    return doc[15].get_textpage().get_text_range()


def main() -> int:
    truth = json.load(open(os.path.join(FIX, "truth/LG035-R7-T1.table.json"), encoding="utf-8"))
    gold = open(os.path.join(REPO, "probes/lg035/fixtures/phototest.gold.txt"), encoding="utf-8").read()
    prelim = json.load(open(os.path.join(EVID, "call_results_prelim.json"), encoding="utf-8"))
    by_call = {r["call"]: r for r in prelim}

    scores: dict = {"table": {}, "pages": {}, "calls": {}}

    # ---- call 1: table ----
    t1_text = read_text("call1_LG035-R7-T1_pNone_text.txt")
    if by_call.get(1, {}).get("status") == "ok":
        s = score_table(t1_text, truth)
        s["machine_text_sha256"] = by_call[1].get("machine_text_sha256")
        scores["table"] = s
    else:
        scores["table"] = {"status": by_call.get(1, {}).get("status", "NOTEXECUTED"),
                           "table_gate_pass": False, "note": "call did not produce text"}

    # ---- call 2: MIX page 1 born-digital ----
    ref = native_p16_text()
    if by_call.get(2, {}).get("status") == "ok":
        hyp = read_text("call2_LG035-R7-MIX_p1_text.txt")
        pcer = cer(ref, hyp)
        scores["pages"]["mix_p1_born_digital"] = {
            "page_cer": pcer, "threshold": 0.15, "pass": pcer <= 0.15,
            "truth_source": "NIST SP811 p16 native text layer",
            "truth_len_norm": len(norm(ref)), "hyp_len_norm": len(norm(hyp))}
    else:
        scores["pages"]["mix_p1_born_digital"] = {
            "status": by_call.get(2, {}).get("status", "NOTEXECUTED"), "pass": False,
            "threshold": 0.15}

    # ---- call 3: MIX page 2 real scan vs gold ----
    if by_call.get(3, {}).get("status") == "ok":
        hyp = read_text("call3_LG035-R7-MIX_p2_text.txt")
        pcer = cer(gold, hyp)
        scores["pages"]["mix_p2_real_scan"] = {
            "page_cer": pcer, "threshold": 0.15, "pass": pcer <= 0.15,
            "truth_source": "phototest.gold.txt",
            "truth_len_norm": len(norm(gold)), "hyp_len_norm": len(norm(hyp))}
    else:
        scores["pages"]["mix_p2_real_scan"] = {
            "status": by_call.get(3, {}).get("status", "NOTEXECUTED"), "pass": False,
            "threshold": 0.15}

    # call-level provenance/usage summary
    for r in prelim:
        scores["calls"][str(r["call"])] = {
            "sample": r["sample"], "page": r.get("page"), "status": r.get("status"),
            "input_sha256": r.get("input_sha256"), "input_bytes": r.get("input_bytes"),
            "latency_seconds": r.get("latency_seconds"),
            "prompt_tokens": r.get("prompt_tokens"), "completion_tokens": r.get("completion_tokens"),
            "finish_reason": r.get("finish_reason"), "model": r.get("model_returned") or r.get("model"),
            "raw_response_path": r.get("raw_response_path"),
            "machine_text_path": r.get("machine_text_path"),
            "prompt_sha256": r.get("prompt_sha256"),
        }

    scores["summary"] = {
        "table_gate_pass": scores["table"].get("table_gate_pass", False),
        "mix_p1_pass": scores["pages"]["mix_p1_born_digital"].get("pass", False),
        "mix_p2_pass": scores["pages"]["mix_p2_real_scan"].get("pass", False),
        "executed_calls": sum(1 for r in prelim if r.get("status") in ("ok", "error")),
    }
    with open(os.path.join(EVID, "scores.json"), "w", encoding="utf-8") as fh:
        json.dump(scores, fh, ensure_ascii=False, indent=2)
    print(json.dumps(scores["summary"], ensure_ascii=False))
    print("table:", json.dumps({k: scores["table"].get(k) for k in
          ("parse_method", "machine_rows", "machine_cols", "cell_cer", "table_gate_pass")}, ensure_ascii=False))
    print("p1:", json.dumps(scores["pages"]["mix_p1_born_digital"], ensure_ascii=False))
    print("p2:", json.dumps(scores["pages"]["mix_p2_real_scan"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
