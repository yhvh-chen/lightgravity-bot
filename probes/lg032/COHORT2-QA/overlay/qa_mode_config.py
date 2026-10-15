"""LG-032 COHORT2-QA independent driver overlay (QA-owned; frozen driver bytes read-only).

This overlay is the QA-side equivalent of the fix package's ``MODE-ISOLATION/mode_config.py``.
It is written and owned by the *independent serial QA* and is deliberately separate
from the fix owner's overlay.  It ONLY redirects the frozen protocol path constants
to this QA worktree and to a QA-controlled FAKE serial phase root; it never edits a
single byte of the frozen FINAL-COHORT harness semantics and never reads/writes the
formal ``lg032-cohort2-data`` root (reserved for the future PM-authorised formal run).

Why a separate overlay
----------------------
* The QA must exercise the *unmodified* formal driver (``run_attempt.py``) and its
  *unmodified* config object, not an independent re-implementation of the setting
  helpers.  Overriding only path constants keeps the driver's ``_set_mode`` /
  ``_assert_active_mode`` / ``_safe_restore_mode`` bytes and semantics untouched.
* The QA fake serial chain (s1A->s1B->s2A->s2B on ONE shared ``settings.data_dir``)
  must have its own persistent root so it can never touch the formal cohort2 root
  or any METHOD-FINAL / cohort-ready phase root.

Formal root note
----------------
``FORMAL_PHASE_DATA_DIR`` is declared here ONLY as the frozen value the future
formal cohort2 must use.  This overlay never creates it; the QA fake chain writes
to ``QA_SERIAL_PHASE_ROOT`` instead.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

QA_WORKTREE = Path("/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa")
HARNESS_DIR = QA_WORKTREE / "probes" / "lg032" / "FINAL-COHORT" / "harness"
COHORT = QA_WORKTREE / "probes" / "lg032" / "FINAL-COHORT"
QA_DIR = QA_WORKTREE / "probes" / "lg032" / "COHORT2-QA"

#: The formal cohort2 root reserved for the FUTURE PM-authorised formal run.
#: MUST equal the fix owner's declared root.  This QA package NEVER creates it.
FORMAL_PHASE_DATA_DIR = Path("/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data")

#: QA fake serial phase root (0 real provider).  A brand-new persistent root,
#: unique per QA wave, NEVER the formal root, never a TemporaryDirectory.
QA_SERIAL_PHASE_ROOT = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa-data"
)

QA_EVIDENCE_DIR = QA_DIR / "evidence"
FIXTURES_DIR = COHORT / "fixtures"


def install() -> "object":
    """Patch the frozen config module in place and return it.

    Must run BEFORE ``import run_attempt`` so the driver's module-level
    ``os.environ.update(C.phase_env())`` sees the redirected QA phase root.
    Only path constants + the env-pin function are overridden; every other
    frozen value (budgets, caps, model, contract, attempt ids) is untouched.
    """

    if str(HARNESS_DIR) not in sys.path:
        sys.path.insert(0, str(HARNESS_DIR))
    import final_cohort_config as C

    C.WORKTREE = QA_WORKTREE
    C.COHORT = COHORT
    C.PHASE_DATA_DIR = QA_SERIAL_PHASE_ROOT
    C.LEDGER_DIR = QA_SERIAL_PHASE_ROOT / "generation"
    C.LEDGER_HISTORY = C.LEDGER_DIR / "generation.jsonl"
    C.LEDGER_COUNT = C.LEDGER_DIR / "generation.count.json"
    C.RUNS_DIR = QA_DIR / "runs"
    C.EVIDENCE_DIR = QA_EVIDENCE_DIR
    C.FIXTURES_DIR = FIXTURES_DIR

    def _phase_env() -> dict[str, str]:
        return {
            "LIGHTGRAVITY_GENERATION_LEDGER_DIR": str(QA_SERIAL_PHASE_ROOT),
            "LIGHTGRAVITY_DATA_DIR": str(QA_SERIAL_PHASE_ROOT),
            "LIGHTGRAVITY_MAX_GENERATION_CALLS": str(C.TOTAL_GENERATION_LIMIT),
        }

    C.phase_env = _phase_env  # type: ignore[assignment]

    # QA-only shared dry root hook: when ``LG032_QA_SHARED_DRY_ROOT`` is set to
    # an absolute path, every dry attempt reuses that ONE directory as the phase
    # data root -- exactly the single-shared-``settings.data_dir`` requirement
    # (no per-nonce roots that would mask serial pollution).  Never reachable by
    # a formal run (``dry_run=False`` never calls ``new_dry_root``).
    _frozen_new_dry_root = C.new_dry_root

    def _new_dry_root(label: str = "dry") -> Path:
        shared = os.environ.get("LG032_QA_SHARED_DRY_ROOT")
        if shared:
            root = Path(shared)
            root.mkdir(parents=True, exist_ok=True)
            return root
        return _frozen_new_dry_root(label)

    C.new_dry_root = _new_dry_root  # type: ignore[assignment]
    return C


__all__ = [
    "COHORT",
    "FIXTURES_DIR",
    "FORMAL_PHASE_DATA_DIR",
    "HARNESS_DIR",
    "QA_DIR",
    "QA_EVIDENCE_DIR",
    "QA_SERIAL_PHASE_ROOT",
    "QA_WORKTREE",
    "install",
]
