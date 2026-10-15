#!/usr/bin/env python3
"""R6 offline layout probe harness (NO OCR / NO model / NO network).

Mode A — analyse the real Z2 page-2 scan through the **product** rasteriser
(``PdfiumRasterizer``) and print the deterministic geometry.

Mode B — analyse a product-rendered PNG (the exact bytes the OCR adapter would
have seen) so the hash/coordinates are reproducible from a frozen file.

The harness never calls an OCR/embedding/ASR/model endpoint and never reads the
human truth into the algorithm.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from lightgravity.sources.ocr.layout import (  # noqa: E402
    LayoutAnalysis,
    PageGeometry,
    analyse_image_bytes,
    analyse_page,
)


def _emit(analysis: LayoutAnalysis, source: str) -> None:
    out = analysis.to_dict()
    out["source"] = source
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))


def analyse_pdf_page(pdf_path: Path, page_index: int, scale: float) -> LayoutAnalysis:
    from lightgravity.sources.ocr.pdf import PdfiumRasterizer

    data = pdf_path.read_bytes()
    rendered = PdfiumRasterizer().render(data, scale=scale, max_pages=page_index + 1)
    page = rendered[page_index]
    gray, width, height = _png_to_gray(page.png)
    return analyse_page(
        gray,
        width,
        height,
        page=page.page,
        geometry=PageGeometry(
            page=page.page,
            width_pt=float(page.width),
            height_pt=float(page.height),
            scale=scale,
        ),
    )


def _png_to_gray(png: bytes) -> tuple[bytes, int, int]:
    from lightgravity.sources.ocr.layout import decode_png_gray

    return decode_png_gray(png)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, help="PDF to rasterise via the product rasteriser")
    parser.add_argument("--page-index", type=int, default=1, help="0-based page index")
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--png", type=Path, help="pre-rendered PNG to analyse")
    args = parser.parse_args()

    if args.png:
        analysis = analyse_image_bytes(args.png.read_bytes())
        _emit(analysis, f"png:{args.png}")
        return 0
    if args.pdf:
        if not args.pdf.is_file():
            print(f"missing PDF: {args.pdf}", file=sys.stderr)
            return 2
        analysis = analyse_pdf_page(args.pdf, args.page_index, args.scale)
        _emit(analysis, f"pdf:{args.pdf.name}#page={args.page_index + 1}@scale={args.scale}")
        return 0
    parser.error("pass --pdf or --png")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
