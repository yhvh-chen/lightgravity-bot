"""Offline, program-side layout / page geometry analysis for OCR (LG-035 R6).

This module is the **Phase A prototype** for layout-aware page analysis.  It is
deliberately *offline* and *model-free*: it never performs OCR, never calls a
model, never uses ground truth, and never edits an image.  It only measures the
pixels of an already-rendered page (and, optionally, the PDF page geometry the
product rasteriser exposes) to answer a bounded set of structural questions:

* where the ink is (content bounding box, margins);
* which horizontal bands are text lines (row projection + whitespace gaps);
* which vertical whitespace gutters separate candidate columns (column
  projection restricted to the content band);
* whether the page carries explicit ruling (long straight dark runs);
* whether a clean, connected multi-column *table-like* region exists at all.

Why this exists
---------------
The R3/R4/R5 scoring result for the real Z2 table page showed that a *plain OCR
text instruction* cannot recover row/column structure: the model emitted no
machine table and the segment CER stayed above the frozen threshold.  The
honest conclusion was that structural recovery must happen **program-side**
(detect rules/gutters, segment regions, then transcribe per cell/column), not
by another prompt lottery.  This module is the first, testable building block of
that program-side path.

Hard invariants
---------------
* **No network**: the module imports only the standard library.
* **Bounded work**: input dimensions and the number of analysed regions are
  capped; an over-limit input yields an explicit, honest *insufficient*
  analysis, never an unbounded loop.
* **Deterministic**: identical bytes give byte-identical coordinates.
* **No false tabular claim**: a page without explicit ruling and without a
  repeating multi-column gutter is reported single-column.  "Looks like
  text" must not be promoted to "is a table".
* **No hidden truth**: the algorithm is a pure function of pixels (and geometry);
  it never reads the human truth file.
* **Scale-invariant topology (R7)**: the column model and per-region column
  counts are stable at 1x/2x/4x because every gutter/line rule is normalised by
  the median text-line height (a pixel ratio that scales linearly).  Only region
  box edges may drift with rasterisation; the real side-by-side region is never
  collapsed to a single column.

The public entry points are :func:`analyse_page` for a raw grayscale buffer and
:func:`analyse_image_bytes` for an encoded PNG/JPEG page, plus the small data
classes that describe the result.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any

#: A pixel is "ink" when its 0-255 luminance is strictly below this threshold.
#: 128 is the midpoint used by the existing probe harnesses; it is a documented
#: constant, not a per-page tuning knob.
DEFAULT_INK_THRESHOLD = 128

#: Largest page (in pixels per side) the analyser will accept.  A larger raster
#: is reported as ``too_large`` instead of being silently downscaled (which
#: would change the coordinate provenance).
MAX_PAGE_SIDE = 8000

#: Largest total pixel count accepted (bounded memory/work).
MAX_PAGE_PIXELS = 24_000_000

#: A whitespace gap must span at least this many pixels to be a candidate
#: gutter/line separator.  This is an **absolute floor** for tiny rasters; the
#: effective minimum is raised by the scale-normalised rules below so the same
#: page gives the same model at 1x/2x/4x.  Expressed in pixels.
MIN_GUTTER_PX = 4

#: Scale-normalised gutter rule (the core R7 fix).  A real column gutter is at
#: least this fraction of the *median text-line height* in pixels.  Both the
#: gutter and the line height scale linearly with render scale, so this ratio is
#: **scale-invariant**: real side-by-side gutters measure 0.9-2.2x the line
#: height on the real Z2 page at 1x/2x/4x, while CJK inter-character spacings
#: measure <= 0.7x.  0.9x sits in the measured stable plateau and keeps the
#: topology identical across scales.  This is a pure pixel ratio (no page/text/
#: GT data).
GUTTER_LINE_HEIGHT_FACTOR = 0.9

#: Physical floor for the effective gutter when PDF point geometry is known:
#: a real column gutter is at least this many PDF points (1/72 inch) wide,
#: independent of render scale.  Used as an additional lower bound.
MIN_GUTTER_PT = 8.0

#: Per-line-band emptiness requirement (scale-invariant).  A candidate gutter
#: must be ink-free in at least this fraction of the region's **text-line
#: bands**, not merely this fraction of its rows.  A genuine column gutter (the
#: Z2 side-by-side split, the label column) is empty in every text line; a
#: ragged CJK inter-character gap is occupied by some lines, so it fails.  This
#: is what stops 1x raster aliasing from promoting a ragged gap to a column.
GUTTER_LINE_BAND_EMPTY_FRACTION = 0.6

#: A vertical gutter must also carry at least this fraction of the region-band
#: height as *no ink*.  Kept as a cheap secondary guard alongside the per-line
#: rule above.
GUTTER_EMPTY_FRACTION = 0.90

#: A horizontal rule must cover at least this fraction of the content width.
RULE_WIDTH_FRACTION = 0.60

#: A vertical rule must cover at least this fraction of the content height.
RULE_HEIGHT_FRACTION = 0.40

#: A band with at least this much ink is a text line.
MIN_LINE_INK = 10

#: Relative ink floor: a band must carry at least this fraction of the *largest
#: band ink* to be a real text line.  Band ink scales with the squared render
#: scale, so this relative floor is scale-invariant and stops a speck that is
#: filtered at 2x from becoming a phantom line at 4x (which would perturb region
#: grouping and the column model).  Measured on the real Z2 page, real text
#: lines carry ~1x the largest band ink while scan specks carry < 1/1000, so
#: 1/50 is a wide, safe separation.
RELATIVE_MIN_LINE_INK_FRACTION = 0.02
MAX_RELATIVE_MIN_LINE_INK_FRACTION = 1.0 / 50.0

#: A vertical gap of at least this multiple of the median line height starts a
#: new layout region (section break), so per-region column analysis can run.
REGION_GAP_FACTOR = 1.6

#: Minimum accepted column width.  The fraction is relative to the region's
#: own ink span and is therefore already scale-invariant; the pixel floor only
#: guards tiny rasters.  A split that would leave a narrower sliver is merged
#: into its neighbour instead of being reported as a column.  The fraction was
#: raised from the R6 value (0.06) because at 4x the CJK spacing produced
#: narrow false slivers that passed the old test.
MIN_COLUMN_WIDTH_PX = 8
MIN_COLUMN_WIDTH_FRACTION = 0.10
#: A candidate column must also be at least this many median line heights wide,
#: so a one-character sliver is never promoted to a column.  Scale-invariant.
MIN_COLUMN_WIDTH_LINE_FACTOR = 0.5


class LayoutAnalysisError(Exception):
    """A clear layout-analysis failure (never fabricated structure)."""


@dataclass(frozen=True, slots=True)
class PageGeometry:
    """Optional PDF geometry for a page, when the rasteriser can provide it.

    Values are PDF user units (1/72 inch).  ``None`` fields mean "unknown";
    the pixel analysis is still valid without geometry, it just cannot report
    absolute physical provenance.
    """

    page: int | None = None
    width_pt: float | None = None
    height_pt: float | None = None
    scale: float | None = None


@dataclass(frozen=True, slots=True)
class TextLine:
    """One horizontal text band with its pixel bounds."""

    index: int
    y0: int
    y1: int
    x0: int
    x1: int
    ink: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "y0": self.y0,
            "y1": self.y1,
            "x0": self.x0,
            "x1": self.x1,
            "ink": self.ink,
        }


@dataclass(frozen=True, slots=True)
class ColumnRegion:
    """A candidate column: a vertical slice of the content band.

    ``gutter_left``/``gutter_right`` are the x-ranges of the vertical whitespace
    gutters that bound this column, so the exact split is reproducible.
    """

    index: int
    x0: int
    x1: int
    width: int
    gutter_left: tuple[int, int] | None
    gutter_right: tuple[int, int] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "x0": self.x0,
            "x1": self.x1,
            "width": self.width,
            "gutter_left": list(self.gutter_left) if self.gutter_left else None,
            "gutter_right": list(self.gutter_right) if self.gutter_right else None,
        }


@dataclass(frozen=True, slots=True)
class RegionAnalysis:
    """Layout of one vertical region (a group of consecutive text lines).

    A region is a maximal run of text lines whose inter-line gaps are below the
    section-separation threshold.  Column detection runs **per region**, not
    just globally, because a page can mix a single-column block with a genuine
    side-by-side (multi-column) block — the exact failure mode of a global-only
    projection.
    """

    index: int
    y0: int
    y1: int
    line_indices: tuple[int, ...]
    columns: tuple[ColumnRegion, ...]

    @property
    def column_count(self) -> int:
        return len(self.columns)

    def crop_box(self) -> tuple[int, int, int, int]:
        """Inclusive pixel crop ``(x0, y0, x1, y1)`` covering this region."""

        x0 = min(c.x0 for c in self.columns)
        x1 = max(c.x1 for c in self.columns)
        return x0, self.y0, x1, self.y1

    def column_crops(self) -> list[tuple[int, int, int, int]]:
        """Inclusive pixel crop for each column of this region."""

        return [(c.x0, self.y0, c.x1, self.y1) for c in self.columns]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "y0": self.y0,
            "y1": self.y1,
            "line_indices": list(self.line_indices),
            "column_count": self.column_count,
            "crop_box": list(self.crop_box()),
            "column_crops": [list(b) for b in self.column_crops()],
            "columns": [c.to_dict() for c in self.columns],
        }


@dataclass(frozen=True, slots=True)
class LayoutAnalysis:
    """Deterministic, coordinate-bearing description of one page's layout."""

    width: int
    height: int
    ink_threshold: int
    input_sha256: str
    page: int | None
    geometry: PageGeometry
    content_box: tuple[int, int, int, int] | None  # x0, y0, x1, y1 (inclusive)
    lines: tuple[TextLine, ...]
    columns: tuple[ColumnRegion, ...]
    regions: tuple[RegionAnalysis, ...]
    horizontal_rules: tuple[int, ...]
    vertical_rules: tuple[int, ...]
    mean_line_height: float
    #: Whether the analysis ran on the whole page or was refused for size.
    status: str
    reason: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def column_count(self) -> int:
        """Global (whole-page) column count from the content-band projection."""

        return len(self.columns)

    @property
    def max_region_columns(self) -> int:
        """Largest column count found in any single region (local structure)."""

        return max((r.column_count for r in self.regions), default=self.column_count)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def has_ruling(self) -> bool:
        return bool(self.horizontal_rules or self.vertical_rules)

    @property
    def is_multicolumn(self) -> bool:
        """True when *any* region shows a real side-by-side text column split."""

        return self.max_region_columns > 1

    @property
    def column_model(self) -> str:
        """Coarse, honest summary of the page's column layout.

        * ``blank``            — no ink;
        * ``single_column``    — one text column everywhere;
        * ``multi_column_local`` — at least one region is side-by-side while the
          page is not uniformly multi-column (the Z2 mixed case);
        * ``multi_column``     — every non-empty region is multi-column;
        * ``unanalysed``       — refused (over-size) or otherwise not measured.
        """

        if self.status != "ok":
            return "blank" if self.status == "blank" else "unanalysed"
        counts = [r.column_count for r in self.regions]
        if not counts or self.max_region_columns <= 1:
            return "single_column"
        if all(c > 1 for c in counts):
            return "multi_column"
        return "multi_column_local"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "lightgravity.bot/v1",
            "kind": "ocr_layout_analysis",
            "width": self.width,
            "height": self.height,
            "ink_threshold": self.ink_threshold,
            "input_sha256": self.input_sha256,
            "page": self.page,
            "geometry": {
                "page": self.geometry.page,
                "width_pt": self.geometry.width_pt,
                "height_pt": self.geometry.height_pt,
                "scale": self.geometry.scale,
            },
            "content_box": list(self.content_box) if self.content_box else None,
            "status": self.status,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "line_count": self.line_count,
            "column_count": self.column_count,
            "has_ruling": self.has_ruling,
            "is_multicolumn": self.is_multicolumn,
            "mean_line_height": self.mean_line_height,
            "horizontal_rules": list(self.horizontal_rules),
            "vertical_rules": list(self.vertical_rules),
            "max_region_columns": self.max_region_columns,
            "column_model": self.column_model,
            "lines": [line.to_dict() for line in self.lines],
            "columns": [col.to_dict() for col in self.columns],
            "regions": [region.to_dict() for region in self.regions],
        }


