"""Frozen unified phase budget/ledger config for the LG-022 stream-stop QA phase.

The prior R2 phase split the real-call budget across TWO ledgers (main chain
limit 10 + light-QA limit 3), so the recorded "8/10" was a post-hoc sum rather
than usage under one hard cap.  This phase freezes ONE path and ONE limit and
must hand the SAME (path, limit) to every stage (worker, reviewer, retry, any
QA re-verify), so the whole phase is bounded by a single persistent ledger.

Keep this module free of product imports so it can be read by every harness and
by the report generator without starting any runtime.
"""

from __future__ import annotations

from pathlib import Path

#: The single controlled, *persistent* runtime/ledger root for this QA phase.
#: Project-adjacent (never /tmp, never a TemporaryDirectory) so evidence and the
#: ledger survive the process and are auditable after the run.
PHASE_DATA_DIR = Path(
    "/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-stream-data"
)

#: The single real-DeepSeek generation hard cap for the ENTIRE phase.  Every
#: worker/reviewer/retry and any QA re-verification consumes this one ledger;
#: there is no second ledger and no post-hoc "8/10" unification.
PHASE_GENERATION_LIMIT = 10

#: Ledger sub-path (mirrors PersistentGenerationLedger's own layout).
LEDGER_DIR = PHASE_DATA_DIR / "generation"
LEDGER_HISTORY = LEDGER_DIR / "generation.jsonl"


def phase_env() -> dict[str, str]:
    """Environment overrides that pin every stage to this one ledger/limit.

    ``LIGHTGRAVITY_GENERATION_LEDGER_DIR`` is the explicit override honoured by
    ``generation_ledger.ledger_root_from_env``; ``LIGHTGRAVITY_DATA_DIR`` is the
    product data root.  ``LIGHTGRAVITY_MAX_GENERATION_CALLS`` is the single hard
    cap shared by the whole process (worker + reviewer + SDK retry).
    """

    return {
        "LIGHTGRAVITY_GENERATION_LEDGER_DIR": str(PHASE_DATA_DIR),
        "LIGHTGRAVITY_DATA_DIR": str(PHASE_DATA_DIR),
        "LIGHTGRAVITY_MAX_GENERATION_CALLS": str(PHASE_GENERATION_LIMIT),
    }


__all__ = [
    "LEDGER_DIR",
    "LEDGER_HISTORY",
    "PHASE_DATA_DIR",
    "PHASE_GENERATION_LIMIT",
    "phase_env",
]
