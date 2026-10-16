#!/usr/bin/env python3
"""Cross-scale layout diagnosis (LG-035 R7).

Offline, model-free: renders the real Z2 page 2 scan and the ordinary English
controls at several render scales through the **product** rasteriser and runs
the layout analyser on the exact PNG bytes. Prints, per scale, the observed
global/region column counts and the per-region column boxes normalised by the
render scale (so positions are comparable across scales).

No OCR, no network, no model, no ground truth used by the algorithm.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from lightgravity.sources.ocr.layout import analyse_rendered_page  # noqa: E402
from lightgravity.sources.ocr.pdf import PdfiumRasterizer  # noqa: E402

REPO = ROOT
Z2 = REPO / "probes/materials-ocr-r4-20261016/private/LG035-ZH-Z2.pdf"
CLEAR = REPO / "probes/lg035/fixtures/clear_real.pdf"
MULTI = REPO / "probes/lg035/fixtures/multipage_real.pdf"


def analyse(pdf: pathlib.Path, page: int, scale: float) -> dict:
    data = pdf.read_bytes()
    pages = PdfiumRasterizer().render(data, scale=scale, max_pages=page)
    rendered = pages[page - 1]
    a = analyse_rendered_page(rendered, scale=scale)
    regions = []
    for r in a.regions:
        regions.append(
            {
                "index": r.index,
                "y_norm": [round(r.y0 / scale, 2), round(r.y1 / scale, 2)],
                "cols": r.column_count,
                "col_boxes_norm": [
                    [round(c.x0 / scale, 2), round(c.x1 / scale, 2)] for c in r.columns
                ],
                "col_widths_norm": [round(c.width / scale, 2) for c in r.columns],
            }
        )
    return {
        "pdf": pdf.name,
        "page": page,
        "scale": scale,
        "png_sha256": hashlib.sha256(rendered.png).hexdigest()[:16],
        "width": a.width,
        "height": a.height,
        "content_box_norm": [round(v / scale, 2) for v in a.content_box]
        if a.content_box
        else None,
        "line_count": a.line_count,
        "global_cols": a.column_count,
        "max_region_cols": a.max_region_columns,
        "column_model": a.column_model,
        "has_ruling": a.has_ruling,
        "region_counts": [r.column_count for r in a.regions],
        "regions": regions,
    }


def main() -> int:
    out = {"z2": [], "controls": []}
    for scale in (1.0, 2.0, 4.0):
        out["z2"].append(analyse(Z2, 2, scale))
    for scale in (1.0, 2.0, 4.0):
        out["controls"].append(analyse(CLEAR, 1, scale))
        out["controls"].append(analyse(MULTI, 1, scale))

    dest = HERE.parent / "evidence" / "scale_diagnosis.json"
    dest.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")

    for group in ("z2", "controls"):
        print(f"=== {group} ===")
        for d in out[group]:
            print(
                f"  {d['pdf']} p{d['page']} s{d['scale']}: "
                f"lines={d['line_count']} gcols={d['global_cols']} "
                f"maxreg={d['max_region_cols']} model={d['column_model']} "
                f"regions={d['region_counts']}"
            )
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
