#!/usr/bin/env python3
"""materials-ocr-r4 — raster grid metadata (offline, 0 POST).

Reads the real PNG IHDR width/height produced by the product `PdfiumRasterizer`
at the default scale 2.0 and the retest scale 4.0, so the "408x689" mislabel
(that is the page *point* size) is corrected from actual PNG metadata rather
than inferred. This is product rendering (allowed), not image editing.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIV = os.path.join(ROOT, "private")
EVID = os.path.join(ROOT, "evidence")
sys.path.insert(0, os.path.join(ROOT, "backend"))

from lightgravity.sources.ocr.pdf import PdfiumRasterizer  # noqa: E402

PDF = os.path.join(PRIV, "LG035-ZH-Z2.pdf")
PDF_SHA = "da50c9f6963f70bc022db55a367b88fd4d6c5be36d899ae5a1d7392aada0eb5a"


def png_ihdr(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    # IHDR payload starts at byte 16 (8 sig + 4 len + 4 tag).
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def main() -> int:
    with open(PDF, "rb") as fh:
        pdf_bytes = fh.read()
    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    if pdf_sha != PDF_SHA:
        print("PDF sha mismatch:", pdf_sha)
        return 2

    raster = PdfiumRasterizer()
    out: dict[str, object] = {"pdf_sha256": pdf_sha, "renders": {}}
    for scale in (2.0, 4.0):
        pages = raster.render(pdf_bytes, scale=scale, max_pages=2)
        page2 = [p for p in pages if p.page == 2][0]
        w, h = png_ihdr(page2.png)
        out["renders"][str(scale)] = {
            "scale": scale,
            "approx_dpi": round(scale * 72, 1),
            "page_point_size": {"width": page2.width, "height": page2.height},
            "png_pixels": {"width": w, "height": h},
            "png_bytes": len(page2.png),
            "png_sha256": hashlib.sha256(page2.png).hexdigest(),
        }
        print(f"scale={scale} point={page2.width}x{page2.height} "
              f"png={w}x{h} bytes={len(page2.png)} ~{scale*72:.0f}DPI")

    with open(os.path.join(EVID, "raster_grid.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("wrote evidence/raster_grid.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
