#!/usr/bin/env python3
"""R6 audit: the frozen "15x3" interpretation vs the actual page geometry.

This does **not** feed truth into the algorithm.  It reads the human truth only
to *count* what the frozen interpretation claims (5 sections x 3 dialects = 15
rows, 3 columns) and compares that against the independently measured pixel
geometry produced by ``layout.py``.  It is an audit, not a scorer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def truth_structure(path: Path) -> dict:
    lines = [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8").splitlines()]
    content = [ln for ln in lines if ln.strip() and not ln.strip().startswith("<h2>")]
    # Sections are separated by blank lines in the truth prose.
    sections: list[list[str]] = []
    current: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("<h2>"):
            continue
        if not stripped:
            if current:
                sections.append(current)
                current = []
            continue
        current.append(stripped)
    if current:
        sections.append(current)
    dialect_markers = [ln[:1] for sec in sections for ln in sec if ln.startswith("*")]
    lines_per_section = [len(sec) for sec in sections]
    section_column_counts = sorted({n for n in lines_per_section})
    return {
        "content_line_count": len(content),
        "section_count": len(sections),
        "lines_per_section": lines_per_section,
        "section_column_counts": section_column_counts,
        "dialect_markers": dialect_markers,
        "frozen_interpretation": {
            "claimed_sections": 5,
            "claimed_dialects_per_section": 3,
            "claimed_rows": len(content),
            "claimed_columns": 3,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    struct = truth_structure(args.truth)
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))

    regions = analysis.get("regions", [])
    region_columns = [r["column_count"] for r in regions]
    verdict = {
        "truth_structure": struct,
        "measured_geometry": {
            "content_box": analysis.get("content_box"),
            "has_ruling": analysis.get("has_ruling"),
            "horizontal_rules": analysis.get("horizontal_rules"),
            "vertical_rules": analysis.get("vertical_rules"),
            "line_count": analysis.get("line_count"),
            "global_column_count": analysis.get("column_count"),
            "region_column_counts": region_columns,
            "max_region_columns": analysis.get("max_region_columns"),
            "column_model": analysis.get("column_model"),
        },
        "findings": [],
    }

    findings = verdict["findings"]
    findings.append(
        "truth has a single dialect-marker prefix (`*國/蘇/廣…`) per line: the "
        "'3 columns' is a *dialect label* mapping, not a repeated per-row cell grid."
    )
    if not analysis.get("has_ruling"):
        findings.append(
            "the page carries NO horizontal and NO vertical ruling; a table with "
            "15 rows x 3 columns would normally show cell borders or at least "
            "consistent column gutters."
        )
    if analysis.get("has_ruling"):
        findings.append("explicit ruling present; needs region/border analysis.")
    if analysis.get("column_model") in ("single_column", "multi_column_local"):
        findings.append(
            "measured geometry is not a uniform 3-column page: "
            f"region column counts = {region_columns}."
        )
    findings.append(
        "the truth flattens reading order (left column block then right column "
        "block); the page actually places those blocks side by side, which is why "
        "plain OCR merges them onto one line — a reading-order mismatch, not "
        "necessarily an OCR miss."
    )

    text = json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
