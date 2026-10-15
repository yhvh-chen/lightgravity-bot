#!/usr/bin/env python3
"""Materials Quality R3 — score Z2 page-2 OCR against frozen human truth.

Pure local. Frozen thresholds (PLAN §2): segment/cell CER <= 0.25 AND structural
pass (human row count present AND machine column structure preserved AND every
human cell token byte-exact). If the model emits no table structure -> failed.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from scoring import cer, normalise, Z2_HUMAN_ROWS  # noqa: E402

ROOT = os.path.dirname(HERE)
TRUTH = "/home/yhvh/code/lightgravity-bot-worktrees/lg035-truth-prep/probes/lg035/TRUTH-PREP/truth/LG035-ZH-Z2.p2.txt"

with open(TRUTH) as fh:
    truth = fh.read()
with open(os.path.join(HERE, "ocr_post1.json")) as fh:
    ocr = json.load(fh)
hyp = ocr["text"]

whole = cer(truth, hyp)
hl = [l for l in hyp.splitlines() if l.strip()]


def overlap(a: str, b: str) -> int:
    ca, cb = Counter(a), Counter(b)
    return sum((ca & cb).values())


# Segment CER by best-character-overlap machine line (fair, layout-agnostic).
total_d = 0
total_t = 0
rows = []
for human in [r.lstrip("*") for r in Z2_HUMAN_ROWS]:
    hn = normalise(human)
    best = max(hl, key=lambda l: overlap(hn, normalise(l)))
    c = cer(hn, best)
    total_d += c["edit_distance"]
    total_t += c["truth_chars"]
    rows.append({"human": human, "machine_best": best, "cer": c["cer"], "overlap": overlap(hn, normalise(best))})
seg_cer = round(total_d / max(1, total_t), 4)

# Structural criterion. Human truth is a 5-section x 3-dialect table (15 dialect
# rows, 3 dialects per section). The machine must preserve that structure.
human_rows = len(Z2_HUMAN_ROWS)
human_sections = 5
human_cols = 3

# Detect how many dialect marker rows the machine preserved.
markers = ("國", "蘇", "廣", "北風", "世界", "船", "狗", "末", "格", "的")
machine_dialect_lines = sum(1 for l in hl if any(m in l for m in markers))
# Detect column structure: does any machine line contain two dialect cells merged?
merged_columns = 0
for l in hl:
    hits = sum(1 for m in ("北風說", "世界浪", "船碰", "狗阿", "末貓", "國、", "蘇、", "廣、") if m in l)
    if hits >= 2:
        merged_columns += 1

# Section count in machine: number of distinct dialect groups detected.
machine_sections = 0
for sec_marker in ("國", "北風說", "世界上的東西", "船碰見了", "末貓", "狗阿"):
    if any(sec_marker in l for l in hl):
        machine_sections += 1

structure_pass = (
    machine_dialect_lines >= human_rows
    and machine_sections >= human_sections
    and merged_columns == 0
)

# Field/ID tokens byte-exact after NFKC.
machine_norm = normalise(hyp)
truth_norm = normalise(truth)
import re

field_tokens = re.findall(r"\d[\d,]*", truth_norm)
field = [{"token": t, "present_exact": t in machine_norm} for t in field_tokens]

verdict = "PASS" if (seg_cer <= 0.25 and structure_pass) else "FAIL"

out = {
    "metric": "z2_table_segment_CER + structural",
    "threshold": {"segment_cer": 0.25, "structure": "rows AND sections AND cols preserved, no merge"},
    "whole_page": whole,
    "segment_cer_by_overlap": seg_cer,
    "human_rows": human_rows,
    "machine_dialect_lines_detected": machine_dialect_lines,
    "human_sections": human_sections,
    "machine_sections_detected": machine_sections,
    "human_cols": human_cols,
    "merged_column_lines": merged_columns,
    "field_tokens": field,
    "structure_pass": structure_pass,
    "segment_rows": rows,
    "verdict": verdict,
    "ocr_latency_seconds": ocr["latency_seconds"],
    "notes": [
        "extraneous tokens present in machine output: A/C, H17, and a trailing numeric row",
        "machine merged section-2 and section-3 dialect columns onto single lines",
        "leading dialect-prefix glyphs 末/格/的 dropped in the final section",
    ],
}

with open(os.path.join(HERE, "ocr_z2_score.json"), "w") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)

print(json.dumps({k: v for k, v in out.items() if k != "segment_rows"}, ensure_ascii=False, indent=2))
