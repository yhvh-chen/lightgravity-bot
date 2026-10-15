#!/usr/bin/env python3
"""R6 deterministic evidence run (offline; NO OCR / NO model / NO network).

Renders real pages through the **product** ``PdfiumRasterizer`` and writes a
frozen JSON analysis per page to ``evidence/``.  This is the coordinate proof
for the report: identical inputs must reproduce identical coordinates/hashes.

Real inputs only (no synthetic/quality fixtures):

* ``z2-page2``  — the real Chinese form scan, PD, from the LG-035 truth pack;
* ``clear-real`` and ``multipage-real`` — ordinary English scanned/printed
  PDFs from ``probes/lg035/fixtures`` used as **non-table regression controls**.

The harness never reads the human truth into the algorithm.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from lightgravity.sources.ocr.layout import analyse_rendered_page  # noqa: E402
from lightgravity.sources.ocr.pdf import PdfiumRasterizer  # noqa: E402


def analyse_pdf(pdf_path: Path, *, page_index: int, scale: float) -> dict:
    data = pdf_path.read_bytes()
    rendered = PdfiumRasterizer().render(data, scale=scale, max_pages=page_index + 1)
    page = rendered[page_index]
    analysis = analyse_rendered_page(page, scale=scale)
    out = analysis.to_dict()
    out["source"] = {
        "pdf_name": pdf_path.name,
        "pdf_sha256": hashlib.sha256(data).hexdigest(),
        "page_index": page_index,
        "scale": scale,
        "raster_png_sha256": hashlib.sha256(page.png).hexdigest(),
        "raster_bytes": len(page.png),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--z2-pdf", type=Path, required=True)
    parser.add_argument("--clear-pdf", type=Path, required=True)
    parser.add_argument("--multipage-pdf", type=Path, required=True)
    parser.add_argument("--scale", type=float, default=2.0)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    jobs = [
        ("z2_page2_scale2", args.z2_pdf, 1, args.scale),
        ("z2_page2_scale4", args.z2_pdf, 1, 4.0),
        ("clear_real_page1_scale2", args.clear_pdf, 0, args.scale),
        ("multipage_real_page1_scale2", args.multipage_pdf, 0, args.scale),
    ]
    summary = {}
    for name, pdf, idx, scale in jobs:
        result = analyse_pdf(pdf, page_index=idx, scale=scale)
        (args.out / f"{name}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        summary[name] = {
            "status": result["status"],
            "line_count": result["line_count"],
            "global_column_count": result["column_count"],
            "max_region_columns": result["max_region_columns"],
            "column_model": result["column_model"],
            "has_ruling": result["has_ruling"],
            "input_sha256": result["input_sha256"],
            "content_box": result["content_box"],
        }
        print(name, summary[name], flush=True)

    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
