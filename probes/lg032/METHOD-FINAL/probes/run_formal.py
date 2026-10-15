#!/usr/bin/env python3
"""LG-032 METHOD-FINAL formal attempt runner (real provider, one attempt per call).

This is the entry point the FORMAL freeze (``FORMAL-FREEZE.md``) refers to.  It:

* installs the METHOD-FINAL config overlay FIRST, so the ONE phase data_root is
  this worktree's frozen ``lg032-method-final-data`` (NOT the cohort-ready root);
* delegates to the byte-identical frozen driver ``run_attempt.run_attempt`` with
  ``dry_run=False`` and the real ``DEEPSEEK_API_KEY`` from the environment;
* never writes the key anywhere and never switches the provider.

Usage (PM-authorised formal run only; secret from env, value never printed)::

    DEEPSEEK_API_KEY=... .venv/bin/python \
        probes/lg032/METHOD-FINAL/probes/run_formal.py --sample s1_units --arm A
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import method_config as MC  # noqa: E402

C = MC.install()
sys.path.insert(0, str(MC.HARNESS_DIR))

import run_attempt as R  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, choices=sorted(R.SAMPLE_SPEC))
    ap.add_argument("--arm", required=True, choices=["A", "B"])
    args = ap.parse_args()
    return R.run_attempt(args.sample, args.arm, dry_run=False)


if __name__ == "__main__":
    raise SystemExit(main())
