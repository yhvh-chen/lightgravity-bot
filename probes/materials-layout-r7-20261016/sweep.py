#!/usr/bin/env python3
"""Parameter sweep for the cross-scale gutter rule (LG-035 R7, offline).

Explores (line-height factor, per-band-empty fraction, min width in line
heights) and reports the resulting Z2 region column counts at 1x/2x/4x plus
whether controls stay single-column. Used to pick the declared rule BEFORE the
final comparison. No OCR/network/model/GT.
"""

from __future__ import annotations

import itertools
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from lightgravity.sources.ocr.layout import decode_png_gray  # noqa: E402
from lightgravity.sources.ocr.pdf import PdfiumRasterizer  # noqa: E402

Z2 = ROOT / "probes/materials-ocr-r4-20261016/private/LG035-ZH-Z2.pdf"
CLEAR = ROOT / "probes/lg035/fixtures/clear_real.pdf"


def band_columns(
    g: bytes,
    w: int,
    h: int,
    y0: int,
    y1: int,
    lines: list[tuple[int, int]],
    *,
    lh_factor: float,
    band_empty: float,
    width_factor: float,
    scale: float,
) -> int:
    # median line height over the whole page's lines
    hs = sorted(b - a + 1 for a, b in lines)
    med = hs[len(hs) // 2]
    min_gut = med * lh_factor
    min_col = med * width_factor
    col = [0] * w
    for y in range(y0, y1 + 1):
        for x in range(w):
            if g[y * w + x] < 128:
                col[x] += 1
    xs = [x for x in range(w) if col[x] > 0]
    if not xs:
        return 0
    # per-line-band empty test
    relevant = [ln for ln in lines if ln[0] >= y0 - 2 and ln[1] <= y1 + 2]
    empty_bands = [0] * w
    for x in range(w):
        empty_bands[x] = sum(
            1 for (ly0, ly1) in relevant if not any(g[y * w + x] < 128 for y in range(ly0, ly1 + 1))
        )
    need = int(len(relevant) * band_empty)
    # candidate gutters
    gutters: list[tuple[int, int]] = []
    run = None
    for x in range(xs[0], xs[-1] + 1):
        ok = empty_bands[x] >= need
        if ok and run is None:
            run = x
        elif not ok and run is not None:
            if (x - run) >= min_gut:
                gutters.append((run, x - 1))
            run = None
    if run is not None and (xs[-1] + 1 - run) >= min_gut:
        gutters.append((run, xs[-1]))
    # accept greedily if both sides >= min_col
    accepted = []
    left = xs[0]
    for g0, g1 in gutters:
        if g0 - left < min_col:
            continue
        accepted.append((g0, g1))
        left = g1 + 1
    while accepted and (xs[-1] - accepted[-1][1]) < min_col:
        accepted.pop()
    return len(accepted) + 1


def measure(pdf: pathlib.Path, page: int, scale: float):
    data = pdf.read_bytes()
    r = PdfiumRasterizer().render(data, scale=scale, max_pages=page)[page - 1]
    g, w, h = decode_png_gray(r.png)
    rowink = [sum(1 for x in range(w) if g[y * w + x] < 128) for y in range(h)]
    lines = []
    inb = False
    y0 = 0
    for y in range(h):
        if rowink[y] > 0 and not inb:
            y0 = y
            inb = True
        elif rowink[y] == 0 and inb:
            if sum(rowink[y0:y]) >= 10:
                lines.append((y0, y - 1))
            inb = False
    regions = [(319, 454), (550, 627), (721, 798), (875, 1039)]
    norms = [(int(a * scale / 2), int(b * scale / 2)) for a, b in regions]
    return g, w, h, lines, norms


def main() -> int:
    cache = {s: measure(Z2, 2, s) for s in (1.0, 2.0, 4.0)}
    for lh_factor in (0.7, 0.8, 0.9, 1.0):
        for band_empty in (0.6, 0.75, 0.9, 1.0):
            for width_factor in (0.3, 0.5, 0.8):
                counts = []
                for s in (1.0, 2.0, 4.0):
                    g, w, h, lines, norms = cache[s]
                    counts.append(
                        [
                            band_columns(
                                g, w, h, a, b, lines,
                                lh_factor=lh_factor,
                                band_empty=band_empty,
                                width_factor=width_factor,
                                scale=s,
                            )
                            for (a, b) in norms
                        ]
                    )
                stable = counts[0] == counts[1] == counts[2]
                if stable:
                    print(
                        f"lh={lh_factor} be={band_empty} wf={width_factor} "
                        f"-> {counts[0]} (STABLE)"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
