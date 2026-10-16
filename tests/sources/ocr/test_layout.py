"""Focused tests for the offline layout analysis (LG-035 R6, ``layout.py``).

These are **geometry/behaviour** tests, not OCR-quality tests.  They verify:

* the analysis is deterministic and coordinate-bearing (input SHA-256, boxes);
* a clean single-column page is **not** spuriously reported tabular;
* a real side-by-side two-column block **is** detected;
* explicit ruling is detected and flagged;
* blank / over-size inputs degrade honestly (no fabricated columns);
* region grouping separates a single-column block from a multi-column block;
* the PNG decoder round-trips the product rasteriser's exact output format;
* boundary/overflow inputs raise clear errors instead of looping or guessing.

No OCR / network / model is used.  Fixtures are tiny geometry vectors built
with the standard library, not quality samples.
"""

from __future__ import annotations

import struct
import zlib

import pytest

from lightgravity.sources.ocr.layout import (
    MAX_PAGE_SIDE,
    ColumnRegion,
    LayoutAnalysis,
    LayoutAnalysisError,
    PageGeometry,
    analyse_image_bytes,
    analyse_page,
    decode_png_gray,
)


# ------------------------------------------------------------- tiny raster kit
def blank(width: int, height: int, value: int = 255) -> bytearray:
    return bytearray([value] * (width * height))


def fill_rect(
    buf: bytearray, width: int, x0: int, y0: int, x1: int, y1: int, value: int = 0
) -> None:
    for y in range(y0, y1):
        base = y * width
        for x in range(x0, x1):
            buf[base + x] = value


