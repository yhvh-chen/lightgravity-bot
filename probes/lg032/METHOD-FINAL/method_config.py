"""LG-032 METHOD-FINAL audit overlay over the frozen FINAL-COHORT config.

This module is the ONLY method-final-specific configuration.  It redirects the
frozen protocol constants to THIS worktree's own persistent phase data root
without editing a single byte of the existing harness (``probes/lg032/
FINAL-COHORT/harness/**`` stays read-only).

Why an overlay is required
--------------------------
``final_cohort_config.py`` (frozen, in the cohort-ready worktree) hard-codes

    WORKTREE = .../lg032-cohort-ready
    PHASE_DATA_DIR = .../lg032-cohort-ready-data

The independent method audit runs in a *different* worktree
(``lg032-method-final``) and MUST follow one phase data_root frozen to THIS
worktree ("本实际 worktree 冻结一个 phase data_root 贯穿 4 attempt").  So the
audit imports the frozen config, then rewrites exactly the path constants and
re-derives the dependent paths, before importing the driver.  Nothing about the
protocol semantics (limits, arms, samples, model, caps) is changed.

Preservation: only path constants are moved; the cohort-ready phase root is
never created, read, or written.
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKTREE = Path("/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final")
HARNESS_DIR = WORKTREE / "probes" / "lg032" / "FINAL-COHORT" / "harness"
COHORT = WORKTREE / "probes" / "lg032" / "FINAL-COHORT"
METHOD_DIR = WORKTREE / "probes" / "lg032" / "METHOD-FINAL"

#: The ONE controlled persistent phase data root for the WHOLE method-final
#: audit and the (not-yet-authorized) formal cohort.  Fresh root: the formal
#: attempt ledger has never been started, so this is not a reset of any data.
PHASE_DATA_DIR = WORKTREE.parent / "lg032-method-final-data"
LEDGER_DIR = PHASE_DATA_DIR / "generation"
LEDGER_HISTORY = LEDGER_DIR / "generation.jsonl"
LEDGER_COUNT = LEDGER_DIR / "generation.count.json"

RUNS_DIR = METHOD_DIR / "runs"
EVIDENCE_DIR = METHOD_DIR / "evidence"
#: Fixtures (initial/reference/acceptance/seed pin) are the FROZEN protocol
#: inputs; they stay where the driver expects them (read-only).  Only the
#: *output* roots (runs/evidence) are redirected into METHOD-FINAL so this audit
#: never writes into the read-only FINAL-COHORT tree.
FIXTURES_DIR = COHORT / "fixtures"

#: Independent, method-final-only sandbox for boundary probes (small caps).
BOUNDARY_DIR = PHASE_DATA_DIR.parent / "lg032-method-final-boundary"


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
    return C


__all__ = [
    "BOUNDARY_DIR",
    "COHORT",
    "EVIDENCE_DIR",
    "FIXTURES_DIR",
    "HARNESS_DIR",
    "METHOD_DIR",
    "PHASE_DATA_DIR",
    "WORKTREE",
    "install",
]
