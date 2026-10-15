"""LG-032 MODE-ISOLATION overlay over the frozen FINAL-COHORT config.

This is the ONLY mode-isolation-specific configuration.  It redirects the frozen
protocol path constants to the NEW persistent cohort2 root (``lg032-cohort2-data``),
without editing a single byte of the frozen FINAL-COHORT harness semantics.

Why a new root
--------------
The first (polluted) formal cohort used ``lg032-method-final-data`` and its 87
real requests are permanently recorded as a PROTOCOL FAILURE; they must never be
reused, appended to, or zeroed.  The mode fix therefore targets a brand-new
independent persistent root so the future (PM-authorised) 4-attempt cohort2 runs
under a clean, isolated ledger.  This overlay does **not** create that phase root
and does **not** send any real request -- it only points the harness at it.

Preservation: only path constants are moved; the method-final / cohort-ready
phase roots are never created, read, or written.
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKTREE = Path("/home/yhvh/code/lightgravity-bot-worktrees/lg032-mode-isolation")
HARNESS_DIR = WORKTREE / "probes" / "lg032" / "FINAL-COHORT" / "harness"
COHORT = WORKTREE / "probes" / "lg032" / "FINAL-COHORT"
MODE_DIR = WORKTREE / "probes" / "lg032" / "MODE-ISOLATION"

#: The ONE controlled persistent phase data root for the (future) cohort2.
#: Fresh root: never created by this package (0 real provider); the future
#: formal cohort2 must use exactly this root.
PHASE_DATA_DIR = WORKTREE.parent / "lg032-cohort2-data"
LEDGER_DIR = PHASE_DATA_DIR / "generation"
LEDGER_HISTORY = LEDGER_DIR / "generation.jsonl"
LEDGER_COUNT = LEDGER_DIR / "generation.count.json"

RUNS_DIR = MODE_DIR / "runs"
EVIDENCE_DIR = MODE_DIR / "evidence"
#: Frozen protocol inputs stay where the driver expects them (read-only).
FIXTURES_DIR = COHORT / "fixtures"

#: Unique persistent root for the 0-real serial bootstrap probe (shared
#: settings.data_dir across serial A->B->A->B bootstraps).
SERIAL_ROOT = WORKTREE.parent / "lg032-cohort2-serial"


def install() -> "object":
    """Patch the frozen config module in place and return it.

    Must run BEFORE ``import run_attempt`` so the driver's module-level
    ``os.environ.update(C.phase_env())`` sees the redirected phase root.
    """

    if str(HARNESS_DIR) not in sys.path:
        sys.path.insert(0, str(HARNESS_DIR))
    import final_cohort_config as C

    C.WORKTREE = WORKTREE
    C.COHORT = COHORT
    C.PHASE_DATA_DIR = PHASE_DATA_DIR
    C.LEDGER_DIR = LEDGER_DIR
    C.LEDGER_HISTORY = LEDGER_HISTORY
    C.LEDGER_COUNT = LEDGER_COUNT
    C.RUNS_DIR = RUNS_DIR
    C.EVIDENCE_DIR = EVIDENCE_DIR
    C.FIXTURES_DIR = FIXTURES_DIR
    C.PRODUCT_BASE_COMMIT = "a29e94f"
    C.PRODUCT_FIX_COMMIT = "0814b80"

    def _phase_env() -> dict[str, str]:
        return {
            "LIGHTGRAVITY_GENERATION_LEDGER_DIR": str(PHASE_DATA_DIR),
            "LIGHTGRAVITY_DATA_DIR": str(PHASE_DATA_DIR),
            "LIGHTGRAVITY_MAX_GENERATION_CALLS": str(C.TOTAL_GENERATION_LIMIT),
        }

    C.phase_env = _phase_env  # type: ignore[assignment]

    # MODE-ISOLATION: allow an explicitly-opted-in SHARED dry root for the 0-real
    # serial SDK fake probe (A-after-B on ONE settings.data_dir).  Only active
    # when ``LG032_MODE_SHARED_DRY_ROOT`` is set to an absolute path; otherwise
    # the frozen unique-dry-root preservation behaviour is unchanged.  Never
    # usable for a formal run (``dry_run=False`` never calls ``new_dry_root``).
    _frozen_new_dry_root = C.new_dry_root

    def _new_dry_root(label: str = "dry") -> Path:
        import os as _os

        shared = _os.environ.get("LG032_MODE_SHARED_DRY_ROOT")
        if shared:
            root = Path(shared)
            root.mkdir(parents=True, exist_ok=True)
            return root
        return _frozen_new_dry_root(label)

    C.new_dry_root = _new_dry_root  # type: ignore[assignment]
    return C


__all__ = [
    "COHORT",
    "EVIDENCE_DIR",
    "FIXTURES_DIR",
    "HARNESS_DIR",
    "LEDGER_COUNT",
    "LEDGER_DIR",
    "LEDGER_HISTORY",
    "MODE_DIR",
    "PHASE_DATA_DIR",
    "RUNS_DIR",
    "SERIAL_ROOT",
    "WORKTREE",
    "install",
]
