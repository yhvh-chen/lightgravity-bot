#!/usr/bin/env python3
"""LG-047 E-QA — Flow B: selected material -> real SDK worker deliverable ->
real independent reviewer -> view/accept after confirmed stop.

Observed end to end at the real HTTP seam against the isolated real-product app.

The delivery is started from the **global** conversation with a concrete
file-producing intent carrying ``selected_sources`` (docs/11 §4). The program
freezes the Run trigger binding from that exact message; the worker must receive
the same bounded selected body; the artifact must quote the fixture facts and no
decoy; the real reviewer (separate role/context) must run; acceptance must
respect the stop gate.

Usage:
    python flow_b_delivery.py --base <url> --out <json> [--data-dir <dir>]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import Api  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
FIX = REPO / "examples/selected-material-prototype/fixtures"


def rec(out, key, value):
    out[key] = value
    print(f"[{key}] {json.dumps(value, default=str)[:400]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--deadline-s", type=int, default=180)
    args = ap.parse_args()

    api = Api(args.base)
    out: dict = {}
    _, g0 = api.generation()
    out["ledger_before"] = g0

    alpha = (FIX / "alpha-brief.txt").read_text()

    # Upload alpha into GLOBAL scope (task_ref=None) so the global delivery can
    # select it; materialize a trusted machine body via the product writer.
    up = api.upload_inline(request_id="qa-flowB-alpha", filename="alpha-brief.txt",
                           text=alpha, task_ref=None, title="ORION-71 brief (sample)")
    rec(out, "upload_alpha_global", {"status": up["status"], "source": up["body"]["source"]})
    sid = up["body"]["source"]["id"]
    ver = up["body"]["source"]["source_version"]
    h = up["body"]["source"]["content_hash"]
    seed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "seed_machine.py"),
         "--data-dir", args.data_dir, "--source-id", sid,
         "--text-file", str(FIX / "alpha-brief.txt")],
        capture_output=True, text=True,
    )
    rec(out, "seed_machine_alpha", {"rc": seed.returncode, "stdout": seed.stdout})

    # Global delivery message: concrete Markdown file with the exact facts.
    objective = (
        "Create a Markdown file named orion-summary.md that states these exact "
        "facts from the selected brief: project code name ORION-71, programme "
        "owner Halden Reyes, primary launch date 2027-03-14, total budget EUR "
        "418,250, project id PRJ-ORION-71, and change ticket CB-8842."
    )
    gm = api.global_message(
        message_id="qa-flowB-deliver",
        content=objective,
        selected_sources=[{"source_id": sid, "source_version": ver, "content_hash": h}],
        request_id="qa-flowB-deliver",
    )
    rec(out, "global_delivery", {"status": gm["status"], "body": gm["body"]})
    tid = gm["body"].get("task_id") if isinstance(gm["body"], dict) else None

    # Poll the task until verification produces a candidate or it stops.
    deadline = time.time() + args.deadline_s
    last = None
    while time.time() < deadline:
        st, task = api.task(tid)
        last = task
        phase = (task.get("entity") or {}).get("phase") if isinstance(task, dict) else None
        acc = (task.get("entity") or {}).get("acceptance") if isinstance(task, dict) else None
        active = (task.get("entity") or {}).get("active_run") if isinstance(task, dict) else None
        print(f"  poll phase={phase} active_run={active} acceptance={acc}")
        if phase in ("awaiting_acceptance", "done", "failed", "cancelled", "recovery_required"):
            break
        time.sleep(3)
    rec(out, "task_final", last)

    st, arts = api.artifacts(tid)
    rec(out, "artifacts", {"status": st, "body": arts})

    _, g1 = api.generation()
    out["ledger_after"] = g1
    out["task_id"] = tid
    out["source_ref"] = {"source_id": sid, "source_version": ver, "content_hash": h}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
