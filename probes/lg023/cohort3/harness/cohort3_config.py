"""LG-023 cohort-3 FROZEN protocol configuration (PM pre-registered).

Single source of truth for the cohort-3 protocol.  Every threshold below is
frozen **before the first real DeepSeek request** and must not be changed
afterwards.  Free of product imports so any harness / prover / report generator
can read the same numbers without starting a runtime.

Key difference from cohort-2 (fixes audited defect D1): the **entire phase
shares ONE real ``settings.data_dir``** (``PHASE_DATA_DIR``).  The product's
``build_runtime`` calls ``configure_generation_ledger(settings.data_dir)``
unconditionally, so a single phase data_dir makes the mature product ledger
naturally continue the same physical JSONL across every serial attempt and
runtime restart.  Per-attempt isolation is expressed through ``workspaces/``,
``secrets/`` and candidate workspaces under the attempt namespace -- never by
swapping ``data_dir``.

Pre-registration (PM, 2026-10-16) -- see ``../PLAN.md`` and the cohort-2
``STATUS/REPORT`` + ``evidence/cohort2-D1.json``:

* 2 samples (S1 independent, S2 interface) x 2 arms (A single, B dependent two
  workers) x 1 repeat = **exactly 4 attempts**, each attempt runs **once**.
* Both arms share the same: SDK 0.1.22, model ``deepseek-v4-flash``, contract
  1.10.0, initial git tree, requirement text, machine acceptance gate,
  independent reviewer, version acceptance gate, worker prompt template, tool
  set, and the **one** persistent phase ledger.  The only independent variable
  is the number of program-planned write nodes (A=1, B=2).
* Old program-dispatch path (``autonomous_claim`` OFF, collaboration off).
* Old 45 (cohort-1) + 4 (cohort-2) real generations are protocol-deviation /
  harness-defect cost: NOT merged into this ledger, NOT washed to 0, listed
  separately.  Known real-evaluation upper bound: 45 + 4 + 48 = **97**.

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
COHORT3 = WORKTREE / "probes" / "lg023" / "cohort3"

#: The ONE controlled persistent phase data root for the WHOLE phase.
#: This is passed verbatim as ``Settings.data_dir`` for every serial attempt /
#: runtime start, so the product ledger rooted at ``data_dir/generation`` is
#: the single phase ledger (fix D1).
PHASE_DATA_DIR = WORKTREE.parent / "lg023-cohort3-data"

#: Ledger sub-path -- this is the product's OWN layout under ``data_dir``
#: (``PersistentGenerationLedger(data_dir)`` writes ``generation/`` inside it),
#: so the frozen physical path is exactly what the product would create.
LEDGER_DIR = PHASE_DATA_DIR / "generation"
LEDGER_HISTORY = LEDGER_DIR / "generation.jsonl"
LEDGER_COUNT = LEDGER_DIR / "generation.count.json"

#: Per-attempt immutable output root (created once, never overwritten).
RUNS_DIR = COHORT3 / "runs"
EVIDENCE_DIR = COHORT3 / "evidence"
FIXTURES_DIR = COHORT3 / "fixtures"

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
    """Environment overrides pinning every stage to the one ledger/limit.

    ``LIGHTGRAVITY_DATA_DIR`` and ``LIGHTGRAVITY_GENERATION_LEDGER_DIR`` both
    point at the one phase root, consistent with the product's own
    ``configure_generation_ledger(settings.data_dir)`` call -- no per-attempt
    swap, no post-build re-pin.
    """

    return {
        "LIGHTGRAVITY_GENERATION_LEDGER_DIR": str(PHASE_DATA_DIR),
        "LIGHTGRAVITY_DATA_DIR": str(PHASE_DATA_DIR),
        "LIGHTGRAVITY_MAX_GENERATION_CALLS": str(PHASE_GENERATION_LIMIT),
    }


def attempt_root(attempt_id: str) -> Path:
    """Per-attempt isolation root (workspaces/secrets/candidate), NOT data_dir."""

    return PHASE_DATA_DIR / "attempts" / attempt_id


__all__ = [
    "ARMS",
    "ATTEMPT_GENERATION_LIMIT",
    "ATTEMPTS",
    "BASE_URL",
    "COHORT3",
    "CONTRACT_VERSION",
    "CREDENTIAL_REF",
    "EVIDENCE_DIR",
    "FIXTURES_DIR",
    "HTTP_TIMEOUT_SECONDS",
    "LEDGER_COUNT",
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
    "attempt_root",
    "phase_env",
]
