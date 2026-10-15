#!/usr/bin/env python3
"""LG-032 FINAL-COHORT offline dry-run runner (real product entry + fake upstream).

Runs the SAME ``run_attempt`` code path the formal attempt uses, with a scripted
loopback fake upstream instead of real DeepSeek.  Preservation rules:

* Every invocation creates its **own unique** dry data root (UTC + nonce) and
  its own capture dir; nothing is deleted or overwritten.
* Full stdout/stderr are redirected to a unique log file by the caller wrapper.
* Uses a **dummy** credential so the real key can never be sent anywhere (the
  fake upstream is loopback-only anyway).

Usage::

    .venv/bin/python probes/lg032/FINAL-COHORT/harness/run_dry.py \
        --sample s1_units --arm A
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fake_upstream as F  # noqa: E402
import final_cohort_config as C  # noqa: E402
import run_attempt as R  # noqa: E402

CAPTURE_DIR = C.COHORT / "offline" / "dry_captures"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, choices=sorted(R.SAMPLE_SPEC))
    ap.add_argument("--arm", required=True, choices=["A", "B"])
    ap.add_argument("--capture-only", action="store_true",
                    help="only record the outbound tool schema / request shape")
    args = ap.parse_args()

    # Never use the real credential for an offline fake-upstream run.
    os.environ["DEEPSEEK_API_KEY"] = "dummy-offline-credential"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    upstream = F.FakeUpstream(sample=args.sample, arm=args.arm,
                              capture_only=args.capture_only)
    try:
        rc = R.run_attempt(args.sample, args.arm, dry_run=True,
                           fake_upstream=upstream.base_url,
                           dry_label=f"dry-{args.sample}-{args.arm}")
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        cap = CAPTURE_DIR / f"{stamp}-{args.sample}-{args.arm}.json"
        cap.write_text(json.dumps({
            "sample": args.sample, "arm": args.arm, "rc": rc,
            "fake_base_url": upstream.base_url,
            "captured_tools": upstream.captured_tools,
            "records": upstream.records,
        }, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"CAPTURE {cap}", flush=True)
    finally:
        upstream.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
