#!/usr/bin/env python3
"""materials-ocr-r4 — independent re-scoring (offline, 0 POST).

Replaces R3's buggy single-line segment matcher with:

1. **whole-page CER** per TRUTH-PREP SCORING-PROTOCOL §1 (NFKC + strip
   whitespace, code-point Levenshtein).
2. **principled segmental alignment**: each human row is compared to the best
   alignment window of consecutive machine lines (1..3 lines) so a machine that
   wraps/merges a row is scored fairly, never by a single best line.
3. **original protocol §4 strict structure check** implemented separately:
   human row count == machine row count AND human column count == machine
   column count AND every human cell token byte-exact after NFKC. Counts that
   cannot be reliably inferred from plain OCR text are recorded **unverified**,
   never faked into a pass.

This is append-only; it does NOT edit R3. Thresholds are read from the frozen
protocol and never relaxed.
"""
from __future__ import annotations

import argparse
import json
import os
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVID = os.path.join(ROOT, "evidence")

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


# --------------------------------------------------------------------- truth
def human_rows(path: str) -> list[str]:
    """Human dialect rows: lines beginning with ``*`` (heading/blank excluded)."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("*"):
                rows.append(line[1:].strip())
    return rows


def human_section_rows(path: str) -> list[list[str]]:
    """Human rows grouped into the blank-line-separated sections (dialect groups)."""
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


# ----------------------------------------------------------------------- hyp
def _looks_noise(line: str) -> bool:
    n = normalise(line)
    return len(n) == 0


def machine_rows(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if not _looks_noise(ln)]


def align_cer_per_human_row(rows: list[str], machine_lines: list[str]) -> dict:
    """Principled global alignment of human rows to 1..N machine lines.

    Dynamic programming over (human row index i, machine line index j): a human
    row may match a window of 1..window_max consecutive machine lines, and
    machine lines that belong to no human row (headers/footers/extra lines) are
    **skipped** as insertions at zero cost. This is the fair counterpart to
    R3's "best single line" (which over-counts) and a greedy cursor (which can
    force leading noise onto the first row). Per-row CER is kept raw for
    transparency; the aggregate caps each row at 1.0 so a merged superset line
    cannot inflate the score.
    """

    window_max = 3
    n = len(rows)
    m = len(machine_lines)
    truth_norm = [normalise(r) for r in rows]
    # dp[i][j] = min total (capped) CER aligning rows[i:] against lines[j:].
    INF = float("inf")
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    choice: list[list[tuple[int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[n][m] = 0.0
    for j in range(m - 1, -1, -1):
        dp[n][j] = dp[n][j + 1]  # skip trailing machine lines free
        choice[n][j] = (n, j + 1)
    for i in range(n - 1, -1, -1):
        # Option: skip this human row (should not be needed but keeps DP total)
        dp[i][m] = 1.0 + dp[i + 1][m]
        choice[i][m] = (i + 1, m)
        for j in range(m - 1, -1, -1):
            best = dp[i][j + 1]  # skip machine line j (insertion)
            best_choice: tuple[int, int] = (i, j + 1)
            for size in range(1, window_max + 1):
                end = j + size
                if end > m:
                    break
                cand_text = normalise("".join(machine_lines[j:end]))
                c = cer(truth_norm[i], cand_text)
                total = min(c, 1.0) + dp[i + 1][end]
                if total < best:
                    best = total
                    best_choice = (i + 1, end)
            dp[i][j] = best
            choice[i][j] = best_choice

    # Reconstruct per-row matches.
    per_row: list[dict] = []
    i = j = 0
    while i < n:
        nxt = choice[i][j]
        if nxt is None:
            break
        ni, nj = nxt
        if ni == i:  # skipped a machine line
            j = nj
            continue
        if ni == i + 1 and nj == j:  # skipped a human row (not expected)
            per_row.append({"human": rows[i], "machine_best": "", "cer": 1.0, "window": 0})
            i = ni
            continue
        window = machine_lines[j:nj]
        cand = normalise("".join(window))
        c = cer(truth_norm[i], cand)
        per_row.append(
            {"human": rows[i], "machine_best": cand, "cer": round(c, 6),
             "window": len(window)}
        )
        i, j = ni, nj
    while i < n:
        per_row.append({"human": rows[i], "machine_best": "", "cer": 1.0, "window": 0})
        i += 1

    aggregated = [min(r["cer"], 1.0) for r in per_row]
    mean_cer = sum(aggregated) / max(1, len(aggregated))
    total_edits = sum(
        min(r["cer"], 1.0) * max(1, len(normalise(r["human"]))) for r in per_row
    )
    total_truth = sum(max(1, len(normalise(r["human"]))) for r in per_row)
    independent = independent_best_window(rows, machine_lines, window_max)
    return {
        "per_row": per_row,
        "mean_row_cer": round(mean_cer, 6),
        "token_weighted_cer": round(total_edits / max(1, total_truth), 6),
        "independent_best_window_mean_cer": independent["mean_row_cer"],
        "independent_best_window_token_weighted_cer": independent["token_weighted_cer"],
        "independent_best_window_per_row": independent["per_row"],
    }


def independent_best_window(
    rows: list[str], machine_lines: list[str], window_max: int = 3
) -> dict:
    """Fair lower-bound: each human row vs its best window of 1..N machine lines.

    Windows may overlap (no monotonic cursor), matching the independent audit's
    fair method so the score is not penalised by a single merged output line.
    Windows wider than the row (supersets) are still scored against the row, so
    a merged line cannot be silently ignored.
    """

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
    edits = sum(
        r["cer"] * max(1, len(normalise(r["human"]))) for r in per_row
    )
    truth_len = sum(max(1, len(normalise(r["human"]))) for r in per_row)
    return {
        "per_row": per_row,
        "mean_row_cer": round(sum(capped) / max(1, len(capped)), 6),
        "token_weighted_cer": round(edits / max(1, truth_len), 6),
    }


# --------------------------------------------------- protocol §4 structure
def strict_structure(truth_path: str, machine_lines: list[str]) -> dict:
    """Implement protocol §4 explicitly and record each count.

    Human truth is a 5-section × 3-dialect (column) table => 15 rows, 3 columns.
    The machine output is **plain text without reliable table boundaries**, so
    a true machine row/column count cannot be inferred with confidence; those
    counts are recorded as **unverified** rather than fabricated. The
    reliably-checkable part is the set of human row/segment tokens: we require
    every human cell token to appear byte-exact after NFKC in the machine text.
    """

    sections = human_section_rows(truth_path)
    human_rows = [r for sec in sections for r in sec]
    human_cols = max((len(sec) for sec in sections), default=0)

    machine_norm = normalise("".join(machine_lines))
    tokens = []
    for row in human_rows:
        token = normalise(row)
        # A row-long exact substring is the protocol's cell/segment test; shorter
        # number/ID tokens are also checked byte-exact after NFKC.
        present = token in machine_norm if token else False
        tokens.append({"token": row, "present_exact": present})

    numeric = [t for t in _numeric_tokens(human_rows)]
    numeric_present = [
        {"token": tok, "present_exact": normalise(tok) in machine_norm} for tok in numeric
    ]

    return {
        "human_row_count": len(human_rows),
        "human_column_count": human_cols,
        "human_section_count": len(sections),
        "machine_row_count": "unverified",
        "machine_column_count": "unverified",
        "machine_row_count_reason": (
            "plain OCR text has no reliable row boundaries; cannot infer machine "
            "table rows without layout analysis (not available)"
        ),
        "machine_column_count_reason": (
            "plain OCR text has no reliable column boundaries; cannot infer machine "
            "table columns without layout analysis (not available)"
        ),
        "structure_pass": False,
        "structure_pass_reason": (
            "protocol §4 requires machine row count == human row count AND machine "
            "column count == human column count AND every cell token byte-exact; "
            "machine row/column counts are unverified from plain text, so the "
            "structural gate CANNOT be claimed as pass (recorded as fail/unverified, "
            "never faked)"
        ),
        "row_token_exact_present": sum(1 for t in tokens if t["present_exact"]),
        "row_token_total": len(tokens),
        "row_tokens": tokens,
        "numeric_tokens": numeric_present,
    }


def _numeric_tokens(rows: list[str]) -> list[str]:
    import re

    out = []
    for row in rows:
        for m in re.findall(r"[0-9]+", row):
            out.append(m)
    return out


# ------------------------------------------------------------------ scoring
def score(truth_path: str, hyp_text: str) -> dict:
    machine_lines = machine_rows(hyp_text)
    rows = human_rows(truth_path)
    truth_all = normalise("".join(rows))

    whole = cer(truth_all, normalise("".join(machine_lines)))
    segment = align_cer_per_human_row(rows, machine_lines)
    structure = strict_structure(truth_path, machine_lines)

    return {
        "thresholds": {
            "segment_cer": SEGMENT_CER_THRESHOLD,
            "printed_page_cer": PRINTED_PAGE_CER_THRESHOLD,
        },
        "truth_chars": len(truth_all),
        "hyp_chars": len(normalise("".join(machine_lines))),
        "whole_page_cer": round(whole, 6),
        "whole_page_pass_at_0.15": whole <= PRINTED_PAGE_CER_THRESHOLD,
        "segmental": segment,
        "segment_cer_mean": segment["mean_row_cer"],
        "segment_cer_pass_at_0.25": segment["mean_row_cer"] <= SEGMENT_CER_THRESHOLD,
        "segment_cer_independent_mean": segment["independent_best_window_mean_cer"],
        "segment_cer_independent_pass_at_0.25": (
            segment["independent_best_window_mean_cer"] <= SEGMENT_CER_THRESHOLD
        ),
        "segment_cer_independent_token_weighted": segment[
            "independent_best_window_token_weighted_cer"
        ],
        "segment_cer_independent_token_weighted_pass_at_0.25": (
            segment["independent_best_window_token_weighted_cer"]
            <= SEGMENT_CER_THRESHOLD
        ),
        "structure": structure,
        "table_quality_pass": bool(
            segment["mean_row_cer"] <= SEGMENT_CER_THRESHOLD and structure["structure_pass"]
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default=os.path.join(ROOT, "private", "truth_z2_p2.txt"))
    ap.add_argument("--machine", required=True, help="JSON file with a 'text' field")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.machine, encoding="utf-8") as fh:
        payload = json.load(fh)
    result = score(args.truth, payload["text"])
    result["machine_input_sha256"] = payload.get("input_sha256")
    result["machine_model"] = payload.get("model")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in (
        "whole_page_cer", "segment_cer_mean", "segment_cer_pass_at_0.25",
        "structure", "table_quality_pass")}, ensure_ascii=False, indent=2)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