# --------------------------------------------------------------------- buffer
def _validate_buffer(data: bytes, width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise LayoutAnalysisError("width and height must be positive")
    expected = width * height
    if len(data) < expected:
        raise LayoutAnalysisError(
            f"buffer too small: have {len(data)} bytes, need {expected}"
        )


def _too_large(width: int, height: int) -> str | None:
    if width > MAX_PAGE_SIDE or height > MAX_PAGE_SIDE:
        return f"page side exceeds cap {MAX_PAGE_SIDE}px"
    if width * height > MAX_PAGE_PIXELS:
        return f"page pixels exceed cap {MAX_PAGE_PIXELS}"
    return None


# ------------------------------------------------------------------- analysis
def analyse_page(
    data: bytes,
    width: int,
    height: int,
    *,
    page: int | None = None,
    geometry: PageGeometry | None = None,
    ink_threshold: int = DEFAULT_INK_THRESHOLD,
    min_gutter_px: int = MIN_GUTTER_PX,
    min_line_ink: int = MIN_LINE_INK,
    input_sha256: str | None = None,
) -> LayoutAnalysis:
    """Analyse one grayscale (8-bit, row-major, stride=width) page raster.

    The function is pure and deterministic.  It returns a
    :class:`LayoutAnalysis` in every non-error case, including the honest
    ``too_large`` refusal (which carries *no* fabricated columns/lines).

    ``input_sha256`` overrides the recorded provenance hash.  When analysing a
    raw gray buffer the default is the SHA-256 of that buffer; when the caller
    decoded an encoded image, it must pass the hash of the **encoded bytes** so
    the provenance points at the exact bytes an OCR backend would see.
    """

    if not (0 <= ink_threshold <= 255):
        raise LayoutAnalysisError("ink_threshold must be within 0..255")
    if min_gutter_px < 1:
        raise LayoutAnalysisError("min_gutter_px must be >= 1")
    if min_line_ink < 1:
        raise LayoutAnalysisError("min_line_ink must be >= 1")

    digest = input_sha256 or hashlib.sha256(bytes(data[: width * height])).hexdigest()
    geo = geometry or PageGeometry(page=page)
    if geo.page is None and page is not None:
        geo = PageGeometry(
            page=page,
            width_pt=geo.width_pt,
            height_pt=geo.height_pt,
            scale=geo.scale,
        )

    too_large = _too_large(width, height)
    if too_large is not None:
        return LayoutAnalysis(
            width=width,
            height=height,
            ink_threshold=ink_threshold,
            input_sha256=digest,
            page=page,
            geometry=geo,
            content_box=None,
            lines=(),
            columns=(),
            regions=(),
            horizontal_rules=(),
            vertical_rules=(),
            mean_line_height=0.0,
            status="too_large",
            reason=too_large,
        )

    _validate_buffer(data, width, height)

    # 1. Ink mask + projections.
    col_ink = [0] * width
    row_ink = [0] * height
    for y in range(height):
        base = y * width
        row_count = 0
        for x in range(width):
            if data[base + x] < ink_threshold:
                col_ink[x] += 1
                row_count += 1
        row_ink[y] = row_count

    content_box = _content_box(col_ink, row_ink, width, height)
    if content_box is None:
        return LayoutAnalysis(
            width=width,
            height=height,
            ink_threshold=ink_threshold,
            input_sha256=digest,
            page=page,
            geometry=geo,
            content_box=None,
            lines=(),
            columns=(),
            regions=(),
            horizontal_rules=(),
            vertical_rules=(),
            mean_line_height=0.0,
            status="blank",
            reason="no ink found at the given threshold",
        )

    cx0, cy0, cx1, cy1 = content_box

    # 2. Horizontal text lines (bands between low-ink rows), noise-filtered.
    lines = _segment_lines(row_ink, cx0, cx1, width, cy0, cy1, data, ink_threshold, min_line_ink)

    # 2b. Scale-normalised geometry (the R7 fix).  The effective minimum gutter
    #     and column width are derived from the *median text-line height* in
    #     pixels plus, when available, the PDF point geometry.  Because both the
    #     line height and any real gutter scale linearly with render scale, the
    #     resulting column topology is the same at 1x/2x/4x.  This uses only
    #     pixels and point dimensions - never text, ground truth or page ids.
    median_line_height = _median_line_height(lines)
    px_per_pt = _pixels_per_point(width, geo)
    effective_min_gutter_px = _effective_min_gutter_px(
        median_line_height, px_per_pt, min_gutter_px
    )
    effective_min_col_width_px = _effective_min_col_width_px(median_line_height)

    # 3. Explicit ruling detection (long straight dark runs) — checked before
    #    any column claim so a ruled form is never confused with free text.
    horizontal_rules = _detect_horizontal_rules(data, width, cx0, cx1, cy0, cy1, ink_threshold)
    vertical_rules = _detect_vertical_rules(data, width, cx0, cx1, cy0, cy1, ink_threshold)

    # 4. Global (whole-page) candidate column gutters within the content band.
    all_bands = [(line.y0, line.y1) for line in lines]
    columns, gutter_warnings = _segment_columns(
        col_ink,
        cx0,
        cx1,
        cy0,
        cy1,
        effective_min_gutter_px,
        effective_min_col_width_px,
        data=data,
        width=width,
        line_bands=all_bands,
        ink_threshold=ink_threshold,
    )

    # 5. Region-aware local column detection (the real structural signal).
    regions = _segment_regions(
        data,
        width,
        col_ink,
        lines,
        cx0,
        cx1,
        effective_min_gutter_px,
        effective_min_col_width_px,
        ink_threshold,
    )

    mean_h = (
        sum(line.y1 - line.y0 + 1 for line in lines) / len(lines) if lines else 0.0
    )
    warnings = list(gutter_warnings)
    if horizontal_rules or vertical_rules:
        warnings.append(
            "explicit ruling detected; region/border analysis is a later step"
        )
    max_region_cols = max((r.column_count for r in regions), default=len(columns))
    if max_region_cols > 1 and not (horizontal_rules or vertical_rules):
        # Multi-column *free text* is reported, but a table claim is withheld:
        # without ruling we can only say "side-by-side text", not "table".
        warnings.append(
            "multi-column guard: side-by-side text columns detected without "
            "explicit ruling; reported as text columns, not a confirmed table"
        )

    return LayoutAnalysis(
        width=width,
        height=height,
        ink_threshold=ink_threshold,
        input_sha256=digest,
        page=page,
        geometry=geo,
        content_box=content_box,
        lines=tuple(lines),
        columns=tuple(columns),
        regions=tuple(regions),
        horizontal_rules=tuple(horizontal_rules),
        vertical_rules=tuple(vertical_rules),
        mean_line_height=round(mean_h, 3),
        status="ok",
        warnings=tuple(warnings),
    )


def _median_line_height(lines: list[TextLine]) -> float:
    """Median text-line height in pixels (0.0 when there are no lines).

    The median is scale-covariant: rendering the same page at 1x/2x/4x yields
    1x/2x/4x the pixel height.  Dividing a gutter width by it therefore gives a
    dimensionless, scale-invariant ratio.
    """

    if not lines:
        return 0.0
    heights = sorted(line.y1 - line.y0 + 1 for line in lines)
    return float(heights[len(heights) // 2])


def _pixels_per_point(width: int, geometry: PageGeometry) -> float | None:
    """Pixels per PDF point from the declared scale or the page point width.

    Returns ``None`` when no trustworthy geometry is available, in which case
    only the line-height rule applies.
    """

    if geometry.width_pt and geometry.width_pt > 0 and width > 0:
        return width / geometry.width_pt
    if geometry.scale and geometry.scale > 0:
        return geometry.scale
    return None


def _effective_min_gutter_px(
    median_line_height: float,
    px_per_pt: float | None,
    configured_floor: int,
) -> int:
    """Scale-normalised minimum gutter width in pixels.

    The minimum is the largest of:

    * the caller's absolute floor (``min_gutter_px``);
    * :data:`GUTTER_LINE_HEIGHT_FACTOR` x the median text-line height — the
      scale-invariant rule that distinguishes a real column gutter from
      inter-character spacing;
    * :data:`MIN_GUTTER_PT` PDF points, when point geometry is known.

    Every term scales with the render scale, so the accepted gutter set (and
    the page's column topology) is identical across render scales.
    """

    floor = max(int(configured_floor), 1)
    candidates = [floor]
    if median_line_height > 0:
        candidates.append(int(median_line_height * GUTTER_LINE_HEIGHT_FACTOR))
    if px_per_pt is not None:
        candidates.append(int(MIN_GUTTER_PT * px_per_pt))
    return max(candidates)


def _effective_min_col_width_px(median_line_height: float) -> int:
    """Scale-invariant minimum accepted column width in pixels."""

    candidates = [MIN_COLUMN_WIDTH_PX]
    if median_line_height > 0:
        candidates.append(int(median_line_height * MIN_COLUMN_WIDTH_LINE_FACTOR))
    return max(candidates)


def _content_box(
    col_ink: list[int], row_ink: list[int], width: int, height: int
) -> tuple[int, int, int, int] | None:
    xs = [x for x in range(width) if col_ink[x] > 0]
    ys = [y for y in range(height) if row_ink[y] > 0]
    if not xs or not ys:
        return None
    return xs[0], ys[0], xs[-1], ys[-1]


def _segment_lines(
    row_ink: list[int],
    cx0: int,
    cx1: int,
    width: int,
    cy0: int,
    cy1: int,
    data: bytes,
    ink_threshold: int,
    min_line_ink: int,
) -> list[TextLine]:
    """Split the content band into horizontal text lines by row whitespace.

    Bands whose ink count is below ``min_line_ink`` are dropped as specks/
    noise so a stray pixel cannot create a phantom line (or split a real one).
    """

    raw: list[TextLine] = []
    in_band = False
    y0 = 0
    for y in range(cy0, cy1 + 1):
        has_ink = row_ink[y] > 0
        if has_ink and not in_band:
            y0 = y
            in_band = True
        elif not has_ink and in_band:
            raw.append(_make_line(data, width, ink_threshold, 0, y0, y - 1, cx0, cx1))
            in_band = False
    if in_band:
        raw.append(_make_line(data, width, ink_threshold, 0, y0, cy1, cx0, cx1))

    # The absolute ink floor alone is scale-sensitive: a raster rendered at 4x
    # carries ~4x the ink of the same page at 2x, so a speck that was filtered at
    # 2x crosses an absolute threshold at 4x and creates a phantom line (which
    # then perturbs region grouping).  Use a *relative* floor tied to the
    # largest band ink: this is scale-invariant (band ink scales with the squared
    # render scale) and, on a real page, separates text lines (~1x the maximum)
    # from scan specks (< 1/1000 of it).
    floor = min_line_ink
    if raw:
        max_ink = max(line.ink for line in raw)
        floor = max(floor, int(max_ink * MAX_RELATIVE_MIN_LINE_INK_FRACTION))
    kept = [line for line in raw if line.ink >= floor]
    return [
        TextLine(
            index=index,
            y0=line.y0,
            y1=line.y1,
            x0=line.x0,
            x1=line.x1,
            ink=line.ink,
        )
        for index, line in enumerate(kept)
    ]


def _make_line(
    data: bytes,
    width: int,
    ink_threshold: int,
    index: int,
    y0: int,
    y1: int,
    cx0: int,
    cx1: int,
) -> TextLine:
    min_x: int | None = None
    max_x: int | None = None
    ink = 0
    for y in range(y0, y1 + 1):
        base = y * width
        for x in range(cx0, cx1 + 1):
            if data[base + x] < ink_threshold:
                ink += 1
                if min_x is None or x < min_x:
                    min_x = x
                if max_x is None or x > max_x:
                    max_x = x
    return TextLine(
        index=index,
        y0=y0,
        y1=y1,
        x0=min_x if min_x is not None else cx0,
        x1=max_x if max_x is not None else cx1,
        ink=ink,
    )


def _segment_columns(
    col_ink: list[int],
    cx0: int,
    cx1: int,
    cy0: int,
    cy1: int,
    min_gutter_px: int,
    min_col_width_px: int,
    *,
    data: bytes | None = None,
    width: int = 0,
    line_bands: list[tuple[int, int]] | None = None,
    ink_threshold: int = DEFAULT_INK_THRESHOLD,
) -> tuple[list[ColumnRegion], list[str]]:
    """Find full-height vertical whitespace gutters inside the content band.

    A gutter qualifies only when it is at least ``min_gutter_px`` wide **and**
    is ink-free in at least :data:`GUTTER_LINE_BAND_EMPTY_FRACTION` of the
    region's text lines (falling back to :data:`GUTTER_EMPTY_FRACTION` of the
    rows when line bands are unavailable).  The per-line test is the
    scale-invariant generality guard: a genuine column gutter runs empty
    through every text line, while a ragged CJK inter-character gap is
    occupied by some lines — so an ordinary page (and a low-resolution raster
    of a ragged region) stays single-column.

    A candidate split is only accepted when **both** resulting columns are at
    least ``min_col_width`` pixels wide; otherwise the sliver is merged into its
    neighbour.  This stops a stray dot or page-number mark from being read as a
    column boundary.
    """

    # Use the ink extent *within this region/band*, not the caller's broader
    # content box, so an empty right margin is not mistaken for a sliver column.
    xs = [x for x in range(cx0, cx1 + 1) if col_ink[x] > 0]
    if not xs:
        return (
            [
                ColumnRegion(
                    index=0,
                    x0=cx0,
                    x1=cx1,
                    width=cx1 - cx0 + 1,
                    gutter_left=None,
                    gutter_right=None,
                )
            ],
            [],
        )
    effective_x0 = xs[0]
    effective_x1 = xs[-1]

    span = effective_x1 - effective_x0 + 1
    # The caller-derived minimum column width already carries the scale-
    # normalised line-height term; the relative term guards very wide regions.
    min_col_width = max(min_col_width_px, int(span * MIN_COLUMN_WIDTH_FRACTION))
    band_height = cy1 - cy0 + 1

    qualifies = _qualifying_gutter_columns(
        col_ink,
        effective_x0,
        effective_x1,
        band_height,
        data,
        width,
        line_bands,
        ink_threshold,
    )

    # Collect raw wide-enough gutters, then keep only those whose split leaves
    # two usable columns.
    raw_gutters: list[tuple[int, int]] = []
    run_start: int | None = None
    for x in range(effective_x0, effective_x1 + 1):
        if qualifies[x] and run_start is None:
            run_start = x
        elif not qualifies[x] and run_start is not None:
            if x - run_start >= min_gutter_px:
                raw_gutters.append((run_start, x - 1))
            run_start = None
    if run_start is not None and (effective_x1 + 1 - run_start) >= min_gutter_px:
        raw_gutters.append((run_start, effective_x1))

    # Greedily accept gutters that split two wide-enough columns, skipping those
    # that would carve off a sliver.
    accepted: list[tuple[int, int]] = []
    left = effective_x0
    for g0, g1 in raw_gutters:
        if g0 - left < min_col_width:
            continue  # would carve a too-narrow left column: merge it
        accepted.append((g0, g1))
        left = g1 + 1
    # Drop trailing gutters that leave a too-narrow final column.
    while accepted and (effective_x1 - accepted[-1][1]) < min_col_width:
        accepted.pop()

    if not accepted:
        return (
            [
                ColumnRegion(
                    index=0,
                    x0=effective_x0,
                    x1=effective_x1,
                    width=span,
                    gutter_left=None,
                    gutter_right=None,
                )
            ],
            [],
        )

    columns: list[ColumnRegion] = []
    left = effective_x0
    for i, (g0, g1) in enumerate(accepted):
        columns.append(
            ColumnRegion(
                index=len(columns),
                x0=left,
                x1=g0 - 1,
                width=g0 - left,
                gutter_left=accepted[i - 1] if i > 0 else None,
                gutter_right=(g0, g1),
            )
        )
        left = g1 + 1
    columns.append(
        ColumnRegion(
            index=len(columns),
            x0=left,
            x1=effective_x1,
            width=effective_x1 - left + 1,
            gutter_left=accepted[-1],
            gutter_right=None,
        )
    )
    return [c for c in columns if c.width > 0], []


def _qualifying_gutter_columns(
    col_ink: list[int],
    effective_x0: int,
    effective_x1: int,
    band_height: int,
    data: bytes | None,
    width: int,
    line_bands: list[tuple[int, int]] | None,
    ink_threshold: int,
) -> list[bool]:
    """Per-x boolean: does this column qualify as (part of) a real gutter?

    The primary, scale-invariant test is **per text-line emptiness**: with line
    bands available, a column qualifies when it carries no ink in at least
    :data:`GUTTER_LINE_BAND_EMPTY_FRACTION` of those bands.  When line bands are
    unavailable (a raw buffer passed straight to column segmentation) the
    function falls back to the row-based :data:`GUTTER_EMPTY_FRACTION` test.
    """

    qualifies = [False] * len(col_ink)
    if data is not None and line_bands:
        need = len(line_bands) * GUTTER_LINE_BAND_EMPTY_FRACTION
        for x in range(effective_x0, effective_x1 + 1):
            empty = 0
            for y0, y1 in line_bands:
                hit = False
                for y in range(y0, y1 + 1):
                    if data[y * width + x] < ink_threshold:
                        hit = True
                        break
                if not hit:
                    empty += 1
            qualifies[x] = empty >= need
        return qualifies

    need_empty = int(band_height * GUTTER_EMPTY_FRACTION)
    for x in range(effective_x0, effective_x1 + 1):
        qualifies[x] = (band_height - col_ink[x]) >= need_empty
    return qualifies


def _detect_horizontal_rules(
    data: bytes,
    width: int,
    cx0: int,
    cx1: int,
    cy0: int,
    cy1: int,
    ink_threshold: int,
) -> list[int]:
    """Rows that are (almost) a full straight dark run across the content."""

    span = cx1 - cx0 + 1
    need = int(span * RULE_WIDTH_FRACTION)
    rules: list[int] = []
    for y in range(cy0, cy1 + 1):
        base = y * width
        if sum(1 for x in range(cx0, cx1 + 1) if data[base + x] < ink_threshold) >= need:
            rules.append(y)
    return _merge_adjacent(rules)


def _detect_vertical_rules(
    data: bytes,
    width: int,
    cx0: int,
    cx1: int,
    cy0: int,
    cy1: int,
    ink_threshold: int,
) -> list[int]:
    """Columns that are (almost) a full straight dark run down the content."""

    span = cy1 - cy0 + 1
    need = int(span * RULE_HEIGHT_FRACTION)
    rules: list[int] = []
    for x in range(cx0, cx1 + 1):
        count = 0
        for y in range(cy0, cy1 + 1):
            if data[y * width + x] < ink_threshold:
                count += 1
                if count >= need:
                    rules.append(x)
                    break
    return _merge_adjacent(rules)


def _merge_adjacent(values: list[int]) -> list[int]:
    """Collapse consecutive coordinates into the first coordinate of each run."""

    merged: list[int] = []
    prev: int | None = None
    for v in values:
        if prev is None or v > prev + 1:
            merged.append(v)
        prev = v
    return merged


def _segment_regions(
    data: bytes,
    width: int,
    col_ink: list[int],
    lines: list[TextLine],
    cx0: int,
    cx1: int,
    min_gutter_px: int,
    min_col_width_px: int,
    ink_threshold: int,
) -> list[RegionAnalysis]:
    """Group text lines into vertical regions and find columns **per region**.

    A new region starts when the gap since the previous line is at least
    :data:`REGION_GAP_FACTOR` x the median line height (a section break).
    Column detection then runs on each region's own row span, so a page that
    mixes a full-width block with a genuine side-by-side block is described
    correctly instead of being flattened by a global projection.
    """

    if not lines:
        return []
    heights = sorted(line.y1 - line.y0 + 1 for line in lines)
    median_h = heights[len(heights) // 2]
    gap_threshold = max(min_gutter_px, int(median_h * REGION_GAP_FACTOR))

    groups: list[list[TextLine]] = [[lines[0]]]
    for prev, cur in zip(lines, lines[1:]):
        if cur.y0 - prev.y1 - 1 >= gap_threshold:
            groups.append([cur])
        else:
            groups[-1].append(cur)

    regions: list[RegionAnalysis] = []
    for index, group in enumerate(groups):
        y0 = group[0].y0
        y1 = group[-1].y1
        # Recompute column ink over this region's row span only.
        region_ink = [0] * len(col_ink)
        for y in range(y0, y1 + 1):
            base = y * width
            for x in range(cx0, cx1 + 1):
                if data[base + x] < ink_threshold:
                    region_ink[x] += 1
        region_columns, _ = _segment_columns(
            region_ink,
            cx0,
            cx1,
            y0,
            y1,
            min_gutter_px,
            min_col_width_px,
            data=data,
            width=width,
            line_bands=[(line.y0, line.y1) for line in group],
            ink_threshold=ink_threshold,
        )
        regions.append(
            RegionAnalysis(
                index=index,
                y0=y0,
                y1=y1,
                line_indices=tuple(line.index for line in group),
                columns=tuple(region_columns),
            )
        )
    return regions


# ---------------------------------------------------------------- image decode
def analyse_image_bytes(
    encoded: bytes,
    *,
    page: int | None = None,
    geometry: PageGeometry | None = None,
    ink_threshold: int = DEFAULT_INK_THRESHOLD,
) -> LayoutAnalysis:
    """Decode a PNG (grayscale or RGB) with the stdlib and analyse it.

    Only PNG is supported here on purpose: it keeps the module dependency-free
    and it is exactly the format the product rasteriser emits.  Any other input
    raises :class:`LayoutAnalysisError` rather than guessing.
    """

    gray, width, height = decode_png_gray(encoded)
    return analyse_page(
        gray,
        width,
        height,
        page=page,
        geometry=geometry,
        ink_threshold=ink_threshold,
        input_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def analyse_rendered_page(
    rendered: Any,
    *,
    scale: float | None = None,
    ink_threshold: int = DEFAULT_INK_THRESHOLD,
) -> LayoutAnalysis:
    """Analyse a product :class:`RenderedPage` with full provenance.

    This is the bridge from the **real product rasteriser** to the layout
    analyser: it reads ``rendered.png`` (the exact bytes an OCR backend would
    receive), decodes it, and records the page number, the PNG input hash and
    the PDF point geometry on the result.  It performs no OCR and no network
    access.
    """

    png = getattr(rendered, "png", None)
    if not isinstance(png, (bytes, bytearray)):
        raise LayoutAnalysisError("rendered page has no PNG bytes")
    page = getattr(rendered, "page", None)
    geometry = PageGeometry(
        page=page if isinstance(page, int) else None,
        width_pt=float(getattr(rendered, "width", 0) or 0) or None,
        height_pt=float(getattr(rendered, "height", 0) or 0) or None,
        scale=scale,
    )
    analysis = analyse_image_bytes(
        bytes(png),
        page=page if isinstance(page, int) else None,
        geometry=geometry,
        ink_threshold=ink_threshold,
    )
    if analysis.input_sha256 != hashlib.sha256(bytes(png)).hexdigest():
        # The provenance hash must be the exact encoded bytes the OCR backend
        # would receive; guard against a future refactor changing that meaning.
        raise LayoutAnalysisError("input provenance hash mismatch")
    return analysis


def decode_png_gray(encoded: bytes) -> tuple[bytes, int, int]:
    """Decode a non-interlaced 8-bit grayscale/RGB PNG into a gray buffer.

    Supports color types 0 (gray) and 2 (RGB), bit depth 8, no interlacing —
    the exact subset the product's stdlib PNG encoder writes.  Returns
    ``(gray_bytes, width, height)``.

    Security (local-bounds review): the declared IHDR geometry is checked
    against :data:`MAX_PAGE_SIDE` / :data:`MAX_PAGE_PIXELS` *before* any
    inflation, and IDAT is inflated through a capped ``decompressobj`` limited
    to the exact declared row bytes, so a small IDAT cannot expand into an
    unbounded buffer (decompression bomb).  Remaining limitation: IDAT payload
    bytes are accumulated in memory as supplied by the caller, so the bound is
    the size of the input the caller already holds, not an independent cap.
    """

    if not encoded.startswith(b"\x89PNG\r\n\x1a\n"):
        raise LayoutAnalysisError("not a PNG")
    pos = 8
    width = height = 0
    bit_depth = 0
    color_type = 0
    idat = bytearray()
    while pos + 8 <= len(encoded):
        (length,) = struct.unpack(">I", encoded[pos : pos + 4])
        tag = encoded[pos + 4 : pos + 8]
        payload = encoded[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, bit_depth, color_type, comp, filt, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if bit_depth != 8 or color_type not in (0, 2) or interlace != 0:
                raise LayoutAnalysisError(
                    f"unsupported PNG: bit_depth={bit_depth} color_type={color_type} "
                    f"interlace={interlace}"
                )
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"IEND":
            break
    if width <= 0 or height <= 0 or not idat:
        raise LayoutAnalysisError("PNG missing IHDR/IDAT")
    # Bound the declared geometry *before* decompressing so a small IDAT can
    # never inflate into an unbounded buffer (decompression bomb).  The IHDR
    # dimensions are attacker-controlled, so they are checked against the same
    # page caps the raw analyser enforces; an over-limit page yields the honest
    # ``too_large`` refusal instead of an allocation.
    too_large = _too_large(width, height)
    if too_large is not None:
        raise LayoutAnalysisError(f"PNG page rejected: {too_large}")
    channels = 1 if color_type == 0 else 3
    stride = width * channels
    expected = (stride + 1) * height
    # Decompress with a hard output cap of exactly the declared row bytes.  If
    # the stream tries to produce more, ``decompressobj`` stops at the cap and
    # ``unconsumed_tail`` stays non-empty, which we report rather than loop.
    decompressor = zlib.decompressobj()
    try:
        raw = decompressor.decompress(bytes(idat), expected)
    except zlib.error as exc:  # malformed/zlib-bomb stream
        raise LayoutAnalysisError(f"invalid PNG IDAT stream: {exc}") from exc
    if decompressor.unconsumed_tail:
        raise LayoutAnalysisError(
            "PNG IDAT stream exceeds declared decoded size (possible bomb)"
        )
    if len(raw) != expected:
        raise LayoutAnalysisError(
            f"unexpected PNG data length {len(raw)} (expected {expected})"
        )
    out = bytearray(width * height)
    prev = bytearray(stride)
    for y in range(height):
        row_start = y * (stride + 1)
        filt = raw[row_start]
        cur = bytearray(raw[row_start + 1 : row_start + 1 + stride])
        _unfilter_row(filt, cur, prev, channels)
        if channels == 1:
            out[y * width : (y + 1) * width] = cur
        else:
            base = y * width
            for x in range(width):
                r = cur[3 * x]
                g = cur[3 * x + 1]
                b = cur[3 * x + 2]
                out[base + x] = (r * 299 + g * 587 + b * 114) // 1000
        prev = cur
    return bytes(out), width, height


def _unfilter_row(filt: int, cur: bytearray, prev: bytearray, bpp: int) -> None:
    if filt == 0:
        return
    length = len(cur)
    if filt == 1:  # Sub
        for i in range(length):
            if i >= bpp:
                cur[i] = (cur[i] + cur[i - bpp]) & 0xFF
    elif filt == 2:  # Up
        for i in range(length):
            cur[i] = (cur[i] + prev[i]) & 0xFF
    elif filt == 3:  # Average
        for i in range(length):
            left = cur[i - bpp] if i >= bpp else 0
            cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 0xFF
    elif filt == 4:  # Paeth
        for i in range(length):
            a = cur[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa = abs(p - a)
            pb = abs(p - b)
            pc = abs(p - c)
            if pa <= pb and pa <= pc:
                pr = a
            elif pb <= pc:
                pr = b
            else:
                pr = c
            cur[i] = (cur[i] + pr) & 0xFF
    else:
        raise LayoutAnalysisError(f"unknown PNG filter type {filt}")


__all__ = [
    "DEFAULT_INK_THRESHOLD",
    "GUTTER_EMPTY_FRACTION",
    "MAX_PAGE_PIXELS",
    "MAX_PAGE_SIDE",
    "MIN_GUTTER_PX",
    "REGION_GAP_FACTOR",
    "ColumnRegion",
    "LayoutAnalysis",
    "LayoutAnalysisError",
    "PageGeometry",
    "RegionAnalysis",
    "TextLine",
    "analyse_image_bytes",
    "analyse_page",
    "analyse_rendered_page",
    "decode_png_gray",
]
