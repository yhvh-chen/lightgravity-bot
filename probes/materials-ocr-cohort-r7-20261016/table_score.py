#!/usr/bin/env python3
"""LG-035 R7 cohort — table parser + scorer (offline, frozen protocol).

Parses ONLY the model's actual emitted structure (Markdown pipe table or explicit
plain aligned table). NEVER reconstructs a missing grid from GT, NEVER populates a
machine cell with truth. Scores against frozen truth with §1 normalisation.
"""
from __future__ import annotations

import json
import re
import unicodedata


def norm(s: str) -> str:
    folded = unicodedata.normalize("NFKC", s or "")
    return "".join(ch for ch in folded if not ch.isspace())


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(truth: str, hyp: str) -> float:
    tn, hn = norm(truth), norm(hyp)
    return edit_distance(tn, hn) / max(1, len(tn))


_MD_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def parse_markdown_table(text: str):
    """Return list[list[str]] if `text` has a GitHub pipe table, else None."""
    lines = [ln for ln in text.splitlines()]
    # find a header line followed by a separator line
    for i in range(len(lines) - 1):
        h, sep = lines[i], lines[i + 1]
        if "|" in h and _MD_SEP.match(sep):
            rows = []
            for ln in lines[i:]:
                if "|" not in ln:
                    if rows:
                        break
                    continue
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                if _MD_SEP.match(ln):
                    continue
                rows.append(cells)
            if rows:
                return rows
    return None


def parse_plain_aligned(text: str):
    """Plain aligned table: lines with >=3 runs separated by 2+ spaces."""
    rows = []
    for ln in text.splitlines():
        if not ln.strip():
            continue
        parts = re.split(r"\s{2,}", ln.strip())
        if len(parts) >= 3:
            rows.append([p.strip() for p in parts])
    return rows or None


def parse_table(text: str):
    """Return (rows, method). rows is list[list[str]] or []."""
    md = parse_markdown_table(text)
    if md and len(md) >= 2:
        ncol = max(len(r) for r in md)
        if all(len(r) == ncol for r in md):
            return md, "markdown_pipe"
    pa = parse_plain_aligned(text)
    if pa and len(pa) >= 2:
        ncol = max(len(r) for r in pa)
        if all(len(r) == ncol for r in pa):
            return pa, "plain_aligned"
    return [], "none"


def score_table(machine_text: str, truth: dict) -> dict:
    """Table hardgate score. `truth` is the frozen table json (structure+cells)."""
    rows, method = parse_table(machine_text)
    truth_rows = [truth["structure"]["header"]] + truth["structure"]["rows"]
    truth_cells = {(c["row"], c["col"]): c["text"] for c in truth["cells"]}
    n_rows_truth = truth["structure"]["n_rows_total_including_header"]
    n_cols_truth = truth["structure"]["n_cols"]

    result: dict = {
        "parse_method": method,
        "machine_rows": len(rows),
        "machine_cols": (len(rows[0]) if rows else 0),
        "truth_rows": n_rows_truth,
        "truth_cols": n_cols_truth,
    }
    rows_ok = len(rows) == n_rows_truth
    cols_ok = bool(rows) and all(len(r) == n_cols_truth for r in rows)
    result["rows_exact"] = rows_ok
    result["cols_exact"] = cols_ok

    # cell CER over the full 24-cell truth grid; missing/mismatched -> CER 1.0
    cers = []
    token_checks = []
    for r in range(n_rows_truth):
        for c in range(n_cols_truth):
            t = truth_cells.get((r, c), "")
            if rows and r < len(rows) and c < len(rows[r]):
                hyp = rows[r][c]
            else:
                hyp = ""
            cers.append(cer(t, hyp))
    result["cell_cer"] = sum(cers) / len(cers) if cers else 1.0

    # numeric/ID tokens byte-exact after NFKC in the symbol column (col 2)
    symbols_truth = [truth["structure"]["rows"][i][2] for i in range(len(truth["structure"]["rows"]))]
    symbol_cells = []
    for r in range(1, n_rows_truth):
        hyp = rows[r][2] if (cols_ok and r < len(rows) and len(rows[r]) > 2) else ""
        symbol_cells.append(hyp)
    for tok, hyp in zip(symbols_truth, symbol_cells):
        token_checks.append({"token": tok, "machine_cell": hyp,
                             "exact_after_nfkc": norm(tok) == norm(hyp)})
    result["symbol_token_checks"] = token_checks
    result["symbol_tokens_all_exact"] = all(t["exact_after_nfkc"] for t in token_checks)

    result["structure_pass"] = rows_ok and cols_ok
    result["table_gate_pass"] = (
        rows_ok and cols_ok and result["cell_cer"] <= 0.25 and result["symbol_tokens_all_exact"]
    )
    # whole-cell CER context INCLUDING all cells (already the 24-cell mean)
    result["table_whole_cell_cer_context"] = result["cell_cer"]
    return result


if __name__ == "__main__":
    import sys
    truth = json.load(open(sys.argv[1], encoding="utf-8"))
    text = open(sys.argv[2], encoding="utf-8").read()
    print(json.dumps(score_table(text, truth), ensure_ascii=False, indent=2))
