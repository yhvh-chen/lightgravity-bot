#!/usr/bin/env python3
"""materials-ocr-r5 — independent re-scoring (offline, 0 POST).

Reuses the R4 fair metrics **where the metric is identical** (whole-page CER;
independent best-window token-weighted segment CER) and adds the R4 finding's
missing piece: when the model emits a Markdown table, its rows/columns are
actually **parsed** and checked against the declared human structure per
TRUTH-PREP SCORING-PROTOCOL §4.  If the model emits no table structure,
``machine_rows = 0`` and the structural gate **FAILS** (never "not applicable").

Differences from R3/R4 are reported explicitly.  This is append-only; it does
NOT edit R3/R4.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVID = ROOT / "evidence"

# Frozen thresholds (TRUTH-PREP SCORING-PROTOCOL §2). DO NOT RELAX.
SEGMENT_CER_THRESHOLD = 0.25
PRINTED_PAGE_CER_THRESHOLD = 0.15


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return "".join(ch for ch in s if not ch.isspace())


def edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(truth_norm: str, hyp_norm: str) -> float:
    return edit_distance(truth_norm, hyp_norm) / max(1, len(truth_norm))


def human_rows(path: str) -> list[str]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("*"):
                rows.append(line[1:].strip())
    return rows


def human_section_rows(path: str) -> list[list[str]]:
    sections: list[list[str]] = []
    current: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("*"):
                current.append(line[1:].strip())
            elif line.strip() == "" and current:
                sections.append(current)
                current = []
        if current:
            sections.append(current)
    return sections


def machine_rows(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if normalise(ln)]


# ------------------------------------------------------- Markdown table parse
def parse_markdown_tables(text: str) -> list[dict]:
    """Parse Markdown pipe tables into {rows: [[cells]], n_rows, n_cols}.

    A table starts at a line containing ``|`` followed by a separator row whose
    cells are only ``:``/``-``/spaces.  Every subsequent line containing ``|``
    belongs to the table until a blank or non-pipe line.  Only actually-parsed
    tables are returned; if none parse, the caller gets an empty list and must
    record ``machine_rows = 0`` (structural FAIL per protocol §4).
    """

    lines = text.splitlines()
    tables: list[dict] = []
    i = 0
    sep_re = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")

    def split_cells(line: str) -> list[str]:
        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        return [c.strip() for c in stripped.split("|")]

    while i < len(lines):
        if "|" in lines[i] and i + 1 < len(lines) and sep_re.match(lines[i + 1]):
            header = split_cells(lines[i])
            data: list[list[str]] = []
            j = i + 2
            while j < len(lines) and "|" in lines[j] and normalise(lines[j]):
                data.append(split_cells(lines[j]))
                j += 1
            widths = {len(header)} | {len(r) for r in data}
            n_cols = max(widths) if widths else 0
            tables.append(
                {
                    "header": header,
                    "rows": data,
                    "n_rows": len(data),
                    "n_cols": n_cols,
                    "raw_start_line": i,
                }
            )
            i = j
        else:
            i += 1
    return tables


def align_cer_per_human_row(rows: list[str], machine_lines: list[str], window_max: int = 3) -> dict:
    """Independent best-window (fair lower bound) — identical to R4's method."""

    per_row = []
    for row in rows:
        truth = normalise(row)
        best = None
        for j in range(len(machine_lines)):
            for size in range(1, window_max + 1):
                end = j + size
                if end > len(machine_lines):
                    break
                cand = normalise("".join(machine_lines[j:end]))
                c = cer(truth, cand)
                if best is None or c < best:
                    best = c
        per_row.append({"human": row, "cer": round(best if best is not None else 1.0, 6)})
    capped = [min(r["cer"], 1.0) for r in per_row]
    edits = sum(r["cer"] * max(1, len(normalise(r["human"]))) for r in per_row)
    truth_len = sum(max(1, len(normalise(r["human"]))) for r in per_row)
    return {
        "per_row": per_row,
        "mean_row_cer": round(sum(capped) / max(1, len(capped)), 6),
        "token_weighted_cer": round(edits / max(1, truth_len), 6),
    }


