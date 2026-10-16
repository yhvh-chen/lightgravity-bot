#!/usr/bin/env python3
"""LG-035 R7 cohort — OFFLINE preflight (no network).

Verifies every predeclared input hash, reproduces the MIX page renders with the
actual product `PdfiumRasterizer`, and writes the frozen reservation records.
Runs BEFORE any POST. Exit non-zero on any mismatch.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIX = "/home/yhvh/code/lightgravity-bot-worktrees/materials-fixtures-r7-20261016/probes/materials-fixtures-r7-20261016"
EVID = os.path.join(HERE, "evidence")

sys.path.insert(0, os.path.join(REPO, "backend"))
from lightgravity.sources.ocr.pdf import PdfiumRasterizer  # noqa: E402


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load(rel: str) -> bytes:
    with open(os.path.join(FIX, rel), "rb") as fh:
        return fh.read()


def main() -> int:
    report: dict = {"phase": "offline_preflight", "checks": []}

    def check(name: str, ok: bool, detail) -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})

    # 1. frozen table input
    t1 = load("fixtures/honest_table_grid_scale4.png")
    check("t1_input_sha", sha(t1) == "39138a971d605f65d10b5df3a13e35c7cec5d3710bc38d55e6eb656fc1219652",
          {"sha256": sha(t1), "bytes": len(t1)})

    # 2. mixed pdf identity
    mix = load("fixtures/mixed_born_digital_plus_scan.pdf")
    check("mix_pdf_sha", sha(mix) == "0f7286016cc22717d4dab67319180604be097374b4d07a53fe68332c9f68ada5",
          {"sha256": sha(mix), "bytes": len(mix)})

    # 3. truth file hash
    truth = load("truth/LG035-R7-T1.table.json")
    check("truth_sha", sha(truth) == "02a4ada1be2c38d356034bf79a1b856394f3cbac5a2bfd8ca0d11bc780d4f39d",
          {"sha256": sha(truth), "bytes": len(truth)})

    # 4. source pdf hash
    src = load("sources/nist-sp811/nistspecialpublication811e2008.pdf")
    check("source_pdf_sha", sha(src) == "788dd8f0bcb0ec06e40c300690266742532a7e760a93be57764b77ed0ef3482f",
          {"sha256": sha(src), "bytes": len(src)})

    # 5. re-render MIX pages with the ACTUAL product rasteriser (offline)
    raster = PdfiumRasterizer()
    pages = raster.render(mix, scale=2.0)
    p1 = [p for p in pages if p.page == 1][0]
    p2 = [p for p in pages if p.page == 2][0]
    check("mix_p1_render_sha", sha(p1.png) == "265f187a8345146435282a6bf898141d748a50b086b8377d4e72fa916150f571",
          {"sha256": sha(p1.png), "bytes": len(p1.png), "wh": [p1.width, p1.height]})
    check("mix_p2_render_sha", sha(p2.png) == "1aebdc639db93532eeb19b4c3a0e0d67d796a621d20cbba6112d5dd975a28276",
          {"sha256": sha(p2.png), "bytes": len(p2.png), "wh": [p2.width, p2.height]})

    # 6. mixed p2 == clear_real p1 @ scale2 (equivalence)
    cr = load("../../probes/lg035/fixtures/clear_real.pdf") if False else None
    with open(os.path.join(REPO, "probes", "lg035", "fixtures", "clear_real.pdf"), "rb") as fh:
        cr = fh.read()
    check("clear_real_sha", sha(cr) == "89c6b42242d0aa16efdb7ff814604c4bfc5214e0bbdd040ead67dcf453d9ec0f",
          {"sha256": sha(cr)})
    crp1 = raster.render(cr, scale=2.0, max_pages=1)[0]
    check("mix_p2_eq_clear_real_p1", sha(crp1.png) == sha(p2.png),
          {"clear_real_p1_sha": sha(crp1.png)})

    # 7. gold text
    with open(os.path.join(REPO, "probes", "lg035", "fixtures", "phototest.gold.txt"), "rb") as fh:
        gold = fh.read()
    check("gold_sha", sha(gold) == "76ef157baeb6ab275b7d90f310477a8060d5822aea2b2e05d480f459b016a6ed",
          {"sha256": sha(gold), "bytes": len(gold)})

    # 8. size caps
    total = len(t1) + len(p1.png) + len(p2.png)
    check("input_sizes", len(t1) <= 2 * 1024 * 1024 and len(p1.png) <= 2 * 1024 * 1024
          and len(p2.png) <= 2 * 1024 * 1024 and total <= 6 * 1024 * 1024,
          {"t1": len(t1), "p1": len(p1.png), "p2": len(p2.png), "total": total})

    report["all_ok"] = all(c["ok"] for c in report["checks"])
    os.makedirs(EVID, exist_ok=True)
    with open(os.path.join(EVID, "offline_preflight.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    for c in report["checks"]:
        print(("OK " if c["ok"] else "FAIL"), c["name"], json.dumps(c["detail"], ensure_ascii=False))
    print("ALL_OK" if report["all_ok"] else "PREFLIGHT_FAILED")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
