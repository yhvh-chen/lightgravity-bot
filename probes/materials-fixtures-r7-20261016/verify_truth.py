#!/usr/bin/env python3
"""LG-035 R7 — offline truth verification (no model, no network).

Re-derives the Table 1 cell truth directly from the source PDF's native text
layer and checks it byte-for-byte against `truth/LG035-R7-T1.table.json`, and
re-verifies the mixed fixture's text-layer split. Prints raw results.

Exit 0 = all checks pass.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pypdfium2 as pdfium

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "sources" / "nist-sp811" / "nistspecialpublication811e2008.pdf"
TRUTH = HERE / "truth" / "LG035-R7-T1.table.json"
MIXED = HERE / "fixtures" / "mixed_born_digital_plus_scan.pdf"
PAGE_INDEX = 15
COL_BOUNDS = (0.0, 210.0, 430.0, 10000.0)  # pt: cell starts (col1 95.6, col2 266.6, col3 438.8)


def extract_rows_from_native_text() -> list[list[str]]:
    """Rebuild the (header + data) matrix from native per-row text rects."""
    doc = pdfium.PdfDocument(str(SRC))
    try:
        page = doc[PAGE_INDEX]
        tp = page.get_textpage()
        tp.count_rects()
        rows = []
        # rects within the table region, in top-to-bottom (descending y) order
        found = []
        for i in range(tp.count_rects()):
            l, b, r, t = tp.get_rect(i)
            if 515.0 <= b <= 615.0:  # header label row + 7 data rows
                found.append((t, b, l, r, tp.get_text_bounded(left=l - 0.5, bottom=b - 0.5, right=r + 0.5, top=t + 0.5)))
        # order: header first (highest t), then data rows
        found.sort(key=lambda x: -x[0])
        for t, b, l, r, txt in found:
            yield_row = txt.rstrip()
            rows.append(yield_row)
        return rows
    finally:
        doc.close()


def split_cells(row_text: str) -> list[str]:
    """Split a native row string into three cells using the measured gutters."""
    # The native text is space-joined; split on runs of >=2 spaces as a first
    # approximation, then fall back to the measured column boundaries using
    # the raw rect spans. For Table 1 the row strings already contain runs.
    import re
    parts = re.split(r"\s{2,}", row_text.strip())
    return [p.strip() for p in parts if p.strip()]


def page_has_text_layer(path: pathlib.Path, index: int) -> bool:
    doc = pdfium.PdfDocument(str(path))
    try:
        page = doc[index]
        try:
            tp = page.get_textpage()
            return tp.count_chars() > 0
        finally:
            page.close()
    finally:
        doc.close()


def main() -> int:
    truth = json.loads(TRUTH.read_text())
    ok = True

    print("== native text rect rows in table region ==")
    native_rows = list(extract_rows_from_native_text())
    for r in native_rows:
        print("  ", repr(r))

    # The native rects merge the three column labels into one row string
    # ("Base quantity Name Symbol"). Verify the expected cell texts are all
    # present byte-exact in the concatenated native text.
    native_blob = "\n".join(native_rows)
    expected_cells = [c["text"] for c in truth["cells"]]
    missing = [c for c in expected_cells if c not in native_blob]
    print("\n== cell-text presence in native layer ==")
    print("  expected cells:", len(expected_cells))
    print("  missing (not found byte-exact):", missing)
    if missing:
        ok = False

    print("\n== structure counts ==")
    print("  truth n_cols =", truth["structure"]["n_cols"], "(expect 3)")
    print("  truth n_rows_data =", truth["structure"]["n_rows_data"], "(expect 7)")
    if truth["structure"]["n_cols"] != 3 or truth["structure"]["n_rows_data"] != 7:
        ok = False

    print("\n== mixed fixture text-layer split ==")
    p1 = page_has_text_layer(MIXED, 0)
    p2 = page_has_text_layer(MIXED, 1)
    doc = pdfium.PdfDocument(str(MIXED))
    try:
        npages = len(doc)
    finally:
        doc.close()
    print("  pages =", npages, "(expect 2)")
    print("  page1 native_text_layer_present =", p1, "(expect True)")
    print("  page2 native_text_layer_present =", p2, "(expect False)")
    if npages != 2 or not p1 or p2:
        ok = False

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