def structure_check(truth_path: str, machine_text: str) -> dict:
    """Protocol §4 structure using parsed Markdown tables (or honest FAIL)."""

    sections = human_section_rows(truth_path)
    human_rows = [r for sec in sections for r in sec]
    human_cols = max((len(sec) for sec in sections), default=0)
    tables = parse_markdown_tables(machine_text)

    if tables:
        main = max(tables, key=lambda t: t["n_rows"])
        machine_row_count: int | str = main["n_rows"]
        machine_col_count: int | str = main["n_cols"]
    else:
        machine_row_count = 0
        machine_col_count = 0

    machine_norm = normalise("".join(machine_rows(machine_text)))
    tokens = [
        {"token": r, "present_exact": normalise(r) in machine_norm if normalise(r) else False}
        for r in human_rows
    ]
    numeric = re.findall(r"[0-9]+", " ".join(human_rows))
    numeric_present = [
        {"token": tok, "present_exact": normalise(tok) in machine_norm} for tok in numeric
    ]

    rows_ok = machine_row_count == len(human_rows)
    cols_ok = machine_col_count == human_cols
    tokens_ok = all(t["present_exact"] for t in tokens)
    structure_pass = bool(rows_ok and cols_ok and tokens_ok)

    return {
        "method": "markdown_table_parse",
        "human_row_count": len(human_rows),
        "human_column_count": human_cols,
        "human_section_count": len(sections),
        "machine_table_count": len(tables),
        "machine_row_count": machine_row_count,
        "machine_column_count": machine_col_count,
        "rows_match": rows_ok,
        "cols_match": cols_ok,
        "all_row_tokens_exact": tokens_ok,
        "row_token_exact_present": sum(1 for t in tokens if t["present_exact"]),
        "row_token_total": len(tokens),
        "structure_pass": structure_pass,
        "row_tokens": tokens,
        "numeric_tokens": numeric_present,
        "machine_table_shape": (
            {"n_rows": machine_row_count, "n_cols": machine_col_count}
            if tables
            else "no_markdown_table_emitted"
        ),
    }


def score(truth_path: str, hyp_text: str) -> dict:
    lines = machine_rows(hyp_text)
    rows = human_rows(truth_path)
    truth_all = normalise("".join(rows))

    whole = cer(truth_all, normalise("".join(lines)))
    segment = align_cer_per_human_row(rows, lines)
    structure = structure_check(truth_path, hyp_text)

    return {
        "thresholds": {
            "segment_cer": SEGMENT_CER_THRESHOLD,
            "printed_page_cer": PRINTED_PAGE_CER_THRESHOLD,
        },
        "truth_chars": len(truth_all),
        "hyp_chars": len(normalise("".join(lines))),
        "whole_page_cer": round(whole, 6),
        "whole_page_pass_at_0.15": whole <= PRINTED_PAGE_CER_THRESHOLD,
        "segment_cer_mean": segment["mean_row_cer"],
        "segment_cer_pass_at_0.25": segment["mean_row_cer"] <= SEGMENT_CER_THRESHOLD,
        "segment_cer_independent_mean": segment["mean_row_cer"],
        "segment_cer_independent_token_weighted": segment["token_weighted_cer"],
        "segment_cer_independent_token_weighted_pass_at_0.25": (
            segment["token_weighted_cer"] <= SEGMENT_CER_THRESHOLD
        ),
        "segmental": segment,
        "structure": structure,
        "table_quality_pass": bool(
            segment["token_weighted_cer"] <= SEGMENT_CER_THRESHOLD
            and structure["structure_pass"]
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", required=True)
    ap.add_argument("--machine", required=True, help="JSON with a 'text' field")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    payload = json.loads(Path(args.machine).read_text(encoding="utf-8"))
    result = score(args.truth, payload["text"])
    result["machine_input_sha256"] = payload.get("input_sha256")
    result["machine_model"] = payload.get("model")
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "whole_page_cer", "segment_cer_independent_token_weighted",
        "table_quality_pass")}, ensure_ascii=False))
    print(json.dumps(result["structure"], ensure_ascii=False)[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
