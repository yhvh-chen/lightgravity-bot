"""LG-023 cohort-2 FROZEN protocol configuration (PM pre-registered).

This module is the single source of truth for the cohort-2 protocol.  Every
threshold below is frozen **before the first real DeepSeek request** and must
not be changed afterwards.  It is deliberately free of product imports so any
harness, the offline prover and the report generator can read the same numbers
without starting a runtime.

Pre-registration (PM, 2026-10-16) — see ``../PLAN.md`` and
``probes/lg023/METHOD-AUDIT/REPORT.md`` §8:

* 2 samples (S1 independent, S2 interface) x 2 arms (A single, B dependent two
  workers) x 1 repeat = **exactly 4 attempts**, each attempt runs **once**.
* Both arms share the same: SDK 0.1.22, model ``deepseek-v4-flash``, contract
  1.10.0, initial git tree, requirement text, machine acceptance gate,
  independent reviewer, version acceptance gate, worker prompt template, tool
  set, and the **one** persistent phase ledger.  The only independent variable
  is the number of program-planned write nodes (A=1, B=2).
* Old program-dispatch path (``autonomous_claim`` OFF, collaboration off); the
  new autonomous claim tool is *not* required and *not* enabled.
* Old 45 real generations are protocol-deviation failure cost: they are NOT
  merged into this ledger and NOT washed to 0.  Known real-evaluation upper
  bound: 45 (old) + 48 (this cohort) = **93**, with failures listed separately.

Budget / hard limits (frozen):

* phase generation total = 48; per attempt = 12; both reserved on the SAME
  persistent ledger **before a request is forwarded**.
* output <= 16000 / HTTP timeout 120s / SDK retries 0 / concurrency <= 2.
* worker+reviewer model calls <= 12 per attempt; tool-call cap 32 per worker.
"""

from __future__ import annotations

from pathlib import Path

# ------------------------------------------------------------------ paths
#: Project-adjacent, persistent, never a TemporaryDirectory.
WORKTREE = Path("/home/yhvh/code/lightgravity-bot-worktrees/lg023-cohort2")
COHORT2 = WORKTREE / "probes" / "lg023" / "cohort2"

#: The ONE controlled persistent runtime/ledger root for the whole phase.
PHASE_DATA_DIR = WORKTREE.parent / "lg023-cohort2-data"

#: Ledger sub-path (mirrors PersistentGenerationLedger's own layout).
LEDGER_DIR = PHASE_DATA_DIR / "generation"
LEDGER_HISTORY = LEDGER_DIR / "generation.jsonl"

#: Per-attempt immutable output root (created once, never overwritten).
RUNS_DIR = COHORT2 / "runs"
EVIDENCE_DIR = COHORT2 / "evidence"
FIXTURES_DIR = COHORT2 / "fixtures"

# ------------------------------------------------------------- budget/limits
#: The single real-DeepSeek generation hard cap for the ENTIRE phase.
PHASE_GENERATION_LIMIT = 48
#: Per-attempt secondary hard cap (secondary to the phase ledger).
ATTEMPT_GENERATION_LIMIT = 12

#: Frozen per-request / transport limits.
OUTPUT_TOKEN_CAP = 16000
HTTP_TIMEOUT_SECONDS = 120
SDK_RETRIES = 0
MAX_CONCURRENCY = 2

#: Frozen worker budget (both arms identical; never the product default).
WORKER_MODEL_CALLS = 12
WORKER_TOOL_CALLS = 32
#: Frozen reviewer budget (independent role, same ledger).
REVIEWER_MODEL_CALLS = 1

#: Frozen experiment shape.
SAMPLES = ("s1_independent", "s2_interface")
ARMS = ("A", "B")
ATTEMPTS = (
    ("s1_independent", "A"),
    ("s1_independent", "B"),
    ("s2_interface", "A"),
    ("s2_interface", "B"),
)

#: Frozen SDK/model/contract identity (asserted at run time, not switched).
SDK_VERSION = "0.1.22"
CONTRACT_VERSION = "1.10.0"
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
CREDENTIAL_REF = "deepseek-api-key"

#: Candidate product tree the cohort snapshot is pinned to (contract 1.10.0).
PRODUCT_BASE_COMMIT = "e0a8cec"


def phase_env() -> dict[str, str]:
    """Environment overrides pinning every stage to the one ledger/limit."""

    return {
        "LIGHTGRAVITY_GENERATION_LEDGER_DIR": str(PHASE_DATA_DIR),
        "LIGHTGRAVITY_DATA_DIR": str(PHASE_DATA_DIR),
        "LIGHTGRAVITY_MAX_GENERATION_CALLS": str(PHASE_GENERATION_LIMIT),
    }


__all__ = [
    "ARMS",
    "ATTEMPT_GENERATION_LIMIT",
    "ATTEMPTS",
    "BASE_URL",
    "COHORT2",
    "CONTRACT_VERSION",
    "CREDENTIAL_REF",
    "EVIDENCE_DIR",
    "FIXTURES_DIR",
    "HTTP_TIMEOUT_SECONDS",
    "LEDGER_DIR",
    "LEDGER_HISTORY",
    "MAX_CONCURRENCY",
    "MODEL",
    "OUTPUT_TOKEN_CAP",
    "PHASE_DATA_DIR",
    "PHASE_GENERATION_LIMIT",
    "PRODUCT_BASE_COMMIT",
    "REVIEWER_MODEL_CALLS",
    "RUNS_DIR",
    "SAMPLES",
    "SDK_RETRIES",
    "SDK_VERSION",
    "WORKER_MODEL_CALLS",
    "WORKER_TOOL_CALLS",
    "WORKTREE",
    "phase_env",
]
