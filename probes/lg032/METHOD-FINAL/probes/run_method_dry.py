#!/usr/bin/env python3
"""LG-032 METHOD-FINAL dry runner (independent 0-fake B attempt).

Identical code path as ``FINAL-COHORT/harness/run_dry.py`` (real product entry,
real SDK selection, loopback fake upstream) but:

* installs the METHOD-FINAL config overlay FIRST, so the phase root and all
  output live under THIS worktree's method-final paths;
* writes captures under ``METHOD-FINAL/evidence/dry_captures`` (never into the
  read-only ``FINAL-COHORT`` tree);
* uses a dummy credential, so no real provider request is ever possible.

Usage::

    .venv/bin/python probes/lg032/METHOD-FINAL/probes/run_method_dry.py \
        --sample s1_units --arm B
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import method_config as MC  # noqa: E402

C = MC.install()
sys.path.insert(0, str(MC.HARNESS_DIR))

import fake_upstream as F  # noqa: E402
import run_attempt as R  # noqa: E402

CAPTURE_DIR = MC.METHOD_DIR / "evidence" / "dry_captures"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, choices=sorted(R.SAMPLE_SPEC))
    ap.add_argument("--arm", required=True, choices=["A", "B"])
    ap.add_argument("--capture-only", action="store_true")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    # Offline-only dummy credential: the real key can never be sent anywhere.
    os.environ["DEEPSEEK_API_KEY"] = "dummy-offline-credential"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = args.label or f"dry-{args.sample}-{args.arm}-method"
    upstream = F.FakeUpstream(sample=args.sample, arm=args.arm,
                              capture_only=args.capture_only)
    try:
        rc = R.run_attempt(args.sample, args.arm, dry_run=True,
                           fake_upstream=upstream.base_url, dry_label=label)
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