def encode_gray_png(width: int, height: int, gray: bytes) -> bytes:
    """Encode an 8-bit grayscale PNG with the standard library (filter 0)."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + gray[y * width : (y + 1) * width] for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def text_lines_fixture(
    width: int,
    height: int,
    cols: list[tuple[int, int]],
    *,
    line_h: int = 8,
    line_gap: int = 10,
    margin: int = 20,
    word_gap: int = 12,
) -> tuple[bytearray, int]:
    """Draw ``cols`` side-by-side columns of *word-like* text bars.

    Each line is broken into short word bars separated by gaps so that no row
    is a single straight full-width dark run (which would (correctly) be read as
    a horizontal rule by a real interface).  This keeps the fixture representative
    of free text, not of a ruled form.
    """

    buf = blank(width, height)
    y = margin
    lines = 0
    while y + line_h <= height - margin:
        # Deterministic per-line offset so word gaps do not align vertically
        # into accidental "rules" (real text words do not stack in columns).
        jitter = (lines * 5) % word_gap
        for (x0, x1) in cols:
            x = x0 + jitter
            while x < x1:
                w = min(max(4, word_gap // 2), x1 - x)
                if w <= 0:
                    break
                fill_rect(buf, width, x, y, x + w, y + line_h)
                x += word_gap
        y += line_h + line_gap
        lines += 1
    return buf, lines


# ----------------------------------------------------------------------- tests
def test_single_column_page_is_not_tabular() -> None:
    """An ordinary full-width text page must stay single-column."""

    width, height = 400, 600
    buf, lines = text_lines_fixture(width, height, [(40, 360)])
    assert lines > 5
    analysis = analyse_page(bytes(buf), width, height, page=1)

    assert analysis.status == "ok"
    assert analysis.column_count == 1
    assert analysis.max_region_columns == 1
    assert analysis.is_multicolumn is False
    assert analysis.has_ruling is False
    # The single column spans essentially the drawn ink extent.
    col = analysis.columns[0]
    assert col.x0 <= 45
    assert col.x1 >= 355


def test_two_column_block_is_detected() -> None:
    """A genuine side-by-side layout must be reported as 2 columns."""

    width, height = 400, 600
    buf, _ = text_lines_fixture(width, height, [(30, 170), (230, 370)])
    analysis = analyse_page(bytes(buf), width, height, page=1)

    assert analysis.status == "ok"
    assert analysis.max_region_columns == 2
    assert analysis.is_multicolumn is True
    # There is a real gutter between the two columns (around x=170..230).
    columns = analysis.columns
    assert len(columns) == 2
    assert columns[0].x1 < 200 < columns[1].x0


def test_mixed_single_and_double_column_regions() -> None:
    """A page that mixes single- and multi-column blocks keeps both facts."""

    width, height = 400, 700
    buf = blank(width, height)
    # Region A: one full-width line near the top.
    fill_rect(buf, width, 40, 40, 360, 60)
    # Region B (after a large gap): two side-by-side columns.
    for y in range(200, 400, 20):
        fill_rect(buf, width, 30, y, 170, y + 10)
        fill_rect(buf, width, 230, y, 370, y + 10)
    analysis = analyse_page(bytes(buf), width, height, page=1)

    assert analysis.status == "ok"
    assert len(analysis.regions) >= 2
    # At least one region is multi-column and the page summary reflects it.
    assert analysis.max_region_columns == 2
    assert analysis.is_multicolumn is True


def test_explicit_horizontal_ruling_is_detected() -> None:
    """Long straight dark runs are reported as ruling, not as text columns."""

    width, height = 400, 300
    buf = blank(width, height)
    # A ruled table: two horizontal rules and one vertical rule.
    fill_rect(buf, width, 40, 80, 360, 84)  # horizontal rule (wide)
    fill_rect(buf, width, 40, 200, 360, 204)  # horizontal rule
    fill_rect(buf, width, 200, 80, 204, 204)  # vertical rule
    # A little text in each cell so there is ink.
    fill_rect(buf, width, 60, 120, 160, 140)
    fill_rect(buf, width, 240, 120, 340, 140)
    analysis = analyse_page(bytes(buf), width, height, page=1)

    assert analysis.status == "ok"
    assert analysis.has_ruling is True
    assert analysis.horizontal_rules, "expected at least one horizontal rule"
    assert analysis.vertical_rules, "expected at least one vertical rule"
    assert any("ruling" in w for w in analysis.warnings)


def test_blank_page_reports_blank_not_columns() -> None:
    width, height = 200, 200
    analysis = analyse_page(bytes(blank(width, height)), width, height)
    assert analysis.status == "blank"
    assert analysis.column_count == 0
    assert analysis.lines == ()
    assert analysis.content_box is None


def test_oversize_page_is_refused_honestly() -> None:
    """An over-limit raster yields ``too_large`` with no fabricated structure."""

    # Do not actually allocate this; just claim the dimensions.  The analyser
    # must refuse before touching the (short) buffer.
    analysis = analyse_page(b"", MAX_PAGE_SIDE + 1, 10)
    assert analysis.status == "too_large"
    assert analysis.column_count == 0
    assert analysis.reason is not None


def test_short_buffer_raises_clear_error() -> None:
    with pytest.raises(LayoutAnalysisError):
        analyse_page(b"\x00" * 10, 100, 100)


def test_invalid_threshold_is_rejected() -> None:
    with pytest.raises(LayoutAnalysisError):
        analyse_page(bytes(blank(10, 10)), 10, 10, ink_threshold=300)
    with pytest.raises(LayoutAnalysisError):
        analyse_page(bytes(blank(10, 10)), 10, 10, min_gutter_px=0)


def test_deterministic_coordinates_and_input_hash() -> None:
    width, height = 300, 200
    buf, _ = text_lines_fixture(width, height, [(20, 280)], line_h=6, line_gap=8)
    data = bytes(buf)
    a = analyse_page(data, width, height, page=7, geometry=PageGeometry(page=7, scale=2.0))
    b = analyse_page(data, width, height, page=7, geometry=PageGeometry(page=7, scale=2.0))

    assert a.to_dict() == b.to_dict()
    assert a.page == 7
    assert a.geometry.scale == 2.0
    assert len(a.input_sha256) == 64
    # Coordinates are integers within the raster.
    for line in a.lines:
        assert 0 <= line.y0 <= line.y1 < height
        assert 0 <= line.x0 <= line.x1 < width
    for col in a.columns:
        assert 0 <= col.x0 <= col.x1 < width


def test_png_roundtrip_matches_product_encoder_format() -> None:
    """Decode the exact PNG shape the product rasteriser writes."""

    width, height = 60, 40
    buf, _ = text_lines_fixture(width, height, [(10, 50)], line_h=4, line_gap=6)
    png = encode_gray_png(width, height, bytes(buf))

    gray, w, h = decode_png_gray(png)
    assert (w, h) == (width, height)
    assert gray == bytes(buf)

    from_png = analyse_image_bytes(png, page=1)
    from_raw = analyse_page(bytes(buf), width, height, page=1)
    # Geometry/coordinates are identical; only the recorded provenance hash differs
    # (PNG bytes vs. decoded gray buffer), which is exactly the intent.
    assert from_png.content_box == from_raw.content_box
    assert [c.to_dict() for c in from_png.columns] == [c.to_dict() for c in from_raw.columns]
    assert from_png.input_sha256 != from_raw.input_sha256


@pytest.mark.parametrize("via", ["raw", "png"])
def test_input_provenance_hash_is_over_exact_bytes(via: str) -> None:
    """The recorded hash must match the exact bytes handed to the analyser."""

    import hashlib

    width, height = 50, 30
    buf, _ = text_lines_fixture(width, height, [(10, 40)], line_h=4, line_gap=6)
    gray = bytes(buf)
    if via == "raw":
        analysis = analyse_page(gray, width, height)
        assert analysis.input_sha256 == hashlib.sha256(gray).hexdigest()
    else:
        png = encode_gray_png(width, height, gray)
        analysis = analyse_image_bytes(png)
        assert analysis.input_sha256 == hashlib.sha256(png).hexdigest()


def test_png_rgb_is_converted_to_gray() -> None:
    """An RGB PNG (product BGR->RGB path) decodes to a gray buffer."""

    width, height = 8, 2
    # All-white RGB image.
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    gray, w, h = decode_png_gray(png)
    assert (w, h) == (width, height)
    assert set(gray) == {255}


def test_non_png_bytes_are_rejected() -> None:
    with pytest.raises(LayoutAnalysisError):
        analyse_image_bytes(b"\xff\xd8\xff\xe0 not a png")


def test_column_region_reports_gutters() -> None:
    width, height = 400, 400
    buf, _ = text_lines_fixture(width, height, [(30, 170), (230, 370)])
    analysis = analyse_page(bytes(buf), width, height)

    multi = [c for c in analysis.columns if c.gutter_right is not None]
    assert multi, "expected an interior gutter"
    gutter = multi[0].gutter_right
    assert gutter is not None
    g0, g1 = gutter
    # The gutter overlaps the whitespace between the two drawn column ranges.
    assert g0 >= 165 and g1 <= 235


def test_analyse_rendered_page_uses_product_rasteriser() -> None:
    """The analysis must work on the exact PNG the product rasteriser emits.

    This drives the real ``PdfiumRasterizer`` product path (no OCR/network) and
    checks the provenance/hash contract end to end.
    """

    import hashlib
    import io

    import pypdfium2 as pdfium

    from lightgravity.sources.ocr import PdfiumRasterizer
    from lightgravity.sources.ocr.layout import analyse_rendered_page

    document = pdfium.PdfDocument.new()
    page = document.new_page(200, 100)
    page.close()
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()

    rendered = PdfiumRasterizer().render(buffer.getvalue(), scale=2.0)
    assert rendered
    analysis = analyse_rendered_page(rendered[0], scale=2.0)
    assert analysis.page == 1
    assert analysis.input_sha256 == hashlib.sha256(rendered[0].png).hexdigest()
    assert analysis.geometry.scale == 2.0
    assert analysis.status in ("ok", "blank")


# ------------------------------------------------- cross-scale acceptance (R7)
#: Predeclared tolerance for normalized (per-render-scale) region coordinates.
#: Topology is asserted *exactly*; only box edges are allowed this much drift,
#: because 1x rasterisation drops faint right-edge word fragments below the ink
#: threshold.  The value is fixed before comparison and is far too small to let
#: a real gutter be lost or a region collapse (a collapsed page would differ by
#: the whole gutter width, ~40+ normalized px here).
CROSS_SCALE_COORD_TOLERANCE_NORM = 15.0

_Z2 = "probes/materials-ocr-r4-20261016/private/LG035-ZH-Z2.pdf"
_CONTROL = "probes/lg035/fixtures/clear_real.pdf"


def _render_analyse(pdf: str, page: int, scale: float):  # type: ignore[no-untyped-def]
    import pathlib

    import pypdfium2 as pdfium

    from lightgravity.sources.ocr import PdfiumRasterizer
    from lightgravity.sources.ocr.layout import analyse_rendered_page

    root = pathlib.Path(__file__).resolve().parents[3]
    path = root / pdf
    if not path.exists():
        pytest.skip(f"fixture missing: {pdf}")
    document = pdfium.PdfDocument(path.read_bytes())
    raster = PdfiumRasterizer().render(path.read_bytes(), scale=scale, max_pages=page)
    assert len(raster) >= page
    analysis = analyse_rendered_page(raster[page - 1], scale=scale)
    return analysis


def _norm_regions(analysis) -> list[dict]:  # type: ignore[no-untyped-def]
    return [
        {
            "index": r.index,
            "cols": r.column_count,
            "y_norm": [round(r.y0 / analysis.geometry.scale, 2), round(r.y1 / analysis.geometry.scale, 2)],
            "boxes_norm": [
                [round(c.x0 / analysis.geometry.scale, 2), round(c.x1 / analysis.geometry.scale, 2)]
                for c in r.columns
            ],
        }
        for r in analysis.regions
    ]


def test_z2_side_by_side_region_is_stable_across_scales() -> None:
    """The real Z2 page keeps its multi-column topology at 1x/2x/4x.

    Exact: high-level column model, region count vector, and the presence of the
    side-by-side (two-column) region.  Within tolerance: normalized region
    coordinates.  This is the anti-collapse acceptance: a page whose real gutter
    vanished at some scale would fail the exact checks, not slip through.
    """

    scales = (1.0, 2.0, 4.0)
    per_scale = {s: _render_analyse(_Z2, 2, s) for s in scales}

    models = {s: a.column_model for s, a in per_scale.items()}
    assert len(set(models.values())) == 1, models
    # The real side-by-side block must stay multi-column at every scale.
    assert per_scale[1.0].is_multicolumn is True
    assert per_scale[1.0].max_region_columns == 2
    assert per_scale[2.0].max_region_columns == 2
    assert per_scale[4.0].max_region_columns == 2

    counts = {s: tuple(r.column_count for r in a.regions) for s, a in per_scale.items()}
    assert len(set(counts.values())) == 1, counts

    ref = _norm_regions(per_scale[1.0])
    two_col = [r for r in ref if r["cols"] == 2]
    assert len(two_col) == 1, "expected exactly one side-by-side region"
    idx = two_col[0]["index"]

    for s in (2.0, 4.0):
        got = _norm_regions(per_scale[s])
        assert got[idx]["cols"] == 2, f"side-by-side lost at {s}x"
        for r_ref, r_got in zip(ref, got):
            assert r_ref["index"] == r_got["index"]
            assert r_ref["cols"] == r_got["cols"]
            for a, b in zip(r_ref["y_norm"], r_got["y_norm"]):
                assert abs(a - b) <= CROSS_SCALE_COORD_TOLERANCE_NORM
            for box_ref, box_got in zip(r_ref["boxes_norm"], r_got["boxes_norm"]):
                for a, b in zip(box_ref, box_got):
                    assert abs(a - b) <= CROSS_SCALE_COORD_TOLERANCE_NORM


def test_ordinary_control_stays_single_column_across_scales() -> None:
    """The ordinary English control must never be promoted to multi-column."""

    for scale in (1.0, 2.0, 4.0):
        a = _render_analyse(_CONTROL, 1, scale)
        assert a.column_model == "single_column", (scale, a.column_model)
        assert tuple(r.column_count for r in a.regions) == (1,), (scale, a.regions)
        assert a.is_multicolumn is False


def test_png_decoder_bounds_declared_geometry() -> None:
    """A PNG claiming an over-limit page is refused before decompression."""

    # IHDR claims a 9000x9000 grayscale page (> MAX_PAGE_SIDE) with a tiny IDAT.
    ihdr = struct.pack(">IIBBBBB", 9000, 9000, 8, 0, 0, 0, 0)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00" * 64))
        + chunk(b"IEND", b"")
    )
    with pytest.raises(LayoutAnalysisError):
        decode_png_gray(png)


def test_png_decoder_rejects_over_long_idat_stream() -> None:
    """An IDAT that inflates beyond the declared size is refused, not looped."""

    width, height = 4, 4
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    # Declared row bytes are (4+1)*4 = 20; this stream inflates far beyond.
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00" * 10000))
        + chunk(b"IEND", b"")
    )
    with pytest.raises(LayoutAnalysisError):
        decode_png_gray(png)
