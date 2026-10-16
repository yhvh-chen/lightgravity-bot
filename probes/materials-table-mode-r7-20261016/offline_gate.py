#!/usr/bin/env python3
"""Offline table-classifier gate check (NO model / NO network).

Proves the true-gating requirement BEFORE any POST: the classifier must fire on
the real T1 grid fixture and must NOT fire on ordinary controls (NIST full p16
born-digital prose page, mixed PDF p1 prose, mixed PDF p2 real scan, Z1 Chinese
printed JPEG).  Ground truth is never used; only the product layout analyser.

Run:  PYTHONPATH=$PWD/backend .venv/bin/python probes/.../offline_gate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.sources.ocr import classify_image_bytes  # noqa: E402
from lightgravity.sources.ocr.pdf import PdfiumRasterizer  # noqa: E402

FIX = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/materials-fixtures-r7-20261016"
    "/probes/materials-fixtures-r7-20261016"
)
Z1 = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/materials-retry-20261016-r2"
    "/probes/lg035/TRUTH-PREP/samples/private/lg035_truth_zh_laojielao_p10.jpg"
)


def main() -> int:
    checks: list[dict] = []

    def add(name: str, expect: bool, png: bytes) -> None:
        got = classify_image_bytes(png)
        ok = got.is_table is expect
        checks.append(
            {
                "name": name,
                "expect_is_table": expect,
                "got_is_table": got.is_table,
                "ok": ok,
                **{k: v for k, v in got.to_dict().items() if k != "is_table"},
            }
        )
        print(f"[{'OK ' if ok else 'FAIL'}] {name}: expect={expect} got={got.is_table} "
              f"({got.reason}, cols={got.column_count}, lf={got.line_fraction:.2f}, "
              f"rules={got.rules_in_region}, cons={got.line_consistency:.2f})")

    add("LG035-R7-T1 (real grid)", True, (FIX / "fixtures/honest_table_grid_scale4.png").read_bytes())
    add(
        "NIST p16 full page (born-digital prose+table)",
        False,
        (FIX / "fixtures/born_digital_table_page16_full_scale2.png").read_bytes(),
    )

    mixed = (FIX / "fixtures/mixed_born_digital_plus_scan.pdf").read_bytes()
    for page in PdfiumRasterizer().render(mixed, scale=2.0):
        add(f"LG035-R7-MIX p{page.page} (ordinary)", False, page.png)

    if Z1.is_file():
        add("LG035-ZH-Z1 (Chinese printed JPEG)", False, Z1.read_bytes())
    else:
        print(f"[SKIP] Z1 fixture not found at {Z1}")

    out = Path(__file__).with_name("evidence") / "offline_gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"checks": checks, "all_ok": all(c["ok"] for c in checks)}, ensure_ascii=False, indent=2))
    print(f"\nwrote {out}")
    print("ALL_OK" if all(c["ok"] for c in checks) else "GATE_FAIL")
    return 0 if all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
