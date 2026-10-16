#!/usr/bin/env python3
"""LG-035 R7 fixture builder (OFFLINE / acquisition-only).

Builds a genuine published-grid TABLE fixture from a real official born-digital
PDF, plus a mixed born-digital + real-scan composite PDF fixture.

NO model / OCR / embedding / ASR / product-LAN call is made here. Everything is
local: pypdfium2 (product rasteriser, already a product dependency) + stdlib.

Provenance:
  * Born-digital source: NIST SP 811 (2008), "Guide for the Use of the
    International System of Units (SI)", official NIST Publications host
    https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication811e2008.pdf
    US Government work -> public domain (17 U.S.C. 105). Native text layer,
    human-authored (not OCR).
  * Table: Table 1 "SI base units", PDF page 16 (0-indexed 15) of that file.
  * Real scan source (reused, unchanged): tesseract-ocr/test fixtures already
    committed under probes/lg035/fixtures/ (Apache-2.0).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import struct
import zlib

import pypdfium2 as pdfium

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # worktree root
SRC = HERE / "sources" / "nist-sp811" / "nistspecialpublication811e2008.pdf"
OUT = HERE / "fixtures"
SCAN_DIR = ROOT / "probes" / "lg035" / "fixtures"

# ---------------------------------------------------------------------------
# Region of interest: Table 1 "SI base units", PDF page 16.
# PDF coordinate system: origin bottom-left, y increases upward, points (72/inch).
# Bounds derived from the native text layer of that page (see truth manifest).
#   caption row ("Table 1. SI base units")        y 630.2 .. 637.3
#   spanning column header ("SI base unit")       y 617.0 .. 624.2
#   column-label header ("Base quantity ...")     y 603.2 .. 612.2
#   seven data rows                               y 522.2 .. 591.2
# ---------------------------------------------------------------------------
PAGE_INDEX = 15  # 0-indexed page 16
TABLE_BOX = (90.0, 517.0, 524.6, 627.5)   # grid only (header + 7 rows), no caption
CAPTION_BOX = (90.0, 628.0, 524.6, 638.5)  # caption line, kept as whole-page ref only
CONTEXT_BOX = (90.0, 510.0, 524.6, 645.0)  # caption + grid + a little context
RENDER_SCALE = 4.0  # product MAX_OCR_SCALE, deterministic

# Column x boundaries (points) measured from native char geometry:
#   col1 "Base quantity" starts x~95.6, col2 "Name" x~266.6, col3 "Symbol" x~438.8
#   per-row gaps > 50 pt separate the three cells.
COL_BOUNDS = (0.0, 210.0, 430.0, 10000.0)

# Human cell truth, transcribed from the PDF's ORIGINAL TEXT LAYER
# (pypdfium2 get_text_bounded / pdftotext -layout), BEFORE any model call.
TABLE_HEADER = ["Base quantity", "Name", "Symbol"]
TABLE_ROWS = [
    ["length", "meter", "m"],
    ["mass", "kilogram", "kg"],
    ["time", "second", "s"],
    ["electric current", "ampere", "A"],
    ["thermodynamic temperature", "kelvin", "K"],
    ["amount of substance", "mole", "mol"],
    ["luminous intensity", "candela", "cd"],
]


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _png_gray8(width: int, height: int, rows: list[bytes]) -> bytes:
    """Minimal stdlib grayscale-8 PNG encoder (matches product encoder shape)."""
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def bitmap_to_png(bitmap) -> bytes:
    """Encode a pypdfium2 bitmap to PNG (grayscale or BGR/BGRA), stdlib only."""
    fmt = int(bitmap.format)
    width = int(bitmap.width)
    height = int(bitmap.height)
    stride = int(bitmap.stride)
    buf = bytes(bitmap.buffer)
    if fmt == 1:  # FPDFBITMAP_GRAY
        rows = [buf[r * stride : r * stride + width] for r in range(height)]
        return _png_gray8(width, height, rows)
    # BGR/BGRX/BGRA -> convert to gray
    channels = 4 if fmt in (4, 5) else 3
    rows = []
    for r in range(height):
        line = buf[r * stride : r * stride + width * channels]
        gray = bytearray(width)
        for x in range(width):
            b, g, rr = line[x * channels], line[x * channels + 1], line[x * channels + 2]
            gray[x] = (rr * 299 + g * 587 + b * 114) // 1000
        rows.append(bytes(gray))
    return _png_gray8(width, height, rows)


def render_png(doc, page_index: int, *, scale: float, box: tuple[float, float, float, float] | None = None) -> bytes:
    """Render a page (optionally restricted to PDF-coordinate bounds) to PNG.

    Cropping uses the PDF-native CropBox (``set_cropbox``) in PDF points, so the
    region is expressed in original page coordinates and the source file is
    never mutated (pypdfium2 edits only the in-memory document handle).
    """
    page = doc[page_index]
    try:
        if box is not None:
            page.set_cropbox(*box)
        bitmap = page.render(scale=scale)
        try:
            return bitmap_to_png(bitmap)
        finally:
            bitmap.close()
    finally:
        page.close()


def build_table_truth() -> dict:
    """Ground-truth cell matrix + provenance, from the native text layer."""
    cells = []
    for r, row in enumerate([TABLE_HEADER] + TABLE_ROWS):
        for c, val in enumerate(row):
            cells.append({"row": r, "col": c, "text": val})
    return {
        "source_kind": "born_digital_native_text_human_authored",
        "is_ocr": False,
        "header": TABLE_HEADER,
        "rows": TABLE_ROWS,
        "n_rows_data": len(TABLE_ROWS),
        "n_cols": len(TABLE_HEADER),
        "cells": cells,
        "cell_matrix_shape": [len(TABLE_ROWS) + 1, len(TABLE_HEADER)],
        "column_source": "PDF native text layer, 'Table 1. SI base units' (NIST SP 811, p.16)",
        "transcription_note": (
            "Row/column split verified mechanically: per-row native char boxes show "
            "three cells separated by >50 pt gaps at consistent column starts."
        ),
    }


def build_scan_list() -> list[dict]:
    """Reused real-scan fixtures (tesseract-ocr/test, Apache-2.0), unchanged."""
    out = []
    for name, tif in (
        ("phototest.tif", SCAN_DIR / "phototest.tif"),
        ("8071_093.3B.tif", SCAN_DIR / "8071_093.3B.tif"),
    ):
        if tif.exists():
            out.append(
                {
                    "name": name,
                    "path": str(tif.relative_to(ROOT)),
                    "sha256": sha256_file(tif),
                    "bytes": tif.stat().st_size,
                    "license": "Apache-2.0 (tesseract-ocr/test)",
                }
            )
    return out


def _page_has_text_layer(doc_path: pathlib.Path, page_index: int) -> bool:
    """Mechanically test for a native text layer via pypdfium2 (no OCR)."""
    doc = pdfium.PdfDocument(str(doc_path))
    try:
        page = doc[page_index]
        try:
            tp = page.get_textpage()
            return tp.count_chars() > 0
        finally:
            page.close()
    finally:
        doc.close()


def build_mixed_pdf() -> dict:
    """Composite one born-digital page (native text) + one real scan page (no text).

    Page 1: NIST SP 811 page 16  -> born-digital, native text layer present.
    Page 2: clear_real.pdf page 1 -> real scan (tesseract-ocr/test), no text layer.
    The composite is an explicit TEST FIXTURE; it is NOT an unmodified
    historical document.
    """
    scan_pdf = SCAN_DIR / "clear_real.pdf"
    out_path = OUT / "mixed_born_digital_plus_scan.pdf"
    src = pdfium.PdfDocument(str(SRC))
    scan = pdfium.PdfDocument(str(scan_pdf))
    out = pdfium.PdfDocument.new()
    try:
        out.import_pages(src, [PAGE_INDEX])
        out.import_pages(scan, [0])
        out.save(str(out_path))
    finally:
        out.close()
        src.close()
        scan.close()
    return {
        "path": str(out_path.relative_to(ROOT)),
        "sha256": sha256_file(out_path),
        "bytes": out_path.stat().st_size,
        "page1": {
            "provenance": "born_digital NIST SP 811 page 16 (native text layer)",
            "source_sha256": sha256_file(SRC),
            "native_text_layer_present": _page_has_text_layer(out_path, 0),
        },
        "page2": {
            "provenance": "real scan clear_real.pdf (tesseract-ocr/test, Apache-2.0)",
            "source_sha256": sha256_file(scan_pdf),
            "native_text_layer_present": _page_has_text_layer(out_path, 1),
        },
        "disclosure": (
            "Composite TEST FIXTURE assembled locally from one born-digital page and "
            "one real-scan page. Not an unmodified original historical document. "
            "Page 1 keeps its native text layer; page 2 is a scan with no text layer."
        ),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(SRC))
    try:
        page_count = len(doc)

        # 1. Whole-page reference of the born-digital page (native text preserved).
        full_png = render_png(doc, PAGE_INDEX, scale=2.0)
        (OUT / "born_digital_table_page16_full_scale2.png").write_bytes(full_png)

        # 2. Cropped table grid region via product-native PDF coordinate bounds.
        crop_table = render_png(doc, PAGE_INDEX, scale=RENDER_SCALE, box=TABLE_BOX)
        (OUT / "honest_table_grid_scale4.png").write_bytes(crop_table)

        # 3. Cropped region containing caption+grid (context).
        crop_ctx = render_png(doc, PAGE_INDEX, scale=2.0, box=CONTEXT_BOX)
        (OUT / "born_digital_table_region_scale2.png").write_bytes(crop_ctx)

        # 4. Extract native text layer of the table region (human-authored truth).
        page = doc[PAGE_INDEX]
        try:
            tp = page.get_textpage()
            tp.count_rects()
            table_text_rects = []
            for i in range(tp.count_rects()):
                l, b, r, t = tp.get_rect(i)
                if 515.0 <= b <= 645.0:
                    txt = tp.get_text_bounded(left=l - 0.5, bottom=b - 0.5, right=r + 0.5, top=t + 0.5)
                    table_text_rects.append(
                        {"rect": [round(l, 2), round(b, 2), round(r, 2), round(t, 2)], "text": txt}
                    )
        finally:
            page.close()
    finally:
        doc.close()

    truth = build_table_truth()
    scan_list = build_scan_list()

    # 5. Mixed born-digital + real-scan composite PDF fixture.
    mixed_info = build_mixed_pdf()

    src_sha256 = sha256_file(SRC)
    manifest = {
        "package": "LG-035 R7 materials fixtures",
        "purpose": "offline/acquisition-only fixtures: genuine published grid table + mixed born-digital+scan PDF",
        "model_ocr_embedding_asr_calls": 0,
        "product_lan_calls": 0,
        "born_digital_source": {
            "title": "Guide for the Use of the International System of Units (SI), NIST SP 811 (2008)",
            "issuer": "National Institute of Standards and Technology (US federal)",
            "url": "https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication811e2008.pdf",
            "host": "nvlpubs.nist.gov (official NIST Publications)",
            "license": "US Government work -> public domain (17 U.S.C. 105)",
            "sha256": src_sha256,
            "bytes": SRC.stat().st_size,
            "pdf_pages": page_count,
            "native_text_layer": True,
            "page_used": PAGE_INDEX + 1,
            "table": "Table 1. SI base units",
        },
        "table_region_pdf_coords_points": list(TABLE_BOX),
        "caption_region_pdf_coords_points": list(CAPTION_BOX),
        "render_scale": RENDER_SCALE,
        "table_truth": truth,
        "native_text_rects_in_region": table_text_rects,
        "outputs": {
            "born_digital_table_page16_full_scale2.png": sha256_bytes(full_png),
            "honest_table_grid_scale4.png": sha256_bytes(crop_table),
            "born_digital_table_region_scale2.png": sha256_bytes(crop_ctx),
        },
        "mixed_fixture": mixed_info,
        "reused_real_scans": scan_list,
        "disclosure": (
            "The table page is BORN-DIGITAL (native text), not a historical scan; it is NOT "
            "claimed to be a scanned document. Real-document OCR applies because the product "
            "rasterises the real published page and the model sees pixels."
        ),
    }
    (OUT / "table_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: manifest[k] for k in ("table_region_pdf_coords_points", "outputs")}, indent=2))
    print("wrote", OUT / "table_manifest.json")


if __name__ == "__main__":
    main()
