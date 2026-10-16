#!/usr/bin/env python3
"""Score the LIVE 2-call table-mode results against frozen truth (offline).

Reuses the frozen R7 cohort parser/scorer (`table_score.py`, unchanged) for the
table hardgate and the frozen §1 normalisation for the Z1 page gate.  Machine
text is read from the already-persisted derivatives; truth is never fed to a
prompt and never used to reconstruct a grid.

Run: PYTHONPATH=$PWD/backend .venv/bin/python probes/.../score_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COHORT = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-cohort-r7-20261016"
    "/probes/materials-ocr-cohort-r7-20261016"
)
FIX = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/materials-fixtures-r7-20261016"
    "/probes/materials-fixtures-r7-20261016"
)
Z1_TRUTH = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-cohort-r7-20261016"
    "/probes/lg035/TRUTH-PREP/truth/LG035-ZH-Z1.p10.txt"
)
sys.path.insert(0, str(COHORT))

from table_score import cer, score_table  # noqa: E402


def page_body(markdown: str) -> str:
    """Take the transcription body after the page comment line (wrapper is not content)."""

    return markdown.split("-->", 1)[1].strip() if "-->" in markdown else markdown


def main() -> int:
    results = json.loads((HERE / "evidence" / "call_results.json").read_text(encoding="utf-8"))
    truth = json.loads((FIX / "truth" / "LG035-R7-T1.table.json").read_text(encoding="utf-8"))
    z1_truth = Z1_TRUTH.read_text(encoding="utf-8")

    scored: dict = {"calls": {}}
    for r in results:
        call = r["call"]
        machine = (HERE / r["machine_path"]).read_text(encoding="utf-8") if r.get("machine_path") else ""
        req = (r.get("requests") or [{}])[0]
        entry = {
            "sample": r["sample"],
            "input_sha256": r["input_sha256"],
            "media_type": r["media_type"],
            "processing_status": r.get("processing_status"),
            "prompt_kind": "table" if req.get("prompt_override") else "default",
            "request_prompt_sha256": req.get("prompt_sha256"),
            "default_prompt_sha256": req.get("default_prompt_sha256"),
            "default_prompt_unchanged": req.get("prompt_sha256") == req.get("default_prompt_sha256"),
        }
        if call == 1:
            entry["table"] = score_table(machine, truth)
        elif call == 2:
            entry["z1_page_cer"] = cer(z1_truth, page_body(machine))
            entry["z1_page_gate_pass"] = entry["z1_page_cer"] <= 0.15
        scored["calls"][str(call)] = entry

    (HERE / "evidence" / "scores.json").write_text(
        json.dumps(scored, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(scored, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
